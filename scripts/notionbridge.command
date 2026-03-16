#!/bin/bash
# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title NotionBridge Sync
# @raycast.mode fullOutput
# @raycast.packageName notionbridge
# @raycast.icon 📕
# Optional parameters:
# @raycast.keyword notionbridge sync
# @raycast.description Sync Xiaohongshu board to Notion DB (local)

set -euo pipefail

PROJECT_DIR="/Users/hawkmor/Documents/NotionBridge"
PYTHON="$PROJECT_DIR/.venv/bin/python"
COOKIES_JSON="$PROJECT_DIR/cookies.json"
GET_COOKIES="$PROJECT_DIR/get_cookies.py"
LOG_DIR="$PROJECT_DIR/logs"
LOCKFILE="/tmp/notionbridge_xhs_sync.lock"

cd "$PROJECT_DIR"

# Prevent double-run
if [ -f "$LOCKFILE" ]; then
  echo "Another sync is running. If not, delete: $LOCKFILE"
  exit 0
fi
trap 'rm -f "$LOCKFILE"' EXIT
touch "$LOCKFILE"

# Basic checks
if [ ! -x "$PYTHON" ]; then
  echo "ERROR: Python not found at $PYTHON"
  echo "Fix: recreate venv: python3 -m venv .venv && pip install -r requirements.txt"
  exit 1
fi

# Load env if present
if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  source "$PROJECT_DIR/.env" || true
  set +a
fi

# Ensure cookies exist (created by get_cookies.py)
if [ ! -f "$COOKIES_JSON" ]; then
  echo "ERROR: cookies.json not found at $COOKIES_JSON"
  if [ -f "$GET_COOKIES" ]; then
    echo "Fix: run cookie login first:"
    echo "  $PYTHON $GET_COOKIES"
  else
    echo "Fix: ensure get_cookies.py exists in $PROJECT_DIR"
  fi
  exit 1
fi

# Quick sanity check: file not empty
if [ ! -s "$COOKIES_JSON" ]; then
  echo "ERROR: cookies.json exists but is empty: $COOKIES_JSON"
  echo "Fix: rerun cookie login: $PYTHON $GET_COOKIES"
  exit 1
fi

mkdir -p "$LOG_DIR"

echo "== notionbridge: start =="
echo "Project : $PROJECT_DIR"
echo "CWD     : $(pwd)"
echo "Python  : $("$PYTHON" -V)"
echo "Cookies : $COOKIES_JSON"
echo "Time    : $(date)"

# Ensure playwright chromium exists (only if playwright is installed in this venv)
if "$PYTHON" -c "import playwright" >/dev/null 2>&1; then
  "$PYTHON" -m playwright install chromium >/dev/null 2>&1 || true
else
  echo "WARN: playwright not installed in venv ($PYTHON)."
  echo "      If your sync requires a browser step, install it with:"
  echo "      $PYTHON -m pip install playwright && $PYTHON -m playwright install chromium"
fi

# Run & tee logs
OUT="$LOG_DIR/$(date +%Y%m%d-%H%M%S).log"
if COOKIE_FILE="$COOKIES_JSON" "$PYTHON" -m app.main 2>&1 | tee "$OUT"; then
  osascript -e 'display notification "同步完成" with title "NotionBridge"'
  echo "== DONE =="
else
  osascript -e 'display notification "同步失败，已打开 logs" with title "NotionBridge"'
  open "$LOG_DIR" || true
  exit 1
fi