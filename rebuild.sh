#!/bin/bash
#
# Clean rebuild TransfPro — removes all build artifacts and rebuilds
# the .app bundle + DMG installer from scratch.
#
# Usage:
#   chmod +x rebuild.sh
#   ./rebuild.sh
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "================================================"
echo "  TransfPro — Clean Rebuild"
echo "================================================"
echo ""

# ── Step 1: Remove old build artifacts ──
echo "[1/4] Cleaning build artifacts..."
rm -rf build/ dist/
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true
echo "      Done."
echo ""

# ── Step 2: Run tests ──
echo "[2/4] Running tests..."
python3 -m pytest tests/ -q
echo ""

# ── Step 3: Build .app ──
echo "[3/4] Building TransfPro.app..."
if ! command -v pyinstaller &> /dev/null; then
    echo "      Installing PyInstaller..."
    pip3 install pyinstaller
fi
pyinstaller transfpro.spec --noconfirm

if [ ! -d "dist/TransfPro.app" ]; then
    echo "ERROR: Build failed."
    exit 1
fi
echo "      dist/TransfPro.app created."
echo ""

# ── Step 4: Create DMG ──
echo "[4/4] Creating DMG installer..."
if ! python3 -c "import dmgbuild" 2>/dev/null; then
    echo "      Installing dmgbuild..."
    pip3 install dmgbuild
fi
rm -f dist/TransfPro-Installer.dmg
dmgbuild -s dmg_settings.py "Install TransfPro" dist/TransfPro-Installer.dmg

if [ ! -f "dist/TransfPro-Installer.dmg" ]; then
    echo "ERROR: DMG creation failed."
    exit 1
fi
echo ""

# ── Done ──
DMG_SIZE=$(du -h dist/TransfPro-Installer.dmg | cut -f1)
echo "================================================"
echo "  Build complete!"
echo "  App: dist/TransfPro.app"
echo "  DMG: dist/TransfPro-Installer.dmg ($DMG_SIZE)"
echo "================================================"
echo ""
echo "  Run:     open dist/TransfPro.app"
echo "  Install: open dist/TransfPro-Installer.dmg"
echo ""
