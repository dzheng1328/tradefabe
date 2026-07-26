#!/bin/bash
# Create the project venv OUTSIDE the iCloud-synced tree, symlinked back to .venv (#60).
#
# Why: this repo lives in ~/Documents, which has iCloud Desktop & Documents sync on.
# iCloud stamps files in the synced tree with the macOS `hidden` flag and leaves "<name> 2"
# conflict copies. Python 3.14's site module SILENTLY SKIPS hidden .pth files, so the
# editable install's path file stops working and `import tradefabe` fails after a
# perfectly good install. Putting the venv outside the synced tree removes the cause;
# the symlink keeps every existing path (.venv/bin/pytest, the launchd plists, the .app
# launcher) working unchanged.
#
# Usage:  ops/setup_venv.sh [--venv-home DIR] [--python PATH]
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_HOME="$HOME/.venvs"
PYTHON="${PYTHON:-python3}"

while [ $# -gt 0 ]; do
  case "$1" in
    --venv-home) VENV_HOME="$2"; shift 2 ;;
    --python) PYTHON="$2"; shift 2 ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

TARGET="$VENV_HOME/tradefabe"

case "$TARGET" in
  "$HOME/Documents"/*|"$HOME/Desktop"/*)
    echo "error: $TARGET is inside the iCloud-synced tree, which is the bug this script exists to avoid." >&2
    exit 1 ;;
esac

echo "==> creating $TARGET"
mkdir -p "$VENV_HOME"
rm -rf "$TARGET"
"$PYTHON" -m venv "$TARGET"
"$TARGET/bin/python" -m pip install -q --upgrade pip
echo "==> installing $REPO in editable mode with dev AND desktop extras"
# [desktop] is not optional in practice: pywebview backs the .app entry point, and
# desktop.py imports it LAZILY inside main(), so omitting it leaves an importable module
# and an app that dies on launch. Installing only [dev] here is exactly what broke it.
"$TARGET/bin/pip" install -q -e "$REPO[dev,desktop]"

echo "==> linking $REPO/.venv -> $TARGET"
if [ -e "$REPO/.venv" ] && [ ! -L "$REPO/.venv" ]; then
  mv "$REPO/.venv" "$REPO/.venv.old-$(date +%s)"
  echo "    (existing real .venv moved aside, not deleted)"
fi
rm -f "$REPO/.venv"
ln -s "$TARGET" "$REPO/.venv"

echo "==> verifying import works with NO PYTHONPATH set"
env -u PYTHONPATH "$REPO/.venv/bin/python" -c \
  "import tradefabe; print('    OK ->', tradefabe.__file__)"
# webview specifically: desktop.py defers this import, so a missing pywebview is
# invisible to `import tradefabe.desktop` and only shows up when the app fails to open.
env -u PYTHONPATH "$REPO/.venv/bin/python" -c \
  "import webview; print('    webview OK ->', webview.__version__)"
echo
echo "done. .venv -> $TARGET"
