# dmgbuild settings for TransfPro installer DMG.
# Used by create_dmg.sh via: dmgbuild -s dmg_settings.py "Install TransfPro" dist/TransfPro-Installer.dmg

import os
import sys

APP_NAME = "TransfPro"
# dmgbuild exec()s this file, so __file__ isn't available.
# The settings file path is passed as the first defines key by dmgbuild,
# but safest to use cwd (create_dmg.sh cd's to SCRIPT_DIR first).
SCRIPT_DIR = os.getcwd()

# Debug: print paths so we can verify they're correct
_bg = os.path.join(SCRIPT_DIR, "resources", "dmg_background.png")
print(f"[dmg_settings] SCRIPT_DIR = {SCRIPT_DIR}", file=sys.stderr)
print(f"[dmg_settings] background = {_bg}", file=sys.stderr)
print(f"[dmg_settings] background exists = {os.path.exists(_bg)}", file=sys.stderr)
if os.path.exists(_bg):
    from PIL import Image
    img = Image.open(_bg)
    px = img.getpixel((10, 10))
    print(f"[dmg_settings] background pixel(10,10) = {px}", file=sys.stderr)

# Volume format
format = "UDZO"
size = None  # auto-calculate

# Files to include
files = [
    (os.path.join(SCRIPT_DIR, "dist", f"{APP_NAME}.app"), f"{APP_NAME}.app"),
]
symlinks = {
    "Applications": "/Applications",
}

# Volume icon
icon = os.path.join(SCRIPT_DIR, "resources", "transfpro_icon.icns")

# Window appearance
background = _bg
window_rect = ((200, 120), (600, 400))
default_view = "icon-view"
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False

# Icon view options
icon_size = 100
text_size = 14
icon_locations = {
    f"{APP_NAME}.app": (150, 190),
    "Applications": (450, 190),
}
