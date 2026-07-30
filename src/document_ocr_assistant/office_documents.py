from __future__ import annotations

import os
import sys
from pathlib import Path

from .runtime import find_soffice


def convert_word(source: Path, timeout: int = 180) -> tuple[str, str | None]:
    """Convert a Word/WPS document with the platform-native backend."""
    if os.name == "nt":
        from .office_windows import convert_word_windows

        return convert_word_windows(source, timeout=timeout)

    from .libreoffice import convert_word as convert_word_libreoffice

    return convert_word_libreoffice(source, timeout=timeout)


def office_backend_description() -> str:
    if sys.platform == "darwin":
        if find_soffice():
            return "LibreOffice · 使用系统安装"
        return "未检测到 LibreOffice（图片/PDF OCR 不受影响）"
    if os.name != "nt":
        return "LibreOffice 7.6 · 随包离线运行"
    try:
        from .office_windows import registered_office_backends

        backends = registered_office_backends()
    except Exception:
        backends = []
    if not backends:
        return "未检测到 Microsoft Word 或 WPS Office"
    return " / ".join(backends) + " · 自动选择"
