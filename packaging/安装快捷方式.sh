#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPLICATIONS="$HOME/.local/share/applications"
DESKTOP_FILE="$APPLICATIONS/document-ocr-assistant.desktop"
mkdir -p "$APPLICATIONS"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=文档OCR助手
Comment=离线图片、PDF、Word 与表格 OCR
Exec=$ROOT/启动文档OCR助手.sh
Icon=$ROOT/assets/app-icon.svg
Terminal=false
Categories=Office;Utility;
StartupNotify=true
StartupWMClass=文档OCR助手
EOF
chmod +x "$DESKTOP_FILE"

DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
if [ -n "$DESKTOP_DIR" ] && [ -d "$DESKTOP_DIR" ]; then
  cp "$DESKTOP_FILE" "$DESKTOP_DIR/文档OCR助手.desktop"
  chmod +x "$DESKTOP_DIR/文档OCR助手.desktop"
fi
echo "快捷方式已安装：$DESKTOP_FILE"

