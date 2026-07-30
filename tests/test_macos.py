from __future__ import annotations

import sys
from pathlib import Path

import pytest

from document_ocr_assistant import runtime


def test_frozen_macos_runtime_includes_bundle_resources(monkeypatch, tmp_path: Path) -> None:
    executable = tmp_path / "文档OCR助手.app" / "Contents" / "MacOS" / "文档OCR助手"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.setattr(sys, "platform", "darwin")
    roots = runtime.runtime_roots()
    assert executable.parent.parent / "Resources" in roots


def test_explicit_soffice_is_detected(monkeypatch, tmp_path: Path) -> None:
    soffice = tmp_path / "soffice"
    soffice.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("DOCUMENT_OCR_SOFFICE", str(soffice))
    assert runtime.find_soffice() == soffice


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS Carbon integration")
def test_macos_global_hotkey_registers_and_stops(monkeypatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from document_ocr_assistant.ui.screenshot_page import GlobalHotkey

    application = QApplication.instance() or QApplication([])
    hotkey = GlobalHotkey("Ctrl+Alt+F12")
    failures: list[str] = []
    hotkey.registration_failed.connect(failures.append)
    hotkey.start()
    application.processEvents()
    assert failures == []
    assert hotkey._macos_hotkey_ref
    hotkey.stop()
    assert hotkey._macos_hotkey_ref is None
