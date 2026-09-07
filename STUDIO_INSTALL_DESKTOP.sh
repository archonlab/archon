#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "STUDIO_INSTALL_DESKTOP.sh currently installs the Linux desktop-menu entry only." >&2
  echo "Use ./ARCHON_STUDIO.sh directly on this platform." >&2
  exit 2
fi

APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ENTRY="$APP_DIR/archon-studio.desktop"
mkdir -p "$APP_DIR"

# Desktop Entry Exec accepts double-quoted absolute paths. Escape the only
# characters that are special inside that quoted field.
escape_exec() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/`/\\`/g; s/\$/\\$/g'
}
ROOT_Q="$(escape_exec "$ROOT")"
LAUNCHER_Q="$(escape_exec "$ROOT/ARCHON_STUDIO.sh")"

cat > "$ENTRY" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=ARCHON Studio
Comment=Project ARCHON scientific research studio
Exec="$LAUNCHER_Q"
Path=$ROOT_Q
Terminal=false
Categories=Science;Development;
StartupNotify=true
StartupWMClass=ARCHONStudio
Icon=applications-science
EOF
chmod 0755 "$ENTRY"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
fi
printf 'Installed ARCHON Studio desktop entry:\n  %s\n' "$ENTRY"
printf 'Launch it from your application menu as “ARCHON Studio”.\n'
