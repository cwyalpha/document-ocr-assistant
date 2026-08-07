#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export DOCUMENT_OCR_ROOT="$ROOT"
export SAL_USE_VCLPLUGIN="${SAL_USE_VCLPLUGIN:-svp}"
export QT_AUTO_SCREEN_SCALE_FACTOR="${QT_AUTO_SCREEN_SCALE_FACTOR:-1}"

APP="$ROOT/app/文档OCR助手/文档OCR助手"
if [ ! -x "$APP" ]; then
  echo "未找到文档OCR助手主程序：$APP" >&2
  exit 2
fi
exec "$APP" "$@"
