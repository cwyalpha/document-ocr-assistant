#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPLICATIONS="$HOME/.local/share/applications"
EDITION="$(sed -n 's/.*"edition"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$ROOT/build-info.json" | head -n 1)"
if [ "$EDITION" = "ocr" ]; then
  APP_NAME="文档OCR助手 OCR版"
  COMMENT="离线图片与 PDF OCR"
else
  APP_NAME="文档OCR助手 完整版"
  COMMENT="离线图片、PDF、Word 与表格 OCR"
fi
DESKTOP_FILE="$APPLICATIONS/document-ocr-assistant-$EDITION.desktop"
mkdir -p "$APPLICATIONS"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=$APP_NAME
Comment=$COMMENT
Exec=$ROOT/启动文档OCR助手.sh
Icon=$ROOT/assets/app-icon.svg
Terminal=false
Categories=Office;Utility;
StartupNotify=true
StartupWMClass=$APP_NAME
EOF
chmod +x "$DESKTOP_FILE"

DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
if [ -n "$DESKTOP_DIR" ] && [ -d "$DESKTOP_DIR" ]; then
  cp "$DESKTOP_FILE" "$DESKTOP_DIR/$APP_NAME.desktop"
  chmod +x "$DESKTOP_DIR/$APP_NAME.desktop"
fi
echo "快捷方式已安装：$DESKTOP_FILE"
