# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for siphon-collector

Build with: pyinstaller collector.spec
"""

import sys
from pathlib import Path

# Get the project root directory
project_root = Path(SPECPATH)

a = Analysis(
    [str(project_root / 'src' / 'session_siphon' / 'collector' / '__main__.py')],
    pathex=[str(project_root / 'src')],
    binaries=[],
    datas=[],
    hiddenimports=[
        'session_siphon',
        'session_siphon.collector',
        'session_siphon.collector.copier',
        'session_siphon.collector.daemon',
        'session_siphon.collector.sources',
        'session_siphon.collector.state',
        'session_siphon.config',
        'session_siphon.logging',
        'session_siphon.models',
        'watchdog',
        'watchdog.observers',
        'watchdog.events',
        'yaml',
        'click',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude processor-only dependencies to reduce binary size
        'typesense',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='siphon-collector',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
