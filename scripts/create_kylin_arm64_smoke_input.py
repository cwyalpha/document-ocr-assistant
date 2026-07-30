#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _font(size: int) -> ImageFont.FreeTypeFont:
    candidates = (
        "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )
    for candidate in candidates:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size=size)
    raise RuntimeError("未找到用于生成 Kylin ARM64 OCR 测试图片的字体。")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a synthetic Kylin ARM64 OCR input")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    image = Image.new("RGB", (1500, 700), "white")
    draw = ImageDraw.Draw(image)
    title = _font(66)
    body = _font(50)
    draw.text((100, 100), "Kylin ARM64 PP-OCRv6 CLI Test", fill="#111827", font=title)
    draw.text((100, 260), "Offline OCR on aarch64", fill="#111827", font=body)
    draw.text((100, 390), "Document OCR Assistant 2026", fill="#111827", font=body)
    draw.rectangle((70, 70, 1430, 560), outline="#1d4ed8", width=8)
    image.save(output)
    print(f"[smoke] {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
