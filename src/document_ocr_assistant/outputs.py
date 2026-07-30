from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
from typing import Iterable

from .models import InputItem, OutputMode, PassthroughFile, ProcessingOptions


def create_batch_directory(parent: Path, now: datetime | None = None) -> Path:
    timestamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    candidate = parent / f"批次-{timestamp}"
    counter = 2
    while candidate.exists():
        candidate = parent / f"批次-{timestamp}-{counter}"
        counter += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def ensure_batch_directory(options: ProcessingOptions) -> Path | None:
    if options.output_mode is OutputMode.ALONGSIDE_SOURCE:
        return None
    if options.batch_directory:
        options.batch_directory.mkdir(parents=True, exist_ok=True)
        return options.batch_directory
    parent = options.output_parent or Path.home() / "Documents" / "文档OCR输出"
    parent.mkdir(parents=True, exist_ok=True)
    options.batch_directory = create_batch_directory(parent)
    return options.batch_directory


def _stem_without_compound_suffix(path: Path) -> str:
    lower = path.name.lower()
    if lower.endswith(".tar.gz"):
        return path.name[:-7]
    return path.stem


def deduplicate_path(path: Path) -> Path:
    if not path.exists():
        return path
    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem}-{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def output_path(item: InputItem, options: ProcessingOptions, extension: str) -> Path:
    extension = extension if extension.startswith(".") else f".{extension}"
    logical_source = item.virtual_path if item.virtual_path else item.source_path
    filename = f"{_stem_without_compound_suffix(logical_source)}_ocr{extension}"

    if options.output_mode is OutputMode.ALONGSIDE_SOURCE:
        if item.archive_path and item.virtual_path:
            base = item.archive_path.parent / f"{_stem_without_compound_suffix(item.archive_path)}_ocr"
            target = base / item.virtual_path.parent / filename
        else:
            target = item.source_path.parent / filename
    else:
        batch = ensure_batch_directory(options)
        assert batch is not None
        if item.archive_path and item.virtual_path:
            base = batch / f"{_stem_without_compound_suffix(item.archive_path)}_ocr"
            target = base / item.virtual_path.parent / filename
        elif item.root_path and item.virtual_path:
            target = batch / item.root_path.name / item.virtual_path.parent / filename
        else:
            target = batch / filename

    target.parent.mkdir(parents=True, exist_ok=True)
    return deduplicate_path(target)


def atomic_write_text(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)


def atomic_write_bytes(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def passthrough_output_path(item: PassthroughFile, options: ProcessingOptions) -> Path | None:
    if (
        options.output_mode is not OutputMode.NEW_BATCH_DIRECTORY
        or not options.copy_unconverted_files
    ):
        return None
    batch = ensure_batch_directory(options)
    assert batch is not None
    if item.archive_path:
        base = batch / f"{_stem_without_compound_suffix(item.archive_path)}_ocr"
    elif item.root_path:
        base = batch / item.root_path.name
    else:
        base = batch
    target = base / item.virtual_path
    try:
        target.resolve().relative_to(base.resolve())
    except ValueError as exc:
        raise ValueError(f"未转换文件包含不安全路径：{item.virtual_path}") from exc
    return target


def copy_passthrough_files(
    items: Iterable[PassthroughFile], options: ProcessingOptions
) -> list[Path]:
    outputs: list[Path] = []
    for item in items:
        target = passthrough_output_path(item, options)
        if target is None or not item.source_path.is_file() or item.source_path.is_symlink():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(item.source_path, target)
        outputs.append(target)
    return outputs
