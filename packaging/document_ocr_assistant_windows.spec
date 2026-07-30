from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


ROOT = Path(SPECPATH).resolve().parent


def without_bundled_models(entries):
    return [entry for entry in entries if "/models/" not in entry[0].replace("\\", "/")]


datas = without_bundled_models(collect_data_files("rapidocr"))
datas += without_bundled_models(collect_data_files("rapid_table"))
hiddenimports = collect_submodules("rapidocr") + collect_submodules("rapid_table")
hiddenimports += [
    "pythoncom",
    "pywintypes",
    "win32timezone",
    "win32com",
    "win32com.client",
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
    excludes=["paddle", "paddleocr", "torch", "tensorflow", "Xlib"],
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
    name="文档OCR助手",
)

