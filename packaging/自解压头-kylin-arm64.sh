#!/usr/bin/env bash
set -euo pipefail

SELF="$0"
LINE="$(awk '/^__DOCUMENT_OCR_PAYLOAD__$/ {print NR + 1; exit}' "$SELF")"
TARGET="$(cd "$(dirname "$SELF")" && pwd)"
PACKAGE="$(tail -n +"$LINE" "$SELF" | tar -tzf - | sed -n '1s#/.*##p')"
tail -n +"$LINE" "$SELF" | tar -xzf - -C "$TARGET"
exec "$TARGET/$PACKAGE/文档OCR助手命令行.sh" "$@"
__DOCUMENT_OCR_PAYLOAD__
