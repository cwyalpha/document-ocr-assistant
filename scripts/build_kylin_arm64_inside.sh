#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="0.2.0"
EDITION="${DOCUMENT_OCR_BUILD_EDITION:-full}"
if [ "$EDITION" != "ocr" ] && [ "$EDITION" != "full" ]; then
  echo "[error] edition 必须为 ocr 或 full。" >&2
  exit 2
fi
PYTHON="${PYTHON_BIN:-/opt/python312/bin/python3.12}"
BUILD_ROOT="$ROOT/build/kylin-arm64"
PYI_DIST="$BUILD_ROOT/pyi-dist"
PYI_WORK="$BUILD_ROOT/pyi-work"
TEST_ROOT="$BUILD_ROOT/tests"
CACHE_DIR="$ROOT/.build-cache"
OCR_MODELS="$CACHE_DIR/ppocrv6-medium"
TABLE_MODEL="$CACHE_DIR/slanet-plus.onnx"
ORIENTATION_MODEL="$CACHE_DIR/orientation/rapid_orientation.onnx"
PACKAGE_NAME="document-ocr-assistant-$VERSION-kylin-v10-arm64-cli-$EDITION"
PACKAGE_ROOT="$ROOT/dist/$PACKAGE_NAME"
RUN_PATH="$ROOT/dist/$PACKAGE_NAME.run"
CHECKSUM_PATH="$ROOT/dist/SHA256SUMS-kylin-arm64-$EDITION.txt"
BUILD_INFO="$BUILD_ROOT/metadata/$EDITION/build-info.json"

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
if [ ! -f "$ORIENTATION_MODEL" ]; then
  "$PYTHON" "$ROOT/scripts/fetch_orientation_model.py" "$(dirname "$ORIENTATION_MODEL")"
fi

"$PYTHON" -m pytest -q \
  "$ROOT/tests/test_core.py" \
  "$ROOT/tests/test_archives.py" \
  "$ROOT/tests/test_office_windows.py"
"$PYTHON" -m compileall -q "$ROOT/src" "$ROOT/scripts" "$ROOT/tests"

rm -rf "$PYI_DIST" "$PYI_WORK" "$TEST_ROOT" "$PACKAGE_ROOT"
rm -f "$RUN_PATH" "$CHECKSUM_PATH"
mkdir -p "$PYI_DIST" "$PYI_WORK" "$TEST_ROOT" "$PACKAGE_ROOT"

"$PYTHON" "$ROOT/scripts/write_build_info.py" "$BUILD_INFO" \
  --edition "$EDITION" --version "$VERSION" --platform kylin-v10 --architecture arm64
DOCUMENT_OCR_BUILD_EDITION="$EDITION" \
DOCUMENT_OCR_BUILD_INFO="$BUILD_INFO" \
DOCUMENT_OCR_BUILD_VERSION="$VERSION" \
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
  "$PACKAGE_ROOT/models/table" \
  "$PACKAGE_ROOT/models/orientation"
mv "$PYI_DIST/文档OCR助手命令行" "$PACKAGE_ROOT/app/文档OCR助手命令行"
cp "$ROOT/assets/app-icon.svg" "$PACKAGE_ROOT/assets/app-icon.svg"
cp "$OCR_MODELS/"*.onnx "$PACKAGE_ROOT/models/ppocrv6-medium/"
cp "$TABLE_MODEL" "$PACKAGE_ROOT/models/table/slanet-plus.onnx"
cp "$ORIENTATION_MODEL" "$PACKAGE_ROOT/models/orientation/rapid_orientation.onnx"
cp "$BUILD_INFO" "$PACKAGE_ROOT/build-info.json"
cp "$ROOT/packaging/启动命令行-kylin-arm64.sh" "$PACKAGE_ROOT/文档OCR助手命令行.sh"
"$PYTHON" "$ROOT/scripts/write_package_readme.py" "$PACKAGE_ROOT/使用说明.txt" \
  --platform kylin-arm64 --edition "$EDITION"
chmod +x "$PACKAGE_ROOT/文档OCR助手命令行.sh"

if [ "$EDITION" = "full" ]; then
  "$PYTHON" "$ROOT/scripts/bundle_kylin_libreoffice.py" \
    --libreoffice-root /usr/lib64/libreoffice \
    --output-root "$PACKAGE_ROOT/bin/libreoffice" \
    --unrar /usr/bin/unrar
fi

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

"$PYTHON" "$ROOT/scripts/create_release_test_materials.py" "$TEST_ROOT/materials"
for angle in 0 90 180 270; do
  "$PACKAGE_ROOT/文档OCR助手命令行.sh" \
    "$TEST_ROOT/materials/orientation-$angle.png" \
    -o "$TEST_ROOT/orientation-$angle" \
    --report-json "$TEST_ROOT/orientation-$angle.json" \
    --no-table
  if ! grep -R -Eq 'Document|OCR' "$TEST_ROOT/orientation-$angle"; then
    echo "[error] ARM64 冻结命令行未通过 $angle° 页面方向测试。" >&2
    exit 1
  fi
done
"$PYTHON" - "$TEST_ROOT" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
expected = {0: 0, 90: 270, 180: 180, 270: 90}
for source_angle, correction in expected.items():
    report = json.loads((root / f"orientation-{source_angle}.json").read_text(encoding="utf-8"))
    actual = report[0]["metadata"]["pages"][0]["applied_angle"]
    if actual != correction:
        raise SystemExit(
            f"ARM64 frozen orientation mismatch: {source_angle=} {correction=} {actual=}"
        )
print("[orientation] ARM64 frozen 0/90/180/270 passed")
PY

VERSION_OUTPUT="$("$PACKAGE_ROOT/文档OCR助手命令行.sh" --version)"
if [[ "$VERSION_OUTPUT" != *"($EDITION, kylin-v10, arm64)"* ]]; then
  echo "[error] 冻结程序 build metadata 不正确：$VERSION_OUTPUT" >&2
  exit 1
fi

if [ "$EDITION" = "full" ]; then
  "$PACKAGE_ROOT/bin/libreoffice/program/soffice" --headless --version
  "$PACKAGE_ROOT/文档OCR助手命令行.sh" \
    "$SMOKE_DOCX" \
    -o "$TEST_ROOT/office-output" \
    --no-table
  if ! grep -R -q "Kylin ARM64 LibreOffice bundled conversion test" "$TEST_ROOT/office-output"; then
    echo "[error] 随包 LibreOffice 未完成 DOCX 命令行转换。" >&2
    exit 1
  fi
else
  set +e
  REFUSAL="$("$PACKAGE_ROOT/文档OCR助手命令行.sh" "$SMOKE_DOCX" --no-table 2>&1)"
  REFUSAL_STATUS=$?
  set -e
  if [ "$REFUSAL_STATUS" -eq 0 ] || [[ "$REFUSAL" != *"OCR版不支持 Word/WPS"* ]]; then
    echo "[error] ARM64 OCR 版未清晰拒绝 Word/WPS：$REFUSAL" >&2
    exit 1
  fi
  if find "$PACKAGE_ROOT" \( -iname '*libreoffice*' -o -iname '*.doc' -o -iname '*.docx' -o -iname '*.wps' \) | grep -q .; then
    echo "[error] OCR 版包含 Office 运行时或测试文档。" >&2
    exit 1
  fi
fi

cp "$ROOT/packaging/自解压头-kylin-arm64.sh" "$RUN_PATH"
tar -czf - -C "$ROOT/dist" "$PACKAGE_NAME" >> "$RUN_PATH"
chmod +x "$RUN_PATH"

(
  cd "$ROOT/dist"
  sha256sum "$(basename "$RUN_PATH")" \
    > "$(basename "$CHECKSUM_PATH")"
)

echo "[done] 目录包：$PACKAGE_ROOT"
echo "[done] 自解压包：$RUN_PATH"
echo "[done] SHA-256：$CHECKSUM_PATH"
