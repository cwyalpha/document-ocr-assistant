#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
        if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size=size)
    raise RuntimeError("未找到用于生成 macOS OCR 测试图片的字体。")


def centered(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    value_font: ImageFont.FreeTypeFont,
) -> None:
    left, top, right, bottom = box
    bounds = draw.textbbox((0, 0), text, font=value_font)
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    draw.text(
        ((left + right - width) / 2, (top + bottom - height) / 2 - 2),
        text,
        fill="#111827",
        font=value_font,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a macOS OCR/table smoke image")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1500, 980), "white")
    draw = ImageDraw.Draw(image)
    title_font = font(48, bold=True)
    header_font = font(34, bold=True)
    body_font = font(31)
    draw.text((100, 70), "文档 OCR 助手 macOS ONNX 验证", fill="#111827", font=title_font)
    xs = [100, 460, 840, 1160, 1400]
    ys = [210, 350, 490, 630, 770, 910]
    for x in xs:
        draw.line((x, ys[0], x, ys[-1]), fill="#111827", width=5)
    for y in ys:
        draw.line((xs[0], y, xs[-1], y), fill="#111827", width=5)
    # Erase internal vertical separators in the first row to create a colspan.
    for x in xs[1:-1]:
        draw.line((x, ys[0] + 4, x, ys[1] - 4), fill="white", width=9)
    centered(
        draw,
        (xs[0], ys[0], xs[-1], ys[1]),
        "macOS OCR Table / 合并单元格",
        header_font,
    )
    values = [
        ("项目", "平台", "架构", "状态"),
        ("离线 OCR", "macOS", "arm64", "通过"),
        ("中文识别", "Apple", "Silicon", "正常"),
        ("表格结构", "SLANet", "ONNX", "完成"),
    ]
    for row, row_values in enumerate(values, start=1):
        for column, value in enumerate(row_values):
            centered(
                draw,
                (xs[column], ys[row], xs[column + 1], ys[row + 1]),
                value,
                header_font if row == 1 else body_font,
            )
    image.save(output)
    print(f"[smoke] {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
