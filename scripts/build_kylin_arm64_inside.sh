#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="0.2.0"
EDITION="${DOCUMENT_OCR_BUILD_EDITION:-full}"
if [ "$EDITION" != "full" ]; then
  echo "[error] Kylin ARM64 当前只构建带图形界面和 LibreOffice 的 full 版本。" >&2
  exit 2
fi
APP_NAME="document-ocr-assistant-full"
PYTHON="${PYTHON_BIN:-/opt/python310/bin/python3.10}"
BUILD_ROOT="$ROOT/build/kylin-arm64"
PYI_DIST="$BUILD_ROOT/pyi-dist"
PYI_WORK="$BUILD_ROOT/pyi-work"
TEST_ROOT="$BUILD_ROOT/tests"
CACHE_DIR="$ROOT/.build-cache"
OCR_MODELS="$CACHE_DIR/ppocrv6-medium"
TABLE_MODEL="$CACHE_DIR/slanet-plus.onnx"
ORIENTATION_MODEL="$CACHE_DIR/orientation/rapid_orientation.onnx"
PACKAGE_NAME="document-ocr-assistant-$VERSION-kylin-v10-arm64-$EDITION"
PACKAGE_ROOT="$ROOT/dist/$PACKAGE_NAME"
RUN_PATH="$ROOT/dist/$PACKAGE_NAME.run"
CHECKSUM_PATH="$ROOT/dist/SHA256SUMS-kylin-arm64-$EDITION.txt"
BUILD_INFO="$BUILD_ROOT/metadata/$EDITION/build-info.json"

if [ "$(uname -s)" != "Linux" ] || [ "$(uname -m)" != "aarch64" ]; then
  echo "[error] 请在 Kylin/Linux ARM64（aarch64）中执行本脚本。" >&2
  exit 2
fi
if [ ! -x "$PYTHON" ]; then
  echo "[error] 找不到 Python 3.10：$PYTHON" >&2
  exit 2
fi
if ! "$PYTHON" -c 'from PySide2 import QtCore, QtGui, QtWidgets; assert QtCore.qVersion().startswith("5.15.")'; then
  echo "[error] 构建环境缺少固定版本 Qt 5.15 / PySide2。" >&2
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

QT_QPA_PLATFORM=offscreen "$PYTHON" -m pytest -q
"$PYTHON" -m compileall -q "$ROOT/src" "$ROOT/scripts" "$ROOT/tests"

rm -rf "$PYI_DIST" "$PYI_WORK" "$TEST_ROOT" "$PACKAGE_ROOT"
rm -f "$RUN_PATH" "$CHECKSUM_PATH"
mkdir -p "$PYI_DIST" "$PYI_WORK" "$TEST_ROOT" "$PACKAGE_ROOT"

"$PYTHON" "$ROOT/scripts/write_build_info.py" "$BUILD_INFO" \
  --edition "$EDITION" --version "$VERSION" --platform kylin-v10 --architecture arm64
DOCUMENT_OCR_BUILD_EDITION="$EDITION" \
DOCUMENT_OCR_BUILD_INFO="$BUILD_INFO" \
DOCUMENT_OCR_BUILD_VERSION="$VERSION" \
DOCUMENT_OCR_QT_BINDING="PySide2" \
DOCUMENT_OCR_APP_NAME="$APP_NAME" \
"$PYTHON" -m PyInstaller \
  --noconfirm \
  --clean \
  --distpath "$PYI_DIST" \
  --workpath "$PYI_WORK" \
  "$ROOT/packaging/document_ocr_assistant.spec"

mkdir -p \
  "$PACKAGE_ROOT/app" \
  "$PACKAGE_ROOT/assets" \
  "$PACKAGE_ROOT/models/ppocrv6-medium" \
  "$PACKAGE_ROOT/models/table" \
  "$PACKAGE_ROOT/models/orientation"
mv "$PYI_DIST/$APP_NAME" "$PACKAGE_ROOT/app/$APP_NAME"
for qt_runtime_library in libGL.so.1 libGLX.so.0 libGLdispatch.so.0; do
  source_library="/usr/lib64/$qt_runtime_library"
  if [ ! -e "$source_library" ]; then
    echo "[error] Qt 图形运行库不存在：$source_library" >&2
    exit 1
  fi
  cp -L "$source_library" "$PACKAGE_ROOT/app/$APP_NAME/_internal/$qt_runtime_library"
done
cp "$ROOT/assets/app-icon.svg" "$PACKAGE_ROOT/assets/app-icon.svg"
cp "$OCR_MODELS/"*.onnx "$PACKAGE_ROOT/models/ppocrv6-medium/"
cp "$TABLE_MODEL" "$PACKAGE_ROOT/models/table/slanet-plus.onnx"
cp "$ORIENTATION_MODEL" "$PACKAGE_ROOT/models/orientation/rapid_orientation.onnx"
cp "$BUILD_INFO" "$PACKAGE_ROOT/build-info.json"
cp "$ROOT/packaging/启动文档OCR助手.sh" "$PACKAGE_ROOT/启动文档OCR助手.sh"
cp "$ROOT/packaging/文档OCR助手命令行.sh" "$PACKAGE_ROOT/文档OCR助手命令行.sh"
cp "$ROOT/packaging/安装快捷方式.sh" "$PACKAGE_ROOT/安装快捷方式.sh"
"$PYTHON" "$ROOT/scripts/write_package_readme.py" "$PACKAGE_ROOT/使用说明.txt" \
  --platform kylin-arm64 --edition "$EDITION"
chmod +x \
  "$PACKAGE_ROOT/启动文档OCR助手.sh" \
  "$PACKAGE_ROOT/文档OCR助手命令行.sh" \
  "$PACKAGE_ROOT/安装快捷方式.sh"

"$PYTHON" "$ROOT/scripts/bundle_kylin_libreoffice.py" \
  --libreoffice-root /usr/lib64/libreoffice \
  --output-root "$PACKAGE_ROOT/bin/libreoffice" \
  --unrar /usr/bin/unrar

MAIN_EXECUTABLE="$PACKAGE_ROOT/app/$APP_NAME/$APP_NAME"
if ! file "$MAIN_EXECUTABLE" | grep -q "ARM aarch64"; then
  echo "[error] 冻结主程序不是 ARM64：$(file "$MAIN_EXECUTABLE")" >&2
  exit 1
fi

VERSION_OUTPUT="$("$MAIN_EXECUTABLE" --cli --version)"
if [[ "$VERSION_OUTPUT" != *"($EDITION, kylin-v10, arm64)"* ]]; then
  echo "[error] 冻结程序 build metadata 不正确：$VERSION_OUTPUT" >&2
  exit 1
fi

DOCUMENT_OCR_UI_SMOKE_SCREENSHOT="$TEST_ROOT/gui.png" \
  QT_QPA_PLATFORM=offscreen "$MAIN_EXECUTABLE"
if [ ! -s "$TEST_ROOT/gui.png" ]; then
  echo "[error] Kylin ARM64 图形界面未生成冒烟测试截图。" >&2
  exit 1
fi

SMOKE_IMAGE="$TEST_ROOT/kylin-arm64-ocr.png"
SMOKE_DOCX="$TEST_ROOT/kylin-arm64-office.docx"
"$PYTHON" "$ROOT/scripts/create_kylin_arm64_smoke_input.py" "$SMOKE_IMAGE"
"$PYTHON" "$ROOT/scripts/create_office_smoke_input.py" "$SMOKE_DOCX"

"$PACKAGE_ROOT/文档OCR助手命令行.sh" \
  "$SMOKE_IMAGE" -o "$TEST_ROOT/ocr-output" --no-table
if ! grep -R -q "Kylin ARM64" "$TEST_ROOT/ocr-output"; then
  echo "[error] ARM64 冻结程序没有识别出 Kylin ARM64。" >&2
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
    echo "[error] ARM64 冻结程序未通过 $angle° 页面方向测试。" >&2
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

"$PACKAGE_ROOT/bin/libreoffice/program/soffice" --headless --version
"$PACKAGE_ROOT/文档OCR助手命令行.sh" \
  "$SMOKE_DOCX" -o "$TEST_ROOT/office-output" --no-table
if ! grep -R -q "Kylin ARM64 LibreOffice bundled conversion test" "$TEST_ROOT/office-output"; then
  echo "[error] 随包 LibreOffice 未完成 DOCX 转换。" >&2
  exit 1
fi

cp "$ROOT/packaging/自解压头-kylin-arm64.sh" "$RUN_PATH"
tar -czf - -C "$ROOT/dist" "$PACKAGE_NAME" >> "$RUN_PATH"
chmod +x "$RUN_PATH"

(
  cd "$ROOT/dist"
  sha256sum "$(basename "$RUN_PATH")" > "$(basename "$CHECKSUM_PATH")"
)

echo "[done] 目录包：$PACKAGE_ROOT"
echo "[done] GUI 自解压包：$RUN_PATH"
echo "[done] SHA-256：$CHECKSUM_PATH"
