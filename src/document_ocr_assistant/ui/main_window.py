from __future__ import annotations

from PySide6.QtCore import QSize, QTimer, Qt, Slot
from PySide6.QtGui import QAction, QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyle,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from ..history import HistoryStore
from ..office_documents import office_backend_description
from ..ocr_engine import OcrEngine
from ..settings import AppSettings, SettingsStore
from .batch_page import BatchPage
from .screenshot_page import GlobalHotkey, HistoryPage, ScreenshotPage


class SettingsPage(QWidget):
    def __init__(self, settings: AppSettings, store: SettingsStore) -> None:
        super().__init__()
        self.settings = settings
        self.store = store
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)
        title = QLabel("设置")
        title.setObjectName("PageTitle")
        root.addWidget(title)
        card = QFrame()
        card.setObjectName("SettingsCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        rows = [
            ("OCR 引擎", "PP-OCRv6 Medium · ONNX Runtime"),
            ("表格引擎", "SLANet-plus · ONNX Runtime · 自动检测可关闭"),
            ("识别语言", "简体中文 + 英文"),
            ("Office 文档引擎", office_backend_description()),
            ("截图快捷键", settings.hotkey),
            ("隐私", "所有内容均在本机离线处理"),
        ]
        for label, value in rows:
            row = QHBoxLayout()
            key = QLabel(label)
            key.setStyleSheet("font-weight: 650;")
            val = QLabel(value)
            val.setObjectName("Muted")
            row.addWidget(key)
            row.addStretch()
            row.addWidget(val)
            layout.addLayout(row)
        close_row = QHBoxLayout()
        close_label = QLabel("关闭主窗口")
        close_label.setStyleSheet("font-weight: 650;")
        self.close_behavior = QComboBox()
        self.close_behavior.addItem("每次询问", "ask")
        self.close_behavior.addItem("缩小到右下角", "tray")
        self.close_behavior.addItem("退出程序", "quit")
        if not settings.remember_close_choice:
            behavior = "ask"
        else:
            behavior = "tray" if settings.close_to_tray else "quit"
        self.close_behavior.setCurrentIndex(self.close_behavior.findData(behavior))
        self.close_behavior.currentIndexChanged.connect(self.save_close_behavior)
        close_row.addWidget(close_label)
        close_row.addStretch()
        close_row.addWidget(self.close_behavior)
        layout.addLayout(close_row)
        root.addWidget(card)
        root.addStretch()

    @Slot()
    def save_close_behavior(self) -> None:
        behavior = str(self.close_behavior.currentData())
        self.settings.remember_close_choice = behavior != "ask"
        if behavior != "ask":
            self.settings.close_to_tray = behavior == "tray"
        self.store.save(self.settings)


class MainWindow(QMainWindow):
    def __init__(self, settings: AppSettings, store: SettingsStore) -> None:
        super().__init__()
        self.settings = settings
        self.store = store
        self._really_close = False
        self.setWindowTitle("文档OCR助手")
        self.setMinimumSize(1080, 720)
        self.resize(1380, 860)
        self.ocr_engine = OcrEngine()
        self.history_store = HistoryStore(limit=settings.history_limit)
        self._build_ui()
        self._build_tray()
        self.hotkey = GlobalHotkey(settings.hotkey)
        self.hotkey.activated.connect(self.screenshot_page.start_capture)
        self.hotkey.registration_failed.connect(self.on_hotkey_failure)
        self.hotkey.start()

    def _build_ui(self) -> None:
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(218)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(16, 22, 16, 18)
        side_layout.setSpacing(7)
        brand_row = QHBoxLayout()
        logo = QLabel()
        application_icon = QApplication.windowIcon()
        if application_icon.isNull():
            logo.setText("◆")
            logo.setStyleSheet("font-size: 22px; color: #3478F6; font-weight: 700;")
        else:
            logo.setPixmap(application_icon.pixmap(QSize(30, 30)))
        logo.setFixedSize(32, 32)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("文档OCR助手")
        title.setObjectName("AppTitle")
        brand_row.addWidget(logo)
        brand_row.addWidget(title)
        side_layout.addLayout(brand_row)
        side_layout.addSpacing(20)

        self.stack = QStackedWidget()
        self.batch_page = BatchPage(self.settings, self.store)
        self.screenshot_page = ScreenshotPage(self.history_store, self.ocr_engine)
        self.history_page = HistoryPage(self.history_store)
        self.settings_page = SettingsPage(self.settings, self.store)
        self.screenshot_page.history_changed.connect(self.history_page.refresh)
        for page in (self.batch_page, self.screenshot_page, self.history_page, self.settings_page):
            self.stack.addWidget(page)

        self.nav_buttons: list[QPushButton] = []
        for index, label in enumerate(("批量识别", "截图识别", "历史记录", "设置")):
            button = QPushButton(label)
            button.setProperty("nav", True)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, value=index: self.select_page(value))
            side_layout.addWidget(button)
            self.nav_buttons.append(button)
        self.nav_buttons[0].setChecked(True)
        side_layout.addStretch()
        version = QLabel("离线版 · ONNX")
        version.setObjectName("Muted")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        side_layout.addWidget(version)
        layout.addWidget(sidebar)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self)
        icon = self.windowIcon()
        if icon.isNull():
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView)
        self.tray.setIcon(icon)
        menu = QMenu()
        open_action = QAction("打开文档OCR助手", self)
        screenshot_action = QAction("截图识别", self)
        exit_action = QAction("退出", self)
        open_action.triggered.connect(self.show_main_window)
        screenshot_action.triggered.connect(self.screenshot_page.start_capture)
        exit_action.triggered.connect(self.exit_application)
        menu.addAction(open_action)
        menu.addAction(screenshot_action)
        menu.addSeparator()
        menu.addAction(exit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show_main_window() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    @Slot(int)
    def select_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for position, button in enumerate(self.nav_buttons):
            button.setChecked(position == index)
        if index == 2:
            self.history_page.refresh()

    @Slot()
    def show_main_window(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    @Slot(str)
    def on_hotkey_failure(self, message: str) -> None:
        self.statusBar().showMessage(message, 8000)

    @Slot()
    def exit_application(self) -> None:
        self._really_close = True
        self._prepare_shutdown()
        QApplication.quit()

    def _prepare_shutdown(self) -> None:
        self.hotkey.stop()
        if self.batch_page.worker and self.batch_page.worker.isRunning():
            self.batch_page.worker.cancel()
            self.batch_page.worker.wait(3000)

    def _ask_close_behavior(self) -> tuple[str, bool]:
        message = QMessageBox(self)
        message.setWindowTitle("关闭文档OCR助手")
        message.setIcon(QMessageBox.Icon.Question)
        message.setText("关闭主窗口后要执行什么操作？")
        message.setInformativeText("缩小到右下角后，仍可使用截图快捷键和托盘菜单。")
        remember = QCheckBox("记住本次选择")
        remember.setChecked(False)
        message.setCheckBox(remember)
        tray_button = message.addButton(
            "缩小到右下角", QMessageBox.ButtonRole.AcceptRole
        )
        quit_button = message.addButton("退出程序", QMessageBox.ButtonRole.DestructiveRole)
        message.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        message.setDefaultButton(tray_button)
        message.exec()
        clicked = message.clickedButton()
        if clicked is tray_button:
            return "tray", remember.isChecked()
        if clicked is quit_button:
            return "quit", remember.isChecked()
        return "cancel", False

    def _remember_close_behavior(self, behavior: str) -> None:
        self.settings.remember_close_choice = True
        self.settings.close_to_tray = behavior == "tray"
        self.store.save(self.settings)
        index = self.settings_page.close_behavior.findData(behavior)
        if index >= 0:
            self.settings_page.close_behavior.blockSignals(True)
            self.settings_page.close_behavior.setCurrentIndex(index)
            self.settings_page.close_behavior.blockSignals(False)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._really_close or not self.tray.isVisible():
            self._prepare_shutdown()
            event.accept()
            # QApplication keeps running without a tray because the app uses
            # setQuitOnLastWindowClosed(False). Explicitly quit when no tray is
            # available (common in minimal X11 sessions).
            QTimer.singleShot(0, QApplication.quit)
            return

        if self.settings.remember_close_choice:
            behavior = "tray" if self.settings.close_to_tray else "quit"
            remember = False
        else:
            behavior, remember = self._ask_close_behavior()
        if behavior == "cancel":
            event.ignore()
            return
        if remember:
            self._remember_close_behavior(behavior)
        if behavior == "quit":
            self._really_close = True
            self._prepare_shutdown()
            event.accept()
            QTimer.singleShot(0, QApplication.quit)
            return
        event.ignore()
        self.hide()
        self.tray.showMessage("文档OCR助手", "程序已缩小到右下角，可继续使用截图快捷键。")
