import os
import time


APP_VERSION = "1.1"
VERSION_LABEL = "Version %s" % APP_VERSION

DEFAULT_WINDOW_WIDTH = 1152
DEFAULT_WINDOW_HEIGHT = 944
MIN_WINDOW_WIDTH = 1040
MIN_WINDOW_HEIGHT = 760


def window_geometry():
    width, height = DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT
    geometry = {}
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        area = wintypes.RECT()
        if hasattr(user32, "SystemParametersInfoW") and user32.SystemParametersInfoW(
                0x0030, 0, ctypes.byref(area), 0):
            left, top, right, bottom = area.left, area.top, area.right, area.bottom
        else:
            left, top = 0, 0
            right, bottom = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        dpi = user32.GetDpiForSystem() if hasattr(user32, "GetDpiForSystem") else 96
        scale = (dpi or 96) / 96
        available_w, available_h = (right - left) / scale, (bottom - top) / scale
        if available_w > 0 and available_h > 0:
            width = min(width, max(1, available_w - 32))
            height = min(height, max(1, available_h - 32))
            geometry.update(left=left / scale + (available_w - width) / 2,
                            top=top / scale + (available_h - height) / 2)
    except (AttributeError, OSError, ValueError):
        pass
    geometry.update(min_width=min(MIN_WINDOW_WIDTH, width),
                    min_height=min(MIN_WINDOW_HEIGHT, height),
                    width=width, height=height)
    return geometry


def cfg_path(name):
    path = os.path.join(os.getenv("LOCALAPPDATA") or os.getcwd(),
                        "L4D2ModLoader")
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass
    return os.path.join(path, name)


def dbg(msg):
    try:
        base = os.getenv("LOCALAPPDATA") or os.getcwd()
        path = os.path.join(base, "L4D2ModLoader")
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, "debug.log"), "a",
                  encoding="utf-8") as file:
            file.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), msg))
    except Exception:
        pass


def debug_log(msg):
    print(msg)
    dbg("core: " + str(msg))
