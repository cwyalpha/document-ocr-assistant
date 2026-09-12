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
  echo "[error] UOS ARM64 当前只构建带图形界面和 LibreOffice 的 full 版本。" >&2
  exit 2
fi
BUILDER_IMAGE="${UOS_ARM64_BUILDER_IMAGE:-document-ocr-uos-arm64-gui-builder:latest}"
BASE_IMAGE="${UOS_ARM64_BASE_IMAGE:-macrosan/uos:v20-1060}"
PACKAGE_NAME="document-ocr-assistant-$VERSION-uos-v20-arm64-$EDITION"
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
  echo "[error] 请先拉取 ARM64 UOS 镜像：docker pull --platform linux/arm64 $BASE_IMAGE" >&2
  exit 2
fi

docker build \
  --platform linux/arm64 \
  --pull=false \
  --build-arg UOS_BASE_IMAGE="$BASE_IMAGE" \
  -f "$ROOT/docker/uos-arm64/Dockerfile" \
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
  /bin/bash /workspace/scripts/build_uos_arm64_inside.sh

docker run --rm \
  --platform linux/arm64 \
  -e DOCUMENT_OCR_PACKAGE_NAME="$PACKAGE_NAME" \
  -e DOCUMENT_OCR_EDITION="$EDITION" \
  -v "$ROOT:/workspace:ro" \
  "$BASE_IMAGE" \
  /bin/bash -lc '
set -euo pipefail
TESTS="/workspace/build/uos-arm64/tests"
PORTABLE_TEST="/tmp/UOS/桌面/文档 OCR 绿色版测试"
mkdir -p "$PORTABLE_TEST"
tar -xzf "/workspace/dist/$DOCUMENT_OCR_PACKAGE_NAME.tar.gz" -C "$PORTABLE_TEST"
PACKAGE_ROOT="$PORTABLE_TEST/$DOCUMENT_OCR_PACKAGE_NAME"
APP_NAME="文档OCR助手完整版"
MAIN_EXECUTABLE="$PACKAGE_ROOT/$APP_NAME"

test "$(uname -m)" = "aarch64"
test -x "$MAIN_EXECUTABLE"
test -f "$PACKAGE_ROOT/_internal/build-info.json"
VERSION_OUTPUT="$(LC_ALL=C LANG=C "$MAIN_EXECUTABLE" --cli --version)"
if [[ "$VERSION_OUTPUT" != *"($DOCUMENT_OCR_EDITION, uos-v20, arm64)"* ]]; then
  echo "[error] UOS ARM64 解压或版本验证失败：$VERSION_OUTPUT" >&2
  exit 1
fi

"$MAIN_EXECUTABLE" --cli "$TESTS/uos-arm64-ocr.png" \
  -o "$PORTABLE_TEST/ocr-output" --no-table
grep -R -q "UOS ARM64" "$PORTABLE_TEST/ocr-output"

DOCUMENT_OCR_PIPELINE_SMOKE_INPUT="$TESTS/materials/table.png" \
DOCUMENT_OCR_PIPELINE_SMOKE_OUTPUT="$PORTABLE_TEST/table-result.json" \
  "$MAIN_EXECUTABLE"
grep -Eq "\"ocr_blocks\": [1-9][0-9]*" "$PORTABLE_TEST/table-result.json"
grep -Eq "\"tables\": [1-9][0-9]*" "$PORTABLE_TEST/table-result.json"

"$PACKAGE_ROOT/bin/libreoffice/program/soffice" --headless --version \
  > "$PORTABLE_TEST/libreoffice-version.txt"
grep -q "LibreOffice 6.4.7.2" "$PORTABLE_TEST/libreoffice-version.txt"
"$MAIN_EXECUTABLE" --cli "$TESTS/uos-arm64-office.docx" \
  -o "$PORTABLE_TEST/office-output" --no-table
grep -R -q "UOS ARM64 LibreOffice bundled conversion test" "$PORTABLE_TEST/office-output"

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

LC_ALL=C LANG=C DOCUMENT_OCR_UI_SMOKE_SCREENSHOT="$PORTABLE_TEST/gui.png" \
QT_QPA_PLATFORM=offscreen "$MAIN_EXECUTABLE"
test -s "$PORTABLE_TEST/gui.png"
'

test -s "$ARCHIVE_FILE"
echo "[done] UOS ARM64 绿色版完成 GUI、OCR、表格、LibreOffice 和快捷方式验收。"
echo "[done] 发布包：$ARCHIVE_FILE"
