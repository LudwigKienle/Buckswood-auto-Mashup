#!/bin/zsh
set -eu
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
export MASHUP_DATA="${MASHUP_DATA:-$HOME/Library/Application Support/Mashup Studio}"
mashup_local="$MASHUP_DATA"
if [[ ! -x "$mashup_local/runtime/bin/python" || ! -f "$mashup_local/app/studio/server.py" ]]; then
  print 'Bitte zuerst scripts/setup.sh im Projektordner ausführen.'
  exit 1
fi
cd "$mashup_local/app"
exec "$mashup_local/runtime/bin/python" -m scripts.launch "$@"
