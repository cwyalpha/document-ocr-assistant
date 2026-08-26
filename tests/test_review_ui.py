from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from document_ocr_assistant.qt import QApplication, QTableWidgetItem

from document_ocr_assistant.models import InputItem, InputKind, OcrBlock, TaskRecord
from document_ocr_assistant.settings import AppSettings, SettingsStore
from document_ocr_assistant.ui.batch_page import BatchPage


def test_review_tabs_preview_pagination_and_settings_persistence(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    image_path = tmp_path / "review.png"
    Image.new("RGB", (400, 220), "white").save(image_path)
    settings_path = tmp_path / "settings.json"
    store = SettingsStore(settings_path)
    settings = AppSettings()
    page = BatchPage(settings, store)
    record = TaskRecord(
        InputItem(image_path, InputKind.IMAGE),
        text="整理结果",
        raw_text="高置信文字\n低置信文字",
        markdown="# 结果\n",
        blocks=[
            OcrBlock("高置信文字", [[10, 10], [160, 10], [160, 45], [10, 45]], 0.98),
            OcrBlock("低置信文字", [[10, 70], [160, 70], [160, 105], [10, 105]], 0.22),
        ],
        metadata={"page_count": 1, "pdf_dpi": None, "pages": [{"page_index": 0}]},
    )
    page.records.append(record)
    page.table.insertRow(0)
    page.table.setItem(0, 0, QTableWidgetItem("review.png"))
    page.table.setCurrentCell(0, 0)
    page._display_record(record)

    assert page.result_tabs.count() == 4
    assert page.result_editor.toPlainText() == "整理结果"
    assert page.raw_editor.toPlainText() == "高置信文字\n低置信文字"
    assert len(page.preview._blocks) == 2
    assert page.page_spin.maximum() == 1
    page.select_result_block(1)
    assert page.raw_editor.textCursor().selectedText() == "低置信文字"

    page.ocr_preset.setCurrentIndex(page.ocr_preset.findData("custom"))
    page.page_orientation.setCurrentIndex(page.page_orientation.findData("270"))
    page.page_range.setText("1")
    page.include_page_numbers.setChecked(True)
    page.text_score.setValue(0.61)
    options = page._options()
    assert options.page_orientation.value == "270"
    assert options.page_range == "1"
    assert options.include_page_numbers is True
    assert options.text_score == 0.61
    assert SettingsStore(settings_path).load().text_score == 0.61
    assert SettingsStore(settings_path).load().include_page_numbers is True
    page.close()
    app.processEvents()
