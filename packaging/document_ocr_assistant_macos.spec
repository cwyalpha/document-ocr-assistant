import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


ROOT = Path(SPECPATH).resolve().parent
EDITION = os.environ.get("DOCUMENT_OCR_BUILD_EDITION", "full")
APP_NAME = "文档OCR助手 OCR版" if EDITION == "ocr" else "文档OCR助手 完整版"
BUILD_INFO = os.environ.get("DOCUMENT_OCR_BUILD_INFO", "")
VERSION = os.environ.get("DOCUMENT_OCR_BUILD_VERSION", "0.2.0")


def without_bundled_models(entries):
    return [
        entry
        for entry in entries
        if "/models/" not in entry[0].replace("\\", "/")
    ]


datas = without_bundled_models(collect_data_files("rapidocr"))
datas += without_bundled_models(collect_data_files("rapid_table"))
# charset-normalizer ships accelerated extensions alongside pure Python
# package files. Copy the latter out of PYZ so the package is not shadowed by
# its Frameworks directory in a macOS app bundle.
datas += collect_data_files("charset_normalizer", include_py_files=True)
datas += [(str(ROOT / "assets" / "app-icon.svg"), "assets")]
if BUILD_INFO:
    datas += [(BUILD_INFO, ".")]
hiddenimports = collect_submodules("rapidocr") + collect_submodules("rapid_table")
hiddenimports += collect_submodules("charset_normalizer")
excludes = [
    "paddle",
    "paddleocr",
    "torch",
    "tensorflow",
    "Xlib",
    "pythoncom",
    "pywintypes",
    "win32com",
]
if EDITION == "ocr":
    excludes += [
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
    target_arch="arm64",
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "app-icon.icns"),
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
app = BUNDLE(
    collect,
    name=f"{APP_NAME}.app",
    icon=str(ROOT / "assets" / "app-icon.icns"),
    bundle_identifier=f"com.documentocr.assistant.{EDITION}",
    info_plist={
        "CFBundleDisplayName": APP_NAME,
        "CFBundleName": APP_NAME,
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": "3",
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "Copyright © 2026 Document OCR Assistant",
        "NSSupportsAutomaticGraphicsSwitching": True,
    },
)
