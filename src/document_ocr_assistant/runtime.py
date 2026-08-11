from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Iterable


def runtime_roots() -> list[Path]:
    roots: list[Path] = []
    configured = os.environ.get("DOCUMENT_OCR_ROOT")
    if configured:
        roots.append(Path(configured))
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable)
        bundle_root = Path(getattr(sys, "_MEIPASS", executable.parent))
        roots.extend(
            [
                bundle_root,
                executable.parent,
                executable.parent.parent,
                executable.parent.parent.parent,
            ]
        )
        if sys.platform == "darwin":
            # PyInstaller places application data in Contents/Resources.
            roots.append(executable.parent.parent / "Resources")
    else:
        source = Path(__file__).resolve()
        roots.extend([source.parents[2], source.parents[3]])
    roots.append(Path.cwd())
    seen: set[str] = set()
    unique: list[Path] = []
    for root in roots:
        try:
            key = os.path.normcase(str(root.resolve()))
        except OSError:
            key = os.path.normcase(str(root.absolute()))
        if key not in seen:
            unique.append(root)
            seen.add(key)
    return unique


def find_file(env_names: Iterable[str], relative_paths: Iterable[str]) -> Path | None:
    for env_name in env_names:
        value = os.environ.get(env_name)
        if value and Path(value).is_file():
            return Path(value)
    for root in runtime_roots():
        for relative in relative_paths:
            candidate = root / relative
            if candidate.is_file():
                return candidate
    return None


def find_ppocrv6_models() -> dict[str, Path] | None:
    explicit = os.environ.get("DOCUMENT_OCR_MODELS")
    candidates: list[Path] = [Path(explicit)] if explicit else []
    for root in runtime_roots():
        candidates.extend(
            [
                root / "models" / "ppocrv6-medium",
                root / "bin" / "rapidocr" / "models",
                root / "offline_components" / "rapidocr-ppocrv6-medium",
            ]
        )
    names = {
        "det": "PP-OCRv6_det_medium.onnx",
        "rec": "PP-OCRv6_rec_medium.onnx",
        "cls": "ch_ppocr_mobile_v2.0_cls_mobile.onnx",
    }
    for directory in candidates:
        result = {key: directory / name for key, name in names.items()}
        if all(path.is_file() for path in result.values()):
            return result
    return None


def find_orientation_model() -> Path | None:
    return find_file(
        ("DOCUMENT_OCR_ORIENTATION_MODEL",),
        (
            "models/orientation/rapid_orientation.onnx",
            "bin/rapidorientation/models/rapid_orientation.onnx",
        ),
    )


def find_table_model() -> Path | None:
    return find_file(
        ("DOCUMENT_OCR_TABLE_MODEL",),
        (
            "models/table/slanet-plus.onnx",
            "models/table/slanet_plus.onnx",
            "bin/rapidtable/models/slanet-plus.onnx",
        ),
    )


def find_app_icon() -> Path | None:
    return find_file((), ("assets/app-icon.svg", "assets/app-icon.png"))


def find_soffice() -> Path | None:
    candidate = find_file(
        ("DOCUMENT_OCR_SOFFICE", "SOFFICE_BIN", "LIBREOFFICE_BIN"),
        (
            "bin/libreoffice/program/soffice",
            "bin/libreoffice/opt/libreoffice/program/soffice",
            "bin/libreoffice/program/soffice.exe",
        ),
    )
    if candidate:
        return candidate
    if sys.platform == "darwin":
        for application in (
            Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"),
            Path.home() / "Applications/LibreOffice.app/Contents/MacOS/soffice",
        ):
            if application.is_file():
                return application
    found = shutil.which("soffice") or shutil.which("libreoffice")
    return Path(found) if found else None


def find_archive_tool(names: tuple[str, ...] = ("7zz", "7z", "unrar")) -> Path | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return Path(found)
    for root in runtime_roots():
        for name in names:
            variants = (name, f"{name}.exe") if os.name == "nt" else (name,)
            for variant in variants:
                for relative in (
                    f"bin/archive/{variant}",
                    f"bin/{name}/{variant}",
                    f"bin/{variant}",
                ):
                    candidate = root / relative
                    if candidate.is_file():
                        return candidate
    return None
