import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


ROOT = Path(SPECPATH).resolve().parent
EDITION = os.environ.get("DOCUMENT_OCR_BUILD_EDITION", "full")
APP_NAME = "文档OCR助手OCR版" if EDITION == "ocr" else "文档OCR助手完整版"
BUILD_INFO = os.environ.get("DOCUMENT_OCR_BUILD_INFO", "")


def without_bundled_models(entries):
    return [entry for entry in entries if "/models/" not in entry[0].replace("\\", "/")]


datas = without_bundled_models(collect_data_files("rapidocr"))
datas += without_bundled_models(collect_data_files("rapid_table"))
if BUILD_INFO:
    datas += [(BUILD_INFO, ".")]
hiddenimports = collect_submodules("rapidocr") + collect_submodules("rapid_table")
if EDITION == "full":
    hiddenimports += [
        "pythoncom",
        "pywintypes",
        "win32timezone",
        "win32com",
        "win32com.client",
    ]
excludes = ["paddle", "paddleocr", "torch", "tensorflow", "Xlib"]
if EDITION == "ocr":
    excludes += [
        "pythoncom",
        "pywintypes",
        "win32com",
        "document_ocr_assistant.libreoffice",
        "document_ocr_assistant.office_documents",
        "document_ocr_assistant.office_windows",
    ]

analysis = Analysis(
    [str(ROOT / "src" / "document_ocr_assistant_app.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=1,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "app-icon.ico"),
)
collect = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)
