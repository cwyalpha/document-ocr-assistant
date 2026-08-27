from __future__ import annotations

import logging
import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from .edition import is_full_edition
from .models import (
    InputItem,
    InputKind,
    LayoutMode,
    OcrBlock,
    PdfMode,
    ProcessResult,
    ProcessingOptions,
    TableResult,
)
from .ocr_engine import OcrEngine
from .orientation import OrientationEngine, OrientationResult, blocks_to_original
from .page_numbers import (
    PageNumberMatch,
    PositionedTextLine,
    find_page_number_matches,
    native_pdf_text_lines,
    ocr_blocks_to_positioned_lines,
)
from .table_engine import TableEngine
from .text_format import blocks_to_text, build_markdown, html_document_without_tables_to_text


LOGGER = logging.getLogger(__name__)
ProgressCallback = Callable[[int, str], None]


@dataclass(slots=True)
class _PdfPageState:
    page_index: int
    native_text: str
    native_lines: list[PositionedTextLine]
    needs_ocr: bool
    raw_blocks: list[OcrBlock]
    accepted_blocks: list[OcrBlock]
    tables: list[TableResult]
    oriented: OrientationResult | None
    image_width: int
    image_height: int
    metadata: dict[str, object]


def load_image_bgr(source: str | Path | bytes) -> np.ndarray:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("未安装 OpenCV。") from exc
    if isinstance(source, bytes):
        array = np.frombuffer(source, dtype=np.uint8)
        image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    else:
        # np.fromfile supports non-ASCII paths on Windows better than imread.
        array = np.fromfile(str(source), dtype=np.uint8)
        image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"无法读取图片：{source}")
    return image


def _render_pdf_page(page, dpi: int = 200) -> np.ndarray:
    import fitz

    pixmap = page.get_pixmap(dpi=dpi, alpha=False, colorspace=fitz.csRGB)
    image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, 3)
    return image[:, :, ::-1].copy()


def parse_page_range(value: str, page_count: int) -> list[int]:
    """Parse a user-facing 1-based page range into sorted zero-based indexes."""
    if not value.strip():
        return list(range(page_count))
    selected: set[int] = set()
    for raw_part in value.replace("，", ",").split(","):
        part = raw_part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = (item.strip() for item in part.split("-", 1))
            if not start_text or not end_text:
                raise ValueError(f"无效页码范围：{part}")
            start, end = int(start_text), int(end_text)
            if start > end:
                raise ValueError(f"页码范围起始值不能大于结束值：{part}")
            values = range(start, end + 1)
        else:
            values = (int(part),)
        for page_number in values:
            if page_number < 1 or page_number > page_count:
                raise ValueError(f"页码 {page_number} 超出文档范围 1-{page_count}")
            selected.add(page_number - 1)
    if not selected:
        raise ValueError("页码范围不能为空。")
    return sorted(selected)


def _is_substantial_pdf_text(text: str) -> bool:
    compact = "".join(text.split())
    if len(compact) < 30:
        return False
    printable = sum(character.isprintable() for character in compact)
    return printable / max(1, len(compact)) >= 0.9


def _table_blocks_for_region(blocks: list[OcrBlock], table: TableResult) -> list[OcrBlock]:
    if not table.bbox:
        return []
    x1, y1, x2, y2 = table.bbox
    result = []
    for block in blocks:
        bx1, by1, bx2, by2 = block.bounds
        center_x, center_y = (bx1 + bx2) / 2, (by1 + by2) / 2
        if x1 <= center_x <= x2 and y1 <= center_y <= y2:
            result.append(block)
    return result


def _non_table_text(blocks: list[OcrBlock], tables: list[TableResult], layout_mode: str) -> str:
    if not tables:
        return blocks_to_text(blocks, layout_mode)
    excluded = {id(block) for table in tables for block in _table_blocks_for_region(blocks, table)}
    return blocks_to_text([block for block in blocks if id(block) not in excluded], layout_mode)


class DocumentProcessors:
    def __init__(
        self,
        ocr_engine: OcrEngine | None = None,
        table_engine: TableEngine | None = None,
        orientation_engine: OrientationEngine | None = None,
    ) -> None:
        self.ocr = ocr_engine or OcrEngine()
        self.tables = table_engine or TableEngine()
        self.orientation = orientation_engine or OrientationEngine()

    def process(
        self,
        item: InputItem,
        options: ProcessingOptions,
        progress: ProgressCallback | None = None,
        cancelled: threading.Event | None = None,
    ) -> ProcessResult:
        callback = progress or (lambda value, message: None)
        if item.kind is InputKind.IMAGE:
            return self._process_image(item, options, callback, cancelled)
        if item.kind is InputKind.PDF:
            return self._process_pdf(item, options, callback, cancelled)
        if item.kind is InputKind.WORD:
            if not is_full_edition():
                raise RuntimeError("OCR版不支持 Word/WPS 文档，请下载完整版。")
            return self._process_word(item, options, callback)
        raise RuntimeError(f"没有适用于 {item.kind.value} 的处理器。")

    def _process_image(
        self,
        item: InputItem,
        options: ProcessingOptions,
        progress: ProgressCallback,
        cancelled: threading.Event | None,
    ) -> ProcessResult:
        progress(10, "正在读取图片")
        image = load_image_bgr(item.source_path)
        if cancelled and cancelled.is_set():
            raise InterruptedError("任务已取消")
        progress(30, "正在识别文字")
        oriented = self.orientation.orient(
            image, options.page_orientation, options.orientation_confidence
        )
        raw_oriented_blocks = self.ocr.recognize(oriented.image, options=options)
        accepted_oriented_blocks = [
            block for block in raw_oriented_blocks if block.score >= options.text_score
        ]
        tables: list[TableResult] = []
        warnings: list[str] = [oriented.warning] if oriented.warning else []
        if options.table_detection:
            if self.tables.available:
                progress(70, "正在检测表格结构")
                tables = self.tables.analyze(oriented.image, accepted_oriented_blocks)
            else:
                warnings.append("表格模型不可用，已完成普通文字识别。")
        text = blocks_to_text(accepted_oriented_blocks, options.layout_mode)
        raw_text = blocks_to_text(raw_oriented_blocks, LayoutMode.RAW.value)
        markdown_text = _non_table_text(
            accepted_oriented_blocks, tables, options.layout_mode
        )
        markdown = build_markdown(markdown_text, tables, item.source_path.stem)
        blocks = blocks_to_original(raw_oriented_blocks, oriented)
        progress(100, "识别完成")
        return ProcessResult(
            text,
            markdown,
            blocks,
            tables,
            warnings=warnings,
            raw_text=raw_text,
            metadata={
                "source_kind": "image",
                "page_count": 1,
                "pdf_dpi": None,
                "pages": [
                    {
                        "page_index": 0,
                        "width": oriented.original_width,
                        "height": oriented.original_height,
                        "detected_angle": oriented.detected_angle,
                        "applied_angle": oriented.applied_angle,
                        "orientation_confidence": oriented.confidence,
                        "low_confidence_blocks": sum(
                            block.score < options.text_score for block in raw_oriented_blocks
                        ),
                    }
                ],
            },
        )

    def _process_pdf(
        self,
        item: InputItem,
        options: ProcessingOptions,
        progress: ProgressCallback,
        cancelled: threading.Event | None,
    ) -> ProcessResult:
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError("未安装 PyMuPDF。") from exc
        document = fitz.open(item.source_path)
        page_texts: list[str] = []
        page_markdowns: list[str] = []
        all_blocks: list[OcrBlock] = []
        all_tables: list[TableResult] = []
        warnings: list[str] = []
        pages_metadata: list[dict[str, object]] = []
        raw_page_texts: list[str] = []
        page_states: list[_PdfPageState] = []
        try:
            total_pages = max(1, document.page_count)
            selected_pages = set(parse_page_range(options.page_range, document.page_count))
            resolved = options.resolved_ocr_values()
            pdf_dpi = int(resolved["pdf_dpi"])
            for page_index, page in enumerate(document):
                if cancelled and cancelled.is_set():
                    raise InterruptedError("任务已取消")
                if page_index not in selected_pages:
                    percent = int(((page_index + 1) / total_pages) * 95)
                    progress(percent, f"已跳过第 {page_index + 1}/{total_pages} 页")
                    continue
                native_text = page.get_text("text").strip()
                has_native_text = _is_substantial_pdf_text(native_text)
                needs_ocr = options.pdf_mode is PdfMode.FORCE_OCR or (
                    options.pdf_mode is PdfMode.AUTO and not has_native_text
                )
                native_lines = (
                    native_pdf_text_lines(page, page_index)
                    if options.remove_pdf_page_numbers and not needs_ocr
                    else []
                )
                needs_image = needs_ocr or options.table_detection
                image: np.ndarray | None = (
                    _render_pdf_page(page, dpi=pdf_dpi) if needs_image else None
                )
                raw_oriented_blocks: list[OcrBlock] = []
                accepted_oriented_blocks: list[OcrBlock] = []
                oriented = None
                if image is not None and (needs_ocr or options.table_detection):
                    oriented = self.orientation.orient(
                        image,
                        options.page_orientation,
                        options.orientation_confidence,
                    )
                    if oriented.warning:
                        warnings.append(f"第 {page_index + 1} 页：{oriented.warning}")
                    raw_oriented_blocks = self.ocr.recognize(
                        oriented.image, page_index, options
                    )
                    accepted_oriented_blocks = [
                        block
                        for block in raw_oriented_blocks
                        if block.score >= options.text_score
                    ]
                tables: list[TableResult] = []
                if options.table_detection and image is not None:
                    if self.tables.available:
                        assert oriented is not None
                        tables = self.tables.analyze(
                            oriented.image, accepted_oriented_blocks, page_index
                        )
                    elif page_index == 0:
                        warnings.append("表格模型不可用，已跳过 PDF 表格结构识别。")
                page_metadata: dict[str, object] = {
                    "page_index": page_index,
                    "width": image.shape[1] if image is not None else 0,
                    "height": image.shape[0] if image is not None else 0,
                    "native_text": not needs_ocr,
                    "detected_angle": oriented.detected_angle if oriented else 0,
                    "applied_angle": oriented.applied_angle if oriented else 0,
                    "orientation_confidence": oriented.confidence if oriented else 1.0,
                    "low_confidence_blocks": sum(
                        block.score < options.text_score for block in raw_oriented_blocks
                    ),
                }
                pages_metadata.append(page_metadata)
                page_states.append(
                    _PdfPageState(
                        page_index,
                        native_text,
                        native_lines,
                        needs_ocr,
                        raw_oriented_blocks,
                        accepted_oriented_blocks,
                        tables,
                        oriented,
                        oriented.image.shape[1] if oriented is not None else 0,
                        oriented.image.shape[0] if oriented is not None else 0,
                        page_metadata,
                    )
                )
                percent = int(((page_index + 1) / total_pages) * 95)
                progress(percent, f"正在处理第 {page_index + 1}/{total_pages} 页")

            detection_lines: list[PositionedTextLine] = []
            native_line_objects: set[int] = set()
            ocr_line_objects: set[int] = set()
            if options.remove_pdf_page_numbers:
                for state in page_states:
                    detection_lines.extend(state.native_lines)
                    native_line_objects.update(id(line) for line in state.native_lines)
                    if state.raw_blocks and state.oriented is not None:
                        ocr_lines = ocr_blocks_to_positioned_lines(
                            state.raw_blocks,
                            state.page_index,
                            state.image_width,
                            state.image_height,
                        )
                        detection_lines.extend(ocr_lines)
                        ocr_line_objects.update(id(line) for line in ocr_lines)
            matches = find_page_number_matches(detection_lines, document.page_count)
            matches_by_page: dict[int, list[PageNumberMatch]] = {}
            for match in matches:
                matches_by_page.setdefault(match.line.page_index, []).append(match)

            for state in page_states:
                page_matches = matches_by_page.get(state.page_index, [])
                removed_native_lines = {
                    id(match.line)
                    for match in page_matches
                    if id(match.line) in native_line_objects
                }
                removed_ocr_ids = {
                    source_id
                    for match in page_matches
                    if id(match.line) in ocr_line_objects
                    for source_id in match.line.source_ids
                }
                raw_blocks = [
                    block for block in state.raw_blocks if id(block) not in removed_ocr_ids
                ]
                accepted_blocks = [
                    block for block in state.accepted_blocks if id(block) not in removed_ocr_ids
                ]
                native_text = state.native_text
                if removed_native_lines:
                    native_text = "\n".join(
                        line.text
                        for line in state.native_lines
                        if id(line) not in removed_native_lines
                    ).strip()

                if state.needs_ocr:
                    text = blocks_to_text(accepted_blocks, options.layout_mode)
                    raw_text = blocks_to_text(raw_blocks, LayoutMode.RAW.value)
                    md_text = _non_table_text(
                        accepted_blocks, state.tables, options.layout_mode
                    )
                else:
                    text = native_text
                    raw_text = native_text
                    md_text = native_text

                if options.include_page_numbers:
                    page_label = f"第 {state.page_index + 1} 页"
                    page_texts.append(
                        f"{page_label}\n\n{text}" if text.strip() else page_label
                    )
                else:
                    page_texts.append(text)
                raw_page_texts.append(raw_text)
                page_title = (
                    f"第 {state.page_index + 1} 页"
                    if options.include_page_numbers
                    else None
                )
                page_markdowns.append(
                    build_markdown(md_text, state.tables, page_title)
                )
                all_tables.extend(state.tables)

                if state.oriented is not None:
                    restored_blocks = blocks_to_original(raw_blocks, state.oriented)
                    restored_accepted_blocks = blocks_to_original(
                        accepted_blocks, state.oriented
                    )
                    all_blocks.extend(restored_blocks)
                    if (
                        options.searchable_pdf
                        and state.needs_ocr
                        and restored_accepted_blocks
                        and state.image_width
                        and state.image_height
                    ):
                        self._insert_searchable_text(
                            document[state.page_index],
                            restored_accepted_blocks,
                            state.image_width,
                            state.image_height,
                        )

                removed_texts = list(
                    {
                        (match.region, match.parsed.value): match.line.text.strip()
                        for match in page_matches
                    }.values()
                )
                state.metadata["removed_page_number_count"] = len(removed_texts)
                state.metadata["removed_page_numbers"] = removed_texts
                state.metadata["low_confidence_blocks"] = sum(
                    block.score < options.text_score for block in raw_blocks
                )
            searchable_bytes = None
            if options.searchable_pdf:
                searchable_bytes = document.tobytes(garbage=3, deflate=True)
            progress(100, "PDF 处理完成")
            return ProcessResult(
                "\n\n".join(page_texts).strip(),
                "\n\n".join(page_markdowns).strip() + "\n",
                all_blocks,
                all_tables,
                searchable_pdf_bytes=searchable_bytes,
                warnings=warnings,
                raw_text="\n\n".join(raw_page_texts).strip(),
                metadata={
                    "source_kind": "pdf",
                    "page_count": document.page_count,
                    "processed_pages": sorted(index + 1 for index in selected_pages),
                    "pdf_dpi": pdf_dpi,
                    "pages": pages_metadata,
                },
            )
        finally:
            document.close()

    @staticmethod
    def _insert_searchable_text(page, blocks: list[OcrBlock], image_width: int, image_height: int) -> None:
        scale_x = page.rect.width / max(1, image_width)
        scale_y = page.rect.height / max(1, image_height)
        for block in blocks:
            x1, y1, x2, y2 = block.bounds
            fontsize = max(4.0, (y2 - y1) * scale_y * 0.8)
            try:
                # insert_textbox silently drops text when the OCR rectangle is
                # only a fraction too tight. A baseline insertion preserves a
                # real searchable text layer while render_mode=3 keeps it
                # invisible over the original scan.
                page.insert_text(
                    (x1 * scale_x, y2 * scale_y),
                    block.text,
                    fontsize=fontsize,
                    fontname="china-s",
                    render_mode=3,
                    overlay=True,
                )
            except Exception as exc:
                LOGGER.debug("Unable to insert searchable text block: %s", exc)

    def _process_word(
        self, item: InputItem, options: ProcessingOptions, progress: ProgressCallback
    ) -> ProcessResult:
        progress(15, "正在调用 Microsoft Word/WPS" if os.name == "nt" else "正在启动 LibreOffice")
        from .office_documents import convert_word

        text, html_text = convert_word(item.source_path)
        tables: list[TableResult] = []
        if options.table_detection and html_text:
            for table_html in re.findall(r"(?is)<table\b.*?</table>", html_text):
                tables.append(TableResult(table_html))
        progress(90, "正在整理文档结构")
        markdown_body = html_document_without_tables_to_text(html_text) if html_text else text
        markdown = build_markdown(markdown_body, tables, item.source_path.stem)
        progress(100, "Word 转换完成")
        return ProcessResult(text, markdown, tables=tables)
