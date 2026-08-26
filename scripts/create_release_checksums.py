#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def asset_names(version: str) -> list[str]:
    prefix = f"document-ocr-assistant-{version}"
    return [
        f"{prefix}-macos-arm64-{edition}.dmg"
        for edition in ("ocr", "full")
    ] + [
        f"{prefix}-windows-x86_64-{edition}.zip"
        for edition in ("ocr", "full")
    ] + [
        f"{prefix}-kylin-v10-x86_64-{edition}.run"
        for edition in ("ocr", "full")
    ] + [
        f"{prefix}-kylin-v10-arm64-{edition}.run"
        for edition in ("ocr", "full")
    ]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the eight-asset release checksum file")
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--version", default="0.2.0")
    args = parser.parse_args()
    missing = [name for name in asset_names(args.version) if not (args.dist / name).is_file()]
    if missing:
        raise SystemExit("缺少发布资产：\n" + "\n".join(missing))
    output = args.dist / "SHA256SUMS.txt"
    output.write_text(
        "".join(
            f"{sha256(args.dist / name)}  {name}\n"
            for name in asset_names(args.version)
        ),
        encoding="utf-8",
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
