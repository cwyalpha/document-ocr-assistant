#!/usr/bin/env python3
"""Re-encode public PNG screenshots without ancillary metadata chunks."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

from PIL import Image


def strip(path: Path) -> None:
    path = path.resolve()
    with Image.open(path) as source:
        source.load()
        pixels = source.copy()
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.stem}-clean-", suffix=".png", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        pixels.save(temporary, format="PNG", optimize=True)
        with Image.open(temporary) as check:
            if check.getexif() or check.info:
                raise RuntimeError(f"PNG metadata was not removed: {path}")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path)
    args = parser.parse_args()
    for image in args.images:
        strip(image)
        print(f"[png] metadata removed: {image}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
