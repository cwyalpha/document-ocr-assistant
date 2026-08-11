#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def main() -> int:
    parser = argparse.ArgumentParser(description="Rewrite a public image without metadata")
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    with Image.open(args.image) as source:
        pixels = source.copy()
        image_format = source.format or "PNG"
    pixels.save(args.image, format=image_format)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
