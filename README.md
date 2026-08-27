# 文档OCR助手

文档OCR助手是一款面向图片、扫描 PDF 和办公文档的本地离线 OCR 工具。它以 PP-OCRv6 Medium 为核心，提供批量识别、页面方向旋正、表格解析、可搜索 PDF、结果审校和截图识别；文件和识别结果始终留在本机，无需上传到云端。

[下载最新版](https://github.com/cwyalpha/document-ocr-assistant/releases/latest) · [查看 Releases](https://github.com/cwyalpha/document-ocr-assistant/releases)

![文档OCR助手批量识别界面](docs/images/macos-main-window.png)

## 主要功能

- **批量导入**：支持文件、文件夹和常见压缩包，可连续处理多张图片或多份文档，并保留来源层级输出结果。
- **扫描 PDF OCR**：能够识别没有文本层、无法搜索和复制的扫描 PDF；也可自动判断原生文本 PDF、强制 OCR 或仅提取已有文本。
- **PDF 页码清理**：可选移除页顶、页底的中英文或横线包围页码，并利用位置和跨页序列降低 OCR 误识别造成的误删。
- **可搜索 PDF**：在原页面上写入透明文字层，识别后的扫描件可搜索、选择和复制文字。
- **页面方向检测**：自动检测并旋正整页 0°、90°、180°、270°，也可关闭或手动指定角度；支持普通文本行 0°/180° 分类。
- **表格识别**：使用 SLANet-plus 分析表格结构，输出 Markdown 表格，并尽量保留合并单元格。
- **识别审校**：逐页预览图片或 PDF，叠加 OCR 文本框；整理文本、原始文本、Markdown 和识别信息可切换查看，支持修改、复制和重新识别。
- **低置信度提示**：低置信度文本框以不同颜色标记，便于快速定位可能需要人工确认的内容。
- **截图识别**：通过按钮或全局快捷键框选屏幕区域，识别后可编辑、复制，并保留本地历史记录。
- **多种排版方式**：提供多栏自然段、多栏逐行、单栏自然段、单栏逐行、保留缩进和原始结果。
- **流水线预设**：内置快速、均衡、精度优先和自定义预设；高级设置可调整 PDF DPI、图像边长、检测阈值、框扩张、识别置信度、批次和 CPU 线程。
- **完整版 Office 转换**：除图片和 PDF 外，还可处理 DOC、DOCX、WPS 文档。
- **图形界面与命令行**：桌面端适合日常操作，命令行模式便于批处理和脚本调用。

## PDF 页码清理

“移除 PDF 原有页码”位于批量识别页的高级设置中，默认关闭。开启后，程序会从原始文本、整理文本、TXT、Markdown、OCR 预览框和可搜索 PDF 的隐藏文字层中移除页顶或页底的页码，但不会涂改 PDF 页面上肉眼可见的内容。

- 支持裸数字、`第 1 页`、`Page 1`、`Page 1 of 20`、`1 / 20`，以及 `- 1 -`、`—1-`、`- 1—` 等左右横线不同、空格不对称的形式。
- 会结合页码位置和跨页递增关系判断；期刊第一页从 101、102 等任意数字开始也能识别，不要求从 1 开始。
- 对 `I/l/|/丨 → 1`、`O/o/〇 → 0` 等常见 OCR 错误进行保守纠正，并利用连续性降低误删风险。
- 不将 `(1)`、`[1]`、`【1】` 等括号数字作为页码，以避免误删正文引用和脚注。
- 命令行可使用 `--remove-pdf-page-numbers` 开启；可同时使用 `--include-page-numbers`，先移除原页码，再添加统一的“第 N 页”标记。

## 界面预览

### 截图识别

![文档OCR助手截图识别界面](docs/images/macos-screenshot-ocr.png)

### OCR 与隐私设置

![文档OCR助手设置界面](docs/images/macos-settings.png)

以上截图基于 macOS 版生成，其他桌面平台的功能布局一致。

## 支持的输入与输出

| 类型 | 支持内容 |
| --- | --- |
| 图片 | JPG、JPEG、JFIF、PNG、WebP、BMP、TIF、TIFF |
| PDF | 原生文本 PDF、混合 PDF、无文本层扫描 PDF、指定页码范围 |
| Office（完整版） | DOC、DOCX、WPS |
| 压缩包 | ZIP、RAR、7Z、TAR、TAR.GZ、TGZ |
| 输出 | TXT、Markdown、可搜索 PDF、识别报告 |

## 支持的系统

| 系统 | 架构 | 使用方式 |
| --- | --- | --- |
| macOS 12 或更高版本 | Apple Silicon arm64 | 图形界面、命令行 |
| Windows 10 / 11 | x86_64 | 图形界面、命令行 |
| Kylin V10 | x86_64 | 图形界面、命令行 |
| Kylin V10 | ARM64 / aarch64 | 图形界面、命令行 |

Windows x86 和 Kylin x86 均指 64 位 x86_64，不提供 32 位版本。

## 识别引擎与隐私

- 文字识别：RapidOCR 3.9.1 + PP-OCRv6 Medium ONNX
- 文本行方向：PaddleOCR 0°/180° 分类模型
- 页面方向：固定版本的四方向 ONNX 模型
- 表格结构：SLANet-plus ONNX
- 推理运行时：ONNX Runtime（CPU）
- 隐私：OCR、表格分析、排版整理和文档转换均在本机完成

当前支持整页四方向旋正和普通横排文本行方向分类，不包含竖排文字识别或竖排阅读顺序重排。

## 下载

[前往 GitHub Releases 下载最新版](https://github.com/cwyalpha/document-ocr-assistant/releases/latest)

请根据 Releases 页面中的系统和架构名称选择程序包，并在下载后核对随 Release 提供的 SHA-256 校验值。
