# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for TransfPro macOS .app bundle.

Usage:
    pip install pyinstaller
    cd transfpro
    pyinstaller transfpro.spec
"""
import os
import sys
from pathlib import Path

block_cipher = None

# Project root (where this .spec file lives)
ROOT = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    [os.path.join(ROOT, 'main.py')],
    pathex=[ROOT],
    binaries=[],
    datas=[
        # Include the icon and any resources
        (os.path.join(ROOT, 'resources', 'transfpro_icon.png'), 'resources'),
        (os.path.join(ROOT, 'resources', 'transfpro_icon.icns'), 'resources'),
    ],
    hiddenimports=[
        'paramiko',
        'cryptography',
        'PyQt5.sip',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # keyring accesses macOS Keychain and triggers permission prompts
        'keyring', 'keyring.backends',
        # Heavy libraries not used by TransfPro
        'matplotlib', 'matplotlib.backends',
        'pyqtgraph',
        'numpy', 'scipy', 'pandas',
        'PIL', 'Pillow',
        # Standard library modules not needed at runtime
        'tkinter', 'unittest', 'test',
        'xmlrpc', 'pydoc', 'doctest',
        'lib2to3', 'ensurepip', 'idlelib',
        'distutils', 'setuptools', 'pkg_resources',
        # Unused Qt modules (save ~20 MB each)
        'PyQt5.QtWebEngine', 'PyQt5.QtWebEngineWidgets',
        'PyQt5.QtWebEngineCore',
        'PyQt5.QtMultimedia', 'PyQt5.QtMultimediaWidgets',
        'PyQt5.QtBluetooth', 'PyQt5.QtNfc',
        'PyQt5.QtPositioning', 'PyQt5.QtLocation',
        'PyQt5.QtSensors', 'PyQt5.QtSerialPort',
        'PyQt5.QtSql', 'PyQt5.QtXml', 'PyQt5.QtXmlPatterns',
        'PyQt5.QtDesigner', 'PyQt5.QtHelp',
        'PyQt5.QtOpenGL', 'PyQt5.Qt3DCore', 'PyQt5.Qt3DRender',
        'PyQt5.QtQuick', 'PyQt5.QtQml',
        'PyQt5.QtTest', 'PyQt5.QtDBus',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TransfPro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    console=False,  # No terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,  # Disabled: causes macOS permission prompts via Apple Events
    target_arch=None,
    # For distribution: set your Apple Developer identity here
    # e.g., codesign_identity='Developer ID Application: Your Name (TEAMID)',
    # and create entitlements.plist with com.apple.security.network.client = true
    codesign_identity=os.environ.get('CODESIGN_IDENTITY', None),
    entitlements_file=os.path.join(ROOT, 'entitlements.plist') if os.path.exists(os.path.join(ROOT, 'entitlements.plist')) else None,
    icon=os.path.join(ROOT, 'resources', 'transfpro_icon.icns'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=True,
    upx=True,
    upx_exclude=[],
    name='TransfPro',
)

app = BUNDLE(
    coll,
    name='TransfPro.app',
    icon=os.path.join(ROOT, 'resources', 'transfpro_icon.icns'),
    bundle_identifier='com.transfpro.app',
    info_plist={
        'CFBundleName': 'TransfPro',
        'CFBundleDisplayName': 'TransfPro',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSHighResolutionCapable': True,
        'NSRequiresAquaSystemAppearance': False,  # Support dark mode
        'LSMinimumSystemVersion': '10.15',
    },
)
