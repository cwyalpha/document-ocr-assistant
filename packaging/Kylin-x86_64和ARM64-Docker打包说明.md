# Kylin x86_64 与 ARM64 Docker 打包说明

本文说明如何生成 Kylin V10 的 x86_64 与 ARM64 图形完整版。两个架构不能交叉复用冻结程序、Qt、LibreOffice 或压缩工具；PyInstaller 必须在目标架构的 Linux 容器中运行。

## 产物区别

| 目标 | Docker 平台 | 当前产物 | 界面 | Office 组件 |
| --- | --- | --- | --- | --- |
| Kylin V10 x86_64 | `linux/amd64` | `document-ocr-assistant-0.2.0-kylin-v10-x86_64-full.tar.gz` 绿色目录版 | 根目录原生程序、PySide6 图形界面和 CLI | 离线组件目录中的 LibreOffice 7.6 x86_64 |
| Kylin V10 ARM64 | `linux/arm64` | `document-ocr-assistant-0.2.0-kylin-v10-arm64-full.tar.gz` 绿色目录版 | 根目录原生程序、Qt 5.15 / PySide2 图形界面和 CLI | Kylin ARM64 仓库中的 LibreOffice 6.0.6.1 |

ARM64 使用在 Kylin V10 容器内源码构建的 Qt 5.15.2 与 PySide2 5.15.2.1，以保持 glibc 2.28 兼容；程序同时提供图形界面和命令行入口。

## 通用要求

1. Docker Desktop 或 Docker Engine 已启动，并至少预留 12 GB 磁盘和 8 GB 内存。
2. 源码路径和输出磁盘应支持单个 2 GB 以上文件。
3. 首次构建 builder 镜像需要访问 Kylin 软件仓库、Python 官方下载和 PyPI；最终应用运行不需要联网。
4. 发布前必须在目标架构容器或真机解压最终发布文件，并执行其中的主程序 `--cli --version`；不能只测试 PyInstaller 的临时输出目录。

仓库的 `.gitattributes` 已强制所有 `.sh` 和 Dockerfile 使用 LF。若从旧的 Windows 工作区复制源码，请先确认 Shell 脚本不是 CRLF，否则容器会出现 `$'do\r'` 或 `bad interpreter` 错误。

可先确认 Docker 实际架构：

```bash
docker run --rm --platform linux/amd64 macrosan/kylin:v10-sp1 uname -m
# 预期：x86_64

docker run --rm --platform linux/arm64 macrosan/kylin:v10-sp1 uname -m
# 预期：aarch64
```

如果输出与预期不符，不要继续打包。Apple Silicon Mac 构建 x86_64 时会使用 Docker 的 amd64 模拟，速度明显慢于 ARM64 原生构建。

## 绿色目录版固定结构

x86_64 和 ARM64 均采用以下结构，只有 CPU 架构、Qt 版本和 LibreOffice 来源不同：

```text
document-ocr-assistant-0.2.0-kylin-v10-<arch>-full/
├── 文档OCR助手完整版          # 根目录原生 ELF 主程序，同时提供 GUI 和 --cli
├── _internal/                 # PyInstaller 运行库，build-info.json 也在这里
├── models/
│   ├── ppocrv6-medium/        # PP-OCRv6 Medium ONNX
│   ├── table/                 # SLANet-plus ONNX
│   └── orientation/           # 页面方向 ONNX
├── bin/
│   ├── libreoffice/           # full 版离线 Office 转换组件
│   ├── unrar/                 # 解压工具；实际子结构按架构构建脚本为准
│   └── ...
├── assets/
│   └── app-icon.svg
├── 安装快捷方式.sh
└── 使用说明.txt
```

固定规则：

1. 主程序直接位于压缩包总目录根部，不能再放入 `app/<程序名>/`。
2. 不再依赖 `启动文档OCR助手.sh`、`文档OCR助手命令行.sh` 或自解压头；GUI 和 CLI 都直接调用根目录主程序。
3. `_internal`、`models`、`bin`、`assets` 必须与主程序一起移动，主程序不能脱离附件目录单独复制。
4. `build-info.json` 使用 PyInstaller onedir 的 `_internal/build-info.json`，不要在根目录再放一份重复文件。
5. 发布物使用保留一个总目录的 `.tar.gz`；不要在 macOS 主机上重新打包 Linux 目录，也不要用 `.zip` 代替，否则容易丢失 ELF 和 Shell 脚本的执行权限。
6. `ocr` 版不得包含 LibreOffice；`full` 版必须实际执行一次 DOCX 转换，不能只检查 `soffice` 文件存在。

PyInstaller onedir 输出必须整体平铺到发布目录根部。关键命令为：

```bash
PACKAGE_ROOT="$ROOT/dist/$PACKAGE_NAME"
mkdir -p "$PACKAGE_ROOT"
cp -a "$PYI_DIST/$APP_NAME/." "$PACKAGE_ROOT/"
rm -rf "$PYI_DIST/$APP_NAME"
chmod +x "$PACKAGE_ROOT/$APP_NAME" "$PACKAGE_ROOT/安装快捷方式.sh"
```

必须使用 `cp -a source/. destination/`。末尾的 `/.` 会复制目录内容及隐藏文件，同时保留 Linux 权限；不要把整个 PyInstaller 输出目录复制成新的嵌套层级。

ARM64 原脚本把 Qt 图形运行库复制到 `app/$APP_NAME/_internal`。改为绿色结构后，相同文件必须复制到：

```bash
cp -L "$source_library" "$PACKAGE_ROOT/_internal/$qt_runtime_library"
```

## UTF-8、中文目录和空格处理

构建、归档和验收都在 Kylin Linux 容器内完成。Docker 启动构建命令时建议明确设置：

```bash
docker run --rm \
  --platform linux/amd64 \
  -e LANG=C.UTF-8 \
  -e LC_ALL=C.UTF-8 \
  -e PYTHONUTF8=1 \
  -e PYTHONIOENCODING=UTF-8 \
  ...
```

ARM64 将 `linux/amd64` 改为 `linux/arm64`。先在容器内运行 `locale -a` 确认 `C.UTF-8` 可用；如果镜像只提供 `zh_CN.UTF-8`，则统一改用该 locale。不要只在 macOS 主机设置 locale，因为真正执行 PyInstaller 和 tar 的是容器。

所有 Shell 路径变量都必须使用双引号，包括 `ROOT`、`PACKAGE_ROOT`、主程序、模型路径、输出目录和 Docker 挂载源。不要使用 `for file in $(find ...)` 处理文件名，也不要依赖按空格分词。

创建压缩包及检查中文文件名时使用 GNU tar：

```bash
ARCHIVE_FILE="$ROOT/dist/$PACKAGE_NAME.tar.gz"
tar -czf "$ARCHIVE_FILE" -C "$ROOT/dist" "$PACKAGE_NAME"

# Kylin 的最小 C locale 可能把中文显示成八进制转义；必须请求原样清单。
ARCHIVE_NAMES="$(tar --quoting-style=literal -tzf "$ARCHIVE_FILE")"
grep -Fxq "$PACKAGE_NAME/文档OCR助手完整版" <<<"$ARCHIVE_NAMES"
grep -Fxq "$PACKAGE_NAME/_internal/build-info.json" <<<"$ARCHIVE_NAMES"
```

`tar -tzf` 在 `LC_ALL=C` 下可能把 `文档OCR助手完整版` 显示为 `\346\226...`。这只是清单的转义显示，不代表归档乱码；如果直接用普通 `grep`，会误报“缺少主程序”。使用 `--quoting-style=literal` 后再进行精确匹配。

归档前至少检查：

```bash
test -x "$PACKAGE_ROOT/文档OCR助手完整版"
test -f "$PACKAGE_ROOT/_internal/build-info.json"
test ! -e "$PACKAGE_ROOT/app"
if find "$PACKAGE_ROOT" -maxdepth 1 -type f -name '启动*.sh' | grep -q .; then
  echo "绿色版不应依赖启动脚本" >&2
  exit 1
fi
```

最终归档必须解压到同时包含中文和空格的新目录再测试，不能只测试构建目录：

```bash
PORTABLE_TEST="/tmp/KOS/桌面/文档 OCR 绿色版测试"
mkdir -p "$PORTABLE_TEST"
tar -xzf "$ARCHIVE_FILE" -C "$PORTABLE_TEST"
PACKAGE_ROOT="$PORTABLE_TEST/$PACKAGE_NAME"
MAIN_EXECUTABLE="$PACKAGE_ROOT/文档OCR助手完整版"

test -x "$MAIN_EXECUTABLE"
file "$MAIN_EXECUTABLE"
"$MAIN_EXECUTABLE" --cli --version
INSTALL_HOME="$PORTABLE_TEST/install-home"
DESKTOP_DIR="$INSTALL_HOME/桌面"
mkdir -p "$DESKTOP_DIR"
DOCUMENT_OCR_INSTALL_HOME="$INSTALL_HOME" \
DOCUMENT_OCR_DESKTOP_DIR="$DESKTOP_DIR" \
  "$PACKAGE_ROOT/安装快捷方式.sh"
QT_QPA_PLATFORM=offscreen \
  DOCUMENT_OCR_UI_SMOKE_SCREENSHOT="$PORTABLE_TEST/gui.png" \
  "$MAIN_EXECUTABLE"
test -s "$PORTABLE_TEST/gui.png"
```

还必须从这个解压目录执行 OCR、页面方向、表格和 DOCX 转换。这样才能同时发现 PyInstaller 中文路径、Qt 插件相对路径、LibreOffice 子进程库路径以及快捷方式 `Exec=` 引号问题。

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
5. 在带中文和空格的干净目录解压最终 tar.gz，测试根目录主程序、OCR、Office、快捷方式、offscreen GUI 和架构元数据。

输出位于：

```text
dist/document-ocr-assistant-0.2.0-kylin-v10-x86_64-full.tar.gz
```

在 Kylin x86_64 真机验证：

```bash
tar -xzf document-ocr-assistant-0.2.0-kylin-v10-x86_64-full.tar.gz
cd document-ocr-assistant-0.2.0-kylin-v10-x86_64-full
chmod +x 文档OCR助手完整版 安装快捷方式.sh
./文档OCR助手完整版 --cli --version
# 预期包含：(full, kylin-v10, x86_64)

# 启动图形界面
./文档OCR助手完整版

# 可选：创建当前用户的应用菜单和桌面入口
./安装快捷方式.sh
```

## 在 Kylin x86_64 真机直接构建

真机构建需要 Python 3.10—3.12、`binutils`、编译工具和 Qt/XCB 运行库。准备好离线组件后执行：

```bash
export OCR_OFFLINE_COMPONENTS=/absolute/path/offline_components
export PYTHON_BIN=/absolute/path/python3.12
export OCR_BUILD_VENV=/absolute/path/ocr-build-venv
bash scripts/build_kylin_offline.sh --edition full
```

推荐使用 Docker 脚本，因为它固定了 Kylin V10、Python 和依赖版本，并自动解压最终 tar.gz 验证绿色目录版。

## 在 Apple Silicon Mac 上构建 ARM64

ARM64 构建脚本已经与 x86_64 绿色目录方案对齐。先拉取 ARM64 基础镜像，再运行统一脚本：

```bash
docker pull --platform linux/arm64 macrosan/kylin:v10-sp1
cd /absolute/path/document-ocr-assistant
bash scripts/build_kylin_arm64_docker.sh --edition full
```

输出为：

```text
dist/document-ocr-assistant-0.2.0-kylin-v10-arm64-full.tar.gz
dist/SHA256SUMS-kylin-arm64-full.txt
```

脚本会在 ARM64 builder 容器中冻结 PySide2 客户端、装入模型与 LibreOffice，并生成保留 Linux 权限的 tar.gz。随后使用全新的 Kylin ARM64 基础容器，将最终压缩包解压到 `/tmp/KOS/桌面/文档 OCR 绿色版测试`，直接从含中文和空格的路径验证：

- PP-OCRv6 Medium 图片 OCR；
- 0/90/180/270° 页面方向；
- SLANet-plus 表格；
- 随包 ARM64 LibreOffice 的 `--headless --version` 和 DOCX 转换；
- `安装快捷方式.sh` 同时生成应用菜单和桌面入口，并确认 `Exec=".../文档OCR助手完整版"` 对中文空格路径有引号；
- `LANG=C` 下的版本命令和 `QT_QPA_PLATFORM=offscreen` GUI 截图。

在 Kylin ARM64 真机中完整解压后使用：

```bash
tar -xzf document-ocr-assistant-0.2.0-kylin-v10-arm64-full.tar.gz
cd document-ocr-assistant-0.2.0-kylin-v10-arm64-full
chmod +x 文档OCR助手完整版 安装快捷方式.sh
./文档OCR助手完整版 --cli --version
# 预期包含：(full, kylin-v10, arm64)
./文档OCR助手完整版

# 可选：一键创建应用菜单和桌面快捷方式
./安装快捷方式.sh
```

## 常见故障

- x86_64 主程序不能执行：确认完整解压 tar.gz、主程序具有执行权限，并用 `uname -m` 确认系统为 `x86_64`；不要只复制主程序文件。
- ARM64 旧 `.run` 立即退出：改用当前 tar.gz 绿色目录版，并完整解压后从根目录运行主程序。
- ARM64 双击没有窗口：在终端直接运行解压目录根部主程序查看 Qt/XCB 报错，并确认当前会话是 Kylin 图形桌面而非纯终端环境。
- `Exec format error`：构建容器架构错误，x86_64 与 ARM64 文件不能混用。
- `GLIBC_x.y not found`：构建基础系统比目标系统新；必须使用 Kylin V10 基础镜像重新冻结。
- Qt 报 XCB 库缺失：在 Kylin 桌面安装系统的 `libxkbcommon-x11`、`xcb-util`、`xcb-util-image`、`xcb-util-keysyms`、`xcb-util-renderutil`、`xcb-util-wm` 和 `mesa-libGL`。
- Office 转换失败：确认使用 `full` 版，且 LibreOffice 的 CPU 架构与目标机器一致。
- Docker 中构建成功、真机失败：应在真机完整解压最终发布文件，并直接运行包内主程序 `--cli --version`；同时核对发布页提供的 SHA-256。
