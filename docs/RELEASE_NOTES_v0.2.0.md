# 文档OCR助手 v0.2.0

本版本新增页面 0°/90°/180°/270° 自动旋正、普通文本行 0°/180° 分类、OCR 流水线预设与高级参数、PDF 页码范围，以及图片/PDF 与文字框联动的审校界面。竖排文字识别和竖排阅读顺序不在本版本范围内。

发行版分为两种：

- OCR 版：只处理图片、PDF、文件夹和包含这些文件的压缩包，不携带任何 Office 转换组件。
- 完整版：在 OCR 功能之外处理 DOC/DOCX/WPS；Office 依赖策略随平台而异。

本次先发布 macOS arm64 和 Kylin V10 ARM64 CLI 的 OCR 版与完整版，共 4 个主程序包。Windows x86_64 和 Kylin V10 x86_64 的程序包将在完成原生环境构建与验证后追加到同一 Release。

当前资产及 SHA-256：

- `document-ocr-assistant-0.2.0-macos-arm64-ocr.dmg`：`271f1a32a646b3971e1d3241c78b721ab4e2a34a1b85f5cff1aeb5ee18ad154e`
- `document-ocr-assistant-0.2.0-macos-arm64-full.dmg`：`d4d6335f033d996db33e3608d68e3468f05652e498fe0ceb714db7cadada02f0`
- `document-ocr-assistant-0.2.0-kylin-v10-arm64-cli-ocr.run`：`d50863b30b89449d03be8a7836f469f2642b84add15edb61f1b692911d74711f`
- `document-ocr-assistant-0.2.0-kylin-v10-arm64-cli-full.run`：`7f6b82cc204a350f57e70cf8049fb7806da005b74a001545f607a57b2d35a901`

## macOS 安装

1. 下载所需 edition 的 macOS arm64 DMG。
2. 打开 DMG，将应用拖入 `Applications`。
3. 首次启动若提示来源未知，请到“系统设置 → 隐私与安全性”确认打开。
4. 截图识别需要“录屏与系统录音”权限；授权后完全退出并重新打开应用。
5. macOS 完整版不携带 LibreOffice，DOC/DOCX/WPS 转换需要系统已安装 LibreOffice。

macOS OCR 版和完整版使用不同的应用名称与 Bundle ID，可以同时安装。
