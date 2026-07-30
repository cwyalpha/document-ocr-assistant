#!/usr/bin/env python3
"""Fetch or copy the pinned PP-OCRv6 Medium ONNX model set."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import tempfile
import urllib.request
from pathlib import Path


MODEL_BASE_URL = (
    "https://www.modelscope.cn/models/RapidAI/RapidOCR/"
    "resolve/v3.9.1/onnx"
)
MODELS = {
    "PP-OCRv6_det_medium.onnx": (
        f"{MODEL_BASE_URL}/PP-OCRv6/det/PP-OCRv6_det_medium.onnx",
        "92078b7355007ccfffcd4c8cd441a3afd4538904d06881b29a155e1e679907c2",
    ),
    "PP-OCRv6_rec_medium.onnx": (
        f"{MODEL_BASE_URL}/PP-OCRv6/rec/PP-OCRv6_rec_medium.onnx",
        "eef444829dbbe18d7fea59a3f6eb75647518d2b3a9568d27c92e42940204894b",
    ),
    "ch_ppocr_mobile_v2.0_cls_mobile.onnx": (
        f"{MODEL_BASE_URL}/PP-OCRv4/cls/ch_ppocr_mobile_v2.0_cls_mobile.onnx",
        "e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c",
    ),
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def install_model(
    name: str,
    url: str,
    expected_hash: str,
    output: Path,
    source_directory: Path | None,
) -> None:
    destination = output / name
    if destination.is_file() and digest(destination) == expected_hash:
        print(f"[model] cached and verified: {destination}")
        return

    output.mkdir(parents=True, exist_ok=True)
    source = source_directory / name if source_directory else None
    with tempfile.NamedTemporaryFile(dir=output, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        if source and source.is_file():
            print(f"[model] copying {source}")
            shutil.copy2(source, temporary)
        else:
            print(f"[model] downloading {url}")
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "document-ocr-assistant-build/0.1"},
            )
            with urllib.request.urlopen(request, timeout=180) as response:
                with temporary.open("wb") as target:
                    shutil.copyfileobj(response, target)
        actual_hash = digest(temporary)
        if actual_hash != expected_hash:
            raise RuntimeError(
                f"{name} SHA-256 mismatch: expected {expected_hash}, got {actual_hash}"
            )
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"[model] ready: {destination}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare pinned PP-OCRv6 Medium models")
    parser.add_argument("output", type=Path)
    parser.add_argument("--source-dir", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    source = args.source_dir.resolve() if args.source_dir else None
    for name, (url, expected_hash) in MODELS.items():
        install_model(name, url, expected_hash, output, source)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
