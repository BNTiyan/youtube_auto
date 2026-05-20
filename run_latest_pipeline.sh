#!/bin/bash
# Local runner for the latest-topic pipeline.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$(which python3)"

[ -f "$HOME/.zshrc" ] && source "$HOME/.zshrc" 2>/dev/null || true
[ -f "$HOME/.bash_profile" ] && source "$HOME/.bash_profile" 2>/dev/null || true
[ -f "$HOME/.bashrc" ] && source "$HOME/.bashrc" 2>/dev/null || true

cd "$SCRIPT_DIR"

mkdir -p latest_videos latest_shorts generated

if [ -n "${LATEST_TOPIC_SOURCE_URL:-}" ]; then
  "$PYTHON" latest_topic_pipeline.py --source-url "$LATEST_TOPIC_SOURCE_URL"
else
  "$PYTHON" latest_topic_pipeline.py
fi

TOPIC_NAME="$("$PYTHON" - <<'PY'
import json
with open("generated/latest_topic_package.json") as f:
    data = json.load(f)
cat = next(iter(data))
item = data[cat]["items"][0]
print(item["name"])
PY
)"

TOPIC_CAT="$("$PYTHON" - <<'PY'
import json
with open("generated/latest_topic_package.json") as f:
    data = json.load(f)
print(next(iter(data)))
PY
)"

"$PYTHON" tech_video_creator.py \
  --item "$TOPIC_NAME" \
  --cat "$TOPIC_CAT" \
  --config generated/latest_topic_package.json \
  --output-dir latest_videos

"$PYTHON" shorts_creator.py \
  --item "$TOPIC_NAME" \
  --cat "$TOPIC_CAT" \
  --config generated/latest_topic_package.json \
  --style tech \
  --output-dir latest_shorts

echo "Latest-topic video and short generated locally."
