# Kylin V10 ARM64 命令行构建与测试记录

测试日期：2026-07-30（Asia/Shanghai）

## 环境

- 宿主：Apple Silicon Mac（arm64）
- Docker：Docker Desktop 4.68.0，Linux ARM64 引擎
- 基础镜像：`macrosan/kylin:v10-sp1`
- 镜像系统：Kylin Linux Advanced Server V10 (Tercel)
- 容器架构：aarch64
- glibc：2.28
- 构建 Python：3.12.13（在 Kylin ARM64 容器内由源码构建）
- PyInstaller：6.18.0
- ONNX Runtime：1.23.2
- OCR：PP-OCRv6 Medium
- Office：Kylin 官方 ARM64 LibreOffice 6.0.6.1 补丁版
- RAR：Kylin 官方 ARM64 unrar 5.8.3

## 产物

| 产物 | 文件大小 | SHA-256 |
| --- | ---: | --- |
| `文档OCR助手-kylin-v10-arm64-cli.tar.gz` | 424 MiB | `8cbf9f94e127afc3beb4746fb5e93d5766ef4dc0ba60b149a4ae8d1abcec2a45` |
| `文档OCR助手-kylin-v10-arm64-cli.run` | 424 MiB | `6bf7cb677160b2b81e744bea0a7c93c5d6db1f824ec51f65310f17b9301a3323` |

未压缩目录约 1.0 GiB。主程序和随包 unrar 均经 `file` 确认为原生 ARM aarch64 ELF。

## 自动化与构建测试

- ARM64 命令行相关单测：18 项全部通过。
- `compileall`：`src`、`scripts`、`tests` 全部通过。
- PyInstaller onedir 冻结成功。
- PP-OCRv6 三个模型使用固定 SHA-256 校验后随包。
- LibreOffice 程序树和 225 个非 glibc 动态依赖随包，并通过便携路径启动。
- 最终 `.run` 资产在全新 Kylin ARM64 容器中自解压后完成图片 OCR，退出码为 0。

PyInstaller 日志中的 TensorRT 和 Torch 缺失提示符合预期：本项目只使用 ONNX Runtime，不打包 TensorRT、Torch、Paddle 或 VLM。

## 干净 Kylin ARM64 容器测试

成品构建后，另启动全新的 `macrosan/kylin:v10-sp1` 容器。该容器未安装 Python、OpenCV 或 LibreOffice，只挂载成品和脚本生成的合成测试输入。

### 图片 OCR 命令行

命令行客户端加载成品目录内的 `PP-OCRv6_det_medium.onnx`、`PP-OCRv6_rec_medium.onnx` 和方向分类模型，成功生成 TXT 与 Markdown。TXT 识别结果为：

```text
Kylin ARM64 PP-OCRv6 CLI Test

Offline OCR on aarch64

Document OCR Assistant 2026
```

退出码为 0，处理统计为成功 1、失败 0。

### 随包 LibreOffice

- `soffice --headless --version`：`LibreOffice 6.0.6.1 00(Build:1)`
- 合成 DOCX 经成品命令行客户端成功转换为 TXT 与 Markdown。
- 转换文字包含 `Kylin ARM64 LibreOffice bundled conversion test`。
- 退出码为 0，处理统计为成功 1、失败 0。

这项测试确认运行时使用的是成品内置 LibreOffice，而不是构建容器的系统安装。

## 图形界面限制

Kylin V10 SP1 使用 glibc 2.28。PySide6 6.8.3 的 Linux ARM64 官方 wheel 标记为 manylinux 2.39，不能在该系统可靠运行。因此本次 ARM64 产物明确为原生命令行版，不包含图形界面；没有用 x86 模拟或替换系统 glibc。

## 敏感测试文档审计

- OCR PNG 和 DOCX 均由项目脚本即时合成，只包含上述固定测试文字。
- 合成输入、识别结果、构建目录和缓存均被 `.gitignore` 排除，不进入源码仓库。
- TAR.GZ 与 `.run` 仅包含客户端、模型、Kylin/LibreOffice 运行组件、图标和使用说明；未包含合成 PDF、DOC、DOCX、WPS、XLSX 或 PPTX 测试文档。
- 源码候选文件中未发现私钥、GitHub token、AWS key 或本机用户绝对路径。

LibreOffice 自带的程序图像、模板和图库属于官方运行组件，并非用户或业务测试资料。
