#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# Kids Learning Channel — Daily Upload Pipeline
# Runs automatically via cron at 9:00 AM EST every day.
#
# What it does:
#   1. Loads environment (GEMINI_API_KEY)
#   2. Uploads up to 5 pending videos from the kids' channel queue
#   3. Appends a timestamped log entry to logs/kids_pipeline.log
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPT_DIR/logs/kids_pipeline.log"
PYTHON="$(which python3)"

# ── Load environment ──────────────────────────────────────────────────────────
# Cron doesn't source .zshrc automatically, so we do it here.
# If GEMINI_API_KEY is set via another method (e.g. a secrets manager),
# you can remove these source lines.
[ -f "$HOME/.zshrc" ]       && source "$HOME/.zshrc"       2>/dev/null || true
[ -f "$HOME/.bash_profile" ] && source "$HOME/.bash_profile" 2>/dev/null || true
[ -f "$HOME/.bashrc" ]      && source "$HOME/.bashrc"      2>/dev/null || true

# ── Verify API key is available ───────────────────────────────────────────────
if [ -z "${GEMINI_API_KEY:-}" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')]  ❌  GEMINI_API_KEY is not set. Aborting." >> "$LOG_FILE"
    exit 1
fi

# ── Run scheduler ─────────────────────────────────────────────────────────────
echo "" >> "$LOG_FILE"
echo "════════════════════════════════════════" >> "$LOG_FILE"
echo "[$(date '+%Y-%m-%d %H:%M:%S')]  🚀  Kids Pipeline starting..." >> "$LOG_FILE"

cd "$SCRIPT_DIR"

"$PYTHON" scheduler.py \
    --run-now \
    --channel "Kids Learning" \
    --config scheduler_config.json \
    >> "$LOG_FILE" 2>&1

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')]  ✅  Kids Pipeline finished successfully." >> "$LOG_FILE"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')]  ❌  Kids Pipeline exited with code $EXIT_CODE." >> "$LOG_FILE"
fi

exit $EXIT_CODE
