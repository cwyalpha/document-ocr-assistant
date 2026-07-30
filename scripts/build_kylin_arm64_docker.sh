#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILDER_IMAGE="${KYLIN_ARM64_BUILDER_IMAGE:-document-ocr-kylin-arm64-builder:latest}"
BASE_IMAGE="${KYLIN_ARM64_BASE_IMAGE:-macrosan/kylin:v10-sp1}"
PACKAGE_NAME="文档OCR助手-kylin-v10-arm64-cli"
PACKAGE_ROOT="$ROOT/dist/$PACKAGE_NAME"
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
  -v "$ROOT:/workspace" \
  "$BUILDER_IMAGE" \
  /bin/bash /workspace/scripts/build_kylin_arm64_inside.sh

rm -rf "$TEST_ROOT"
mkdir -p "$TEST_ROOT"
docker run --rm \
  --platform linux/arm64 \
  -v "$ROOT:/workspace" \
  "$BASE_IMAGE" \
  /bin/bash -lc '
set -euo pipefail
PACKAGE="/workspace/dist/文档OCR助手-kylin-v10-arm64-cli"
TESTS="/workspace/build/kylin-arm64/tests"
OUTPUT="/workspace/build/kylin-arm64/clean-container-test"

test "$(uname -m)" = "aarch64"
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
'

echo "[done] Kylin ARM64 干净容器命令行测试通过：$TEST_ROOT"
echo "[done] 发布目录：$PACKAGE_ROOT"
