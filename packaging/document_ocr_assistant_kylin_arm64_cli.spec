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
hiddenimports = collect_submodules("rapidocr") + collect_submodules("rapid_table")
system_binaries = [
    (str(path), ".")
    for path in (
        Path("/usr/lib64/libGL.so.1"),
        Path("/usr/lib64/libGLX.so.0"),
        Path("/usr/lib64/libGLdispatch.so.0"),
    )
    if path.is_file()
]

analysis = Analysis(
    [str(ROOT / "src" / "document_ocr_assistant_cli_app.py")],
    pathex=[str(ROOT / "src")],
    binaries=system_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PySide6", "paddle", "paddleocr", "torch", "tensorflow"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="文档OCR助手命令行",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)
collect = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="文档OCR助手命令行",
)
