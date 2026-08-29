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
APP_NAME="文档OCR助手OCR版"
if [ "$EDITION" = "full" ]; then APP_NAME="文档OCR助手完整版"; fi
COMPONENTS_DIR="${OCR_OFFLINE_COMPONENTS:-$ROOT/offline_components}"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
BUILD_VENV="${OCR_BUILD_VENV:-$ROOT/.build-venv}"
CACHE_DIR="$ROOT/.build-cache"
TABLE_MODEL="${DOCUMENT_OCR_TABLE_MODEL:-$CACHE_DIR/slanet-plus.onnx}"
ORIENTATION_MODEL="$CACHE_DIR/orientation/rapid_orientation.onnx"
PACKAGE_NAME="document-ocr-assistant-$VERSION-kylin-v10-x86_64-$EDITION"
PACKAGE_ROOT="$ROOT/dist/$PACKAGE_NAME"
ARCHIVE_FILE="$ROOT/dist/$PACKAGE_NAME.tar.gz"
BUILD_INFO="$ROOT/build/kylin-x86_64/metadata/$EDITION/build-info.json"

if [ "$(uname -s)" != "Linux" ] || [ "$(uname -m)" != "x86_64" ]; then
  echo "[error] 请在 Kylin/Linux x86_64 中执行本脚本。" >&2
  exit 2
fi
if [ ! -d "$COMPONENTS_DIR" ]; then
  echo "[error] 找不到离线组件目录：$COMPONENTS_DIR" >&2
  exit 2
fi
if ! command -v objdump >/dev/null 2>&1; then
  echo "[error] 构建机缺少 objdump，请安装 Kylin 的 binutils 构建包。" >&2
  exit 2
fi
if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(not ((3, 10) <= sys.version_info[:2] <= (3, 12)))'; then
  echo "[error] 构建 Python 必须为 3.10—3.12；可通过 PYTHON_BIN 指定。" >&2
  exit 2
fi

if [ ! -x "$BUILD_VENV/bin/python" ]; then
  "$PYTHON_BIN" -m venv --system-site-packages "$BUILD_VENV"
fi
PYTHON="$BUILD_VENV/bin/python"
"$PYTHON" -m pip install --upgrade pip wheel setuptools
"$PYTHON" -m pip install -r "$ROOT/requirements-kylin.txt" -r "$ROOT/requirements-table.txt"
"$PYTHON" -m pip install \
  "pyinstaller==6.18.0" \
  "pyinstaller-hooks-contrib==2026.0" \
  "pytest>=7.4,<9"

if [ ! -f "$TABLE_MODEL" ]; then
  "$PYTHON" "$ROOT/scripts/fetch_table_model.py" "$TABLE_MODEL"
fi
if [ ! -f "$ORIENTATION_MODEL" ]; then
  if [ -f "$COMPONENTS_DIR/rapid_orientation_models_v2.zip" ]; then
    "$PYTHON" "$ROOT/scripts/fetch_orientation_model.py" "$(dirname "$ORIENTATION_MODEL")" \
      --source-archive "$COMPONENTS_DIR/rapid_orientation_models_v2.zip"
  else
    "$PYTHON" "$ROOT/scripts/fetch_orientation_model.py" "$(dirname "$ORIENTATION_MODEL")"
  fi
fi

QT_QPA_PLATFORM=offscreen "$PYTHON" -m pytest -q

rm -rf "$ROOT/build/pyinstaller" "$ROOT/dist/$APP_NAME" "$PACKAGE_ROOT"
rm -f "$ARCHIVE_FILE" "$ROOT/dist/SHA256SUMS-kylin-x86_64-$EDITION.txt"
mkdir -p "$PACKAGE_ROOT"
"$PYTHON" "$ROOT/scripts/write_build_info.py" "$BUILD_INFO" \
  --edition "$EDITION" --version "$VERSION" --platform kylin-v10 --architecture x86_64
DOCUMENT_OCR_BUILD_EDITION="$EDITION" \
DOCUMENT_OCR_BUILD_INFO="$BUILD_INFO" \
DOCUMENT_OCR_BUILD_VERSION="$VERSION" \
"$PYTHON" -m PyInstaller \
  --noconfirm \
  --clean \
  --distpath "$ROOT/dist" \
  --workpath "$ROOT/build/pyinstaller" \
  "$ROOT/packaging/document_ocr_assistant.spec"

cp -a "$ROOT/dist/$APP_NAME/." "$PACKAGE_ROOT/"
rm -rf "$ROOT/dist/$APP_NAME"
mkdir -p "$PACKAGE_ROOT/assets"
cp "$ROOT/assets/app-icon.svg" "$PACKAGE_ROOT/assets/app-icon.svg"
cp "$ROOT/packaging/安装快捷方式.sh" "$PACKAGE_ROOT/安装快捷方式.sh"
chmod +x "$PACKAGE_ROOT/$APP_NAME" "$PACKAGE_ROOT/安装快捷方式.sh"

COMPONENT_ARGS=(
  --components-dir "$COMPONENTS_DIR"
  --output-root "$PACKAGE_ROOT"
  --table-model "$TABLE_MODEL"
  --orientation-model "$ORIENTATION_MODEL"
)
if [ "$EDITION" = "ocr" ]; then
  COMPONENT_ARGS+=(--skip-libreoffice)
fi
"$PYTHON" "$ROOT/scripts/prepare_offline_components.py" "${COMPONENT_ARGS[@]}"

"$PYTHON" "$ROOT/scripts/write_package_readme.py" "$PACKAGE_ROOT/使用说明.txt" \
  --platform kylin-x86_64 --edition "$EDITION"

MAIN_EXECUTABLE="$PACKAGE_ROOT/$APP_NAME"
REQUIRED_PORTABLE_PATHS=(
  "$MAIN_EXECUTABLE"
  "$PACKAGE_ROOT/_internal/build-info.json"
  "$PACKAGE_ROOT/models/ppocrv6-medium/PP-OCRv6_det_medium.onnx"
  "$PACKAGE_ROOT/models/ppocrv6-medium/PP-OCRv6_rec_medium.onnx"
  "$PACKAGE_ROOT/models/table/slanet-plus.onnx"
  "$PACKAGE_ROOT/models/orientation/rapid_orientation.onnx"
  "$PACKAGE_ROOT/bin/unrar/unrar"
  "$PACKAGE_ROOT/assets/app-icon.svg"
  "$PACKAGE_ROOT/安装快捷方式.sh"
  "$PACKAGE_ROOT/使用说明.txt"
)
if [ "$EDITION" = "full" ]; then
  REQUIRED_PORTABLE_PATHS+=("$PACKAGE_ROOT/bin/libreoffice/program/soffice")
fi
for required_path in "${REQUIRED_PORTABLE_PATHS[@]}"; do
  if [ ! -e "$required_path" ]; then
    echo "[error] Kylin 绿色版缺少必要文件：$required_path" >&2
    exit 1
  fi
done
if [ -d "$PACKAGE_ROOT/app" ]; then
  echo "[error] Kylin 绿色版不应再包含 app 子目录。" >&2
  exit 1
fi
if find "$PACKAGE_ROOT" -maxdepth 1 -type f -name '启动*.sh' | grep -q .; then
  echo "[error] Kylin 绿色版不应依赖启动脚本。" >&2
  exit 1
fi
VERSION_OUTPUT="$("$MAIN_EXECUTABLE" --cli --version)"
if [[ "$VERSION_OUTPUT" != *"($EDITION, kylin-v10, x86_64)"* ]]; then
  echo "[error] 冻结程序 build metadata 不正确：$VERSION_OUTPUT" >&2
  exit 1
fi
SMOKE_ROOT="$ROOT/build/kylin-x86_64/smoke-$EDITION"
rm -rf "$SMOKE_ROOT"
mkdir -p "$SMOKE_ROOT"
"$PYTHON" "$ROOT/scripts/create_windows_smoke_input.py" "$SMOKE_ROOT/ocr.png"
"$MAIN_EXECUTABLE" --cli "$SMOKE_ROOT/ocr.png" -o "$SMOKE_ROOT/output" --no-table
"$PYTHON" "$ROOT/scripts/create_release_test_materials.py" "$SMOKE_ROOT/materials"
for angle in 0 90 180 270; do
  "$MAIN_EXECUTABLE" --cli "$SMOKE_ROOT/materials/orientation-$angle.png" \
    -o "$SMOKE_ROOT/orientation-$angle" \
    --report-json "$SMOKE_ROOT/orientation-$angle.json" --no-table
  grep -R -Eq 'Document|OCR' "$SMOKE_ROOT/orientation-$angle"
done
"$PYTHON" - "$SMOKE_ROOT" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
for source_angle, correction in {0: 0, 90: 270, 180: 180, 270: 90}.items():
    report = json.loads((root / f"orientation-{source_angle}.json").read_text(encoding="utf-8"))
    actual = report[0]["metadata"]["pages"][0]["applied_angle"]
    if actual != correction:
        raise SystemExit(f"Kylin x86_64 orientation mismatch: {source_angle=} {correction=} {actual=}")
PY
"$PYTHON" "$ROOT/scripts/create_office_smoke_input.py" "$SMOKE_ROOT/office.docx"
if [ "$EDITION" = "full" ]; then
  "$MAIN_EXECUTABLE" --cli "$SMOKE_ROOT/office.docx" \
    -o "$SMOKE_ROOT/office-output" --no-table
  grep -R -q 'Kylin ARM64 LibreOffice bundled conversion test' "$SMOKE_ROOT/office-output"
else
  set +e
  REFUSAL="$("$MAIN_EXECUTABLE" --cli "$SMOKE_ROOT/office.docx" --no-table 2>&1)"
  REFUSAL_STATUS=$?
  set -e
  if [ "$REFUSAL_STATUS" -eq 0 ] || [[ "$REFUSAL" != *"OCR版不支持 Word/WPS"* ]]; then
    echo "[error] OCR 版未清晰拒绝 Word/WPS：$REFUSAL" >&2
    exit 1
  fi
fi
DOCUMENT_OCR_UI_SMOKE_SCREENSHOT="$SMOKE_ROOT/gui.png" \
  QT_QPA_PLATFORM=offscreen "$MAIN_EXECUTABLE"
test -s "$SMOKE_ROOT/gui.png"
if [ "$EDITION" = "ocr" ] && find "$PACKAGE_ROOT" -iname '*libreoffice*' -o -iname '*office*.doc*' | grep -q .; then
  echo "[error] OCR 版包含 Office 运行时或测试文档。" >&2
  exit 1
fi

tar -czf "$ARCHIVE_FILE" -C "$ROOT/dist" "$PACKAGE_NAME"
# GNU tar quotes non-ASCII names as octal escapes under the minimal C locale
# used by some Kylin/Docker images.  Request literal names so the checks below
# validate the actual UTF-8 executable and helper script paths.
ARCHIVE_NAMES="$(tar --quoting-style=literal -tzf "$ARCHIVE_FILE")"
if ! grep -Fxq "$PACKAGE_NAME/$APP_NAME" <<<"$ARCHIVE_NAMES"; then
  echo "[error] Kylin 绿色版压缩包根目录缺少主程序。" >&2
  exit 1
fi
if grep -q "^$PACKAGE_NAME/app/" <<<"$ARCHIVE_NAMES"; then
  echo "[error] Kylin 绿色版压缩包不应包含 app 子目录。" >&2
  exit 1
fi
if grep -Eq "^$PACKAGE_NAME/启动.*\.sh$" <<<"$ARCHIVE_NAMES"; then
  echo "[error] Kylin 绿色版压缩包不应依赖启动脚本。" >&2
  exit 1
fi
ARCHIVE_SHA256="$(sha256sum "$ARCHIVE_FILE" | awk '{print $1}')"

echo "[done] 目录包：$PACKAGE_ROOT"
echo "[done] 绿色版压缩包：$ARCHIVE_FILE"
echo "[done] SHA-256：$ARCHIVE_SHA256"
