import os
import time


DEFAULT_WINDOW_WIDTH = 1152
DEFAULT_WINDOW_HEIGHT = 944
MIN_WINDOW_WIDTH = 1040
MIN_WINDOW_HEIGHT = 760


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
