from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .models import (
    LayoutMode,
    OcrPreset,
    OutputMode,
    PageOrientation,
    PdfMode,
    ProcessingOptions,
)


APP_ID = "document-ocr-assistant"


def _xdg_path(env_name: str, fallback: Path) -> Path:
    value = os.environ.get(env_name)
    return Path(value).expanduser() if value else fallback


def config_directory() -> Path:
    if not os.environ.get("XDG_CONFIG_HOME") and sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_ID
    return _xdg_path("XDG_CONFIG_HOME", Path.home() / ".config") / APP_ID


def data_directory() -> Path:
    if not os.environ.get("XDG_DATA_HOME") and sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_ID
    return _xdg_path("XDG_DATA_HOME", Path.home() / ".local" / "share") / APP_ID


@dataclass(slots=True)
class AppSettings:
    schema_version: int = 3
    output_mode: str = OutputMode.NEW_BATCH_DIRECTORY.value
    output_parent: str = str(Path.home() / "Documents" / "文档OCR输出")
    pdf_mode: str = PdfMode.AUTO.value
    searchable_pdf: bool = False
    table_detection: bool = True
    copy_unconverted_files: bool = False
    layout_mode: str = LayoutMode.RAW.value
    include_page_numbers: bool = False
    ocr_preset: str = OcrPreset.BALANCED.value
    page_orientation: str = PageOrientation.AUTO.value
    orientation_confidence: float = 0.35
    textline_orientation: bool = True
    pdf_dpi: int = 200
    max_side_len: int = 2000
    det_limit_side_len: int = 736
    det_limit_type: str = "min"
    det_thresh: float = 0.3
    det_box_thresh: float = 0.5
    det_unclip_ratio: float = 1.6
    text_score: float = 0.5
    rec_batch_size: int = 6
    cpu_threads: int = 0
    page_range: str = ""
    hotkey: str = "Ctrl+Alt+O"
    close_to_tray: bool = True
    remember_close_choice: bool = False
    theme: str = "system"
    history_limit: int = 100

    def processing_options(self) -> ProcessingOptions:
        return ProcessingOptions(
            output_mode=OutputMode(self.output_mode),
            output_parent=Path(self.output_parent).expanduser(),
            pdf_mode=PdfMode(self.pdf_mode),
            searchable_pdf=self.searchable_pdf,
            table_detection=self.table_detection,
            copy_unconverted_files=self.copy_unconverted_files,
            layout_mode=self.layout_mode,
            include_page_numbers=self.include_page_numbers,
            ocr_preset=OcrPreset(self.ocr_preset),
            page_orientation=PageOrientation(self.page_orientation),
            orientation_confidence=self.orientation_confidence,
            textline_orientation=self.textline_orientation,
            pdf_dpi=self.pdf_dpi,
            max_side_len=self.max_side_len,
            det_limit_side_len=self.det_limit_side_len,
            det_limit_type=self.det_limit_type,
            det_thresh=self.det_thresh,
            det_box_thresh=self.det_box_thresh,
            det_unclip_ratio=self.det_unclip_ratio,
            text_score=self.text_score,
            rec_batch_size=self.rec_batch_size,
            cpu_threads=self.cpu_threads,
            page_range=self.page_range,
        )


class SettingsStore:
    def __init__(self, path: Path | None = None):
        self.path = path or config_directory() / "settings.json"

    def load(self) -> AppSettings:
        if not self.path.exists():
            return AppSettings()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return AppSettings()
        schema_version = payload.get("schema_version", 1)
        if not isinstance(schema_version, int):
            schema_version = 1
        if schema_version < 3:
            # Earlier releases defaulted to multi-column paragraph output. The
            # v3 default is raw OCR order, so existing installations must see
            # the same new default after upgrading rather than silently keeping
            # the legacy implicit value. Preserve other explicit layout choices.
            if payload.get("layout_mode") in {
                None,
                "natural",
                LayoutMode.MULTI_PARAGRAPH.value,
            }:
                payload["layout_mode"] = LayoutMode.RAW.value
            payload["include_page_numbers"] = False
            payload["schema_version"] = 3
        elif payload.get("layout_mode") == "natural":
            payload["layout_mode"] = LayoutMode.MULTI_PARAGRAPH.value
        defaults = asdict(AppSettings())
        values: dict[str, Any] = {key: payload.get(key, value) for key, value in defaults.items()}
        try:
            return AppSettings(**values)
        except (TypeError, ValueError):
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(self.path)
