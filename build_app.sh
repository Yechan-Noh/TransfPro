#!/bin/bash
#
# Build TransfPro.app for macOS
#
# Prerequisites:
#   pip install pyinstaller
#
# Optional environment variables for code signing / notarization:
#   CODESIGN_IDENTITY  — Apple Developer ID, e.g.
#       "Developer ID Application: Your Name (TEAMID)"
#   APPLE_ID           — Apple ID email for notarization
#   APPLE_TEAM_ID      — Apple Developer Team ID
#   APPLE_APP_PASSWORD — App-specific password for notarization
#
# Usage:
#   cd transfpro
#   chmod +x build_app.sh
#   ./build_app.sh
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "================================================"
echo "  Building TransfPro.app"
echo "================================================"

# Check pyinstaller is installed
if ! command -v pyinstaller &> /dev/null; then
    echo "PyInstaller not found. Installing..."
    pip install pyinstaller
fi

# Clean previous builds
echo "Cleaning previous builds..."
rm -rf build/ dist/

# Build
echo "Running PyInstaller..."
pyinstaller transfpro.spec --noconfirm

# Check result
if [ ! -d "dist/TransfPro.app" ]; then
    echo "ERROR: Build failed. Check output above."
    exit 1
fi

echo ""
echo "Build successful: dist/TransfPro.app"

# ── Code Signing ──
if [ -n "$CODESIGN_IDENTITY" ]; then
    echo ""
    echo "Code signing with identity: $CODESIGN_IDENTITY"
    codesign --deep --force --options runtime \
        --entitlements entitlements.plist \
        --sign "$CODESIGN_IDENTITY" \
        dist/TransfPro.app
    echo "Code signing complete."
    codesign --verify --verbose dist/TransfPro.app
else
    echo ""
    echo "Skipping code signing (set CODESIGN_IDENTITY to enable)."
fi

# ── Notarization ──
if [ -n "$APPLE_ID" ] && [ -n "$APPLE_TEAM_ID" ] && [ -n "$APPLE_APP_PASSWORD" ]; then
    echo ""
    echo "Creating ZIP for notarization..."
    ditto -c -k --keepParent dist/TransfPro.app dist/TransfPro.zip

    echo "Submitting for notarization..."
    xcrun notarytool submit dist/TransfPro.zip \
        --apple-id "$APPLE_ID" \
        --team-id "$APPLE_TEAM_ID" \
        --password "$APPLE_APP_PASSWORD" \
        --wait

    echo "Stapling notarization ticket..."
    xcrun stapler staple dist/TransfPro.app
    echo "Notarization complete."
else
    echo "Skipping notarization (set APPLE_ID, APPLE_TEAM_ID, APPLE_APP_PASSWORD to enable)."
fi

echo ""
echo "================================================"
echo "  Done!"
echo "  App: dist/TransfPro.app"
echo "================================================"
echo ""
echo "To create a DMG installer:"
echo "  ./create_dmg.sh"
echo ""
echo "To install manually, drag TransfPro.app to /Applications:"
echo "  cp -r dist/TransfPro.app /Applications/"
echo ""
echo "To run directly:"
echo "  open dist/TransfPro.app"
echo ""
