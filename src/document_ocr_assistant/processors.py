from __future__ import annotations

import io
import logging
import os
import re
import threading
from pathlib import Path
from typing import Callable

import numpy as np

from .office_documents import convert_word
from .models import InputItem, InputKind, OcrBlock, PdfMode, ProcessResult, ProcessingOptions, TableResult
from .ocr_engine import OcrEngine
from .table_engine import TableEngine
from .text_format import blocks_to_text, build_markdown, html_document_without_tables_to_text


LOGGER = logging.getLogger(__name__)
ProgressCallback = Callable[[int, str], None]


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
    def __init__(self, ocr_engine: OcrEngine | None = None, table_engine: TableEngine | None = None) -> None:
        self.ocr = ocr_engine or OcrEngine()
        self.tables = table_engine or TableEngine()

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
        blocks = self.ocr.recognize(image)
        tables: list[TableResult] = []
        warnings: list[str] = []
        if options.table_detection:
            if self.tables.available:
                progress(70, "正在检测表格结构")
                tables = self.tables.analyze(image, blocks)
            else:
                warnings.append("表格模型不可用，已完成普通文字识别。")
        text = blocks_to_text(blocks, options.layout_mode)
        markdown_text = _non_table_text(blocks, tables, options.layout_mode)
        markdown = build_markdown(markdown_text, tables, item.source_path.stem)
        progress(100, "识别完成")
        return ProcessResult(text, markdown, blocks, tables, warnings=warnings)

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
        try:
            total_pages = max(1, document.page_count)
            for page_index, page in enumerate(document):
                if cancelled and cancelled.is_set():
                    raise InterruptedError("任务已取消")
                native_text = page.get_text("text").strip()
                has_native_text = _is_substantial_pdf_text(native_text)
                needs_ocr = options.pdf_mode is PdfMode.FORCE_OCR or (
                    options.pdf_mode is PdfMode.AUTO and not has_native_text
                )
                needs_image = needs_ocr or options.table_detection
                image: np.ndarray | None = _render_pdf_page(page) if needs_image else None
                blocks: list[OcrBlock] = []
                if image is not None and (needs_ocr or options.table_detection):
                    blocks = self.ocr.recognize(image, page_index)
                    all_blocks.extend(blocks)
                tables: list[TableResult] = []
                if options.table_detection and image is not None:
                    if self.tables.available:
                        tables = self.tables.analyze(image, blocks, page_index)
                        all_tables.extend(tables)
                    elif page_index == 0:
                        warnings.append("表格模型不可用，已跳过 PDF 表格结构识别。")
                text = blocks_to_text(blocks, options.layout_mode) if needs_ocr else native_text
                page_texts.append(text)
                md_text = _non_table_text(blocks, tables, options.layout_mode) if needs_ocr else native_text
                page_markdowns.append(build_markdown(md_text, tables, f"第 {page_index + 1} 页"))
                if options.searchable_pdf and needs_ocr and blocks and image is not None:
                    self._insert_searchable_text(page, blocks, image.shape[1], image.shape[0])
                percent = int(((page_index + 1) / total_pages) * 95)
                progress(percent, f"正在处理第 {page_index + 1}/{total_pages} 页")
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
                metadata={"page_count": document.page_count},
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
