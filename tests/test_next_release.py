from __future__ import annotations

from pathlib import Path

import fitz
import numpy as np
from PIL import Image

from document_ocr_assistant.edition import build_info, version_banner
from document_ocr_assistant.inputs import classify_path, unsupported_reason
from document_ocr_assistant.models import (
    InputItem,
    InputKind,
    OcrBlock,
    OcrPreset,
    PageOrientation,
    PdfMode,
    LayoutMode,
    ProcessingOptions,
    ProductEdition,
)
from document_ocr_assistant.orientation import (
    OrientationEngine,
    OrientationResult,
    blocks_to_original,
)
from document_ocr_assistant.processors import DocumentProcessors, parse_page_range
from document_ocr_assistant.settings import AppSettings, SettingsStore


class NoTables:
    available = False

    def analyze(self, *_args, **_kwargs):
        return []


class FixedOcr:
    def recognize(self, _image, page_index=0, options=None):
        return [
            OcrBlock(
                "OCR SEARCHABLE",
                [[20, 20], [220, 20], [220, 55], [20, 55]],
                0.98,
                page_index,
            )
        ]


def test_page_range_and_presets() -> None:
    assert ProcessingOptions().layout_mode == LayoutMode.RAW.value
    assert ProcessingOptions().include_page_numbers is False
    assert parse_page_range("1-3, 5，3", 6) == [0, 1, 2, 4]
    assert ProcessingOptions(ocr_preset=OcrPreset.FAST).resolved_ocr_values() == {
        "pdf_dpi": 150,
        "max_side_len": 1600,
    }
    assert ProcessingOptions(ocr_preset=OcrPreset.ACCURATE).resolved_ocr_values() == {
        "pdf_dpi": 300,
        "max_side_len": 4096,
    }


def test_orientation_low_confidence_and_coordinate_restore(monkeypatch) -> None:
    image = np.arange(2 * 3 * 3, dtype=np.uint8).reshape(2, 3, 3)
    engine = OrientationEngine()
    monkeypatch.setattr("document_ocr_assistant.orientation.find_orientation_model", lambda: Path("model"))
    monkeypatch.setattr(engine, "classify", lambda _image: (90, 0.2))
    unchanged = engine.orient(image, PageOrientation.AUTO, 0.35)
    assert unchanged.applied_angle == 0
    assert "置信度较低" in unchanged.warning

    manual = engine.orient(image, PageOrientation.ROTATE_90, 0.35)
    assert manual.image.shape[:2] == (3, 2)
    rotated_block = OcrBlock("A", [[0, 0], [1, 0], [1, 1], [0, 1]])
    restored = blocks_to_original([rotated_block], manual)[0]
    assert restored.polygon == [[2, 0], [2, 1], [1, 1], [1, 0]]


def test_settings_persist_pipeline_controls(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    settings = AppSettings(
        ocr_preset="custom",
        page_orientation="270",
        textline_orientation=False,
        page_range="2-4",
        pdf_dpi=360,
        max_side_len=5000,
        det_limit_side_len=1216,
        det_thresh=0.25,
        det_box_thresh=0.62,
        det_unclip_ratio=1.9,
        text_score=0.66,
        rec_batch_size=12,
        cpu_threads=4,
        include_page_numbers=True,
    )
    store.save(settings)
    loaded = store.load()
    options = loaded.processing_options()
    assert options.page_orientation is PageOrientation.ROTATE_270
    assert options.textline_orientation is False
    assert options.page_range == "2-4"
    assert options.resolved_ocr_values() == {"pdf_dpi": 360, "max_side_len": 5000}
    assert options.det_box_thresh == 0.62
    assert options.cpu_threads == 4
    assert options.include_page_numbers is True


def test_ocr_edition_rejects_word_and_version_reports_edition(monkeypatch) -> None:
    monkeypatch.setenv("DOCUMENT_OCR_DEV_EDITION", "ocr")
    build_info.cache_clear()
    try:
        assert build_info().edition is ProductEdition.OCR
        assert classify_path(Path("sample.docx")) is InputKind.UNSUPPORTED
        assert "下载完整版" in unsupported_reason(Path("sample.wps"))
        assert "(ocr," in version_banner()
    finally:
        build_info.cache_clear()


def test_scanned_pdf_gets_searchable_text_layer(tmp_path: Path) -> None:
    png = tmp_path / "scan.png"
    Image.new("RGB", (320, 180), "white").save(png)
    source = tmp_path / "scanned.pdf"
    document = fitz.open()
    page = document.new_page(width=320, height=180)
    page.insert_image(page.rect, filename=str(png))
    document.save(source)
    document.close()
    with fitz.open(source) as original:
        assert not original[0].get_text().strip()

    processors = DocumentProcessors(FixedOcr(), NoTables(), OrientationEngine())
    result = processors.process(
        InputItem(source, InputKind.PDF),
        ProcessingOptions(
            pdf_mode=PdfMode.FORCE_OCR,
            searchable_pdf=True,
            table_detection=False,
            page_orientation=PageOrientation.OFF,
        ),
    )
    assert result.searchable_pdf_bytes
    with fitz.open(stream=result.searchable_pdf_bytes, filetype="pdf") as searchable:
        assert "OCR SEARCHABLE" in searchable[0].get_text()
    assert result.metadata["processed_pages"] == [1]
    assert not result.text.startswith("第 1 页")
    assert not result.markdown.startswith("# 第 1 页")

    numbered = processors.process(
        InputItem(source, InputKind.PDF),
        ProcessingOptions(
            pdf_mode=PdfMode.FORCE_OCR,
            table_detection=False,
            page_orientation=PageOrientation.OFF,
            include_page_numbers=True,
        ),
    )
    assert numbered.text.startswith("第 1 页\n\n")
    assert numbered.markdown.startswith("# 第 1 页\n\n")
