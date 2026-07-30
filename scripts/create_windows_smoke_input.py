from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    names = [
        "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for name in names:
        path = Path(name)
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    raise RuntimeError("未找到用于生成 Windows OCR 测试图片的字体。")


def centered(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, text_font) -> None:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=text_font)
    width, height = right - left, bottom - top
    x1, y1, x2, y2 = box
    draw.text(
        (x1 + (x2 - x1 - width) / 2, y1 + (y2 - y1 - height) / 2 - top),
        text,
        fill="#111827",
        font=text_font,
    )


def create_image(output: Path) -> None:
    image = Image.new("RGB", (1800, 1200), "white")
    draw = ImageDraw.Draw(image)
    title_font = font(62, bold=True)
    header_font = font(43, bold=True)
    cell_font = font(36)

    draw.text((100, 80), "文档OCR助手 Windows ONNX 验证", fill="#111827", font=title_font)
    draw.text((100, 175), "PP-OCRv6 Medium + SLANet-plus", fill="#334155", font=font(38))

    xs = [100, 560, 1140, 1700]
    ys = [300, 420, 550, 680, 810]
    line_width = 6
    draw.rectangle((xs[0], ys[0], xs[-1], ys[-1]), outline="#111827", width=line_width)
    for y in ys[1:-1]:
        start_x = xs[1] if y == ys[2] else xs[0]
        draw.line((start_x, y, xs[-1], y), fill="#111827", width=line_width)
    for x in xs[1:-1]:
        draw.line((x, ys[1], x, ys[-1]), fill="#111827", width=line_width)

    centered(draw, (xs[0], ys[0], xs[-1], ys[1]), "Windows OCR Table / 合并单元格", header_font)
    centered(draw, (xs[0], ys[1], xs[1], ys[-1]), "ONNX Engine", header_font)
    centered(draw, (xs[1], ys[1], xs[2], ys[2]), "Model", header_font)
    centered(draw, (xs[2], ys[1], xs[3], ys[2]), "Status", header_font)
    centered(draw, (xs[1], ys[2], xs[2], ys[3]), "PP-OCRv6 Medium", cell_font)
    centered(draw, (xs[2], ys[2], xs[3], ys[3]), "PASS", cell_font)
    centered(draw, (xs[1], ys[3], xs[2], ys[4]), "SLANet-plus", cell_font)
    centered(draw, (xs[2], ys[3], xs[3], ys[4]), "PASS", cell_font)

    draw.text((100, 920), "TXT + Markdown offline output", fill="#334155", font=font(42))
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    create_image(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
