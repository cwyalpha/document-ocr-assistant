from __future__ import annotations

import argparse
import getpass
import sys
import threading
from pathlib import Path

from .inputs import collect_passthrough_files, expand_inputs
from .models import OutputMode, PdfMode, ProcessingOptions
from .outputs import copy_passthrough_files
from .pipeline import ProcessingPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="文档OCR助手命令行处理器（用于测试与自动化）")
    parser.add_argument("inputs", nargs="+", help="图片、PDF、Word、文件夹或压缩包")
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    items, unsupported = expand_inputs(args.inputs)
    passthrough_files = collect_passthrough_files(args.inputs, unsupported)
    passthrough_sources = {item.source_path for item in passthrough_files}
    for path in unsupported:
        if path in passthrough_sources and args.copy_unconverted and not args.alongside_source:
            continue
        print(f"[跳过] 不支持：{path}", file=sys.stderr)
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
    )
    pipeline = ProcessingPipeline()
    task_failures = 0
    copy_failed = False

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
    print(f"处理完成：成功 {len(items) - task_failures}，失败 {task_failures}")
    return 1 if task_failures or copy_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
