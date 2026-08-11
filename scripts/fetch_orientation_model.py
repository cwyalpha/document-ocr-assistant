#!/usr/bin/env python3
"""Fetch the pinned four-way document orientation ONNX model."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path


URL = (
    "https://github.com/RapidAI/RapidOrientation/releases/download/v0.0.0/"
    "rapid_orientation_models_v2.zip"
)
ARCHIVE_SHA256 = "bd21b970190538ae12f7f84972ab496f2aae79fbe4c5af4813920a7611a81d96"
MODEL_SHA256 = "2f62c9bfb830a0b417241269fde7ef2d0ad5446c0ed2b8af33b1f6543545e8e2"
MEMBER = "rapid_orientation_models_v2/rapid_orientation.onnx"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare pinned orientation model")
    parser.add_argument("output", type=Path)
    parser.add_argument("--source-archive", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    destination = output / "rapid_orientation.onnx"
    if destination.is_file() and digest(destination) == MODEL_SHA256:
        print(f"[orientation] cached and verified: {destination}")
        return 0
    with tempfile.TemporaryDirectory(prefix="document-ocr-orientation-") as temporary:
        archive = Path(temporary) / "orientation.zip"
        if args.source_archive:
            shutil.copy2(args.source_archive.resolve(), archive)
        else:
            request = urllib.request.Request(
                URL, headers={"User-Agent": "document-ocr-assistant-build/0.2"}
            )
            with urllib.request.urlopen(request, timeout=180) as response:
                archive.write_bytes(response.read())
        if digest(archive) != ARCHIVE_SHA256:
            raise RuntimeError("orientation archive SHA-256 mismatch")
        with zipfile.ZipFile(archive) as bundle:
            contents = bundle.read(MEMBER)
        temporary_model = Path(temporary) / "rapid_orientation.onnx"
        temporary_model.write_bytes(contents)
        if digest(temporary_model) != MODEL_SHA256:
            raise RuntimeError("orientation model SHA-256 mismatch")
        shutil.copy2(temporary_model, destination)
    print(f"[orientation] ready: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
