# 文档OCR助手 v0.2.0

本版本新增页面 0°/90°/180°/270° 自动旋正、普通文本行 0°/180° 分类、OCR 流水线预设与高级参数、PDF 页码范围，以及图片/PDF 与文字框联动的审校界面。竖排文字识别和竖排阅读顺序不在本版本范围内。

本次更新将转换排版的默认值改为“原始结果”，并兼容迁移旧版设置。PDF 的 TXT 和 Markdown 默认不再附带页码；如需页码，可在“高级设置”中勾选“输出页码”。Kylin ARM64 版同时修复了从桌面等中文路径启动时 PyInstaller/PySide2 的 Latin-1 编码异常。

软件支持两种 edition：

- OCR 版：只处理图片、PDF、文件夹和包含这些文件的压缩包，不携带任何 Office 转换组件。
- 完整版：在 OCR 功能之外处理 DOC/DOCX/WPS；Office 依赖策略随平台而异。

当前 Release 只保留各平台的完整版。Kylin V10 ARM64 包已重构为与 x86_64 版本一致的图形完整版，同时保留命令行入口，并携带 Kylin V10 可用的 LibreOffice 6.0.6.1。

当前资产及 SHA-256：

- `document-ocr-assistant-0.2.0-macos-arm64-full.dmg`：`05ea77277162906b29770cbbd24ac63b23835da0c43822405ee1e716de839a8a`
- `document-ocr-assistant-0.2.0-windows-x86_64-full.zip`：`14cfcbddfd0de36ae40d96544946530c206d91960cd081a13b7a74f12c30ec4e`
- `document-ocr-assistant-0.2.0-kylin-v10-x86_64-full.run`：`57179ac44ca7595a9d6826c5262a920a0a522830689e1ec09eb1f9a918f80ae8`
- `document-ocr-assistant-0.2.0-kylin-v10-arm64-full.run`：`9ca12a501296cafbb969b9f24b1e4a8e064e47f15d48731d6029e7f7f79b34b1`

## macOS 安装

1. 下载 macOS arm64 完整版 DMG。
2. 打开 DMG，将应用拖入 `Applications`。
3. 首次启动若提示来源未知，请到“系统设置 → 隐私与安全性”确认打开。
4. 截图识别需要“录屏与系统录音”权限；授权后完全退出并重新打开应用。
5. macOS 完整版不携带 LibreOffice，DOC/DOCX/WPS 转换需要系统已安装 LibreOffice。

## Kylin ARM64 使用

ARM64 包包含图形界面和命令行。请在终端中完成首次验证：

```bash
chmod +x document-ocr-assistant-0.2.0-kylin-v10-arm64-full.run
./document-ocr-assistant-0.2.0-kylin-v10-arm64-full.run --cli --version
./document-ocr-assistant-0.2.0-kylin-v10-arm64-full.run
```
