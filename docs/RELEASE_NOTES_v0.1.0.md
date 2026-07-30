# 文档OCR助手 v0.1.0

首个公开源码与程序包版本。

## 本次提供

### macOS Apple Silicon

- `文档OCR助手-macos-arm64.dmg`：推荐安装包。
- `文档OCR助手-macos-arm64.zip`：免 DMG 目录压缩包。
- `SHA256SUMS-macos-arm64.txt`：macOS 包校验值。

要求 macOS 12 或更高版本，仅支持 M1/M2/M3/M4/M5 等 Apple Silicon Mac。安装方法见 README 的“安装 macOS Apple Silicon 版”。

当前 macOS 包使用 ad-hoc 签名，未做 Apple 公证。首次启动如被系统拦截，请进入“系统设置 → 隐私与安全性”，在安全提示处选择“仍要打开”。

### Kylin V10 ARM64

- `文档OCR助手-kylin-v10-arm64-cli.run`：推荐的自解压命令行包。
- `文档OCR助手-kylin-v10-arm64-cli.tar.gz`：目录压缩包。
- `SHA256SUMS-kylin-arm64.txt`：Kylin ARM64 包校验值。

ARM64 包已在原生 `macrosan/kylin:v10-sp1` aarch64 容器中验证 PP-OCRv6 图片 OCR、TXT/Markdown 输出、随包 LibreOffice 6.0.6.1 和 DOCX 转换。该版本为命令行版，不包含图形界面。

## 后续资产

Windows x86_64 和 Kylin x86_64 程序包后续可继续上传到本 Release。

## 发布内容审计

源码仓库和 Release 程序包均未包含实际用户/业务测试文档。自动测试输入由脚本合成，位于被忽略的构建目录，不随源码或程序包发布。
