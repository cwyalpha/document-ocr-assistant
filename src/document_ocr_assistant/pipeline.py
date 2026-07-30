from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .archives import ArchiveSession, PasswordProvider
from .models import InputItem, InputKind, ProcessResult, ProcessingOptions
from .outputs import (
    atomic_write_bytes,
    atomic_write_text,
    copy_passthrough_files,
    deduplicate_path,
    output_path,
)
from .processors import DocumentProcessors, ProgressCallback


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class SavedResult:
    item: InputItem
    result: ProcessResult
    outputs: list[Path]


class ProcessingPipeline:
    def __init__(self, processors: DocumentProcessors | None = None) -> None:
        self.processors = processors or DocumentProcessors()

    def process_item(
        self,
        item: InputItem,
        options: ProcessingOptions,
        progress: ProgressCallback | None = None,
        cancelled: threading.Event | None = None,
        password_provider: PasswordProvider | None = None,
    ) -> list[SavedResult]:
        if item.kind is not InputKind.ARCHIVE:
            result = self.processors.process(item, options, progress, cancelled)
            return [self._save(item, result, options)]

        results: list[SavedResult] = []
        session = ArchiveSession(item.source_path, password_provider)
        with session as nested_items:
            total = max(1, len(nested_items))
            for index, nested_item in enumerate(nested_items):
                if cancelled and cancelled.is_set():
                    raise InterruptedError("任务已取消")

                def nested_progress(value: int, message: str) -> None:
                    overall = int(((index + value / 100) / total) * 100)
                    if progress:
                        progress(overall, f"{nested_item.virtual_path}: {message}")

                result = self.processors.process(nested_item, options, nested_progress, cancelled)
                results.append(self._save(nested_item, result, options))
            copied = copy_passthrough_files(session.unconverted_files, options)
            if copied:
                if results:
                    results[0].outputs.extend(copied)
                else:
                    results.append(
                        SavedResult(
                            item,
                            ProcessResult("", "", metadata={"copied_unconverted": len(copied)}),
                            copied,
                        )
                    )
        if progress:
            progress(
                100,
                f"压缩包处理完成，共 {len(results)} 个识别结果"
                + (f"，复制 {len(copied)} 个未转换文件" if copied else ""),
            )
        return results

    @staticmethod
    def _save(item: InputItem, result: ProcessResult, options: ProcessingOptions) -> SavedResult:
        outputs: list[Path] = []
        text_path = output_path(item, options, ".txt")
        atomic_write_text(text_path, result.text.strip() + "\n")
        outputs.append(text_path)

        markdown_path = output_path(item, options, ".md")
        atomic_write_text(markdown_path, result.markdown)
        outputs.append(markdown_path)

        if result.searchable_pdf_bytes is not None and item.kind is InputKind.PDF:
            pdf_path = output_path(item, options, ".pdf")
            pdf_path = deduplicate_path(
                pdf_path.with_name(pdf_path.name.replace("_ocr.pdf", "_searchable.pdf"))
            )
            atomic_write_bytes(pdf_path, result.searchable_pdf_bytes)
            outputs.append(pdf_path)
        return SavedResult(item, result, outputs)
