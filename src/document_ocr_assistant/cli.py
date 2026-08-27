from __future__ import annotations

import argparse
import getpass
import json
import sys
import threading
from pathlib import Path

from .edition import version_banner
from .inputs import collect_passthrough_files, expand_inputs, unsupported_reason
from .models import (
    LayoutMode,
    OcrPreset,
    OutputMode,
    PageOrientation,
    PdfMode,
    ProcessingOptions,
)
from .outputs import copy_passthrough_files
from .pipeline import ProcessingPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="文档OCR助手命令行处理器（用于测试与自动化）")
    parser.add_argument("inputs", nargs="*", help="图片、PDF、Word、文件夹或压缩包")
    parser.add_argument("--version", action="version", version=version_banner())
    parser.add_argument("-o", "--output", type=Path, default=Path.cwd() / "ocr-output", help="输出父目录")
    parser.add_argument(
        "--alongside-source", action="store_true", help="将结果写到源文件旁，而不是新批次目录"
    )
    parser.add_argument(
        "--pdf-mode", choices=[value.value for value in PdfMode], default=PdfMode.AUTO.value
    )
    parser.add_argument("--searchable-pdf", action="store_true")
    parser.add_argument("--no-table", action="store_true", help="关闭自动表格识别")
    parser.add_argument(
        "--copy-unconverted",
        action="store_true",
        help="新建批次目录时原样复制目录和压缩包内未转换的文件",
    )
    parser.add_argument("--archive-password", help="压缩包密码；省略时遇到加密包会交互输入")
    parser.add_argument(
        "--ocr-preset",
        choices=[value.value for value in OcrPreset],
        default=OcrPreset.BALANCED.value,
        help="OCR 参数预设；custom 使用下方高级参数",
    )
    parser.add_argument(
        "--page-orientation",
        choices=[value.value for value in PageOrientation],
        default=PageOrientation.AUTO.value,
        help="页面方向：auto/off/0/90/180/270",
    )
    parser.add_argument(
        "--orientation-confidence", type=float, default=0.35, metavar="0..1"
    )
    parser.add_argument(
        "--textline-orientation",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="启用普通文本行 0°/180° 分类",
    )
    parser.add_argument(
        "--layout-mode",
        choices=[value.value for value in LayoutMode],
        default=LayoutMode.RAW.value,
    )
    parser.add_argument(
        "--include-page-numbers",
        action="store_true",
        help="在 PDF 的 TXT 和 Markdown 输出中标注原始页码",
    )
    parser.add_argument(
        "--remove-pdf-page-numbers",
        action="store_true",
        help="从 PDF 的识别文字结果中自动移除原有页码",
    )
    parser.add_argument("--page-range", default="", help="PDF 页码，例如 1-3,5")
    parser.add_argument("--pdf-dpi", type=int, default=200)
    parser.add_argument("--max-side-len", type=int, default=2000)
    parser.add_argument("--det-limit-side-len", type=int, default=736)
    parser.add_argument("--det-limit-type", choices=("min", "max"), default="min")
    parser.add_argument("--det-thresh", type=float, default=0.3)
    parser.add_argument("--det-box-thresh", type=float, default=0.5)
    parser.add_argument("--det-unclip-ratio", type=float, default=1.6)
    parser.add_argument("--text-score", type=float, default=0.5)
    parser.add_argument("--rec-batch-size", type=int, default=6)
    parser.add_argument("--cpu-threads", type=int, default=0)
    parser.add_argument(
        "--report-json",
        type=Path,
        help="写入机器可读的识别元数据报告（用于自动化测试）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.inputs:
        print("没有可处理的输入。", file=sys.stderr)
        return 2
    items, unsupported = expand_inputs(args.inputs)
    passthrough_files = collect_passthrough_files(args.inputs, unsupported)
    passthrough_sources = {item.source_path for item in passthrough_files}
    for path in unsupported:
        if path in passthrough_sources and args.copy_unconverted and not args.alongside_source:
            continue
        print(f"[跳过] {unsupported_reason(path)}：{path}", file=sys.stderr)
    if not items and not (passthrough_files and args.copy_unconverted and not args.alongside_source):
        print("没有可处理的输入。", file=sys.stderr)
        return 2
    options = ProcessingOptions(
        output_mode=OutputMode.ALONGSIDE_SOURCE if args.alongside_source else OutputMode.NEW_BATCH_DIRECTORY,
        output_parent=args.output,
        pdf_mode=PdfMode(args.pdf_mode),
        searchable_pdf=args.searchable_pdf,
        table_detection=not args.no_table,
        copy_unconverted_files=args.copy_unconverted,
        layout_mode=args.layout_mode,
        include_page_numbers=args.include_page_numbers,
        remove_pdf_page_numbers=args.remove_pdf_page_numbers,
        ocr_preset=OcrPreset(args.ocr_preset),
        page_orientation=PageOrientation(args.page_orientation),
        orientation_confidence=args.orientation_confidence,
        textline_orientation=args.textline_orientation,
        pdf_dpi=args.pdf_dpi,
        max_side_len=args.max_side_len,
        det_limit_side_len=args.det_limit_side_len,
        det_limit_type=args.det_limit_type,
        det_thresh=args.det_thresh,
        det_box_thresh=args.det_box_thresh,
        det_unclip_ratio=args.det_unclip_ratio,
        text_score=args.text_score,
        rec_batch_size=args.rec_batch_size,
        cpu_threads=args.cpu_threads,
        page_range=args.page_range,
    )
    pipeline = ProcessingPipeline()
    task_failures = 0
    copy_failed = False
    reports: list[dict[str, object]] = []

    def password_provider(path: Path) -> str | None:
        return args.archive_password or getpass.getpass(f"请输入 {path.name} 的密码：")

    for index, item in enumerate(items, start=1):
        print(f"[{index}/{len(items)}] {item.display_path}")

        def progress(value: int, message: str) -> None:
            print(f"  {value:3d}% {message}")

        try:
            saved = pipeline.process_item(
                item,
                options,
                progress=progress,
                cancelled=threading.Event(),
                password_provider=password_provider,
            )
            for result in saved:
                reports.append(
                    {
                        "input": item.display_path,
                        "text": result.result.text,
                        "blocks": len(result.result.blocks),
                        "metadata": result.result.metadata,
                        "warnings": result.result.warnings,
                    }
                )
                for output in result.outputs:
                    print(f"  -> {output}")
                for warning in result.result.warnings:
                    print(f"  [警告] {warning}")
        except Exception as exc:
            task_failures += 1
            print(f"  [失败] {exc}", file=sys.stderr)
    try:
        copied = copy_passthrough_files(passthrough_files, options)
        for output in copied:
            print(f"  -> [原样复制] {output}")
    except Exception as exc:
        copy_failed = True
        print(f"  [复制失败] {exc}", file=sys.stderr)
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(
            json.dumps(reports, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(f"处理完成：成功 {len(items) - task_failures}，失败 {task_failures}")
    return 1 if task_failures or copy_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
