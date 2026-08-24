#!/usr/bin/env bash
#
# Register the GUI with GNOME for the current user (no root, no system files).
#
# The .desktop file is generated rather than shipped ready-made because Exec=
# needs the absolute path of this checkout, which differs per machine.
#
#   ./gui/install.sh            install / update
#   ./gui/install.sh --uninstall  remove

set -euo pipefail

APP_ID="io.github.blumoon77.UrlToMarkdown"
GUI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$GUI_DIR")"

# Deliberately ignore XDG_DATA_HOME when it points inside a snap sandbox.
# Running this from a terminal inside snap-packaged VS Code sets it to
# ~/snap/<app>/<rev>/.local/share, which the desktop shell never reads, so the
# launcher would install "successfully" and then not exist.
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
case "$DATA_HOME" in
    "$HOME"/snap/*|/var/snap/*|"$HOME"/.var/app/*)
        echo "Ignoring sandboxed XDG_DATA_HOME ($DATA_HOME)"
        DATA_HOME="$HOME/.local/share"
        ;;
esac

DESKTOP_DIR="$DATA_HOME/applications"
ICON_DIR="$DATA_HOME/icons/hicolor/scalable/apps"
DESKTOP_FILE="$DESKTOP_DIR/$APP_ID.desktop"
ICON_FILE="$ICON_DIR/$APP_ID.svg"

if [[ "${1:-}" == "--uninstall" ]]; then
    rm -f "$DESKTOP_FILE" "$ICON_FILE"
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
    echo "Removed $APP_ID"
    exit 0
fi

# Fail early rather than installing a launcher that can't work.
if ! python3 -c "import gi; gi.require_version('Gtk','4.0'); gi.require_version('Adw','1')" 2>/dev/null; then
    echo "Missing GTK4/libadwaita Python bindings. Install them with:" >&2
    echo "  sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1" >&2
    exit 1
fi

if [[ ! -f "$REPO_DIR/src/index.js" ]]; then
    echo "Cannot find $REPO_DIR/src/index.js - run this from inside the checkout." >&2
    exit 1
fi

mkdir -p "$DESKTOP_DIR" "$ICON_DIR"
install -m 0644 "$GUI_DIR/$APP_ID.svg" "$ICON_FILE"
chmod +x "$GUI_DIR/url_to_markdown_gui.py"

cat > "$DESKTOP_FILE" <<DESKTOP
[Desktop Entry]
Type=Application
Name=URL to Markdown
GenericName=Web Page Converter
Comment=Convert a web page into clean Markdown
Exec=$GUI_DIR/url_to_markdown_gui.py %u
Icon=$APP_ID
Terminal=false
Categories=Utility;TextTools;
Keywords=markdown;html;scrape;convert;web;llm;
StartupNotify=true
StartupWMClass=$APP_ID
DESKTOP

chmod 0644 "$DESKTOP_FILE"

update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
gtk-update-icon-cache -f -t "$DATA_HOME/icons/hicolor" 2>/dev/null || true

if command -v desktop-file-validate >/dev/null 2>&1; then
    desktop-file-validate "$DESKTOP_FILE" && echo "Desktop entry validates."
fi

echo "Installed:"
echo "  $DESKTOP_FILE"
echo "  $ICON_FILE"
echo
echo "Look for 'URL to Markdown' in the app grid. If it doesn't show up yet,"
echo "log out and back in - GNOME caches the application list."
