#!/bin/zsh
set -eu
cd "${0:A:h:h}"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
export MASHUP_DATA="${MASHUP_DATA:-$HOME/Library/Application Support/Mashup Studio}"
mashup_local="$MASHUP_DATA"
if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then
  print -u2 'The HQ separator requires macOS on Apple Silicon.'
  exit 1
fi
if [[ ! -x "$mashup_local/runtime/bin/python" ]]; then
  print -u2 'Run ./scripts/setup.sh first.'
  exit 1
fi
uv venv --python 3.11 --allow-existing "$mashup_local/separation-runtime"
uv pip install --python "$mashup_local/separation-runtime/bin/python" -r requirements-hq.txt
uv pip install --python "$mashup_local/separation-runtime/bin/python" --no-deps mlx-audio==0.5.1
"$mashup_local/runtime/bin/python" -m scripts.install_local
cd "$mashup_local/app"
"$mashup_local/runtime/bin/python" -m scripts.download_roformer
print 'RoFormer is ready. In the studio: Vocals neu trennen.'
