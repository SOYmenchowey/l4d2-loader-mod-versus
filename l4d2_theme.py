import os
import sys


BG = "#0C0C10"
SURFACE = "#16161C"
SURFACE_2 = "#1E1E26"
BORDER = "#2A2A33"
TEXT = "#F2F2F5"
TEXT_DIM = "#8B8B96"
ACCENT = "#4ADE80"
ACCENT_SOFT = "#1B3A2A"
DANGER = "#F87171"
DANGER_SOFT = "#351D24"
AMBER = "#F59E0B"
AMBER_SOFT = "#2E2416"
VSCRIPT_BG = "#3A3A46"
VSCRIPT_TEXT = "#D6D6DC"

CATEGORIES = ["Todos", "Favoritos", "Skins", "Armas", "Sonido", "UI",
              "VScripts", "Otro"]

STAR_ICON = "\u2605"
STAR_OUTLINE = "\u2606"
CHECK_MARK = "\u2713"
CROSS_MARK = "\u2715"
WARN_MARK = "\u26A0"


def asset_path(name):
    dirs = [os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
            else None]
    dirs.append(getattr(sys, "_MEIPASS", None))
    dirs.append(os.path.dirname(os.path.abspath(__file__)))
    for directory in dirs:
        if directory:
            candidate = os.path.join(directory, name)
            if os.path.isfile(candidate):
                return candidate
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), name)


ICONO = asset_path("icono.png")
L4D2_BACKGROUND = asset_path("L4D2 BACKGROUND.png")
TIKTOK_URL = "https://www.tiktok.com/@tokyossz"
