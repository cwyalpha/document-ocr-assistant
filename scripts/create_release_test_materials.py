#!/usr/bin/env python3
"""Generate non-sensitive OCR release-gate fixtures; never package this output."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import fitz
from PIL import Image, ImageDraw, ImageFont


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/usr/share/fonts/cantarell/Cantarell-Regular.otf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "C:/Windows/Fonts/msyh.ttc",
    )
    for candidate in candidates:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def base_page() -> Image.Image:
    image = Image.new("RGB", (1200, 800), "white")
    draw = ImageDraw.Draw(image)
    title = font(54)
    body = font(34)
    draw.text((110, 120), "Document OCR Assistant", fill="black", font=title)
    draw.text((110, 230), "PP-OCRv6 generated release test", fill="black", font=body)
    draw.text((110, 300), "离线识别测试 2026", fill="black", font=body)
    draw.text((110, 370), "Searchable PDF / Page orientation", fill="black", font=body)
    return image


def orientation_page() -> Image.Image:
    """Create a text-dense page that gives the four-way model a stable crop."""
    image = Image.new("RGB", (1200, 800), "white")
    draw = ImageDraw.Draw(image)
    title = font(46)
    body = font(34)
    draw.text((90, 55), "Document OCR Assistant", fill="black", font=title)
    lines = [
        "PP-OCRv6 offline release validation document",
        "Horizontal text verifies automatic page orientation",
        "Searchable PDF output keeps the detected text layer",
        "Table recognition uses the bundled ONNX structure model",
        "LibreOffice converts Word and WPS documents offline",
        "Archive input supports ZIP RAR 7Z TAR and TAR.GZ files",
        "The desktop client processes local files without a web server",
        "Generated test material contains no private user information",
        "Document OCR Assistant release gate line nine",
        "Document OCR Assistant release gate line ten",
        "Document OCR Assistant release gate line eleven",
    ]
    for index, line in enumerate(lines):
        draw.text((90, 145 + index * 55), line, fill="black", font=body)
    return image


def table_page() -> Image.Image:
    image = base_page()
    draw = ImageDraw.Draw(image)
    for x in (110, 430, 760, 1090):
        draw.line((x, 500, x, 700), fill="black", width=3)
    for y in (500, 565, 630, 700):
        draw.line((110, y, 1090, y), fill="black", width=3)
    cell_font = font(26)
    for row, values in enumerate((("Item", "Count", "Status"), ("OCR", "8", "PASS"), ("PDF", "4", "PASS"))):
        for column, value in enumerate(values):
            draw.text((130 + 325 * column, 515 + 65 * row), value, fill="black", font=cell_font)
    return image


def columns_page() -> Image.Image:
    image = Image.new("RGB", (1200, 800), "white")
    draw = ImageDraw.Draw(image)
    title = font(48)
    body = font(28)
    draw.text((100, 70), "Two-column OCR layout", fill="black", font=title)
    for index in range(7):
        draw.text((90, 180 + index * 68), f"Left column line {index + 1}", fill="black", font=body)
        draw.text((650, 180 + index * 68), f"Right column line {index + 1}", fill="black", font=body)
    return image


def save_pdf_with_image(image_path: Path, output: Path) -> None:
    document = fitz.open()
    page = document.new_page(width=600, height=400)
    page.insert_image(page.rect, filename=str(image_path))
    document.save(output)
    document.close()


def save_mixed_pdf(image_path: Path, output: Path) -> None:
    document = fitz.open()
    page = document.new_page(width=600, height=400)
    page.insert_text((72, 100), "Native copyable PDF page", fontsize=24)
    page = document.new_page(width=600, height=400)
    page.insert_image(page.rect, filename=str(image_path))
    document.save(output)
    document.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate safe OCR release fixtures")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    upright = orientation_page()
    upright_path = output / "orientation-0.png"
    upright.save(upright_path)
    for angle in (90, 180, 270):
        upright.rotate(angle, expand=True, fillcolor="white").save(output / f"orientation-{angle}.png")
    upright.resize((480, 320), Image.Resampling.LANCZOS).save(output / "low-resolution-small-text.png")
    table_page().save(output / "table.png")
    columns_page().save(output / "two-columns.png")
    save_pdf_with_image(upright_path, output / "scanned-no-text-layer.pdf")
    save_mixed_pdf(upright_path, output / "mixed-native-and-scanned.pdf")
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "generated": True,
                "sensitive": False,
                "expected_orientation_files": [f"orientation-{angle}.png" for angle in (0, 90, 180, 270)],
                "scanned_pdf_has_native_text": False,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
