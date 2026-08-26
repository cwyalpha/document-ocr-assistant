# 文档OCR助手 v0.2.0

本版本新增页面 0°/90°/180°/270° 自动旋正、普通文本行 0°/180° 分类、OCR 流水线预设与高级参数、PDF 页码范围，以及图片/PDF 与文字框联动的审校界面。竖排文字识别和竖排阅读顺序不在本版本范围内。

软件支持两种 edition：

- OCR 版：只处理图片、PDF、文件夹和包含这些文件的压缩包，不携带任何 Office 转换组件。
- 完整版：在 OCR 功能之外处理 DOC/DOCX/WPS；Office 依赖策略随平台而异。

当前 Release 只保留各平台的完整版。Kylin V10 ARM64 CLI 包已使用最新部署脚本重新构建，修复旧包在 `pipefail` 模式下因读取归档目录名触发 SIGPIPE、导致自解压提前退出的问题。

当前资产及 SHA-256：

- `document-ocr-assistant-0.2.0-macos-arm64-full.dmg`：`d4d6335f033d996db33e3608d68e3468f05652e498fe0ceb714db7cadada02f0`
- `document-ocr-assistant-0.2.0-windows-x86_64-full.zip`：`14cfcbddfd0de36ae40d96544946530c206d91960cd081a13b7a74f12c30ec4e`
- `document-ocr-assistant-0.2.0-kylin-v10-x86_64-full.run`：`57179ac44ca7595a9d6826c5262a920a0a522830689e1ec09eb1f9a918f80ae8`
- `document-ocr-assistant-0.2.0-kylin-v10-arm64-cli-full.run`：`afcedfe7ee5c8819ef0b94a6467a8c29c4e0f5bfa34673a51a25ea2db24caf19`

## macOS 安装

1. 下载 macOS arm64 完整版 DMG。
2. 打开 DMG，将应用拖入 `Applications`。
3. 首次启动若提示来源未知，请到“系统设置 → 隐私与安全性”确认打开。
4. 截图识别需要“录屏与系统录音”权限；授权后完全退出并重新打开应用。
5. macOS 完整版不携带 LibreOffice，DOC/DOCX/WPS 转换需要系统已安装 LibreOffice。

## Kylin ARM64 使用

ARM64 包为命令行完整版，不包含图形界面。请在终端中执行：

```bash
chmod +x document-ocr-assistant-0.2.0-kylin-v10-arm64-cli-full.run
./document-ocr-assistant-0.2.0-kylin-v10-arm64-cli-full.run --version
./document-ocr-assistant-0.2.0-kylin-v10-arm64-cli-full.run input.pdf -o ./ocr-output
```
