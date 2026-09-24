# -*- mode: python ; coding: utf-8 -*-

from importlib.metadata import version
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files
from flet_desktop import ensure_client_cached

if version('flet') != version('flet-desktop'):
    raise RuntimeError('flet and flet-desktop must have matching versions.')

# Resolve the official client at build time, never on the user's first launch.
desktop_dir = ensure_client_cached() / 'flet'
for required in ('flet.exe', 'flutter_windows.dll', 'data/app.so', 'data/icudtl.dat'):
    if not (desktop_dir / required).is_file():
        raise RuntimeError('Incomplete Flet desktop runtime: ' + str(desktop_dir / required))

flet_data = [(str(desktop_dir), 'flet_desktop/app/flet')]
flet_data += collect_data_files('flet.controls.material', includes=['icons.json'])
flet_data += collect_data_files('flet.controls.cupertino', includes=['cupertino_icons.json'])

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets/icons/icono.png', 'assets/icons'),
        ('assets/backgrounds/L4D2 BACKGROUND.png', 'assets/backgrounds'),
        ('assets/glows/survivors/ELLIS salud alta.png',
         'assets/glows/survivors'),
        ('assets/glows/survivors/ELLIS salud media.png',
         'assets/glows/survivors'),
        ('assets/glows/survivors/ELLIS VIDA BAJA.png',
         'assets/glows/survivors'),
        ('assets/glows/survivors/ELLIS SALUD CRITICA.png',
         'assets/glows/survivors'),
        ('assets/glows/survivors/COMPAÑEROS DE EQUIPO GLOW.png',
         'assets/glows/survivors'),
        ('assets/glows/survivors/ELLIS INCAPACITADO GLOW.png',
         'assets/glows/survivors'),
        ('assets/glows/survivors/ELLIS GLOW VOMITADO.png',
         'assets/glows/survivors'),
        ('assets/glows/infected/HUNTER glow dominante.png',
         'assets/glows/infected'),
        ('assets/glows/infected/HUNTER dominante glow mask.png',
         'assets/glows/infected'),
        ('assets/glows/infected/HUNTER GLOW INFECTADO ESPECIAL.png',
         'assets/glows/infected'),
        ('assets/glows/infected/GLOW SUPERVIVIENTE VOMITADO COMO INFECTADO.png',
         'assets/glows/infected'),
        ('assets/glows/infected/WICH AGRESVIA GLOW.png',
         'assets/glows/infected'),
        ('assets/glows/infected/WITCH agresiva glow mask.png',
         'assets/glows/infected'),
        ('assets/glows/objects/GLOW ITEMS SIN MESA.png',
         'assets/glows/objects'),
        ('l4d2_core.py', '.'),
    ] + flet_data,
    hiddenimports=['flet_desktop'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(Path(SPECPATH) / 'packaging_hooks' / 'pyi_rth_flet_desktop.py')],
    excludes=[],
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
    name='L4D2 Mod Loader',
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
    icon=['assets/icons/icon.ico'],
)
