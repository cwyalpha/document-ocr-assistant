from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .models import OcrBlock, ProcessingOptions
from .runtime import find_ppocrv6_models


LOGGER = logging.getLogger(__name__)


class OcrUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OcrRuntimeConfig:
    textline_orientation: bool = True
    max_side_len: int = 2000
    det_limit_side_len: int = 736
    det_limit_type: str = "min"
    det_thresh: float = 0.3
    det_box_thresh: float = 0.5
    det_unclip_ratio: float = 1.6
    rec_batch_size: int = 6
    cpu_threads: int = 0

    @classmethod
    def from_options(cls, options: ProcessingOptions | None) -> "OcrRuntimeConfig":
        if options is None:
            return cls()
        resolved = options.resolved_ocr_values()
        return cls(
            textline_orientation=options.textline_orientation,
            max_side_len=int(resolved["max_side_len"]),
            det_limit_side_len=options.det_limit_side_len,
            det_limit_type=options.det_limit_type,
            det_thresh=options.det_thresh,
            det_box_thresh=options.det_box_thresh,
            det_unclip_ratio=options.det_unclip_ratio,
            rec_batch_size=options.rec_batch_size,
            cpu_threads=options.cpu_threads,
        )


class OcrEngine:
    """Lazy, single-session PP-OCRv6 Medium engine backed by ONNX Runtime."""

    def __init__(self) -> None:
        self._engine: Any = None
        self._lock = threading.RLock()
        self._models: dict[str, Path] | None = None
        self._config: OcrRuntimeConfig | None = None

    @property
    def available(self) -> bool:
        return find_ppocrv6_models() is not None

    @property
    def model_directory(self) -> Path | None:
        models = find_ppocrv6_models()
        return models["det"].parent if models else None

    def _ensure_engine(self, config: OcrRuntimeConfig) -> Any:
        if self._engine is not None and self._config == config:
            return self._engine
        with self._lock:
            if self._engine is not None and self._config == config:
                return self._engine
            models = find_ppocrv6_models()
            if not models:
                raise OcrUnavailableError(
                    "未找到 PP-OCRv6 Medium 模型。请将三个 ONNX 文件放入 "
                    "models/ppocrv6-medium/。"
                )
            try:
                from rapidocr import RapidOCR
            except ImportError as exc:
                raise OcrUnavailableError("未安装 rapidocr==3.9.1。") from exc
            self._engine = RapidOCR(
                params={
                    "Det.model_path": str(models["det"]),
                    "Cls.model_path": str(models["cls"]),
                    "Rec.model_path": str(models["rec"]),
                    "Global.text_score": 0.0,
                    "Global.use_cls": config.textline_orientation,
                    "Global.max_side_len": config.max_side_len,
                    "Det.limit_side_len": config.det_limit_side_len,
                    "Det.limit_type": config.det_limit_type,
                    "Det.thresh": config.det_thresh,
                    "Det.box_thresh": config.det_box_thresh,
                    "Det.unclip_ratio": config.det_unclip_ratio,
                    "Rec.rec_batch_num": config.rec_batch_size,
                    "EngineConfig.onnxruntime.intra_op_num_threads": (
                        config.cpu_threads or -1
                    ),
                }
            )
            self._models = models
            self._config = config
            LOGGER.info("已加载 PP-OCRv6 Medium ONNX 模型：%s", models["det"].parent)
            return self._engine

    def recognize(
        self,
        image: str | Path | bytes | np.ndarray,
        page_index: int = 0,
        options: ProcessingOptions | None = None,
    ) -> list[OcrBlock]:
        config = OcrRuntimeConfig.from_options(options)
        engine = self._ensure_engine(config)
        with self._lock:
            result = engine(
                str(image) if isinstance(image, Path) else image,
                use_cls=config.textline_orientation,
            )
        boxes = getattr(result, "boxes", None)
        texts = getattr(result, "txts", None)
        scores = getattr(result, "scores", None)
        if boxes is None and isinstance(result, tuple) and result:
            legacy = result[0] or []
            boxes = [value[0] for value in legacy]
            texts = [value[1] for value in legacy]
            scores = [value[2] if len(value) > 2 else 1.0 for value in legacy]
        if boxes is None or texts is None:
            return []
        if scores is None:
            scores = [1.0] * len(texts)
        blocks: list[OcrBlock] = []
        for box, text, score in zip(boxes, texts, scores):
            if not str(text).strip():
                continue
            polygon = np.asarray(box, dtype=float).reshape(-1, 2).tolist()
            blocks.append(OcrBlock(str(text), polygon, float(score), page_index))
        return blocks

    @staticmethod
    def rapid_table_payload(
        blocks: list[OcrBlock],
    ) -> tuple[np.ndarray, tuple[str, ...], tuple[float, ...]]:
        boxes = np.asarray([block.polygon for block in blocks], dtype=np.float32)
        texts = tuple(block.text for block in blocks)
        scores = tuple(float(block.score) for block in blocks)
        return boxes, texts, scores
