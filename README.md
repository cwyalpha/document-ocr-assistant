# 文档OCR助手

面向 Kylin V10 SP1 x86_64/ARM64、Windows x86_64 和 macOS Apple Silicon 的本地原生 OCR 客户端。同一套 PySide6 代码按平台选择系统集成，OCR 与表格结构识别统一使用 ONNX Runtime；应用运行时不联网，也不依赖 PaddlePaddle、PaddleOCR-VL 或浏览器服务。

## 功能

- 拖拽图片、PDF、DOC/DOCX/WPS、文件夹、ZIP/RAR/7Z/TAR/TAR.GZ/TGZ；目录和压缩包内层级会保留到输出目录。
- 批量识别可选“复制未转换文件”（默认关闭）；使用新建批次目录时，可将目录或压缩包内的 TXT、JSON、XLSX、PPT 等未转换文件按原层级原样复制到结果目录。
- ZIP 文件名自动兼容 UTF-8、Info-ZIP Unicode Path 与中文 Windows GBK/CP936；Windows 和 Kylin 使用一致的解码逻辑，特殊压缩包可通过 `DOCUMENT_OCR_ZIP_ENCODING` 指定编码。
- PP-OCRv6 Medium 中文/英文识别；PDF 支持自动判断、强制 OCR、仅提取文本以及可搜索 PDF。
- SLANet-plus ONNX 表格结构识别，可自动检测或关闭；普通表格输出 GFM Markdown，合并单元格等复杂表格输出内嵌 HTML。
- Kylin 的 DOC/DOCX/WPS 通过随包 LibreOffice 7.6.7.2 `--headless` 转换，不依赖系统安装；Windows 自动调用本机 Microsoft Word 或 WPS Office；macOS 自动调用 `/Applications/LibreOffice.app`（需用户另行安装）。
- 结果输出 TXT + Markdown，可放在源文件旁或新的时间批次目录。
- X11/Win32/macOS 全局快捷键截图 OCR；桌面画面冻结后可移动和八方向调整选框，确认后才识别，支持连续多次截图；另有结果编辑/复制/保存、最近 100 条历史和系统托盘。
- 关闭主窗口时可选择缩小到右下角、退出或取消；“记住本次选择”默认不勾选，已记住的行为可在设置页改回“每次询问”。
- 现代浅色/深色界面，适配 UKUI 与 Windows 的常用分辨率及缩放。

## 本地命令行验证

```bash
export PYTHONPATH="$PWD/src"
export DOCUMENT_OCR_ROOT=/path/to/prepared-runtime
python -m document_ocr_assistant.cli input.pdf -o ./ocr-output
```

关闭表格识别可加 `--no-table`，生成可搜索 PDF 可加 `--searchable-pdf`。新建批次目录时，加 `--copy-unconverted` 可原样复制目录及压缩包内未转换的文件。客户端入口为：

```bash
python -m document_ocr_assistant
```

## 离线组件

正式包使用 `localkb/tool_kylin_x86/offline_components` 中的以下内容：

- `LibreOffice_7.6.7.2_Linux_x86-64_deb.tar.gz` 及 zh-CN 语言包；
- `rapidocr-ppocrv6-medium/` 三个 ONNX 模型。
- `rarlinux-x64-*.tar.gz` 和 `7z*-linux-x64.tar.xz` 离线解压工具。

`scripts/prepare_offline_components.py` 直接解析 DEB，不调用 apt、dpkg、dnf 或 rpm，因此可在 RPM 系的 Kylin 上以普通用户目录部署。SLANet-plus 模型在构建阶段固定版本并校验 SHA-256，随后随安装包离线分发。

示例：

```bash
python scripts/prepare_offline_components.py \
  --components-dir /path/to/localkb/tool_kylin_x86/offline_components \
  --output-root /tmp/document-ocr-runtime \
  --table-model /path/to/slanet-plus.onnx
```

## 构建 Kylin 离线客户端

在 Kylin/Linux x86_64 的 Python 3.10—3.12 环境执行：

```bash
export OCR_OFFLINE_COMPONENTS=/path/to/localkb/tool_kylin_x86/offline_components
bash scripts/build_kylin_offline.sh
```

生成：

- `dist/文档OCR助手-linux-x86_64/`：可直接复制的目录包；
- `dist/文档OCR助手-linux-x86_64.run`：自解压启动包。

构建过程需要下载/安装 Python 构建依赖；生成后的客户端完全离线。若构建机也必须断网，预先准备 wheel 仓库并把已校验的 `slanet-plus.onnx` 路径传给 `DOCUMENT_OCR_TABLE_MODEL`。

## 构建 Kylin V10 ARM64 命令行客户端

在 Apple Silicon Mac 启动 Docker Desktop，并准备原生 ARM64 Kylin 镜像：

```bash
docker pull --platform linux/arm64 macrosan/kylin:v10-sp1
bash scripts/build_kylin_arm64_docker.sh
```

生成：

- `dist/文档OCR助手-kylin-v10-arm64-cli.tar.gz`：ARM64 目录压缩包；
- `dist/文档OCR助手-kylin-v10-arm64-cli.run`：ARM64 自解压命令行包。

ARM64 包内置 PP-OCRv6 Medium、SLANet-plus、Kylin 官方 ARM64 LibreOffice 6.0.6.1 和 unrar 5.8.3。构建脚本会在 `macrosan/kylin:v10-sp1` 原生 ARM64 容器中冻结程序，再放入全新 Kylin ARM64 容器测试图片 OCR、TXT/Markdown 输出、LibreOffice 版本和 DOCX 转换。

Kylin V10 SP1 使用 glibc 2.28，而 PySide6 的 Linux ARM64 官方 wheel 要求 glibc 2.39，因此当前 ARM64 Release 明确为原生命令行版，不包含图形界面。解压后使用：

```bash
./文档OCR助手命令行.sh input.pdf -o ./ocr-output
```

## 构建 Windows 离线客户端

在 Windows x86_64 PowerShell 中执行：

```powershell
.\scripts\build_windows.ps1
```

生成：

- `dist\文档OCR助手-windows-x86_64\`：双击 `启动文档OCR助手.bat` 即可运行；
- `dist\文档OCR助手-windows-x86_64.zip`：可复制到其他 Windows x86_64 机器使用；
- 安装 Inno Setup 6 时额外生成安装程序，未安装时仍会保留 `packaging\文档OCR助手.iss`。

Windows 版自动探测本机 Office：DOC/DOCX 默认优先 Microsoft Word，WPS 文件默认优先 WPS Office，某一引擎失败时自动尝试另一引擎。可用环境变量 `DOCUMENT_OCR_WINDOWS_OFFICE=word` 或 `wps` 固定转换引擎。构建会自动启动冻结后的 EXE，验证客户端截图以及 PP-OCRv6 Medium + SLANet-plus 合并单元格表格输出。

验证记录见 [Kylin x86 Docker 测试](docs/KYLIN_DOCKER_TEST.md)、[Kylin ARM64 Docker 测试](docs/KYLIN_ARM64_DOCKER_TEST.md)、[Windows 测试](docs/WINDOWS_TEST_REPORT.md) 和 [macOS 测试](docs/MACOS_TEST_REPORT.md)。

## 安装 macOS Apple Silicon 版

1. 从 GitHub Releases 下载 `document-ocr-assistant-macos-arm64.dmg`。该版本要求 macOS 12 或更高版本，仅支持 M1/M2/M3/M4/M5 等 Apple Silicon Mac，不支持 Intel Mac。
2. 双击打开 DMG，将“文档OCR助手.app”拖入其中的“Applications”快捷方式，然后推出安装镜像。
3. 首次启动时，由于当前公开包使用 ad-hoc 签名且未做 Apple 公证，macOS 可能阻止打开。进入“系统设置 → 隐私与安全性”，在安全提示处选择“仍要打开”，按系统提示确认后再次启动。
4. 第一次使用截图 OCR 时，在“系统设置 → 隐私与安全性 → 屏幕与系统音频录制”中允许“文档OCR助手”，然后重新启动应用。

图片、扫描 PDF、表格识别均可完全离线使用。DOC/DOCX/WPS 转换需另行安装 [LibreOffice for macOS](https://www.libreoffice.org/download/download-libreoffice/)，应用会自动查找 `/Applications/LibreOffice.app`。

## 构建 macOS Apple Silicon 客户端

在 Apple Silicon（arm64）Mac 的 Python 3.10—3.12 环境执行：

```bash
bash scripts/build_macos.sh
```

生成：

- `dist/文档OCR助手-macos-arm64/文档OCR助手.app`：标准 macOS App；
- `dist/文档OCR助手-macos-arm64.zip`：保留 App 签名和软链接的压缩包；
- `dist/文档OCR助手-macos-arm64.dmg`：带 Applications 快捷方式的安装镜像。

构建脚本会验证依赖锁定、源码测试、App 签名/结构、冻结 UI 启动、PP-OCRv6 Medium + SLANet-plus 合并单元格流水线，以及完全无文本层扫描 PDF 的 PP-OCRv6 识别和 TXT/Markdown 输出。本机构建无 Developer ID 证书时使用 ad-hoc 签名；公开分发前仍需 Developer ID 签名和 Apple 公证。

## 测试

```bash
python -m pytest -q
python -m compileall -q src scripts tests
```
