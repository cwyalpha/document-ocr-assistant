# 文档OCR助手 v0.1.1

## 本次修复

- 修复 macOS 未开启“录屏与系统录音”权限时，截图遮罩显示黑屏、框选后没有识别结果的问题。
- 开始截图前主动检查并请求 macOS 录屏权限；未授权时保持主窗口可见，并提供系统设置入口。
- 增加纯黑截屏保护，避免把 macOS 权限异常返回的黑色画面传给 PP-OCRv6。

## 下载

- `document-ocr-assistant-macos-arm64.dmg`：macOS Apple Silicon 安装镜像。
- `document-ocr-assistant-macos-arm64.zip`：macOS Apple Silicon 便携压缩包。
- `document-ocr-assistant-kylin-v10-arm64-cli.run`：Kylin V10 ARM64 命令行自解压包。
- `document-ocr-assistant-kylin-v10-arm64-cli.tar.gz`：Kylin V10 ARM64 命令行目录压缩包。

## macOS 安装与截图权限

1. 打开 DMG，将“文档OCR助手.app”拖入“Applications”。
2. 首次启动若被 macOS 阻止，请到“系统设置 → 隐私与安全性”选择“仍要打开”。
3. 第一次使用截图识别时，按系统提示允许录屏。
4. 如果之前拒绝过权限，请到“系统设置 → 隐私与安全性 → 录屏与系统录音”开启“文档OCR助手”，然后完全退出并重新打开应用。

当前公开包使用 ad-hoc 签名。升级到新版本后，macOS 可能把它视为新的应用版本并要求重新开启录屏权限。

所有发布文件均可使用随 Release 提供的 `SHA256SUMS-v0.1.1.txt` 校验。
