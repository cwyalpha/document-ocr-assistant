#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON_BIN:-/opt/python312/bin/python3.12}"
BUILD_ROOT="$ROOT/build/kylin-arm64"
PYI_DIST="$BUILD_ROOT/pyi-dist"
PYI_WORK="$BUILD_ROOT/pyi-work"
TEST_ROOT="$BUILD_ROOT/tests"
CACHE_DIR="$ROOT/.build-cache"
OCR_MODELS="$CACHE_DIR/ppocrv6-medium"
TABLE_MODEL="$CACHE_DIR/slanet-plus.onnx"
PACKAGE_NAME="文档OCR助手-kylin-v10-arm64-cli"
PACKAGE_ROOT="$ROOT/dist/$PACKAGE_NAME"
TAR_PATH="$ROOT/dist/$PACKAGE_NAME.tar.gz"
RUN_PATH="$ROOT/dist/$PACKAGE_NAME.run"
CHECKSUM_PATH="$ROOT/dist/SHA256SUMS-kylin-arm64.txt"

if [ "$(uname -s)" != "Linux" ] || [ "$(uname -m)" != "aarch64" ]; then
  echo "[error] 请在 Kylin/Linux ARM64（aarch64）中执行本脚本。" >&2
  exit 2
fi
if [ ! -x "$PYTHON" ]; then
  echo "[error] 找不到 Python 3.12：$PYTHON" >&2
  exit 2
fi
if ! command -v objdump >/dev/null 2>&1; then
  echo "[error] 构建容器缺少 objdump。" >&2
  exit 2
fi

mkdir -p "$CACHE_DIR" "$ROOT/dist" "$BUILD_ROOT"
"$PYTHON" "$ROOT/scripts/fetch_ocr_models.py" "$OCR_MODELS"
if [ ! -f "$TABLE_MODEL" ]; then
  "$PYTHON" "$ROOT/scripts/fetch_table_model.py" "$TABLE_MODEL"
fi

"$PYTHON" -m pytest -q \
  "$ROOT/tests/test_core.py" \
  "$ROOT/tests/test_archives.py" \
  "$ROOT/tests/test_office_windows.py"
"$PYTHON" -m compileall -q "$ROOT/src" "$ROOT/scripts" "$ROOT/tests"

rm -rf "$PYI_DIST" "$PYI_WORK" "$TEST_ROOT" "$PACKAGE_ROOT"
rm -f "$TAR_PATH" "$RUN_PATH" "$CHECKSUM_PATH"
mkdir -p "$PYI_DIST" "$PYI_WORK" "$TEST_ROOT" "$PACKAGE_ROOT"

"$PYTHON" -m PyInstaller \
  --noconfirm \
  --clean \
  --distpath "$PYI_DIST" \
  --workpath "$PYI_WORK" \
  "$ROOT/packaging/document_ocr_assistant_kylin_arm64_cli.spec"

mkdir -p \
  "$PACKAGE_ROOT/app" \
  "$PACKAGE_ROOT/assets" \
  "$PACKAGE_ROOT/models/ppocrv6-medium" \
  "$PACKAGE_ROOT/models/table"
mv "$PYI_DIST/文档OCR助手命令行" "$PACKAGE_ROOT/app/文档OCR助手命令行"
cp "$ROOT/assets/app-icon.svg" "$PACKAGE_ROOT/assets/app-icon.svg"
cp "$OCR_MODELS/"*.onnx "$PACKAGE_ROOT/models/ppocrv6-medium/"
cp "$TABLE_MODEL" "$PACKAGE_ROOT/models/table/slanet-plus.onnx"
cp "$ROOT/packaging/启动命令行-kylin-arm64.sh" "$PACKAGE_ROOT/文档OCR助手命令行.sh"
cp "$ROOT/packaging/使用说明-kylin-arm64.txt" "$PACKAGE_ROOT/使用说明.txt"
chmod +x "$PACKAGE_ROOT/文档OCR助手命令行.sh"

"$PYTHON" "$ROOT/scripts/bundle_kylin_libreoffice.py" \
  --libreoffice-root /usr/lib64/libreoffice \
  --output-root "$PACKAGE_ROOT/bin/libreoffice" \
  --unrar /usr/bin/unrar

MAIN_EXECUTABLE="$PACKAGE_ROOT/app/文档OCR助手命令行/文档OCR助手命令行"
if ! file "$MAIN_EXECUTABLE" | grep -q "ARM aarch64"; then
  echo "[error] 冻结主程序不是 ARM64：$(file "$MAIN_EXECUTABLE")" >&2
  exit 1
fi

SMOKE_IMAGE="$TEST_ROOT/kylin-arm64-ocr.png"
SMOKE_DOCX="$TEST_ROOT/kylin-arm64-office.docx"
"$PYTHON" "$ROOT/scripts/create_kylin_arm64_smoke_input.py" "$SMOKE_IMAGE"
"$PYTHON" "$ROOT/scripts/create_office_smoke_input.py" "$SMOKE_DOCX"

"$PACKAGE_ROOT/文档OCR助手命令行.sh" \
  "$SMOKE_IMAGE" \
  -o "$TEST_ROOT/ocr-output" \
  --no-table
if ! grep -R -q "Kylin ARM64" "$TEST_ROOT/ocr-output"; then
  echo "[error] 冻结命令行客户端没有识别出 Kylin ARM64。" >&2
  exit 1
fi

"$PACKAGE_ROOT/bin/libreoffice/program/soffice" --headless --version
"$PACKAGE_ROOT/文档OCR助手命令行.sh" \
  "$SMOKE_DOCX" \
  -o "$TEST_ROOT/office-output" \
  --no-table
if ! grep -R -q "Kylin ARM64 LibreOffice bundled conversion test" "$TEST_ROOT/office-output"; then
  echo "[error] 随包 LibreOffice 未完成 DOCX 命令行转换。" >&2
  exit 1
fi

tar -czf "$TAR_PATH" -C "$ROOT/dist" "$PACKAGE_NAME"
cp "$ROOT/packaging/自解压头-kylin-arm64.sh" "$RUN_PATH"
tar -czf - -C "$ROOT/dist" "$PACKAGE_NAME" >> "$RUN_PATH"
chmod +x "$RUN_PATH"

(
  cd "$ROOT/dist"
  sha256sum "$(basename "$TAR_PATH")" "$(basename "$RUN_PATH")" \
    > "$(basename "$CHECKSUM_PATH")"
)

echo "[done] 目录包：$PACKAGE_ROOT"
echo "[done] TAR.GZ：$TAR_PATH"
echo "[done] 自解压包：$RUN_PATH"
echo "[done] SHA-256：$CHECKSUM_PATH"
