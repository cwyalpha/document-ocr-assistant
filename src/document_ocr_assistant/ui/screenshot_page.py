from __future__ import annotations

import ctypes
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import (
    QByteArray,
    QBuffer,
    QIODevice,
    QPoint,
    QRect,
    QSize,
    Qt,
    QThread,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QColor,
    QCursor,
    QDesktopServices,
    QGuiApplication,
    QImage,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QRegion,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..history import HistoryStore
from ..models import ProcessingOptions
from ..ocr_engine import OcrEngine
from ..orientation import OrientationEngine
from ..processors import load_image_bgr
from ..settings import AppSettings
from ..text_format import blocks_to_text


def macos_screen_capture_access_granted() -> bool:
    """Return whether this app may read pixels from other macOS apps."""
    if sys.platform != "darwin":
        return True
    try:
        core_graphics = ctypes.CDLL(
            "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
        )
        preflight = core_graphics.CGPreflightScreenCaptureAccess
        preflight.argtypes = []
        preflight.restype = ctypes.c_bool
        return bool(preflight())
    except (AttributeError, OSError):
        # The app targets macOS 12+, where this API is available. Falling back
        # to the actual capture keeps the feature usable on unusual runtimes.
        return True


def request_macos_screen_capture_access() -> bool:
    """Ask macOS for screen-recording access and return the current result."""
    if sys.platform != "darwin":
        return True
    try:
        core_graphics = ctypes.CDLL(
            "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
        )
        request = core_graphics.CGRequestScreenCaptureAccess
        request.argtypes = []
        request.restype = ctypes.c_bool
        return bool(request())
    except (AttributeError, OSError):
        return False


def image_is_fully_black(image: QImage) -> bool:
    """Detect the opaque black frame macOS returns when capture is denied."""
    if image.isNull() or image.width() <= 0 or image.height() <= 0:
        return True
    sample = image.scaled(
        32,
        18,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.FastTransformation,
    )
    for y in range(sample.height()):
        for x in range(sample.width()):
            color = sample.pixelColor(x, y)
            if color.red() > 3 or color.green() > 3 or color.blue() > 3:
                return False
    return True


class GlobalHotkey(QWidget):
    activated = Signal()
    registration_failed = Signal(str)

    def __init__(self, sequence: str = "Ctrl+Alt+O") -> None:
        super().__init__()
        self.sequence = sequence
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._windows_thread_id: int | None = None
        self._macos_carbon = None
        self._macos_handler = None
        self._macos_handler_ref = None
        self._macos_hotkey_ref = None
        self.setVisible(False)

    def start(self) -> None:
        if self._thread or self._macos_hotkey_ref:
            return
        if sys.platform == "darwin":
            self._start_macos()
            return
        if sys.platform.startswith("linux"):
            target = self._run_x11
        elif sys.platform == "win32":
            target = self._run_windows
        else:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=target, name="ocr-global-hotkey", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._macos_carbon is not None:
            try:
                if self._macos_hotkey_ref:
                    self._macos_carbon.UnregisterEventHotKey(self._macos_hotkey_ref)
                if self._macos_handler_ref:
                    self._macos_carbon.RemoveEventHandler(self._macos_handler_ref)
            except Exception:
                pass
        self._macos_carbon = None
        self._macos_handler = None
        self._macos_handler_ref = None
        self._macos_hotkey_ref = None
        if sys.platform == "win32" and self._windows_thread_id:
            try:
                import ctypes

                ctypes.windll.user32.PostThreadMessageW(self._windows_thread_id, 0x0012, 0, 0)
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        self._windows_thread_id = None

    def _start_macos(self) -> None:
        """Register a global shortcut with Carbon without a PyObjC dependency."""
        import ctypes

        class EventTypeSpec(ctypes.Structure):
            _fields_ = [("event_class", ctypes.c_uint32), ("event_kind", ctypes.c_uint32)]

        class EventHotKeyID(ctypes.Structure):
            _fields_ = [("signature", ctypes.c_uint32), ("identifier", ctypes.c_uint32)]

        key_codes = {
            "a": 0,
            "s": 1,
            "d": 2,
            "f": 3,
            "h": 4,
            "g": 5,
            "z": 6,
            "x": 7,
            "c": 8,
            "v": 9,
            "b": 11,
            "q": 12,
            "w": 13,
            "e": 14,
            "r": 15,
            "y": 16,
            "t": 17,
            "1": 18,
            "2": 19,
            "3": 20,
            "4": 21,
            "6": 22,
            "5": 23,
            "=": 24,
            "9": 25,
            "7": 26,
            "-": 27,
            "8": 28,
            "0": 29,
            "]": 30,
            "o": 31,
            "u": 32,
            "[": 33,
            "i": 34,
            "p": 35,
            "l": 37,
            "j": 38,
            "'": 39,
            "k": 40,
            ";": 41,
            "\\": 42,
            ",": 43,
            "/": 44,
            "n": 45,
            "m": 46,
            ".": 47,
            "f1": 122,
            "f2": 120,
            "f3": 99,
            "f4": 118,
            "f5": 96,
            "f6": 97,
            "f7": 98,
            "f8": 100,
            "f9": 101,
            "f10": 109,
            "f11": 103,
            "f12": 111,
        }
        parts = [part.strip().lower() for part in self.sequence.split("+") if part.strip()]
        key_name = parts[-1] if parts else ""
        key_code = key_codes.get(key_name)
        if key_code is None:
            self.registration_failed.emit(f"不支持的 macOS 快捷键：{self.sequence}")
            return

        modifiers = 0
        if "command" in parts or "cmd" in parts or "meta" in parts:
            modifiers |= 1 << 8
        if "shift" in parts:
            modifiers |= 1 << 9
        if "alt" in parts or "option" in parts:
            modifiers |= 1 << 11
        if "ctrl" in parts or "control" in parts:
            modifiers |= 1 << 12

        try:
            carbon = ctypes.CDLL("/System/Library/Frameworks/Carbon.framework/Carbon")
            callback_type = ctypes.CFUNCTYPE(
                ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
            )
            carbon.GetApplicationEventTarget.restype = ctypes.c_void_p
            carbon.InstallEventHandler.argtypes = [
                ctypes.c_void_p,
                callback_type,
                ctypes.c_uint32,
                ctypes.POINTER(EventTypeSpec),
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_void_p),
            ]
            carbon.RegisterEventHotKey.argtypes = [
                ctypes.c_uint32,
                ctypes.c_uint32,
                EventHotKeyID,
                ctypes.c_void_p,
                ctypes.c_uint32,
                ctypes.POINTER(ctypes.c_void_p),
            ]
            carbon.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]
            carbon.RemoveEventHandler.argtypes = [ctypes.c_void_p]

            def handle_hotkey(_next_handler, _event, _user_data) -> int:
                self.activated.emit()
                return 0

            handler = callback_type(handle_hotkey)
            target = carbon.GetApplicationEventTarget()
            event_type = EventTypeSpec(
                int.from_bytes(b"keyb", "big"),
                6,  # kEventHotKeyPressed
            )
            handler_ref = ctypes.c_void_p()
            status = carbon.InstallEventHandler(
                target,
                handler,
                1,
                ctypes.byref(event_type),
                None,
                ctypes.byref(handler_ref),
            )
            if status:
                raise RuntimeError(f"InstallEventHandler 返回 {status}")

            hotkey_ref = ctypes.c_void_p()
            hotkey_id = EventHotKeyID(int.from_bytes(b"DOCR", "big"), 1)
            status = carbon.RegisterEventHotKey(
                key_code,
                modifiers,
                hotkey_id,
                target,
                0,
                ctypes.byref(hotkey_ref),
            )
            if status:
                carbon.RemoveEventHandler(handler_ref)
                if status == -9878:
                    raise RuntimeError("快捷键已被其他程序占用")
                raise RuntimeError(f"RegisterEventHotKey 返回 {status}")
        except Exception as exc:
            self.registration_failed.emit(f"全局快捷键注册失败：{exc}")
            return

        self._macos_carbon = carbon
        self._macos_handler = handler
        self._macos_handler_ref = handler_ref
        self._macos_hotkey_ref = hotkey_ref

    def _run_windows(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        hotkey_id = 0x4F43
        parts = [part.strip().lower() for part in self.sequence.split("+")]
        key_name = parts[-1].upper()
        if len(key_name) == 1:
            virtual_key = ord(key_name)
        elif key_name.startswith("F") and key_name[1:].isdigit():
            virtual_key = 0x70 + int(key_name[1:]) - 1
        else:
            self.registration_failed.emit(f"不支持的 Windows 快捷键：{self.sequence}")
            return
        modifiers = 0
        if "alt" in parts:
            modifiers |= 0x0001
        if "ctrl" in parts or "control" in parts:
            modifiers |= 0x0002
        if "shift" in parts:
            modifiers |= 0x0004
        self._windows_thread_id = int(kernel32.GetCurrentThreadId())
        if not user32.RegisterHotKey(None, hotkey_id, modifiers, virtual_key):
            self.registration_failed.emit(f"全局快捷键 {self.sequence} 已被其他程序占用。")
            return
        message = wintypes.MSG()
        try:
            while not self._stop.is_set():
                result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result <= 0:
                    break
                if message.message == 0x0312 and message.wParam == hotkey_id:
                    self.activated.emit()
        finally:
            user32.UnregisterHotKey(None, hotkey_id)

    def _run_x11(self) -> None:
        try:
            from Xlib import X, XK, display
        except ImportError:
            self.registration_failed.emit("未安装 python-xlib，全局截图快捷键不可用。")
            return
        try:
            connection = display.Display()
            root = connection.screen().root
            parts = [part.strip().lower() for part in self.sequence.split("+")]
            key_name = parts[-1]
            keysym = XK.string_to_keysym(key_name)
            if not keysym and len(key_name) == 1:
                keysym = XK.string_to_keysym(key_name.upper())
            keycode = connection.keysym_to_keycode(keysym)
            modifiers = 0
            if "ctrl" in parts or "control" in parts:
                modifiers |= X.ControlMask
            if "alt" in parts:
                modifiers |= X.Mod1Mask
            if "shift" in parts:
                modifiers |= X.ShiftMask
            for extra in (0, X.LockMask, X.Mod2Mask, X.LockMask | X.Mod2Mask):
                root.grab_key(keycode, modifiers | extra, True, X.GrabModeAsync, X.GrabModeAsync)
            connection.sync()
            while not self._stop.is_set():
                while connection.pending_events():
                    event = connection.next_event()
                    if event.type == X.KeyPress and event.detail == keycode:
                        self.activated.emit()
                time.sleep(0.04)
        except Exception as exc:
            self.registration_failed.emit(f"全局快捷键注册失败：{exc}")
        finally:
            try:
                connection.close()
            except Exception:
                pass


class CaptureOverlay(QWidget):
    captured = Signal(QImage)
    cancelled = Signal()

    MIN_SELECTION = 12
    HANDLE_RADIUS = 5
    HIT_MARGIN = 10

    def __init__(self) -> None:
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is None:
            raise RuntimeError("没有可用显示器。")
        self.screen = screen
        self.background = screen.grabWindow(0)
        if self.background.isNull():
            raise RuntimeError("未能读取屏幕画面。")
        if sys.platform == "darwin" and image_is_fully_black(
            self.background.toImage()
        ):
            raise RuntimeError("macOS 返回了黑色屏幕画面。")
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # A capture overlay is single-use. Deleting it on close prevents a
        # hidden first overlay from being destroyed while the second capture
        # is being created, which could otherwise clear the new reference and
        # leave the main window hidden in the system tray.
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(screen.geometry())
        self.selection = QRect()
        self.press_point = QPoint()
        self.initial_selection = QRect()
        self.drag_action: str | None = None
        self._finished = False

        self.confirm_button = QPushButton("确认识别", self)
        self.confirm_button.setProperty("primary", True)
        self.confirm_button.setFixedSize(96, 38)
        self.confirm_button.clicked.connect(self.confirm_selection)
        self.cancel_button = QPushButton("取消", self)
        self.cancel_button.setFixedSize(76, 38)
        self.cancel_button.clicked.connect(self.cancel_capture)
        self.confirm_button.hide()
        self.cancel_button.hide()

    def show_capture(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            point = self._bounded_point(event.position().toPoint())
            self.press_point = point
            self.initial_selection = QRect(self.selection)
            self.drag_action = self._hit_test(point)
            if self.drag_action is None:
                self.drag_action = "new"
                self.selection = QRect(point, point)
            self.confirm_button.hide()
            self.cancel_button.hide()
            self.update()

    def mouseMoveEvent(self, event) -> None:
        point = self._bounded_point(event.position().toPoint())
        if self.drag_action:
            if self.drag_action == "new":
                self.selection = QRect(self.press_point, point).normalized().intersected(self.rect())
            elif self.drag_action == "move":
                self.selection = self._moved_selection(point)
            else:
                self.selection = self._resized_selection(point, self.drag_action)
            self.update()
        else:
            self.setCursor(self._cursor_for_action(self._hit_test(point)))

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or not self.drag_action:
            return
        self.drag_action = None
        if not self._selection_valid():
            self.selection = QRect()
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self._position_action_buttons()
            self.setCursor(self._cursor_for_action(self._hit_test(event.position().toPoint())))
        self.update()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.selection.contains(
            event.position().toPoint()
        ):
            self.confirm_selection()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.cancel_capture()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.confirm_selection()
            return
        if self._selection_valid() and event.key() in (
            Qt.Key.Key_Left,
            Qt.Key.Key_Right,
            Qt.Key.Key_Up,
            Qt.Key.Key_Down,
        ):
            step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self._keyboard_resize(event.key(), step)
            else:
                dx = -step if event.key() == Qt.Key.Key_Left else step if event.key() == Qt.Key.Key_Right else 0
                dy = -step if event.key() == Qt.Key.Key_Up else step if event.key() == Qt.Key.Key_Down else 0
                self.initial_selection = QRect(self.selection)
                self.press_point = QPoint(0, 0)
                self.selection = self._moved_selection(QPoint(dx, dy))
            self._position_action_buttons()
            self.update()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        # Draw at the pixmap's device-independent size. Supplying self.rect()
        # as the target stretches the frozen desktop when display scaling is
        # enabled, which makes the selection preview drift from real pixels.
        painter.drawPixmap(QPoint(0, 0), self.background)
        if self._selection_valid():
            outside = QRegion(self.rect()).subtracted(QRegion(self.selection))
            painter.save()
            painter.setClipRegion(outside)
            painter.fillRect(self.rect(), QColor(10, 18, 30, 125))
            painter.restore()
            painter.setPen(QPen(QColor("#4C8BF7"), 2))
            painter.drawRect(self.selection)
            self._draw_handles(painter)
            label = f"{self.selection.width()} × {self.selection.height()}"
            label_y = max(4, self.selection.y() - 29)
            painter.fillRect(self.selection.x(), label_y, 112, 25, QColor(20, 27, 39, 220))
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(self.selection.x() + 8, label_y + 18, label)
        else:
            painter.fillRect(self.rect(), QColor(10, 18, 30, 125))
            message = "拖动框选区域 · 松开后可移动或调整选框 · Esc 取消"
            metrics = painter.fontMetrics()
            box_width = metrics.horizontalAdvance(message) + 36
            box = QRect(max(12, (self.width() - box_width) // 2), 24, box_width, 42)
            painter.fillRect(box, QColor(20, 27, 39, 225))
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, message)

    def _bounded_point(self, point: QPoint) -> QPoint:
        return QPoint(
            min(max(point.x(), 0), max(0, self.width() - 1)),
            min(max(point.y(), 0), max(0, self.height() - 1)),
        )

    def _selection_valid(self) -> bool:
        return (
            self.selection.width() >= self.MIN_SELECTION
            and self.selection.height() >= self.MIN_SELECTION
        )

    def _handle_points(self) -> dict[str, QPoint]:
        rectangle = self.selection
        center = rectangle.center()
        return {
            "top_left": rectangle.topLeft(),
            "top": QPoint(center.x(), rectangle.top()),
            "top_right": rectangle.topRight(),
            "right": QPoint(rectangle.right(), center.y()),
            "bottom_right": rectangle.bottomRight(),
            "bottom": QPoint(center.x(), rectangle.bottom()),
            "bottom_left": rectangle.bottomLeft(),
            "left": QPoint(rectangle.left(), center.y()),
        }

    def _draw_handles(self, painter: QPainter) -> None:
        painter.setPen(QPen(QColor("#3478F6"), 1))
        painter.setBrush(Qt.GlobalColor.white)
        radius = self.HANDLE_RADIUS
        for point in self._handle_points().values():
            painter.drawRect(QRect(point.x() - radius, point.y() - radius, radius * 2, radius * 2))

    def _hit_test(self, point: QPoint) -> str | None:
        if not self._selection_valid():
            return None
        margin = self.HIT_MARGIN
        for action, handle in self._handle_points().items():
            if abs(point.x() - handle.x()) <= margin and abs(point.y() - handle.y()) <= margin:
                return action
        if self.selection.contains(point):
            return "move"
        return None

    @staticmethod
    def _cursor_for_action(action: str | None) -> Qt.CursorShape:
        if action in {"top_left", "bottom_right"}:
            return Qt.CursorShape.SizeFDiagCursor
        if action in {"top_right", "bottom_left"}:
            return Qt.CursorShape.SizeBDiagCursor
        if action in {"left", "right"}:
            return Qt.CursorShape.SizeHorCursor
        if action in {"top", "bottom"}:
            return Qt.CursorShape.SizeVerCursor
        if action == "move":
            return Qt.CursorShape.SizeAllCursor
        return Qt.CursorShape.CrossCursor

    def _moved_selection(self, point: QPoint) -> QRect:
        delta = point - self.press_point
        rectangle = self.initial_selection.translated(delta)
        bounds = self.rect().adjusted(0, 0, -1, -1)
        if rectangle.left() < bounds.left():
            rectangle.moveLeft(bounds.left())
        if rectangle.top() < bounds.top():
            rectangle.moveTop(bounds.top())
        if rectangle.right() > bounds.right():
            rectangle.moveRight(bounds.right())
        if rectangle.bottom() > bounds.bottom():
            rectangle.moveBottom(bounds.bottom())
        return rectangle

    def _resized_selection(self, point: QPoint, action: str) -> QRect:
        rectangle = QRect(self.initial_selection)
        point = self._bounded_point(point)
        if "left" in action:
            rectangle.setLeft(min(point.x(), rectangle.right() - self.MIN_SELECTION + 1))
        if "right" in action:
            rectangle.setRight(max(point.x(), rectangle.left() + self.MIN_SELECTION - 1))
        if "top" in action:
            rectangle.setTop(min(point.y(), rectangle.bottom() - self.MIN_SELECTION + 1))
        if "bottom" in action:
            rectangle.setBottom(max(point.y(), rectangle.top() + self.MIN_SELECTION - 1))
        return rectangle.intersected(self.rect())

    def _keyboard_resize(self, key: int, step: int) -> None:
        rectangle = QRect(self.selection)
        bounds = self.rect().adjusted(0, 0, -1, -1)
        if key == Qt.Key.Key_Left:
            rectangle.setLeft(max(bounds.left(), rectangle.left() - step))
        elif key == Qt.Key.Key_Right:
            rectangle.setRight(min(bounds.right(), rectangle.right() + step))
        elif key == Qt.Key.Key_Up:
            rectangle.setTop(max(bounds.top(), rectangle.top() - step))
        elif key == Qt.Key.Key_Down:
            rectangle.setBottom(min(bounds.bottom(), rectangle.bottom() + step))
        self.selection = rectangle

    def _position_action_buttons(self) -> None:
        if not self._selection_valid():
            self.confirm_button.hide()
            self.cancel_button.hide()
            return
        gap = 8
        total_width = self.confirm_button.width() + self.cancel_button.width() + gap
        x = min(max(4, self.selection.right() - total_width + 1), max(4, self.width() - total_width - 4))
        below = self.selection.bottom() + 10
        if below + self.confirm_button.height() <= self.height() - 4:
            y = below
        else:
            y = max(4, self.selection.top() - self.confirm_button.height() - 10)
        self.confirm_button.move(x, y)
        self.cancel_button.move(x + self.confirm_button.width() + gap, y)
        self.confirm_button.show()
        self.cancel_button.show()
        self.confirm_button.raise_()
        self.cancel_button.raise_()

    @Slot()
    def confirm_selection(self) -> None:
        if self._finished or not self._selection_valid():
            return
        self._finished = True
        ratio = self.background.devicePixelRatio()
        source = QRect(
            round(self.selection.x() * ratio),
            round(self.selection.y() * ratio),
            round(self.selection.width() * ratio),
            round(self.selection.height() * ratio),
        )
        image = self.background.toImage().copy(source)
        image.setDevicePixelRatio(1.0)
        self.captured.emit(image)
        self.close()

    @Slot()
    def cancel_capture(self) -> None:
        if self._finished:
            return
        self._finished = True
        self.cancelled.emit()
        self.close()

    def closeEvent(self, event) -> None:
        if not self._finished:
            self._finished = True
            self.cancelled.emit()
        super().closeEvent(event)


class ScreenshotOcrWorker(QThread):
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        image: QImage,
        engine: OcrEngine,
        options: ProcessingOptions | None = None,
    ) -> None:
        super().__init__()
        self.image = image
        self.engine = engine
        self.options = options

    def run(self) -> None:
        try:
            data = QByteArray()
            buffer = QBuffer(data)
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            self.image.save(buffer, "PNG")
            buffer.close()
            payload = bytes(data)
            if self.options is None:
                # Keep the worker independently testable with a minimal OCR stub.
                blocks = self.engine.recognize(payload)
                self.succeeded.emit(blocks_to_text(blocks, "natural"))
                return
            image = load_image_bgr(payload)
            oriented = OrientationEngine().orient(
                image,
                self.options.page_orientation,
                self.options.orientation_confidence,
            )
            blocks = self.engine.recognize(oriented.image, options=self.options)
            blocks = [block for block in blocks if block.score >= self.options.text_score]
            self.succeeded.emit(blocks_to_text(blocks, self.options.layout_mode))
        except Exception as exc:
            self.failed.emit(str(exc))


class ScreenshotResultDialog(QDialog):
    def __init__(self, text: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("截图识别结果")
        self.resize(620, 420)
        layout = QVBoxLayout(self)
        title = QLabel("识别结果")
        title.setStyleSheet("font-size: 19px; font-weight: 700;")
        self.editor = QPlainTextEdit(text)
        row = QHBoxLayout()
        copy_button = QPushButton("复制文本")
        save_button = QPushButton("保存 TXT")
        close_button = QPushButton("完成")
        close_button.setProperty("primary", True)
        copy_button.clicked.connect(lambda: QApplication.clipboard().setText(self.editor.toPlainText()))
        save_button.clicked.connect(self.save_text)
        close_button.clicked.connect(self.accept)
        row.addStretch()
        row.addWidget(copy_button)
        row.addWidget(save_button)
        row.addWidget(close_button)
        layout.addWidget(title)
        layout.addWidget(self.editor, 1)
        layout.addLayout(row)

    @Slot()
    def save_text(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "保存识别文本", "截图识别.txt", "文本文件 (*.txt)")
        if path:
            Path(path).write_text(self.editor.toPlainText().rstrip() + "\n", encoding="utf-8")


class ScreenshotPage(QWidget):
    history_changed = Signal()

    def __init__(
        self,
        history: HistoryStore,
        engine: OcrEngine,
        settings: AppSettings | None = None,
    ) -> None:
        super().__init__()
        self.history = history
        self.engine = engine
        self.settings = settings
        self.overlay: CaptureOverlay | None = None
        self.worker: ScreenshotOcrWorker | None = None
        self._restore_main_window = False
        self._capture_pending = False
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)
        title = QLabel("截图识别")
        title.setObjectName("PageTitle")
        subtitle = QLabel("冻结屏幕后框选文字，可移动或调整选区，确认后再进行识别")
        subtitle.setObjectName("Muted")
        root.addWidget(title)
        root.addWidget(subtitle)
        card = QFrame()
        card.setObjectName("Card")
        card.setMinimumHeight(310)
        card_layout = QVBoxLayout(card)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        glyph = QLabel("⌗")
        glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        glyph.setStyleSheet("font-size: 72px; color: #3478F6; font-weight: 200;")
        instruction = QLabel("按 Ctrl + Alt + O 或点击按钮冻结屏幕并框选")
        instruction.setAlignment(Qt.AlignmentFlag.AlignCenter)
        instruction.setStyleSheet("font-size: 18px; font-weight: 600;")
        hint = QLabel("拖动选框或八个控制点调整，Enter 确认，Esc 取消")
        hint.setObjectName("Muted")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        button = QPushButton("开始截图识别")
        button.setProperty("primary", True)
        button.setFixedWidth(180)
        button.clicked.connect(self.start_capture)
        card_layout.addStretch()
        card_layout.addWidget(glyph)
        card_layout.addWidget(instruction)
        card_layout.addWidget(hint)
        card_layout.addSpacing(14)
        card_layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignCenter)
        card_layout.addStretch()
        root.addWidget(card)
        self.status = QLabel("准备就绪")
        self.status.setObjectName("Muted")
        root.addWidget(self.status)
        root.addStretch()

    @Slot()
    def start_capture(self) -> None:
        if (
            (self.worker and self.worker.isRunning())
            or self.overlay is not None
            or self._capture_pending
        ):
            return
        if not self._ensure_capture_access():
            return
        self._capture_pending = True
        top_level = self.window()
        self._restore_main_window = top_level.isVisible()
        if self._restore_main_window:
            top_level.hide()
            QTimer.singleShot(180, self._open_capture_overlay)
        else:
            self._open_capture_overlay()

    @Slot()
    def _open_capture_overlay(self) -> None:
        if not self._capture_pending:
            return
        try:
            overlay = CaptureOverlay()
        except Exception as exc:
            self._capture_pending = False
            self._restore_after_capture()
            if sys.platform == "darwin" and (
                not macos_screen_capture_access_granted()
                or "黑色屏幕画面" in str(exc)
            ):
                self._show_macos_capture_permission_help()
                return
            self.show_error(str(exc))
            return
        self.overlay = overlay
        self._capture_pending = False
        overlay.captured.connect(self.recognize_capture)
        overlay.cancelled.connect(self._capture_cancelled)
        overlay.destroyed.connect(self._overlay_destroyed)
        overlay.show_capture()

    def _ensure_capture_access(self) -> bool:
        if macos_screen_capture_access_granted():
            return True
        self.status.setText("需要开启 macOS 录屏权限")
        if request_macos_screen_capture_access():
            return True
        self._show_macos_capture_permission_help()
        return False

    def _show_macos_capture_permission_help(self) -> None:
        self.status.setText("需要开启 macOS 录屏权限")
        message = QMessageBox(self)
        message.setWindowTitle("需要录屏权限")
        message.setIcon(QMessageBox.Icon.Information)
        message.setText("文档OCR助手尚未获得 macOS 录屏权限。")
        message.setInformativeText(
            "未授权时 macOS 只会返回黑色画面，因此无法截图或识别文字。\n\n"
            "请在“隐私与安全性 → 录屏与系统录音”中允许“文档OCR助手”，"
            "然后完全退出并重新打开应用。"
        )
        settings_button = message.addButton(
            "打开系统设置", QMessageBox.ButtonRole.ActionRole
        )
        message.addButton("稍后", QMessageBox.ButtonRole.RejectRole)
        message.exec()
        if message.clickedButton() is settings_button:
            QDesktopServices.openUrl(
                QUrl(
                    "x-apple.systempreferences:"
                    "com.apple.preference.security?Privacy_ScreenCapture"
                )
            )

    @Slot()
    def _overlay_destroyed(self) -> None:
        self.overlay = None
        self._capture_pending = False
        # This is a safety net for platform-level window destruction. Normal
        # confirm/cancel paths restore the window before the overlay is gone.
        self._restore_after_capture()

    @Slot()
    def _capture_cancelled(self) -> None:
        self.status.setText("已取消截图")
        self._restore_after_capture()

    def _restore_after_capture(self) -> None:
        if not self._restore_main_window:
            return
        top_level = self.window()
        top_level.show()
        top_level.raise_()
        top_level.activateWindow()
        self._restore_main_window = False

    @Slot(QImage)
    def recognize_capture(self, image: QImage) -> None:
        self._restore_after_capture()
        self.status.setText("正在识别截图…")
        self.worker = ScreenshotOcrWorker(
            image,
            self.engine,
            self.settings.processing_options() if self.settings else None,
        )
        self.worker.succeeded.connect(self.show_result)
        self.worker.failed.connect(self.show_error)
        self.worker.start()

    @Slot(str)
    def show_result(self, text: str) -> None:
        if not text.strip():
            self.status.setText("未识别到文字")
            return
        self.history.add(text)
        self.history_changed.emit()
        self.status.setText("识别完成")
        dialog = ScreenshotResultDialog(text, self)
        dialog.exec()

    @Slot(str)
    def show_error(self, message: str) -> None:
        self.status.setText("识别失败")
        QMessageBox.warning(self, "截图识别失败", message)


class HistoryPage(QWidget):
    def __init__(self, history: HistoryStore) -> None:
        super().__init__()
        self.history = history
        self.entries = []
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)
        title_row = QHBoxLayout()
        title = QLabel("截图历史")
        title.setObjectName("PageTitle")
        clear = QPushButton("清空历史")
        clear.clicked.connect(self.clear_history)
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(clear)
        root.addLayout(title_row)
        content = QHBoxLayout()
        self.list = QListWidget()
        self.list.setFixedWidth(300)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list.setWordWrap(False)
        self.list.setSpacing(3)
        self.list.currentRowChanged.connect(self.show_entry)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        content.addWidget(self.list)
        content.addWidget(self.preview, 1)
        root.addLayout(content, 1)

    @Slot()
    def refresh(self) -> None:
        self.entries = self.history.list()
        self.list.clear()
        for entry in self.entries:
            summary = " ".join(entry.text.split())[:48]
            item = QListWidgetItem(f"{entry.created_at.replace('T', ' ')}\n{summary}")
            item.setSizeHint(QSize(0, 58))
            item.setToolTip(entry.text)
            self.list.addItem(item)
        if self.entries:
            self.list.setCurrentRow(0)
        else:
            self.preview.clear()

    @Slot(int)
    def show_entry(self, row: int) -> None:
        if 0 <= row < len(self.entries):
            self.preview.setPlainText(self.entries[row].text)

    @Slot()
    def clear_history(self) -> None:
        if QMessageBox.question(self, "清空历史", "确定删除全部截图识别历史吗？") == QMessageBox.StandardButton.Yes:
            self.history.clear()
            self.refresh()
