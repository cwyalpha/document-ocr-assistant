#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="0.2.0"
EDITION="full"
if [ "${1:-}" = "--edition" ]; then
  EDITION="${2:-}"
  shift 2
fi
if [ "$EDITION" != "ocr" ] && [ "$EDITION" != "full" ]; then
  echo "[error] --edition 必须为 ocr 或 full。" >&2
  exit 2
fi

BUILDER_IMAGE="${KYLIN_X86_64_BUILDER_IMAGE:-document-ocr-kylin-x86_64-builder:latest}"
BASE_IMAGE="${KYLIN_X86_64_BASE_IMAGE:-macrosan/kylin:v10-sp1}"
COMPONENTS_DIR="${KYLIN_X86_64_OFFLINE_COMPONENTS:-$ROOT/offline_components}"
PACKAGE_NAME="document-ocr-assistant-$VERSION-kylin-v10-x86_64-$EDITION"
ARCHIVE_FILE="$ROOT/dist/$PACKAGE_NAME.tar.gz"

if ! docker info >/dev/null 2>&1; then
  echo "[error] Docker Desktop 或 Docker Engine 未运行。" >&2
  exit 2
fi
if [ ! -d "$COMPONENTS_DIR" ]; then
  echo "[error] 找不到 Kylin x86_64 离线组件目录：$COMPONENTS_DIR" >&2
  echo "        可设置 KYLIN_X86_64_OFFLINE_COMPONENTS=/absolute/path/offline_components" >&2
  exit 2
fi
COMPONENTS_DIR="$(cd "$COMPONENTS_DIR" && pwd)"

if ! docker image inspect "$BASE_IMAGE" >/dev/null 2>&1; then
  echo "[error] 请先拉取 Kylin x86_64 镜像：docker pull --platform linux/amd64 $BASE_IMAGE" >&2
  exit 2
fi

docker build \
  --platform linux/amd64 \
  --pull=false \
  -f "$ROOT/docker/kylin-x86_64/Dockerfile" \
  -t "$BUILDER_IMAGE" \
  "$ROOT"

docker run --rm \
  --platform linux/amd64 \
  -e OCR_OFFLINE_COMPONENTS=/offline_components \
  -e OCR_BUILD_VENV=/opt/build-venv \
  -e PYTHON_BIN=/opt/python312/bin/python3.12 \
  -v "$ROOT:/workspace" \
  -v "$COMPONENTS_DIR:/offline_components:ro" \
  "$BUILDER_IMAGE" \
  /bin/bash /workspace/scripts/build_kylin_offline.sh --edition "$EDITION"

docker run --rm \
  --platform linux/amd64 \
  -e DOCUMENT_OCR_PACKAGE_NAME="$PACKAGE_NAME" \
  -e DOCUMENT_OCR_EDITION="$EDITION" \
  -v "$ROOT:/workspace:ro" \
  "$BUILDER_IMAGE" \
  /bin/bash -lc '
set -euo pipefail
test "$(uname -m)" = "x86_64"
PORTABLE_TEST="/tmp/文档 OCR 绿色版测试"
mkdir -p "$PORTABLE_TEST"
tar -xzf "/workspace/dist/$DOCUMENT_OCR_PACKAGE_NAME.tar.gz" -C "$PORTABLE_TEST"
PACKAGE_ROOT="$PORTABLE_TEST/$DOCUMENT_OCR_PACKAGE_NAME"
APP_NAME="文档OCR助手OCR版"
if [ "$DOCUMENT_OCR_EDITION" = "full" ]; then APP_NAME="文档OCR助手完整版"; fi
MAIN_EXECUTABLE="$PACKAGE_ROOT/$APP_NAME"
test -x "$MAIN_EXECUTABLE"
test -f "$PACKAGE_ROOT/_internal/build-info.json"
test ! -e "$PACKAGE_ROOT/app"
RUN_VERSION="$("$MAIN_EXECUTABLE" --cli --version)"
if [[ "$RUN_VERSION" != *"($DOCUMENT_OCR_EDITION, kylin-v10, x86_64)"* ]]; then
  echo "[error] x86_64 绿色版解压或版本验证失败：$RUN_VERSION" >&2
  exit 1
fi
"$MAIN_EXECUTABLE" --cli "/workspace/build/kylin-x86_64/smoke-$DOCUMENT_OCR_EDITION/ocr.png" \
  -o "$PORTABLE_TEST/ocr-output" --no-table
grep -R -Eq "Document|OCR|Table" "$PORTABLE_TEST/ocr-output"
if [ "$DOCUMENT_OCR_EDITION" = "full" ]; then
  "$MAIN_EXECUTABLE" --cli "/workspace/build/kylin-x86_64/smoke-$DOCUMENT_OCR_EDITION/office.docx" \
    -o "$PORTABLE_TEST/office-output" --no-table
  grep -R -q "Kylin ARM64 LibreOffice bundled conversion test" "$PORTABLE_TEST/office-output"
fi
INSTALL_HOME="$PORTABLE_TEST/install-home"
DESKTOP_DIR="$INSTALL_HOME/桌面"
mkdir -p "$DESKTOP_DIR"
DOCUMENT_OCR_INSTALL_HOME="$INSTALL_HOME" \
DOCUMENT_OCR_DESKTOP_DIR="$DESKTOP_DIR" \
  "$PACKAGE_ROOT/安装快捷方式.sh"
test -f "$INSTALL_HOME/.local/share/applications/document-ocr-assistant-$DOCUMENT_OCR_EDITION.desktop"
DESKTOP_LABEL="文档OCR助手 OCR版"
if [ "$DOCUMENT_OCR_EDITION" = "full" ]; then DESKTOP_LABEL="文档OCR助手 完整版"; fi
test -f "$DESKTOP_DIR/$DESKTOP_LABEL.desktop"
DOCUMENT_OCR_UI_SMOKE_SCREENSHOT="$PORTABLE_TEST/gui.png" \
  QT_QPA_PLATFORM=offscreen "$MAIN_EXECUTABLE"
test -s "$PORTABLE_TEST/gui.png"
'

test -s "$ARCHIVE_FILE"
echo "[done] Kylin x86_64 绿色目录版解压、OCR、Office、快捷方式和 GUI 测试通过。"
echo "[done] $ARCHIVE_FILE"
