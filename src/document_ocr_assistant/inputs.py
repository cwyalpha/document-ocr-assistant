from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from .edition import is_full_edition
from .models import InputItem, InputKind, PassthroughFile


IMAGE_EXTENSIONS = {".jpg", ".jpe", ".jpeg", ".jfif", ".png", ".webp", ".bmp", ".tif", ".tiff"}
WORD_EXTENSIONS = {".doc", ".docx", ".wps"}
ARCHIVE_EXTENSIONS = {".zip", ".rar", ".7z", ".tar", ".tgz", ".tar.gz"}


def compound_suffix(path: Path) -> str:
    name = path.name.lower()
    if name.endswith(".tar.gz"):
        return ".tar.gz"
    return path.suffix.lower()


def classify_path(path: Path) -> InputKind:
    suffix = compound_suffix(path)
    if suffix in IMAGE_EXTENSIONS:
        return InputKind.IMAGE
    if suffix == ".pdf":
        return InputKind.PDF
    if suffix in WORD_EXTENSIONS and is_full_edition():
        return InputKind.WORD
    if suffix in ARCHIVE_EXTENSIONS:
        return InputKind.ARCHIVE
    return InputKind.UNSUPPORTED


def unsupported_reason(path: Path) -> str:
    if compound_suffix(path) in WORD_EXTENSIONS and not is_full_edition():
        return "OCR版不支持 Word/WPS 文档，请下载完整版"
    return "不支持的文件类型"


def _canonical_key(path: Path) -> str:
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path.absolute()
    return os.path.normcase(str(resolved))


def expand_inputs(paths: Iterable[str | Path]) -> tuple[list[InputItem], list[Path]]:
    """Expand files and directories without following directory symlinks."""
    items: list[InputItem] = []
    unsupported: list[Path] = []
    seen: set[str] = set()

    def add_file(file_path: Path, root: Path | None = None) -> None:
        key = _canonical_key(file_path)
        if key in seen:
            return
        seen.add(key)
        kind = classify_path(file_path)
        if kind is InputKind.UNSUPPORTED:
            unsupported.append(file_path)
            return
        virtual = None
        if root:
            try:
                virtual = file_path.relative_to(root)
            except ValueError:
                virtual = Path(file_path.name)
        items.append(InputItem(file_path, kind, root_path=root, virtual_path=virtual))

    for raw_path in paths:
        path = Path(raw_path).expanduser()
        if path.is_symlink():
            unsupported.append(path)
            continue
        if path.is_file():
            add_file(path)
            continue
        if not path.is_dir():
            unsupported.append(path)
            continue
        for current_root, directories, files in os.walk(path, followlinks=False):
            directories[:] = sorted(
                (
                    name
                    for name in directories
                    if not (Path(current_root) / name).is_symlink()
                ),
                key=str.casefold,
            )
            for name in sorted(files, key=str.casefold):
                file_path = Path(current_root) / name
                if file_path.is_symlink():
                    unsupported.append(file_path)
                else:
                    add_file(file_path, root=path)
    return items, unsupported


def collect_passthrough_files(
    paths: Iterable[str | Path], unsupported: Iterable[Path]
) -> list[PassthroughFile]:
    """Map unsupported regular files back to the dragged directory hierarchy."""
    roots = [
        Path(raw_path).expanduser()
        for raw_path in paths
        if Path(raw_path).expanduser().is_dir()
    ]
    result: list[PassthroughFile] = []
    seen: set[str] = set()
    for file_path in unsupported:
        if not file_path.is_file() or file_path.is_symlink():
            continue
        key = _canonical_key(file_path)
        if key in seen:
            continue
        for root in roots:
            try:
                virtual_path = file_path.relative_to(root)
            except ValueError:
                continue
            result.append(PassthroughFile(file_path, virtual_path, root_path=root))
            seen.add(key)
            break
    return result
