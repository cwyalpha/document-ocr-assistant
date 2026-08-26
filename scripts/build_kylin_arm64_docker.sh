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
PACKAGE_ROOT="$ROOT/dist/$PACKAGE_NAME"
RUN_FILE="$ROOT/dist/$PACKAGE_NAME.run"
TEST_ROOT="$ROOT/build/kylin-arm64/clean-container-test"

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
  -v "$ROOT:/workspace" \
  "$BUILDER_IMAGE" \
  /bin/bash /workspace/scripts/build_kylin_arm64_inside.sh

rm -rf "$TEST_ROOT"
mkdir -p "$TEST_ROOT"
docker run --rm \
  --platform linux/arm64 \
  -e DOCUMENT_OCR_PACKAGE_NAME="$PACKAGE_NAME" \
  -e DOCUMENT_OCR_EDITION="$EDITION" \
  -v "$ROOT:/workspace" \
  "$BASE_IMAGE" \
  /bin/bash -lc '
set -euo pipefail
PACKAGE="/workspace/dist/$DOCUMENT_OCR_PACKAGE_NAME"
TESTS="/workspace/build/kylin-arm64/tests"
OUTPUT="/workspace/build/kylin-arm64/clean-container-test"

test "$(uname -m)" = "aarch64"
VERSION_OUTPUT="$("$PACKAGE/文档OCR助手命令行.sh" --version)"
if [[ "$VERSION_OUTPUT" != *"($DOCUMENT_OCR_EDITION, kylin-v10, arm64)"* ]]; then
  echo "[error] ARM64 冻结程序版本验证失败：$VERSION_OUTPUT" >&2
  exit 1
fi

DOCUMENT_OCR_UI_SMOKE_SCREENSHOT="$OUTPUT/gui.png" \
  QT_QPA_PLATFORM=offscreen "$PACKAGE/启动文档OCR助手.sh"
test -s "$OUTPUT/gui.png"

"$PACKAGE/文档OCR助手命令行.sh" \
  "$TESTS/kylin-arm64-ocr.png" \
  -o "$OUTPUT/ocr-output" \
  --no-table
grep -R -q "Kylin ARM64" "$OUTPUT/ocr-output"

"$PACKAGE/bin/libreoffice/program/soffice" --headless --version \
  > "$OUTPUT/libreoffice-version.txt"
grep -q "LibreOffice 6.0.6.1" "$OUTPUT/libreoffice-version.txt"
"$PACKAGE/文档OCR助手命令行.sh" \
  "$TESTS/kylin-arm64-office.docx" \
  -o "$OUTPUT/office-output" \
  --no-table
grep -R -q "Kylin ARM64 LibreOffice bundled conversion test" "$OUTPUT/office-output"

RUN_TEST=/tmp/KOS/桌面/document-ocr-arm64-run-test
rm -rf "$RUN_TEST"
mkdir -p "$RUN_TEST"
cp "/workspace/dist/$DOCUMENT_OCR_PACKAGE_NAME.run" "$RUN_TEST/"
cd "$RUN_TEST"
RUN_FILE="$RUN_TEST/$DOCUMENT_OCR_PACKAGE_NAME.run"
chmod +x "$RUN_FILE"
DOCUMENT_OCR_UI_SMOKE_SCREENSHOT="$OUTPUT/run-gui.png" \
  QT_QPA_PLATFORM=offscreen "$RUN_FILE"
test -s "$OUTPUT/run-gui.png"
RUN_VERSION="$($RUN_FILE --cli --version)"
if [[ "$RUN_VERSION" != *"($DOCUMENT_OCR_EDITION, kylin-v10, arm64)"* ]]; then
  echo "[error] ARM64 .run 自解压或版本验证失败：$RUN_VERSION" >&2
  exit 1
fi
'

test -s "$RUN_FILE"
echo "[done] Kylin ARM64 干净容器 GUI、CLI、OCR、Office 测试通过：$TEST_ROOT"
echo "[done] Kylin ARM64 GUI .run 自解压测试通过。"
echo "[done] Kylin ARM64 中文路径 GUI、CLI 回归测试通过。"
echo "[done] 发布包：$RUN_FILE"
