#!/bin/bash
#
# Create a macOS DMG installer for TransfPro
#
# Prerequisites:
#   - TransfPro.app must already be built (run build_app.sh first)
#   - pip install dmgbuild
#
# Usage:
#   cd transfpro
#   chmod +x create_dmg.sh
#   ./create_dmg.sh
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

APP_NAME="TransfPro"
APP_PATH="dist/${APP_NAME}.app"
DMG_NAME="${APP_NAME}-Installer"
DMG_PATH="dist/${DMG_NAME}.dmg"
VOLUME_NAME="Install TransfPro"

# ── Pre-flight checks ──
if [ ! -d "$APP_PATH" ]; then
    echo "ERROR: ${APP_PATH} not found."
    echo "Run ./build_app.sh first to create the application bundle."
    exit 1
fi

# Check / install dmgbuild
if ! python3 -c "import dmgbuild" 2>/dev/null; then
    echo "dmgbuild not found. Installing..."
    pip3 install dmgbuild
fi

# Remove previous DMG if it exists
rm -f "$DMG_PATH"

echo "================================================"
echo "  Creating TransfPro Installer DMG"
echo "================================================"
echo ""

# Build DMG using dmgbuild (no Finder / AppleScript needed)
dmgbuild -s dmg_settings.py "$VOLUME_NAME" "$DMG_PATH"

# ── Verify ──
if [ ! -f "$DMG_PATH" ]; then
    echo "ERROR: DMG creation failed."
    exit 1
fi

DMG_SIZE=$(du -h "$DMG_PATH" | cut -f1)
echo ""
echo "================================================"
echo "  DMG created successfully!"
echo "  Path: $DMG_PATH"
echo "  Size: $DMG_SIZE"
echo "================================================"
echo ""
echo "To install, open the DMG and drag TransfPro to Applications."
echo ""
