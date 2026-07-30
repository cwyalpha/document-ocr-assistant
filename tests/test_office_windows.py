from __future__ import annotations

from pathlib import Path

from document_ocr_assistant import office_windows


def test_backend_order_prefers_word_for_docx_and_wps_for_wps(monkeypatch) -> None:
    monkeypatch.setattr(office_windows, "_is_registered", lambda prog_id: True)
    monkeypatch.setenv("DOCUMENT_OCR_WINDOWS_OFFICE", "auto")
    assert office_windows._backend_order(Path("sample.docx"))[0][1] == "Word.Application"
    assert office_windows._backend_order(Path("sample.wps"))[0][1] == "KWPS.Application"


def test_backend_can_be_forced(monkeypatch) -> None:
    monkeypatch.setattr(office_windows, "_is_registered", lambda prog_id: True)
    monkeypatch.setenv("DOCUMENT_OCR_WINDOWS_OFFICE", "wps")
    assert office_windows._backend_order(Path("sample.docx")) == [
        ("WPS Office", "KWPS.Application")
    ]


def test_windows_office_html_and_text_decoding() -> None:
    html = '<meta http-equiv="Content-Type" content="text/html; charset=gb2312"><p>中文</p>'
    assert "中文" in office_windows._decode_html(html.encode("gb18030"))
    assert office_windows._normalize_word_text("A\r\x07B\rC") == "A\nB\nC"

