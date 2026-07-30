from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMainWindow

from document_ocr_assistant.history import HistoryStore
from document_ocr_assistant.ui import screenshot_page
from document_ocr_assistant.ui.screenshot_page import ScreenshotPage


class EmptyOcrEngine:
    def recognize(self, _payload: bytes):
        return []


def _wait_until(predicate, timeout_ms: int = 3_000) -> bool:
    elapsed = 0
    while elapsed < timeout_ms:
        if predicate():
            return True
        QTest.qWait(50)
        elapsed += 50
    return predicate()


def test_second_capture_opens_after_first_capture_is_confirmed(
    monkeypatch, tmp_path: Path
) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        screenshot_page, "macos_screen_capture_access_granted", lambda: True
    )
    monkeypatch.setattr(screenshot_page, "image_is_fully_black", lambda _image: False)
    window = QMainWindow()
    page = ScreenshotPage(
        HistoryStore(tmp_path / "history.sqlite3"),
        EmptyOcrEngine(),  # type: ignore[arg-type]
    )
    window.setCentralWidget(page)
    window.show()
    QTest.qWait(30)

    page.start_capture()
    QTest.qWait(240)
    assert page.overlay is not None and page.overlay.isVisible()
    page.overlay.selection = QRect(10, 10, 100, 100)
    page.overlay.confirm_selection()

    assert page.worker is not None
    assert page.worker.wait(3_000)
    assert _wait_until(lambda: page.overlay is None)
    assert window.isVisible()

    page.start_capture()
    QTest.qWait(240)
    assert page.overlay is not None and page.overlay.isVisible()
    page.overlay.cancel_capture()
    assert _wait_until(lambda: page.overlay is None)
    assert window.isVisible()

    window.close()
    app.processEvents()


def test_capture_permission_denial_keeps_main_window_visible(
    monkeypatch, tmp_path: Path
) -> None:
    app = QApplication.instance() or QApplication([])
    window = QMainWindow()
    page = ScreenshotPage(
        HistoryStore(tmp_path / "history.sqlite3"),
        EmptyOcrEngine(),  # type: ignore[arg-type]
    )
    window.setCentralWidget(page)
    window.show()
    QTest.qWait(30)

    permission_help_shown: list[bool] = []
    monkeypatch.setattr(
        screenshot_page, "macos_screen_capture_access_granted", lambda: False
    )
    monkeypatch.setattr(
        screenshot_page, "request_macos_screen_capture_access", lambda: False
    )
    monkeypatch.setattr(
        page,
        "_show_macos_capture_permission_help",
        lambda: permission_help_shown.append(True),
    )

    page.start_capture()

    assert permission_help_shown == [True]
    assert page.overlay is None
    assert not page._capture_pending
    assert window.isVisible()

    window.close()
    app.processEvents()


def test_black_capture_detection() -> None:
    from PySide6.QtGui import QColor, QImage

    black = QImage(64, 36, QImage.Format.Format_RGB32)
    black.fill(QColor("black"))
    assert screenshot_page.image_is_fully_black(black)

    black.setPixelColor(10, 10, QColor("white"))
    assert not screenshot_page.image_is_fully_black(black)
