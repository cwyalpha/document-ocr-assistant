#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPONENTS_DIR="${OCR_OFFLINE_COMPONENTS:-$ROOT/offline_components}"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
BUILD_VENV="${OCR_BUILD_VENV:-$ROOT/.build-venv}"
CACHE_DIR="$ROOT/.build-cache"
TABLE_MODEL="${DOCUMENT_OCR_TABLE_MODEL:-$CACHE_DIR/slanet-plus.onnx}"
PACKAGE_NAME="文档OCR助手-linux-x86_64"
PACKAGE_ROOT="$ROOT/dist/$PACKAGE_NAME"

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
  "$PYTHON_BIN" -m venv "$BUILD_VENV"
fi
PYTHON="$BUILD_VENV/bin/python"
"$PYTHON" -m pip install --upgrade pip wheel setuptools
"$PYTHON" -m pip install -r "$ROOT/requirements-kylin.txt" -r "$ROOT/requirements-table.txt"
"$PYTHON" -m pip install "pyinstaller==6.18.0" "pyinstaller-hooks-contrib==2026.0"

if [ ! -f "$TABLE_MODEL" ]; then
  "$PYTHON" "$ROOT/scripts/fetch_table_model.py" "$TABLE_MODEL"
fi

rm -rf "$ROOT/build/pyinstaller" "$ROOT/dist/文档OCR助手" "$PACKAGE_ROOT"
mkdir -p "$PACKAGE_ROOT"
"$PYTHON" -m PyInstaller \
  --noconfirm \
  --clean \
  --distpath "$ROOT/dist" \
  --workpath "$ROOT/build/pyinstaller" \
  "$ROOT/packaging/document_ocr_assistant.spec"

mkdir -p "$PACKAGE_ROOT/app" "$PACKAGE_ROOT/assets"
mv "$ROOT/dist/文档OCR助手" "$PACKAGE_ROOT/app/文档OCR助手"
cp "$ROOT/assets/app-icon.svg" "$PACKAGE_ROOT/assets/app-icon.svg"
cp "$ROOT/packaging/启动文档OCR助手.sh" "$PACKAGE_ROOT/启动文档OCR助手.sh"
cp "$ROOT/packaging/安装快捷方式.sh" "$PACKAGE_ROOT/安装快捷方式.sh"
chmod +x "$PACKAGE_ROOT/启动文档OCR助手.sh" "$PACKAGE_ROOT/安装快捷方式.sh"

"$PYTHON" "$ROOT/scripts/prepare_offline_components.py" \
  --components-dir "$COMPONENTS_DIR" \
  --output-root "$PACKAGE_ROOT" \
  --table-model "$TABLE_MODEL"

cat > "$PACKAGE_ROOT/使用说明.txt" <<'EOF'
文档OCR助手（Kylin x86_64 离线版）

1. 双击“启动文档OCR助手.sh”即可运行。
2. 如需应用菜单和桌面图标，执行“安装快捷方式.sh”。
3. 所有 OCR、表格识别和 Word 转换均在本机离线执行。
4. 支持拖入图片、PDF、DOC/DOCX/WPS、文件夹及 ZIP/RAR/7Z/TAR/TAR.GZ/TGZ。
5. 默认输出 TXT 和 Markdown；可选生成带文本层的可搜索 PDF。
6. 批量识别可勾选“复制未转换文件”（默认关闭），将目录或压缩包内其他文件按原层级复制到新批次目录。
7. 关闭主窗口时默认询问缩小到右下角或退出；可选择记住，并可在设置页修改。
EOF

RUN_FILE="$ROOT/dist/$PACKAGE_NAME.run"
rm -f "$RUN_FILE"
cat > "$RUN_FILE" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
SELF="$0"
LINE="$(awk '/^__DOCUMENT_OCR_PAYLOAD__$/ {print NR + 1; exit}' "$SELF")"
TARGET="$(cd "$(dirname "$SELF")" && pwd)"
tail -n +"$LINE" "$SELF" | tar -xzf - -C "$TARGET"
exec "$TARGET/文档OCR助手-linux-x86_64/启动文档OCR助手.sh"
__DOCUMENT_OCR_PAYLOAD__
EOF
tar -czf - -C "$ROOT/dist" "$PACKAGE_NAME" >> "$RUN_FILE"
chmod +x "$RUN_FILE"

echo "[done] 目录包：$PACKAGE_ROOT"
echo "[done] 自解压包：$RUN_FILE"
