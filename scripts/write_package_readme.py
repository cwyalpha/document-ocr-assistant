#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def office_text(platform_name: str, edition: str) -> str:
    if edition == "ocr":
        return "本包为 OCR 版，仅处理图片和 PDF，不包含 LibreOffice、pywin32 或 Word/WPS 转换组件。"
    return {
        "macos": "本包为完整版；DOC/DOCX/WPS 转换需要系统安装 LibreOffice，应用会自动检测。",
        "windows": "本包为完整版；DOC/DOCX/WPS 转换调用本机 Microsoft Word 或 WPS Office。",
        "kylin-x86_64": "本包为完整版；随包携带固定版本并校验哈希的 LibreOffice 7.6.x。",
        "kylin-arm64": "本包为完整版；随包携带已验证的 Kylin ARM64 LibreOffice 6.0.6.1。",
    }[platform_name]


def main() -> int:
    parser = argparse.ArgumentParser(description="Write edition-specific package instructions")
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--platform", choices=("macos", "windows", "kylin-x86_64", "kylin-arm64"), required=True
    )
    parser.add_argument("--edition", choices=("ocr", "full"), required=True)
    args = parser.parse_args()
    edition_name = "OCR版" if args.edition == "ocr" else "完整版"
    lines = [
        f"文档OCR助手 {edition_name}",
        "",
        "OCR 使用 PP-OCRv6 Medium，支持页面 0°/90°/180°/270°旋正和普通文本行 0°/180°分类。",
        "图片、扫描 PDF、表格和可搜索 PDF 均在本机离线处理。",
        office_text(args.platform, args.edition),
    ]
    if args.platform == "macos":
        lines += [
            "",
            "安装方法：",
            "1. 打开 DMG，把应用拖到 Applications 文件夹。",
            "2. 首次启动若提示来源未知，在“系统设置 → 隐私与安全性”中确认打开。",
            "3. 截图识别需要“录屏与系统录音”权限；授权后完全退出并重新启动应用。",
            "4. 本构建仅支持 Apple Silicon arm64（M 系列 Mac）。",
        ]
    elif args.platform == "kylin-x86_64":
        executable = "文档OCR助手OCR版" if args.edition == "ocr" else "文档OCR助手完整版"
        lines += [
            "",
            f"图形界面：解压完整 tar.gz 后，双击根目录中的“{executable}”。",
            f"命令行：./{executable} --cli input.pdf -o ./ocr-output",
            "快捷方式：运行“安装快捷方式.sh”，会在当前用户的应用菜单中创建入口。",
            "便携使用：整个解压目录可移动；不能只复制主程序，必须保留 _internal、models、bin、assets 等附件目录。",
            "本构建仅支持 Kylin V10 x86_64，同时包含图形界面和命令行工具。",
        ]
    elif args.platform == "kylin-arm64":
        executable = "文档OCR助手OCR版" if args.edition == "ocr" else "文档OCR助手完整版"
        lines += [
            "",
            f"图形界面：解压完整 tar.gz 后，双击根目录中的“{executable}”。",
            f"命令行：./{executable} --cli input.pdf -o ./ocr-output",
            "快捷方式：运行“安装快捷方式.sh”，会在当前用户的应用菜单和桌面中创建入口。",
            "便携使用：整个解压目录可移动；不能只复制主程序，必须保留 _internal、models、bin、assets 等附件目录。",
            "本构建仅支持 Kylin V10 ARM64，同时包含图形界面和命令行工具。",
        ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
