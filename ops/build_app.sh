#!/bin/bash
# Build ~/Applications/tradefabe.app from scratch (issue #61).
#
# The bundle used to exist only as three hand-made files on one machine, so losing it
# meant reconstructing it from memory. This is that reconstruction, in git.
#
# Usage:  ops/build_app.sh [--dest DIR] [--repo DIR]
set -euo pipefail

# pwd -P, not pwd: the repo has a compatibility symlink at the old ~/Documents location,
# and a launcher that baked the symlinked path would still route the app through iCloud.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
DEST="$HOME/Applications"

while [ $# -gt 0 ]; do
  case "$1" in
    --dest) DEST="$2"; shift 2 ;;
    --repo) REPO="$(cd "$2" && pwd -P)"; shift 2 ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

APP="$DEST/tradefabe.app"
VENV_BIN="$REPO/.venv/bin"

[ -x "$VENV_BIN/tradefabe-app" ] || {
  echo "error: $VENV_BIN/tradefabe-app not found." >&2
  echo "       run:  $REPO/.venv/bin/pip install -e '$REPO[dev]'" >&2
  exit 1
}

echo "==> building $APP"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>tradefabe</string>
  <key>CFBundleDisplayName</key><string>tradefabe</string>
  <key>CFBundleIdentifier</key><string>com.dzheng.tradefabe.desktop</string>
  <key>CFBundleVersion</key><string>0.1.0</string>
  <key>CFBundleExecutable</key><string>tradefabe</string>
  <key>CFBundleIconFile</key><string>icon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST

# PYTHONPATH is not optional here. Without it the app hits the Python 3.14 hidden-.pth
# bug (CLAUDE.md's Known gaps, issue #60): a sandboxed shell can stamp the editable
# install's .pth file macOS-'hidden', and 3.14's site module silently skips hidden .pth
# files, so `import tradefabe` fails on a perfectly good install. A GUI app gets no shell
# profile, so there is nothing else to fall back on.
cat > "$APP/Contents/MacOS/tradefabe" <<LAUNCH
#!/bin/zsh
export PYTHONPATH="$REPO/src\${PYTHONPATH:+:\$PYTHONPATH}"
exec "$VENV_BIN/tradefabe-app"
LAUNCH
chmod +x "$APP/Contents/MacOS/tradefabe"

if [ -f "$REPO/ops/icon.icns" ]; then
  cp "$REPO/ops/icon.icns" "$APP/Contents/Resources/icon.icns"
elif [ -f "$APP.bak/Contents/Resources/icon.icns" ]; then
  cp "$APP.bak/Contents/Resources/icon.icns" "$APP/Contents/Resources/icon.icns"
else
  echo "    note: no ops/icon.icns -- bundle gets the generic icon."
  echo "          add one with: ops/build_app.sh --help"
fi

# macOS caches bundle metadata aggressively; without this the Dock can keep showing the
# old icon (or none) after a rebuild.
touch "$APP"
/usr/bin/plutil -lint "$APP/Contents/Info.plist" >/dev/null

echo "==> built. verifying it can import the package the same way the app will:"
env -i PATH=/usr/bin:/bin PYTHONPATH="$REPO/src" "$VENV_BIN/python" -c "
from tradefabe.desktop import main
import webview          # deferred inside main(), so import it explicitly here --
                        # otherwise a missing pywebview passes this check and the
                        # bundle still fails to open
print('    desktop entry point + webview import OK')"

echo
echo "done: $APP"
echo "open it with:  open '$APP'"
