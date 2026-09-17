#!/bin/zsh
set -eu
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
SCORE_DATA="${MASHUP_DATA:-$HOME/Library/Application Support/Mashup Studio}"
uv venv --python 3.11 --allow-existing "$SCORE_DATA/score-runtime"
uv pip install --python "$SCORE_DATA/score-runtime/bin/python" -r requirements-score.txt
"$SCORE_DATA/score-runtime/bin/python" -m scripts.download_score
"$SCORE_DATA/runtime/bin/python" -m scripts.install_local
cd "$SCORE_DATA/app/web"
NODE_OPTIONS="${NODE_OPTIONS:-} --use-system-ca" npm ci
npm run build
echo 'SheetSage2 installed. Restart the local studio when no job is running.'
