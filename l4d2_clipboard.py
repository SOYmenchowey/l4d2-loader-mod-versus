import subprocess
import sys


def _log(log, msg):
    if log:
        try:
            log(msg)
        except Exception:
            pass


def _copy_text_with_windows_clipboard(text, log=None):
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        user32.OpenClipboard.argtypes = [ctypes.c_void_p]
        user32.OpenClipboard.restype = ctypes.c_bool
        user32.EmptyClipboard.restype = ctypes.c_bool
        user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
        user32.SetClipboardData.restype = ctypes.c_void_p
        user32.CloseClipboard.restype = ctypes.c_bool
        kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalFree.argtypes = [ctypes.c_void_p]

        data = (text + "\0").encode("utf-16le")
        if not user32.OpenClipboard(None):
            return False
        handle = None
        try:
            if not user32.EmptyClipboard():
                return False
            handle = kernel32.GlobalAlloc(0x0002, len(data))
            if not handle:
                return False
            locked = kernel32.GlobalLock(handle)
            if not locked:
                return False
            ctypes.memmove(locked, data, len(data))
            kernel32.GlobalUnlock(handle)
            if not user32.SetClipboardData(13, handle):
                return False
            handle = None
            return True
        finally:
            user32.CloseClipboard()
            if handle:
                kernel32.GlobalFree(handle)
    except Exception as ex:
        _log(log, "native clipboard ERR %r" % ex)
        return False


def _copy_text_with_powershell(text, log=None):
    if sys.platform != "win32":
        return False
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "Set-Clipboard -Value ([Console]::In.ReadToEnd())",
            ],
            input=text,
            text=True,
            encoding="utf-8",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
            creationflags=flags,
        )
        return proc.returncode == 0
    except Exception as ex:
        _log(log, "powershell clipboard ERR %r" % ex)
        return False


def _copy_text_with_clip_exe(text, log=None):
    if sys.platform != "win32":
        return False
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.run(
            ["clip"],
            input=text,
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
            creationflags=flags,
        )
        return proc.returncode == 0
    except Exception as ex:
        _log(log, "clip.exe ERR %r" % ex)
        return False


def _copy_text_with_flet(page, text, log=None):
    try:
        clipboard = getattr(page, "clipboard", None)
        if clipboard and hasattr(clipboard, "set"):
            clipboard.set(text)
            return True
        if hasattr(page, "set_clipboard"):
            page.set_clipboard(text)
            return True
    except Exception as ex:
        _log(log, "flet clipboard ERR %r" % ex)
    return False


def copy_text_to_clipboard(page, text, prefer_native=True, log=None):
    native_copiers = (
        _copy_text_with_windows_clipboard,
        _copy_text_with_powershell,
        _copy_text_with_clip_exe,
    )
    if prefer_native:
        for copier in native_copiers:
            if copier(text, log=log):
                return True
    if _copy_text_with_flet(page, text, log=log):
        return True
    if not prefer_native:
        for copier in native_copiers:
            if copier(text, log=log):
                return True
    return False
