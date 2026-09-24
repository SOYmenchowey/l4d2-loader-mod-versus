"""Reentrant process locks for game mutations and shared manifest updates."""

from contextlib import contextmanager
from functools import wraps
import hashlib
import os
import tempfile
import threading
import time


def _key(path):
    canonical = os.path.realpath(os.path.abspath(path)).casefold()
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


_threads = {}
_guard = threading.Lock()
_held = threading.local()


@contextmanager
def resource_lock(path, timeout=15):
    key = _key(path)
    with _guard:
        lock = _threads.setdefault(key, threading.RLock())
    if not lock.acquire(timeout=timeout):
        raise TimeoutError('Otra operacion del loader sigue en curso.')
    held = getattr(_held, 'keys', None)
    if held is None:
        held = _held.keys = set()
    handle = None
    try:
        if key in held:
            yield
            return
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
            kernel.CreateMutexW.restype = wintypes.HANDLE
            kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
            kernel.WaitForSingleObject.restype = wintypes.DWORD
            kernel.ReleaseMutex.argtypes = (wintypes.HANDLE,)
            kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
            handle = kernel.CreateMutexW(None, False, 'Global\\L4D2ModLoader-' + key)
            if not handle:
                raise ctypes.WinError(ctypes.get_last_error())
            status = kernel.WaitForSingleObject(handle, int(timeout * 1000))
            if status not in (0, 0x80):  # An abandoned mutex is acquired, too.
                kernel.CloseHandle(handle)
                handle = None
                if status == 0x102:
                    raise TimeoutError('Otra instancia esta modificando esta instalacion.')
                raise ctypes.WinError(ctypes.get_last_error())
        else:
            import fcntl
            handle = open(os.path.join(tempfile.gettempdir(), 'l4d2-loader-' + key + '.lock'), 'a+b')
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        handle.close()
                        handle = None
                        raise TimeoutError('Otra instancia esta modificando esta instalacion.')
                    time.sleep(0.05)
        held.add(key)
        try:
            yield
        finally:
            held.remove(key)
    finally:
        if handle is not None:
            if os.name == 'nt':
                kernel.ReleaseMutex(handle)
                kernel.CloseHandle(handle)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)
                handle.close()
        lock.release()


def installation_lock(l4d2, timeout=15):
    return resource_lock(l4d2, timeout)


def locked_installation(function):
    @wraps(function)
    def locked(l4d2, *args, **kwargs):
        with installation_lock(l4d2):
            return function(l4d2, *args, **kwargs)
    return locked
