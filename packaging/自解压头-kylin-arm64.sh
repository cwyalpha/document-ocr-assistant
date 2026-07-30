#!/usr/bin/env bash
set -euo pipefail

SELF="$0"
LINE="$(awk '/^__DOCUMENT_OCR_PAYLOAD__$/ {print NR + 1; exit}' "$SELF")"
TARGET="$(cd "$(dirname "$SELF")" && pwd)"
tail -n +"$LINE" "$SELF" | tar -xzf - -C "$TARGET"
exec "$TARGET/文档OCR助手-kylin-v10-arm64-cli/文档OCR助手命令行.sh" "$@"
__DOCUMENT_OCR_PAYLOAD__
