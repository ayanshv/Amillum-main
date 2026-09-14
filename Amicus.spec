# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all
from pathlib import Path

datas = [('assets', 'assets'), ('icons', 'icons'), ('styles', 'styles'), ('screens', 'screens')]
binaries = []
hiddenimports = ['native.macos.runtime', 'native.macos.overlay', 'Quartz', 'AppKit', 'ApplicationServices', 'Vision', 'ScreenCaptureKit', 'PyObjCTools.AppHelper']
tmp_ret = collect_all('nicegui')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(Path(SPECPATH) / 'native' / 'macos' / 'frozen_hook.py')],
    excludes=['backend.api', 'backend.provider_engine'],
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
    name='Amillum',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
app = BUNDLE(
    exe,
    name='Amillum.app',
    icon=None,
    bundle_identifier='Amicus',
)
