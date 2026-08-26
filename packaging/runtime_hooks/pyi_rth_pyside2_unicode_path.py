"""Keep PyInstaller's PySide2 Qt prefix relocatable from Unicode paths.

Qt 5 reads qt.conf with Latin-1, while PyInstaller normally writes the
absolute ``sys._MEIPASS`` path into that file. An installation path containing
CJK characters can therefore raise UnicodeEncodeError before the application
starts. On Linux, Qt resolves a relative Prefix from the
directory containing the executable, so the bundled relative path is both
portable and Latin-1 safe.
"""

import os
import sys
import locale

from _pyi_rth_utils import qt as qt_rth_utils


_original_create_embedded_qt_conf = qt_rth_utils.create_embedded_qt_conf


def _ensure_utf8_locale_for_unicode_path(path):
    try:
        path.encode("latin1")
        return
    except UnicodeEncodeError:
        pass

    try:
        codeset = locale.nl_langinfo(locale.CODESET)
    except (AttributeError, ValueError):
        codeset = ""
    if codeset.lower().replace("-", "") == "utf8":
        return

    previous = {
        "LANG": os.environ.get("LANG"),
        "LC_ALL": os.environ.get("LC_ALL"),
    }
    for candidate in ("C.UTF-8", "C.utf8", "zh_CN.UTF-8", "zh_CN.utf8"):
        os.environ["LANG"] = candidate
        os.environ["LC_ALL"] = candidate
        try:
            locale.setlocale(locale.LC_ALL, "")
        except locale.Error:
            continue
        return

    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


_ensure_utf8_locale_for_unicode_path(sys.executable)


def _create_embedded_qt_conf_unicode_safe(qt_bindings, prefix_path):
    if qt_bindings in {"PySide2", "PyQt5"}:
        try:
            prefix_path.encode("latin1")
        except UnicodeEncodeError:
            executable_dir = os.path.dirname(os.path.abspath(sys.executable))
            relative_prefix = os.path.relpath(prefix_path, executable_dir)
            if os.sep == "\\":
                relative_prefix = relative_prefix.replace(os.sep, "/")

            try:
                relative_prefix.encode("latin1")
            except UnicodeEncodeError:
                # The bundled application uses an ASCII-only internal layout,
                # so this is only a defensive fallback. The package hook has
                # already configured QT_PLUGIN_PATH and QML2_IMPORT_PATH.
                return
            prefix_path = relative_prefix

    return _original_create_embedded_qt_conf(qt_bindings, prefix_path)


qt_rth_utils.create_embedded_qt_conf = _create_embedded_qt_conf_unicode_safe
