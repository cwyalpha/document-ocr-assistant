# 统信 UOS V20 ARM64 构建与验收

该版本以 `macrosan/uos:v20-1060` 的原生 `linux/arm64` 镜像为构建和最终验收环境，目标系统为统信 UOS V20 ARM64（glibc 2.28）。发布包同时包含：

- Qt 5.15.2 / PySide2 5.15.2.1 图形界面；
- PP-OCRv6 Medium 图片与 PDF OCR；
- 页面方向和 SLANet-plus 表格模型；
- LibreOffice 6.4.7.2 Writer 及其运行依赖；
- 应用菜单和桌面快捷方式安装脚本。

## 构建

在 Apple Silicon Mac 上运行：

```bash
docker pull --platform linux/arm64 macrosan/uos:v20-1060
./scripts/build_uos_arm64_docker.sh
```

如需使用兼容的其他 UOS V20 ARM64 基础镜像，可设置 `UOS_ARM64_BASE_IMAGE`。Docker Desktop 至少应分配 8 GB 内存。

产物：

```text
dist/document-ocr-assistant-0.2.0-uos-v20-arm64-full.tar.gz
dist/SHA256SUMS-uos-arm64-full.txt
```

## 自动验收范围

构建脚本先在 builder 容器内运行单元测试并冻结应用，然后在全新的 UOS 基础容器中把最终 tar.gz 解压到含中文和空格的路径，验证：

1. 主程序是 `aarch64` ELF，平台元数据为 `uos-v20, arm64`；
2. offscreen GUI 能生成非空截图；
3. PP-OCRv6 Medium 能识别合成图片；
4. 页面方向、表格模型和 OCR 流水线可运行；
5. 随包 LibreOffice 能实际完成 DOCX 转换；
6. 快捷方式中的程序路径和图标路径正确。

## 使用

把 tar.gz 完整解压到 UOS ARM64 机器，不要只复制主程序：

```bash
chmod +x 文档OCR助手完整版 安装快捷方式.sh
./文档OCR助手完整版
```

命令行 OCR：

```bash
./文档OCR助手完整版 --cli input.pdf -o ./ocr-output
```
