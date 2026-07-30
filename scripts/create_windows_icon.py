#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import os
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Render the SVG application icon as Windows ICO")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PIL import Image
    from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QRectF
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    application = QGuiApplication.instance() or QGuiApplication([])
    renderer = QSvgRenderer(str(args.source.resolve()))
    if not renderer.isValid():
        raise RuntimeError(f"Invalid SVG: {args.source}")
    canvas = QImage(256, 256, QImage.Format.Format_ARGB32)
    canvas.fill(0)
    painter = QPainter(canvas)
    renderer.render(painter, QRectF(0, 0, 256, 256))
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    canvas.save(buffer, "PNG")
    buffer.close()
    image = Image.open(io.BytesIO(bytes(data))).convert("RGBA")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(
        args.output,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    application.processEvents()
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

