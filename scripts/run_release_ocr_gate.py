#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import fitz
from PIL import Image


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real PP-OCRv6 orientation/PDF release gate")
    parser.add_argument("materials", type=Path)
    parser.add_argument("--ocr-models", type=Path, required=True)
    parser.add_argument("--orientation-model", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    os.environ["DOCUMENT_OCR_MODELS"] = str(args.ocr_models.resolve())
    os.environ["DOCUMENT_OCR_ORIENTATION_MODEL"] = str(args.orientation_model.resolve())

    from document_ocr_assistant.models import InputItem, InputKind, PageOrientation, PdfMode, ProcessingOptions
    from document_ocr_assistant.processors import DocumentProcessors

    processors = DocumentProcessors()
    options = ProcessingOptions(
        table_detection=False,
        page_orientation=PageOrientation.AUTO,
        orientation_confidence=0.35,
        textline_orientation=True,
        text_score=0.3,
    )
    expected = {0: 0, 90: 270, 180: 180, 270: 90}
    rotations: list[dict[str, object]] = []
    for source_angle, correction in expected.items():
        path = args.materials / f"orientation-{source_angle}.png"
        result = processors.process(InputItem(path, InputKind.IMAGE), options)
        page = result.metadata["pages"][0]
        if page["applied_angle"] != correction:
            raise SystemExit(
                f"方向检测错误：{path.name} expected={correction} actual={page['applied_angle']}"
            )
        if "OCR" not in result.text and "Document" not in result.text:
            raise SystemExit(f"未识别出方向测试关键字：{path.name}: {result.text!r}")
        with Image.open(path) as image:
            width, height = image.size
        for block in result.blocks:
            for x, y in block.polygon:
                if not (-1 <= x <= width and -1 <= y <= height):
                    raise SystemExit(f"框坐标未映射回原图：{path.name}: {(x, y)} / {(width, height)}")
        rotations.append(
            {
                "file": path.name,
                "source_angle": source_angle,
                "applied_angle": page["applied_angle"],
                "confidence": page["orientation_confidence"],
                "blocks": len(result.blocks),
            }
        )

    scanned = args.materials / "scanned-no-text-layer.pdf"
    with fitz.open(scanned) as document:
        if document[0].get_text().strip():
            raise SystemExit("不可复制 PDF 测试源意外含文本层")
    pdf_options = ProcessingOptions(
        pdf_mode=PdfMode.FORCE_OCR,
        searchable_pdf=True,
        table_detection=False,
        page_orientation=PageOrientation.AUTO,
        text_score=0.3,
    )
    pdf_result = processors.process(InputItem(scanned, InputKind.PDF), pdf_options)
    if not pdf_result.searchable_pdf_bytes:
        raise SystemExit("不可复制 PDF 未生成可搜索 PDF")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    searchable_path = args.report.parent / "searchable-output.pdf"
    searchable_path.write_bytes(pdf_result.searchable_pdf_bytes)
    with fitz.open(searchable_path) as document:
        extracted = "".join(page.get_text() for page in document)
    if "OCR" not in extracted and "Document" not in extracted:
        raise SystemExit(f"PP-OCRv6 文本层不可搜索/复制：{extracted!r}")
    args.report.write_text(
        json.dumps(
            {
                "rotations": rotations,
                "scanned_pdf_source_native_text": False,
                "searchable_pdf_text": extracted,
                "searchable_pdf_blocks": len(pdf_result.blocks),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
