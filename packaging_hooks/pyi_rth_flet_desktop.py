"""Use the desktop runtime bundled in the Windows executable, without downloads."""

import os
import sys
from pathlib import Path


if getattr(sys, 'frozen', False) and sys.platform == 'win32':
    desktop = Path(sys._MEIPASS) / 'flet_desktop' / 'app' / 'flet'
    for required in ('flet.exe', 'flutter_windows.dll', 'data/app.so', 'data/icudtl.dat'):
        if not (desktop / required).is_file():
            raise RuntimeError('Falta un archivo del cliente Flet incluido: ' + required)
    os.environ['FLET_VIEW_PATH'] = str(desktop)
