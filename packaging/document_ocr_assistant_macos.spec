from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


ROOT = Path(SPECPATH).resolve().parent


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
hiddenimports = collect_submodules("rapidocr") + collect_submodules("rapid_table")
hiddenimports += collect_submodules("charset_normalizer")

analysis = Analysis(
    [str(ROOT / "src" / "document_ocr_assistant_app.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "paddle",
        "paddleocr",
        "torch",
        "tensorflow",
        "Xlib",
        "pythoncom",
        "pywintypes",
        "win32com",
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="文档OCR助手",
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
    name="文档OCR助手",
)
app = BUNDLE(
    collect,
    name="文档OCR助手.app",
    icon=str(ROOT / "assets" / "app-icon.icns"),
    bundle_identifier="com.documentocr.assistant",
    info_plist={
        "CFBundleDisplayName": "文档OCR助手",
        "CFBundleName": "文档OCR助手",
        "CFBundleShortVersionString": "0.1.1",
        "CFBundleVersion": "2",
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "Copyright © 2026 Document OCR Assistant",
        "NSSupportsAutomaticGraphicsSwitching": True,
    },
)
