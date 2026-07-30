from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .models import OutputMode, PdfMode, ProcessingOptions


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
    output_mode: str = OutputMode.NEW_BATCH_DIRECTORY.value
    output_parent: str = str(Path.home() / "Documents" / "文档OCR输出")
    pdf_mode: str = PdfMode.AUTO.value
    searchable_pdf: bool = False
    table_detection: bool = True
    copy_unconverted_files: bool = False
    layout_mode: str = "natural"
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
