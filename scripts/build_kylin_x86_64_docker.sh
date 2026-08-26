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
RUN_FILE="$ROOT/dist/$PACKAGE_NAME.run"

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
RUN_TEST=/tmp/document-ocr-x86_64-run-test
mkdir -p "$RUN_TEST"
cp "/workspace/dist/$DOCUMENT_OCR_PACKAGE_NAME.run" "$RUN_TEST/"
cd "$RUN_TEST"
RUN_FILE="$RUN_TEST/$DOCUMENT_OCR_PACKAGE_NAME.run"
chmod +x "$RUN_FILE"
RUN_VERSION="$($RUN_FILE --cli --version)"
if [[ "$RUN_VERSION" != *"($DOCUMENT_OCR_EDITION, kylin-v10, x86_64)"* ]]; then
  echo "[error] x86_64 .run 自解压或版本验证失败：$RUN_VERSION" >&2
  exit 1
fi
'

test -s "$RUN_FILE"
echo "[done] Kylin x86_64 .run 自解压测试通过。"
echo "[done] $RUN_FILE"
