#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="0.2.0"
EDITION="full"
if [ "${1:-}" = "--edition" ]; then
  EDITION="${2:-}"
  shift 2
fi
if [ "$EDITION" != "full" ]; then
  echo "[error] Kylin ARM64 当前只构建带图形界面和 LibreOffice 的 full 版本。" >&2
  exit 2
fi
BUILDER_IMAGE="${KYLIN_ARM64_BUILDER_IMAGE:-document-ocr-kylin-arm64-gui-builder:latest}"
BASE_IMAGE="${KYLIN_ARM64_BASE_IMAGE:-macrosan/kylin:v10-sp1}"
PACKAGE_NAME="document-ocr-assistant-$VERSION-kylin-v10-arm64-$EDITION"
ARCHIVE_FILE="$ROOT/dist/$PACKAGE_NAME.tar.gz"

if [ "$(uname -s)" != "Darwin" ] || [ "$(uname -m)" != "arm64" ]; then
  echo "[error] 本脚本用于 Apple Silicon Mac 上的 ARM64 Docker 构建。" >&2
  exit 2
fi
if ! docker info >/dev/null 2>&1; then
  echo "[error] Docker Desktop 未运行。" >&2
  exit 2
fi
if ! docker image inspect "$BASE_IMAGE" >/dev/null 2>&1; then
  echo "[error] 请先拉取 ARM64 Kylin 镜像：docker pull --platform linux/arm64 $BASE_IMAGE" >&2
  exit 2
fi

docker build \
  --platform linux/arm64 \
  --pull=false \
  -f "$ROOT/docker/kylin-arm64/Dockerfile" \
  -t "$BUILDER_IMAGE" \
  "$ROOT"

docker run --rm \
  --platform linux/arm64 \
  -e DOCUMENT_OCR_BUILD_EDITION="$EDITION" \
  -e LANG=C.UTF-8 \
  -e LC_ALL=C.UTF-8 \
  -e PYTHONUTF8=1 \
  -e PYTHONIOENCODING=UTF-8 \
  -v "$ROOT:/workspace" \
  "$BUILDER_IMAGE" \
  /bin/bash /workspace/scripts/build_kylin_arm64_inside.sh

docker run --rm \
  --platform linux/arm64 \
  -e DOCUMENT_OCR_PACKAGE_NAME="$PACKAGE_NAME" \
  -e DOCUMENT_OCR_EDITION="$EDITION" \
  -v "$ROOT:/workspace:ro" \
  "$BASE_IMAGE" \
  /bin/bash -lc '
set -euo pipefail
TESTS="/workspace/build/kylin-arm64/tests"
PORTABLE_TEST="/tmp/KOS/桌面/文档 OCR 绿色版测试"
mkdir -p "$PORTABLE_TEST"
tar -xzf "/workspace/dist/$DOCUMENT_OCR_PACKAGE_NAME.tar.gz" -C "$PORTABLE_TEST"
PACKAGE_ROOT="$PORTABLE_TEST/$DOCUMENT_OCR_PACKAGE_NAME"
APP_NAME="文档OCR助手完整版"
MAIN_EXECUTABLE="$PACKAGE_ROOT/$APP_NAME"

test "$(uname -m)" = "aarch64"
test -x "$MAIN_EXECUTABLE"
test -f "$PACKAGE_ROOT/_internal/build-info.json"
test ! -e "$PACKAGE_ROOT/app"
if find "$PACKAGE_ROOT" -maxdepth 1 -type f -name "启动*.sh" | grep -q .; then
  echo "[error] ARM64 绿色版不应依赖启动脚本。" >&2
  exit 1
fi
VERSION_OUTPUT="$(LC_ALL=C LANG=C "$MAIN_EXECUTABLE" --cli --version)"
if [[ "$VERSION_OUTPUT" != *"($DOCUMENT_OCR_EDITION, kylin-v10, arm64)"* ]]; then
  echo "[error] ARM64 绿色版解压或版本验证失败：$VERSION_OUTPUT" >&2
  exit 1
fi

"$MAIN_EXECUTABLE" --cli \
  "$TESTS/kylin-arm64-ocr.png" \
  -o "$PORTABLE_TEST/ocr-output" \
  --no-table
grep -R -q "Kylin ARM64" "$PORTABLE_TEST/ocr-output"

for angle in 0 90 180 270; do
  case "$angle" in
    0) correction=0 ;;
    90) correction=270 ;;
    180) correction=180 ;;
    270) correction=90 ;;
  esac
  "$MAIN_EXECUTABLE" --cli "$TESTS/materials/orientation-$angle.png" \
    -o "$PORTABLE_TEST/orientation-$angle" \
    --report-json "$PORTABLE_TEST/orientation-$angle.json" --no-table
  grep -R -Eq "Document|OCR" "$PORTABLE_TEST/orientation-$angle"
  grep -q "\"applied_angle\": $correction" "$PORTABLE_TEST/orientation-$angle.json"
done

DOCUMENT_OCR_PIPELINE_SMOKE_INPUT="$TESTS/materials/table.png" \
DOCUMENT_OCR_PIPELINE_SMOKE_OUTPUT="$PORTABLE_TEST/table-result.json" \
  "$MAIN_EXECUTABLE"
grep -Eq "\"ocr_blocks\": [1-9][0-9]*" "$PORTABLE_TEST/table-result.json"
grep -Eq "\"tables\": [1-9][0-9]*" "$PORTABLE_TEST/table-result.json"

"$PACKAGE_ROOT/bin/libreoffice/program/soffice" --headless --version \
  > "$PORTABLE_TEST/libreoffice-version.txt"
grep -q "LibreOffice 6.0.6.1" "$PORTABLE_TEST/libreoffice-version.txt"
"$MAIN_EXECUTABLE" --cli \
  "$TESTS/kylin-arm64-office.docx" \
  -o "$PORTABLE_TEST/office-output" \
  --no-table
grep -R -q "Kylin ARM64 LibreOffice bundled conversion test" "$PORTABLE_TEST/office-output"

INSTALL_HOME="$PORTABLE_TEST/install-home"
DESKTOP_DIR="$INSTALL_HOME/桌面"
mkdir -p "$DESKTOP_DIR"
DOCUMENT_OCR_INSTALL_HOME="$INSTALL_HOME" \
DOCUMENT_OCR_DESKTOP_DIR="$DESKTOP_DIR" \
  "$PACKAGE_ROOT/安装快捷方式.sh"
MENU_FILE="$INSTALL_HOME/.local/share/applications/document-ocr-assistant-$DOCUMENT_OCR_EDITION.desktop"
DESKTOP_FILE="$DESKTOP_DIR/文档OCR助手 完整版.desktop"
test -x "$MENU_FILE"
test -x "$DESKTOP_FILE"
grep -Fq "Exec=\"$MAIN_EXECUTABLE\"" "$MENU_FILE"
grep -Fq "Icon=$PACKAGE_ROOT/assets/app-icon.svg" "$MENU_FILE"

LC_ALL=C LANG=C \
DOCUMENT_OCR_UI_SMOKE_SCREENSHOT="$PORTABLE_TEST/gui.png" \
QT_QPA_PLATFORM=offscreen "$MAIN_EXECUTABLE"
test -s "$PORTABLE_TEST/gui.png"
'

test -s "$ARCHIVE_FILE"
echo "[done] Kylin ARM64 绿色版在中文和空格路径完成 GUI、CLI、OCR、方向、表格、Office 和桌面快捷方式测试。"
echo "[done] 发布包：$ARCHIVE_FILE"
