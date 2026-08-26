# Kylin x86_64 与 ARM64 Docker 打包说明

本文说明如何生成 Kylin V10 的 x86_64 图形完整版和 ARM64 命令行版。两个架构不能交叉复用冻结程序、LibreOffice 或压缩工具；PyInstaller 必须在目标架构的 Linux 容器中运行。

## 产物区别

| 目标 | Docker 平台 | 产物 | 界面 | Office 组件 |
| --- | --- | --- | --- | --- |
| Kylin V10 x86_64 | `linux/amd64` | `document-ocr-assistant-0.2.0-kylin-v10-x86_64-full.run` | PySide6 图形界面和 CLI | 离线组件目录中的 LibreOffice 7.6 x86_64 |
| Kylin V10 ARM64 | `linux/arm64` | `document-ocr-assistant-0.2.0-kylin-v10-arm64-cli-full.run` | 仅 CLI，没有桌面窗口 | Kylin ARM64 仓库中的 LibreOffice 6.0.6.1 |

ARM64 当前是命令行版。双击 `.run` 不会出现图形窗口，应在终端执行 `./文件名.run --version` 或传入待识别文件。

## 通用要求

1. Docker Desktop 或 Docker Engine 已启动，并至少预留 12 GB 磁盘和 8 GB 内存。
2. 源码路径和输出磁盘应支持单个 2 GB 以上文件。
3. 首次构建 builder 镜像需要访问 Kylin 软件仓库、Python 官方下载和 PyPI；最终应用运行不需要联网。
4. 发布前必须在目标架构容器或真机执行最终 `.run --version`。只测试解压前的 `dist/.../app` 目录不能发现自解压头问题。

仓库的 `.gitattributes` 已强制所有 `.sh` 和 Dockerfile 使用 LF。若从旧的 Windows 工作区复制源码，请先确认 Shell 脚本不是 CRLF，否则容器会出现 `$'do\r'` 或 `bad interpreter` 错误。

可先确认 Docker 实际架构：

```bash
docker run --rm --platform linux/amd64 macrosan/kylin:v10-sp1 uname -m
# 预期：x86_64

docker run --rm --platform linux/arm64 macrosan/kylin:v10-sp1 uname -m
# 预期：aarch64
```

如果输出与预期不符，不要继续打包。Apple Silicon Mac 构建 x86_64 时会使用 Docker 的 amd64 模拟，速度明显慢于 ARM64 原生构建。

## x86_64 离线组件

x86_64 完整版需要一个不提交到 Git 的 `offline_components` 目录，至少包含：

```text
offline_components/
├── rapidocr-ppocrv6-medium/
│   ├── PP-OCRv6_det_medium.onnx
│   ├── PP-OCRv6_rec_medium.onnx
│   └── ch_ppocr_mobile_v2.0_cls_mobile.onnx
├── LibreOffice_7.6.7.2_Linux_x86-64_deb.tar.gz
├── LibreOffice_7.6.7.2_Linux_x86-64_deb_langpack_zh-CN.tar.gz
├── rarlinux-x64-723.tar.gz
└── 7z2602-linux-x64.tar.xz
```

构建脚本会校验 PP-OCRv6 Medium、SLANet-plus、页面方向模型和 LibreOffice 文件。完全断网重复构建前，还应保留源码下的：

```text
.build-cache/slanet-plus.onnx
.build-cache/orientation/rapid_orientation.onnx
```

## 在 macOS、Windows Docker 或 Linux 上构建 x86_64

先拉取 amd64 Kylin V10 基础镜像：

```bash
docker pull --platform linux/amd64 macrosan/kylin:v10-sp1
```

设置离线组件的绝对路径，然后运行统一脚本：

```bash
cd /absolute/path/document-ocr-assistant
export KYLIN_X86_64_OFFLINE_COMPONENTS=/absolute/path/offline_components
bash scripts/build_kylin_x86_64_docker.sh --edition full
```

脚本会：

1. 以 `linux/amd64` 构建 `docker/kylin-x86_64/Dockerfile`；
2. 运行单元测试并冻结 PySide6 客户端；
3. 装入 PP-OCRv6 Medium、SLANet-plus、方向模型、LibreOffice、UnRAR 和 7-Zip；
4. 测试 ONNX OCR、合并单元格表格、四向旋转、DOCX 转换和 offscreen GUI；
5. 在干净目录执行最终 `.run --cli --version`，确认自解压入口和架构元数据。

输出位于：

```text
dist/document-ocr-assistant-0.2.0-kylin-v10-x86_64-full.run
dist/SHA256SUMS-kylin-x86_64-full.txt
```

在 Kylin x86_64 真机验证：

```bash
chmod +x document-ocr-assistant-0.2.0-kylin-v10-x86_64-full.run
./document-ocr-assistant-0.2.0-kylin-v10-x86_64-full.run --cli --version
# 预期包含：(full, kylin-v10, x86_64)

# 启动图形界面
./document-ocr-assistant-0.2.0-kylin-v10-x86_64-full.run
```

## 在 Kylin x86_64 真机直接构建

真机构建需要 Python 3.10—3.12、`binutils`、编译工具和 Qt/XCB 运行库。准备好离线组件后执行：

```bash
export OCR_OFFLINE_COMPONENTS=/absolute/path/offline_components
export PYTHON_BIN=/absolute/path/python3.12
export OCR_BUILD_VENV=/absolute/path/ocr-build-venv
bash scripts/build_kylin_offline.sh --edition full
```

推荐使用 Docker 脚本，因为它固定了 Kylin V10、Python 和依赖版本，并自动执行最终 `.run` 验证。

## 在 Apple Silicon Mac 上构建 ARM64

```bash
docker pull --platform linux/arm64 macrosan/kylin:v10-sp1
cd /absolute/path/document-ocr-assistant
bash scripts/build_kylin_arm64_docker.sh --edition full
```

输出为：

```text
dist/document-ocr-assistant-0.2.0-kylin-v10-arm64-cli-full.run
dist/SHA256SUMS-kylin-arm64-full.txt
```

在 Kylin ARM64 真机中从终端测试；当前版本不会弹出 GUI：

```bash
chmod +x document-ocr-assistant-0.2.0-kylin-v10-arm64-cli-full.run
./document-ocr-assistant-0.2.0-kylin-v10-arm64-cli-full.run --version
# 预期包含：(full, kylin-v10, arm64)

./document-ocr-assistant-0.2.0-kylin-v10-arm64-cli-full.run input.pdf -o ./ocr-output
```

## 常见故障

- `.run` 立即退出：先在终端运行并查看错误；确认已 `chmod +x`，再用 `uname -m` 核对架构。
- ARM64 双击没有窗口：ARM64 产物目前是 CLI 版，这是预期行为。
- `Exec format error`：构建容器架构错误，x86_64 与 ARM64 文件不能混用。
- `GLIBC_x.y not found`：构建基础系统比目标系统新；必须使用 Kylin V10 基础镜像重新冻结。
- Qt 报 XCB 库缺失：在 Kylin 桌面安装系统的 `libxkbcommon-x11`、`xcb-util`、`xcb-util-image`、`xcb-util-keysyms`、`xcb-util-renderutil`、`xcb-util-wm` 和 `mesa-libGL`。
- Office 转换失败：确认使用 `full` 版，且 LibreOffice 的 CPU 架构与目标机器一致。
- Docker 中构建成功、真机失败：不要只复制解压目录；应在真机先运行最终 `.run --version`，并用 `sha256sum -c` 校验下载文件。
