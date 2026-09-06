#!/bin/zsh
set -eu
cd "${0:A:h:h}"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
export MASHUP_DATA="${MASHUP_DATA:-$HOME/Library/Application Support/Mashup Studio}"
mashup_local="$MASHUP_DATA"
if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then
  print -u2 'This installer currently supports macOS on Apple Silicon only.'
  exit 1
fi
for dependency in uv git node npm ffmpeg ffprobe clang++; do
  if ! command -v "$dependency" >/dev/null; then
    print -u2 "Missing $dependency. See the prerequisites in README.md."
    exit 1
  fi
done
node -e 'const [a,b]=process.versions.node.split(".").map(Number); if(a<22 || (a===22 && b<19)){console.error("Node.js 22.19+ required");process.exit(1)}'
uv venv --python 3.11 --allow-existing "$mashup_local/runtime"
uv pip install --python "$mashup_local/runtime/bin/python" -r requirements.txt
if [[ ! -d "$mashup_local/automashup" ]]; then
  git clone https://github.com/ax-le/automashup.git "$mashup_local/automashup"
fi
git -C "$mashup_local/automashup" checkout c20d410f24568af23a5db948084746a5e13c8874
uv pip install --python "$mashup_local/runtime/bin/python" --no-deps -e "$mashup_local/automashup"
"$mashup_local/runtime/bin/python" -m scripts.install_local
cd "$mashup_local/app"
"$mashup_local/runtime/bin/python" -m scripts.build_rubberband
cd web
NODE_OPTIONS="${NODE_OPTIONS:-} --use-system-ca" npm ci
npm run build
print 'Ready. Open "Buckswood auto Mashup.command" from the repository.'
