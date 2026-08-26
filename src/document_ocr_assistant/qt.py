"""Qt 5/6 compatibility imports used by the desktop client.

macOS, Windows and Kylin x86_64 use PySide6.  Kylin ARM64 builds PySide2
against Qt 5.15 inside the Kylin V10 container so the GUI keeps the target
system's glibc 2.28 baseline.
"""

from __future__ import annotations

import time

try:
    from PySide6 import QtCore, QtGui, QtWidgets

    try:
        from PySide6 import QtTest
    except ImportError:  # pragma: no cover - minimal runtime builds omit QtTest
        QtTest = None

    QT_API = "PySide6"
except ImportError:  # pragma: no cover - exercised by the Kylin ARM build
    from PySide2 import QtCore, QtGui, QtWidgets

    try:
        from PySide2 import QtTest
    except ImportError:
        QtTest = None

    QT_API = "PySide2"


for _module in (QtCore, QtGui, QtWidgets):
    for _name in dir(_module):
        if not _name.startswith("_"):
            globals().setdefault(_name, getattr(_module, _name))

if QtTest is not None:
    for _name in dir(QtTest):
        if not _name.startswith("_"):
            globals().setdefault(_name, getattr(QtTest, _name))
else:
    class QTest:
        """Small qWait fallback for Qt builds that omit the QtTest module."""

        @staticmethod
        def qWait(milliseconds: int) -> None:
            deadline = time.monotonic() + max(0, milliseconds) / 1000
            while time.monotonic() < deadline:
                QtCore.QCoreApplication.processEvents(QtCore.QEventLoop.AllEvents, 10)
                time.sleep(0.001)
            QtCore.QCoreApplication.processEvents(QtCore.QEventLoop.AllEvents, 10)

Signal = QtCore.Signal
Slot = QtCore.Slot
Qt = QtCore.Qt


def event_position(event):
    """Return a QPointF/QPoint for either the Qt 6 or Qt 5 event API."""
    position = getattr(event, "position", None)
    return position() if position is not None else event.pos()


def point_from_event(event):
    point = event_position(event)
    return point.toPoint() if hasattr(point, "toPoint") else point


def exec_dialog(dialog) -> int:
    execute = getattr(dialog, "exec", None) or dialog.exec_
    return int(execute())


def exec_application(application) -> int:
    execute = getattr(application, "exec", None) or application.exec_
    return int(execute())


def configure_high_dpi_rounding(application_class) -> None:
    setter = getattr(application_class, "setHighDpiScaleFactorRoundingPolicy", None)
    policy_group = getattr(Qt, "HighDpiScaleFactorRoundingPolicy", None)
    policy = getattr(policy_group, "PassThrough", None) if policy_group else None
    if setter is not None and policy is not None:
        setter(policy)


__all__ = [name for name in globals() if not name.startswith("_")]
