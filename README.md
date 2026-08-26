# 文档OCR助手

文档OCR助手是一款本地离线 OCR 工具，支持 macOS、Windows 和 Kylin。图片、扫描 PDF、表格及常见办公文档均可在本机完成识别和整理，无需上传文件。

## 功能介绍

- 使用 PP-OCRv6 Medium 识别中英文图片与扫描 PDF，包括无法复制文字、没有文本层的 PDF。
- 自动检测并旋正 0°/90°/180°/270° 页面，支持普通文本行 0°/180° 方向分类。
- 提供快速、均衡、精度优先和自定义流水线设置，以及 PDF 页码范围和多种排版模式。
- 批量识别支持图片/PDF 与文字框对照审校、低置信度标记、分页预览和重新识别。
- 提供仅处理图片/PDF 的 OCR 版，以及额外支持 DOC/DOCX/WPS 的完整版。
- 使用 SLANet-plus 识别表格结构，并保留复杂表格中的合并单元格。
- 输出 TXT、Markdown，可按需生成带文字层的可搜索 PDF。
- 支持截图 OCR、结果编辑与复制、历史记录、系统托盘和浅色/深色界面。
- OCR 和表格识别均在本机离线运行，文档不会上传到网络。

## 软件截图

![文档OCR助手 macOS 界面](docs/images/macos-main-window.png)

## 下载

[前往 GitHub Releases 下载最新版](https://github.com/cwyalpha/document-ocr-assistant/releases/latest)

各平台当前可用的软件包及版本说明以 Releases 页面为准。

Kylin 的 Docker 构建、离线组件和真机验证方法见
[`packaging/Kylin-x86_64和ARM64-Docker打包说明.md`](packaging/Kylin-x86_64和ARM64-Docker打包说明.md)。
