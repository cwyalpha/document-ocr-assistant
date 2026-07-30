#!/usr/bin/env python3
"""Create a relocatable Kylin ARM64 LibreOffice runtime.

The Kylin RPM places LibreOffice itself under /usr/lib64/libreoffice but many
document filters depend on shared libraries installed elsewhere in /usr/lib64.
This script copies the application tree, discovers ELF dependencies with ldd,
and adds the non-glibc dependency closure beside the bundled program.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path


CORE_SYSTEM_LIBRARIES = {
    "ld-linux-aarch64.so.1",
    "libc.so.6",
    "libdl.so.2",
    "libgcc_s.so.1",
    "libm.so.6",
    "libpthread.so.0",
    "libresolv.so.2",
    "librt.so.1",
    "libstdc++.so.6",
    "libutil.so.1",
}
DEPENDENCY_PATTERN = re.compile(r"(?:=>\s*)?(/[^\s(]+)")


def _is_elf(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        with path.open("rb") as stream:
            return stream.read(4) == b"\x7fELF"
    except OSError:
        return False


def _dependencies(path: Path) -> set[Path]:
    completed = subprocess.run(
        ["ldd", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if completed.returncode not in (0, 1):
        return set()
    result: set[Path] = set()
    for line in completed.stdout.splitlines():
        match = DEPENDENCY_PATTERN.search(line)
        if match:
            candidate = Path(match.group(1))
            if candidate.is_file():
                result.add(candidate)
    return result


def _copy_dependency(source: Path, destination: Path) -> Path:
    target = destination / source.name
    resolved = source.resolve()
    if not target.exists():
        shutil.copy2(resolved, target)
    return target


def bundle(libreoffice_root: Path, output_root: Path, unrar: Path | None) -> None:
    if not (libreoffice_root / "program" / "soffice").is_file():
        raise FileNotFoundError(libreoffice_root / "program" / "soffice")
    if output_root.exists():
        shutil.rmtree(output_root)
    shutil.copytree(libreoffice_root, output_root, symlinks=True)

    program = output_root / "program"
    portable_libraries = program / "portable-libs"
    portable_libraries.mkdir()
    queue = [path for path in output_root.rglob("*") if _is_elf(path)]
    visited: set[Path] = set()
    copied: dict[str, Path] = {}
    while queue:
        binary = queue.pop()
        try:
            key = binary.resolve()
        except OSError:
            key = binary
        if key in visited:
            continue
        visited.add(key)
        for dependency in _dependencies(binary):
            if dependency.name in CORE_SYSTEM_LIBRARIES:
                continue
            if str(dependency).startswith(str(libreoffice_root)):
                continue
            if dependency.name in copied:
                continue
            target = _copy_dependency(dependency, portable_libraries)
            copied[dependency.name] = target
            if _is_elf(target):
                queue.append(target)

    original = program / "soffice"
    real = program / "soffice.real"
    original.rename(real)
    original.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export LD_LIBRARY_PATH="$HERE/portable-libs:$HERE${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export SAL_USE_VCLPLUGIN="${SAL_USE_VCLPLUGIN:-gen}"
exec "$HERE/soffice.real" "$@"
""",
        encoding="utf-8",
    )
    original.chmod(original.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    if unrar:
        archive_destination = output_root.parent / "unrar"
        archive_destination.mkdir(parents=True, exist_ok=True)
        target = archive_destination / "unrar"
        shutil.copy2(unrar, target)
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    print(
        f"[libreoffice] {output_root} dependencies={len(copied)} "
        f"size={sum(path.stat().st_size for path in output_root.rglob('*') if path.is_file())}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Bundle Kylin ARM64 LibreOffice")
    parser.add_argument("--libreoffice-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--unrar", type=Path)
    args = parser.parse_args()
    bundle(
        args.libreoffice_root.resolve(),
        args.output_root.resolve(),
        args.unrar.resolve() if args.unrar else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
