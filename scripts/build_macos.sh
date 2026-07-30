#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/opt/homebrew/bin/python3.12}"
BUILD_VENV="${OCR_BUILD_VENV_MACOS:-$ROOT/.build-venv-macos}"
PYTHON="$BUILD_VENV/bin/python"
CACHE_DIR="$ROOT/.build-cache"
OCR_MODEL_CACHE="$CACHE_DIR/ppocrv6-medium"
TABLE_MODEL="${DOCUMENT_OCR_TABLE_MODEL:-$CACHE_DIR/slanet-plus.onnx}"
COMPONENTS_DIR="${OCR_OFFLINE_COMPONENTS:-}"
PYI_DIST="$ROOT/build/macos/pyi-dist"
PYI_WORK="$ROOT/build/macos/pyi-work"
TEST_ROOT="$ROOT/build/macos/tests"
DMG_ROOT="$ROOT/build/macos/dmg"
PACKAGE_NAME="文档OCR助手-macos-arm64"
PACKAGE_ROOT="$ROOT/dist/$PACKAGE_NAME"
APP_PATH="$PACKAGE_ROOT/文档OCR助手.app"
APP_EXECUTABLE="$APP_PATH/Contents/MacOS/文档OCR助手"
ZIP_PATH="$ROOT/dist/$PACKAGE_NAME.zip"
DMG_PATH="$ROOT/dist/$PACKAGE_NAME.dmg"
CHECKSUM_PATH="$ROOT/dist/SHA256SUMS-macos-arm64.txt"

if [ "$(uname -s)" != "Darwin" ] || [ "$(uname -m)" != "arm64" ]; then
  echo "[error] 请在 Apple Silicon（arm64）Mac 上执行本脚本。" >&2
  exit 2
fi
if [ ! -x "$PYTHON_BIN" ]; then
  echo "[error] 找不到 Python 3.10—3.12：$PYTHON_BIN" >&2
  exit 2
fi
if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(not ((3, 10) <= sys.version_info[:2] <= (3, 12)))'; then
  echo "[error] macOS 构建 Python 必须为 3.10—3.12；可通过 PYTHON_BIN 指定。" >&2
  exit 2
fi
if [ ! -x "$PYTHON" ]; then
  "$PYTHON_BIN" -m venv "$BUILD_VENV"
fi

if [ "${MACOS_SKIP_DEPENDENCY_INSTALL:-0}" != "1" ]; then
  "$PYTHON" -m pip install --upgrade pip wheel setuptools
  "$PYTHON" -m pip install \
    -r "$ROOT/requirements-macos.txt" \
    -r "$ROOT/requirements-table.txt"
  "$PYTHON" -m pip install \
    "pyinstaller==6.18.0" \
    "pyinstaller-hooks-contrib==2026.0" \
    "pytest>=7.4,<9"
fi

mkdir -p "$CACHE_DIR" "$ROOT/build/macos" "$ROOT/dist"
if [ -n "$COMPONENTS_DIR" ] && [ -d "$COMPONENTS_DIR/rapidocr-ppocrv6-medium" ]; then
  "$PYTHON" "$ROOT/scripts/fetch_ocr_models.py" \
    "$OCR_MODEL_CACHE" \
    --source-dir "$COMPONENTS_DIR/rapidocr-ppocrv6-medium"
else
  "$PYTHON" "$ROOT/scripts/fetch_ocr_models.py" "$OCR_MODEL_CACHE"
fi
if [ ! -f "$TABLE_MODEL" ]; then
  "$PYTHON" "$ROOT/scripts/fetch_table_model.py" "$TABLE_MODEL"
fi
"$PYTHON" "$ROOT/scripts/create_macos_icon.py" \
  "$ROOT/assets/app-icon.svg" \
  "$ROOT/assets/app-icon.icns"

QT_QPA_PLATFORM=offscreen "$PYTHON" -m pytest -q
"$PYTHON" -m compileall -q "$ROOT/src" "$ROOT/scripts" "$ROOT/tests"

rm -rf "$PYI_DIST" "$PYI_WORK" "$TEST_ROOT" "$DMG_ROOT" "$PACKAGE_ROOT"
rm -f "$ZIP_PATH" "$DMG_PATH" "$CHECKSUM_PATH"
mkdir -p "$PYI_DIST" "$PYI_WORK" "$TEST_ROOT" "$PACKAGE_ROOT"
"$PYTHON" -m PyInstaller \
  --noconfirm \
  --clean \
  --distpath "$PYI_DIST" \
  --workpath "$PYI_WORK" \
  "$ROOT/packaging/document_ocr_assistant_macos.spec"

cp -R "$PYI_DIST/文档OCR助手.app" "$APP_PATH"
mkdir -p \
  "$APP_PATH/Contents/Resources/models/ppocrv6-medium" \
  "$APP_PATH/Contents/Resources/models/table"
cp "$OCR_MODEL_CACHE/"*.onnx \
  "$APP_PATH/Contents/Resources/models/ppocrv6-medium/"
cp "$TABLE_MODEL" \
  "$APP_PATH/Contents/Resources/models/table/slanet-plus.onnx"
cp "$ROOT/packaging/使用说明-macos.txt" "$PACKAGE_ROOT/使用说明.txt"

xattr -cr "$APP_PATH"
CODESIGN_IDENTITY="${MACOS_CODESIGN_IDENTITY:--}"
codesign --force --deep --sign "$CODESIGN_IDENTITY" "$APP_PATH"
codesign --verify --deep --strict --verbose=2 "$APP_PATH"
plutil -lint "$APP_PATH/Contents/Info.plist"
if ! file "$APP_EXECUTABLE" | grep -q "arm64"; then
  echo "[error] App 主程序不是 arm64：$(file "$APP_EXECUTABLE")" >&2
  exit 1
fi

UI_SCREENSHOT="$TEST_ROOT/macos-ui-smoke.png"
DOCUMENT_OCR_UI_SMOKE_SCREENSHOT="$UI_SCREENSHOT" \
  QT_QPA_PLATFORM=offscreen \
  "$APP_EXECUTABLE"
if [ ! -s "$UI_SCREENSHOT" ]; then
  echo "[error] macOS 冻结客户端界面测试失败。" >&2
  exit 1
fi

PIPELINE_INPUT="$TEST_ROOT/merged-table.png"
PIPELINE_REPORT="$TEST_ROOT/pipeline-result.json"
"$PYTHON" "$ROOT/scripts/create_macos_smoke_input.py" "$PIPELINE_INPUT"
DOCUMENT_OCR_PIPELINE_SMOKE_INPUT="$PIPELINE_INPUT" \
  DOCUMENT_OCR_PIPELINE_SMOKE_OUTPUT="$PIPELINE_REPORT" \
  "$APP_EXECUTABLE"
"$PYTHON" - "$PIPELINE_REPORT" <<'PY'
import json
import sys
from pathlib import Path

report_path = Path(sys.argv[1])
if not report_path.is_file():
    raise SystemExit("冻结客户端未生成 OCR 流水线报告。")
report = json.loads(report_path.read_text(encoding="utf-8"))
if report.get("ocr_blocks", 0) < 1:
    raise SystemExit("冻结客户端没有识别出文字。")
if report.get("tables", 0) < 1:
    raise SystemExit("冻结客户端没有识别出表格。")
if "colspan" not in report.get("markdown", ""):
    raise SystemExit("冻结客户端没有保留合并单元格。")
for output in report.get("outputs", []):
    if not Path(output).is_file():
        raise SystemExit(f"流水线输出不存在：{output}")
print(
    "[smoke] blocks={ocr_blocks} tables={tables} outputs={outputs}".format(
        ocr_blocks=report["ocr_blocks"],
        tables=report["tables"],
        outputs=len(report["outputs"]),
    )
)
PY

SCANNED_PDF="$TEST_ROOT/scanned-no-text-layer.pdf"
SCANNED_PDF_REPORT="$TEST_ROOT/scanned-pdf-result.json"
"$PYTHON" "$ROOT/scripts/create_scanned_pdf_smoke_input.py" \
  "$PIPELINE_INPUT" \
  "$SCANNED_PDF"
DOCUMENT_OCR_PIPELINE_SMOKE_INPUT="$SCANNED_PDF" \
  DOCUMENT_OCR_PIPELINE_SMOKE_OUTPUT="$SCANNED_PDF_REPORT" \
  "$APP_EXECUTABLE"
"$PYTHON" - "$SCANNED_PDF" "$SCANNED_PDF_REPORT" <<'PY'
import json
import sys
from pathlib import Path

import fitz

pdf_path = Path(sys.argv[1])
report_path = Path(sys.argv[2])
with fitz.open(pdf_path) as document:
    if document.page_count != 1:
        raise SystemExit("扫描 PDF 页数不符合测试预期。")
    if sum(len(page.get_images(full=True)) for page in document) < 1:
        raise SystemExit("扫描 PDF 没有图像内容。")
    native_text = "".join(page.get_text("text") for page in document).strip()
if native_text:
    raise SystemExit("扫描 PDF 意外包含可复制文本层。")
if not report_path.is_file():
    raise SystemExit("冻结客户端未生成扫描 PDF 测试报告。")
report = json.loads(report_path.read_text(encoding="utf-8"))
recognized = report.get("text", "")
if report.get("ocr_blocks", 0) < 1:
    raise SystemExit("冻结客户端没有识别扫描 PDF。")
if "macOS" not in recognized or "OCR" not in recognized:
    raise SystemExit(f"扫描 PDF 的关键文字未被识别：{recognized!r}")
if len(report.get("outputs", [])) != 2:
    raise SystemExit("扫描 PDF 未生成 TXT 和 Markdown 两个输出。")
for output in report["outputs"]:
    if not Path(output).is_file():
        raise SystemExit(f"扫描 PDF 流水线输出不存在：{output}")
print(
    "[scanned-pdf] native_text=0 blocks={ocr_blocks} outputs={outputs}".format(
        ocr_blocks=report["ocr_blocks"],
        outputs=len(report["outputs"]),
    )
)
PY

ditto -c -k --sequesterRsrc --keepParent "$PACKAGE_ROOT" "$ZIP_PATH"
mkdir -p "$DMG_ROOT"
cp -R "$APP_PATH" "$DMG_ROOT/文档OCR助手.app"
cp "$ROOT/packaging/使用说明-macos.txt" "$DMG_ROOT/使用说明.txt"
ln -s /Applications "$DMG_ROOT/Applications"
hdiutil create \
  -volname "文档OCR助手" \
  -srcfolder "$DMG_ROOT" \
  -ov \
  -format UDZO \
  "$DMG_PATH"
shasum -a 256 "$ZIP_PATH" "$DMG_PATH" > "$CHECKSUM_PATH"

echo "[done] App: $APP_PATH"
echo "[done] ZIP: $ZIP_PATH"
echo "[done] DMG: $DMG_PATH"
echo "[done] SHA-256: $CHECKSUM_PATH"
echo "[done] UI screenshot: $UI_SCREENSHOT"
echo "[done] Frozen OCR/table smoke: $PIPELINE_REPORT"
echo "[done] Frozen scanned-PDF OCR smoke: $SCANNED_PDF_REPORT"
