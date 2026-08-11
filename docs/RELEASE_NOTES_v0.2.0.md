# 文档OCR助手 v0.2.0

本版本新增页面 0°/90°/180°/270° 自动旋正、普通文本行 0°/180° 分类、OCR 流水线预设与高级参数、PDF 页码范围，以及图片/PDF 与文字框联动的审校界面。竖排文字识别和竖排阅读顺序不在本版本范围内。

发行版分为两种：

- OCR 版：只处理图片、PDF、文件夹和包含这些文件的压缩包，不携带任何 Office 转换组件。
- 完整版：在 OCR 功能之外处理 DOC/DOCX/WPS；Office 依赖策略随平台而异。

本 Release 包含 macOS arm64、Windows x86_64、Kylin V10 x86_64、Kylin V10 ARM64 CLI 四个平台的 OCR 版和完整版，共 8 个主程序包。请使用同一 Release 内的 `SHA256SUMS.txt` 校验下载文件。

## macOS 安装

1. 下载所需 edition 的 macOS arm64 DMG。
2. 打开 DMG，将应用拖入 `Applications`。
3. 首次启动若提示来源未知，请到“系统设置 → 隐私与安全性”确认打开。
4. 截图识别需要“录屏与系统录音”权限；授权后完全退出并重新打开应用。
5. macOS 完整版不携带 LibreOffice，DOC/DOCX/WPS 转换需要系统已安装 LibreOffice。

macOS OCR 版和完整版使用不同的应用名称与 Bundle ID，可以同时安装。
