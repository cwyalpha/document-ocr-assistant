from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

import numpy as np

from .models import OcrBlock, TableResult
from .ocr_engine import OcrEngine
from .runtime import find_table_model


LOGGER = logging.getLogger(__name__)


def _bounds_union(blocks: list[OcrBlock]) -> tuple[int, int, int, int]:
    bounds = [block.bounds for block in blocks]
    return (
        int(min(value[0] for value in bounds)),
        int(min(value[1] for value in bounds)),
        int(max(value[2] for value in bounds)),
        int(max(value[3] for value in bounds)),
    )


def _merge_regions(regions: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    merged: list[tuple[int, int, int, int]] = []
    for region in sorted(regions, key=lambda value: (value[1], value[0])):
        x1, y1, x2, y2 = region
        for index, current in enumerate(merged):
            cx1, cy1, cx2, cy2 = current
            intersection_w = max(0, min(x2, cx2) - max(x1, cx1))
            intersection_h = max(0, min(y2, cy2) - max(y1, cy1))
            if intersection_w * intersection_h > 0 or (
                abs(y1 - cy2) < 20 and max(x1, cx1) < min(x2, cx2)
            ):
                merged[index] = min(x1, cx1), min(y1, cy1), max(x2, cx2), max(y2, cy2)
                break
        else:
            merged.append(region)
    return merged


def detect_table_regions(image: np.ndarray, blocks: list[OcrBlock]) -> list[tuple[int, int, int, int]]:
    """Find ruled tables and likely borderless tables without an extra runtime."""
    try:
        import cv2
    except ImportError:
        cv2 = None
    height, width = image.shape[:2]
    regions: list[tuple[int, int, int, int]] = []
    if cv2 is not None and width >= 120 and height >= 80:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 15
        )
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(20, width // 30), 1))
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(20, height // 30)))
        horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel)
        vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel)
        grid = cv2.add(horizontal, vertical)
        contours, _ = cv2.findContours(grid, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w >= 120 and h >= 60 and w * h >= width * height * 0.015:
                density = float(np.count_nonzero(grid[y : y + h, x : x + w])) / max(1, w * h)
                if density >= 0.018:
                    padding = 8
                    regions.append(
                        (max(0, x - padding), max(0, y - padding), min(width, x + w + padding), min(height, y + h + padding))
                    )

    # Borderless-table heuristic: at least three text rows with repeated columns.
    rows: list[list[OcrBlock]] = []
    for block in sorted(blocks, key=lambda value: (value.bounds[1], value.bounds[0])):
        center_y = (block.bounds[1] + block.bounds[3]) / 2
        block_height = max(1.0, block.bounds[3] - block.bounds[1])
        for row in rows:
            row_y = sum((value.bounds[1] + value.bounds[3]) / 2 for value in row) / len(row)
            if abs(center_y - row_y) <= block_height * 0.65:
                row.append(block)
                break
        else:
            rows.append([block])
    candidate_rows = [row for row in rows if len(row) >= 2]
    if len(candidate_rows) >= 3:
        centers_by_row = [sorted((value.bounds[0] + value.bounds[2]) / 2 for value in row) for row in candidate_rows]
        aligned_pairs = 0
        tolerance = max(20.0, width * 0.025)
        for first, second in zip(centers_by_row, centers_by_row[1:]):
            matches = sum(1 for center in first if any(abs(center - other) <= tolerance for other in second))
            if matches >= 2:
                aligned_pairs += 1
        if aligned_pairs >= 2:
            table_blocks = [value for row in candidate_rows for value in row]
            x1, y1, x2, y2 = _bounds_union(table_blocks)
            regions.append((max(0, x1 - 12), max(0, y1 - 12), min(width, x2 + 12), min(height, y2 + 12)))

    return _merge_regions(regions)


class TableEngine:
    """ONNX-only SLANet-plus table structure engine."""

    def __init__(self) -> None:
        self._engine: Any = None
        self._lock = threading.RLock()

    @property
    def available(self) -> bool:
        if not find_table_model():
            return False
        try:
            import rapid_table  # noqa: F401
        except ImportError:
            return False
        return True

    def _ensure_engine(self) -> Any:
        if self._engine is not None:
            return self._engine
        with self._lock:
            if self._engine is not None:
                return self._engine
            model = find_table_model()
            if not model:
                raise RuntimeError("未找到 models/table/slanet-plus.onnx。")
            try:
                from rapid_table import RapidTable, RapidTableInput
                from rapid_table.utils import EngineType, ModelType
            except ImportError as exc:
                raise RuntimeError("未安装 rapid-table==3.0.2。") from exc
            config = RapidTableInput(
                model_type=ModelType.SLANETPLUS,
                model_dir_or_path=str(model),
                engine_type=EngineType.ONNXRUNTIME,
                # OCR is supplied by the application's PP-OCRv6 Medium engine.
                # Keeping this false prevents RapidTable from constructing its
                # own bundled PP-OCRv6 Small session.
                use_ocr=False,
                engine_cfg={"intra_op_num_threads": -1, "inter_op_num_threads": 1},
            )
            self._engine = RapidTable(config)
            LOGGER.info("已加载 SLANet-plus ONNX 表格模型：%s", model)
            return self._engine

    def analyze(self, image: np.ndarray, blocks: list[OcrBlock], page_index: int = 0) -> list[TableResult]:
        regions = detect_table_regions(image, blocks)
        if not regions:
            return []
        engine = self._ensure_engine()
        tables: list[TableResult] = []
        for x1, y1, x2, y2 in regions:
            crop = image[y1:y2, x1:x2]
            local_blocks: list[OcrBlock] = []
            for block in blocks:
                bx1, by1, bx2, by2 = block.bounds
                center_x, center_y = (bx1 + bx2) / 2, (by1 + by2) / 2
                if x1 <= center_x <= x2 and y1 <= center_y <= y2:
                    local_blocks.append(
                        OcrBlock(
                            block.text,
                            [[point[0] - x1, point[1] - y1] for point in block.polygon],
                            block.score,
                            page_index,
                        )
                    )
            if not local_blocks:
                continue
            payload = OcrEngine.rapid_table_payload(local_blocks)
            with self._lock:
                # RapidTable 3.0.2 does not build HTML from caller-supplied OCR
                # when use_ocr=False, so invoke its pinned structure/matcher
                # stages directly. This remains ONNX-only and avoids a second
                # OCR model family at runtime.
                structures, cell_boxes = engine.table_structure([crop])
                detected_boxes, recognized_text = engine.get_ocr_results(
                    [crop], 0, 1, [payload]
                )
                html_values = engine.table_matcher(
                    structures, cell_boxes, detected_boxes, recognized_text
                )
            if html_values and html_values[0]:
                tables.append(TableResult(str(html_values[0]), page_index, (x1, y1, x2, y2)))
        return tables
