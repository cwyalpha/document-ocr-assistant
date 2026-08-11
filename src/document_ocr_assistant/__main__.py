from __future__ import annotations

import json
import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .edition import build_info
from .runtime import find_app_icon
from .settings import SettingsStore, data_directory
from .ui.main_window import MainWindow
from .ui.theme import DARK_STYLE, LIGHT_STYLE, use_dark_palette


def configure_logging() -> None:
    log_dir = data_directory() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(log_dir / "document-ocr.log", maxBytes=5 * 1024 * 1024, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def main() -> int:
    office_smoke_input = os.environ.get("DOCUMENT_OCR_OFFICE_SMOKE_INPUT")
    office_smoke_output = os.environ.get("DOCUMENT_OCR_OFFICE_SMOKE_OUTPUT")
    if office_smoke_input and office_smoke_output:
        from .office_documents import convert_word

        text, html = convert_word(Path(office_smoke_input))
        Path(office_smoke_output).write_text(
            json.dumps(
                {
                    "text": text,
                    "html_length": len(html or ""),
                    "html_has_table": "<table" in (html or "").lower(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return 0
    pipeline_smoke_input = os.environ.get("DOCUMENT_OCR_PIPELINE_SMOKE_INPUT")
    pipeline_smoke_output = os.environ.get("DOCUMENT_OCR_PIPELINE_SMOKE_OUTPUT")
    if pipeline_smoke_input and pipeline_smoke_output:
        from .inputs import expand_inputs
        from .models import OutputMode, ProcessingOptions
        from .pipeline import ProcessingPipeline

        report_path = Path(pipeline_smoke_output)
        items, unsupported = expand_inputs([pipeline_smoke_input])
        if not items or unsupported:
            raise RuntimeError(f"流水线测试输入不受支持：{pipeline_smoke_input}")
        options = ProcessingOptions(
            output_mode=OutputMode.NEW_BATCH_DIRECTORY,
            output_parent=report_path.parent / "pipeline-output",
            table_detection=True,
            searchable_pdf=True,
        )
        saved = ProcessingPipeline().process_item(
            items[0], options, cancelled=threading.Event()
        )
        report_path.write_text(
            json.dumps(
                {
                    "outputs": [str(path) for entry in saved for path in entry.outputs],
                    "text": "\n".join(entry.result.text for entry in saved),
                    "markdown": "\n".join(entry.result.markdown for entry in saved),
                    "ocr_blocks": sum(len(entry.result.blocks) for entry in saved),
                    "raw_text": "\n".join(entry.result.raw_text for entry in saved),
                    "metadata": [entry.result.metadata for entry in saved],
                    "tables": sum(len(entry.result.tables) for entry in saved),
                    "warnings": [
                        warning for entry in saved for warning in entry.result.warnings
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return 0
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    application = QApplication(sys.argv)
    application_name = f"文档OCR助手（{build_info().display_suffix}）"
    application.setApplicationName(application_name)
    application.setApplicationDisplayName(application_name)
    application.setOrganizationName("DocumentOCR")
    icon_path = find_app_icon()
    if icon_path:
        application.setWindowIcon(QIcon(str(icon_path)))
    application.setQuitOnLastWindowClosed(False)
    configure_logging()
    store = SettingsStore()
    settings = store.load()
    dark = settings.theme == "dark" or (settings.theme == "system" and use_dark_palette(application))
    application.setStyleSheet(DARK_STYLE if dark else LIGHT_STYLE)
    window = MainWindow(settings, store)
    window.show()
    smoke_screenshot = os.environ.get("DOCUMENT_OCR_UI_SMOKE_SCREENSHOT")
    if smoke_screenshot:
        def finish_smoke_test() -> None:
            saved = window.grab().save(smoke_screenshot)
            logging.getLogger(__name__).info("UI smoke screenshot saved=%s path=%s", saved, smoke_screenshot)
            window.exit_application()

        QTimer.singleShot(1000, finish_smoke_test)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
