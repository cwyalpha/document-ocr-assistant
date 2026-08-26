#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM=""
if [ "${1:-}" = "--platform" ]; then
  PLATFORM="${2:-}"
fi
case "$PLATFORM" in
  macos)
    COMMAND=("$ROOT/scripts/build_macos.sh")
    ;;
  windows)
    if ! command -v pwsh >/dev/null 2>&1; then
      echo "[error] Windows 矩阵请在 PowerShell 7 环境执行。" >&2
      exit 2
    fi
    COMMAND=(pwsh -File "$ROOT/scripts/build_windows.ps1" -Edition)
    ;;
  kylin-x86_64)
    COMMAND=("$ROOT/scripts/build_kylin_offline.sh")
    ;;
  kylin-arm64)
    COMMAND=("$ROOT/scripts/build_kylin_arm64_docker.sh")
    ;;
  *)
    echo "用法：$0 --platform macos|windows|kylin-x86_64|kylin-arm64" >&2
    exit 2
    ;;
esac

EDITIONS=(ocr full)
if [ "$PLATFORM" = "kylin-arm64" ]; then
  EDITIONS=(full)
fi
for edition in "${EDITIONS[@]}"; do
  if [ "$PLATFORM" = "windows" ]; then
    "${COMMAND[@]}" "$edition"
  else
    "${COMMAND[@]}" --edition "$edition"
  fi
done

echo "[done] $PLATFORM 构建矩阵已生成：${EDITIONS[*]}。"
