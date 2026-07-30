#!/usr/bin/env python3
"""Create an image-only PDF and prove that it has no selectable text layer."""

from __future__ import annotations

import argparse
from pathlib import Path

import fitz


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an image-only scanned PDF")
    parser.add_argument("image", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    image = args.image.resolve()
    output = args.output.resolve()
    if not image.is_file():
        raise FileNotFoundError(image)

    pixmap = fitz.Pixmap(str(image))
    # Use 144 dpi so one PDF point represents two image pixels.
    width = pixmap.width / 2
    height = pixmap.height / 2
    output.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open()
    try:
        page = document.new_page(width=width, height=height)
        page.insert_image(page.rect, filename=str(image))
        document.save(output, garbage=4, deflate=True)
    finally:
        document.close()

    verification = fitz.open(output)
    try:
        extracted_text = "".join(page.get_text("text") for page in verification).strip()
        image_count = sum(len(page.get_images(full=True)) for page in verification)
        if extracted_text:
            raise RuntimeError("测试 PDF 意外包含可复制文本层。")
        if image_count < 1:
            raise RuntimeError("测试 PDF 没有扫描图像。")
        print(
            f"[scanned-pdf] {output} pages={verification.page_count} "
            f"images={image_count} native_text_chars={len(extracted_text)}"
        )
    finally:
        verification.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
