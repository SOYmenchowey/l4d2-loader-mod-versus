import os
import re
import sys
import csv
import hashlib
import subprocess
from l4d2_migrations import apply_aliases

if sys.platform == "win32":
    import winreg


def _read_text(path, encoding="utf-8"):
    with open(path, encoding=encoding, errors="ignore") as file:
        return file.read()


def _valid_l4d2_root(path):
    if not path:
        return False
    left4dead2 = os.path.join(path, "left4dead2")
    return (os.path.isdir(left4dead2)
            and (os.path.isfile(os.path.join(left4dead2, "gameinfo.txt"))
                 or os.path.isdir(os.path.join(left4dead2, "addons"))))


def resolve_l4d2_path(path):
    if not path:
        return None
    path = os.path.abspath(os.path.expandvars(os.path.expanduser(path)))
    candidates = [
        path,
        os.path.dirname(path),
        os.path.dirname(os.path.dirname(path)),
        os.path.dirname(os.path.dirname(os.path.dirname(path))),
        os.path.join(path, "steamapps", "common", "Left 4 Dead 2"),
        os.path.join(path, "common", "Left 4 Dead 2"),
        os.path.join(path, "Left 4 Dead 2"),
    ]
    for candidate in candidates:
        if _valid_l4d2_root(candidate):
            return candidate
    return None


def _steam_roots_from_registry():
    roots = []
    try:
        locations = [
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam",
             "SteamPath"),
            (winreg.HKEY_LOCAL_MACHINE,
             r"Software\WOW6432Node\Valve\Steam", "InstallPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Valve\Steam",
             "InstallPath"),
        ]
        for hive, subkey, value in locations:
            try:
                key = winreg.OpenKey(hive, subkey)
                root = winreg.QueryValueEx(key, value)[0].replace("/", "\\")
                if root:
                    roots.append(root)
            except OSError:
                pass
    except Exception:
        pass
    return roots


def _available_drive_roots():
    if sys.platform != "win32":
        return ["/"]
    roots = []
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        drive = letter + ":\\"
        if os.path.isdir(drive):
            roots.append(drive)
    return roots


def _common_steam_roots():
    roots = []
    for drive in _available_drive_roots():
        roots.extend([
            os.path.join(drive, "Steam"),
            os.path.join(drive, "SteamLibrary"),
            os.path.join(drive, "Games", "Steam"),
            os.path.join(drive, "Juegos", "Steam"),
            os.path.join(drive, "Program Files", "Steam"),
            os.path.join(drive, "Program Files (x86)", "Steam"),
        ])
    return roots


def _library_roots_from_steam(root):
    roots = [root]
    lib_file = os.path.join(root, "steamapps", "libraryfolders.vdf")
    if os.path.isfile(lib_file):
        try:
            text = _read_text(lib_file)
        except OSError:
            text = ""
        for match in re.finditer(r'"path"\s+"([^"]+)"', text):
            roots.append(match.group(1).replace("\\\\", "\\"))
    return roots


def _dedupe(paths):
    out, seen = [], set()
    for path in paths:
        if not path:
            continue
        normalized = os.path.normcase(os.path.abspath(path))
        if normalized not in seen:
            seen.add(normalized)
            out.append(path)
    return out


def find_l4d2(preferred_path=None):
    preferred = resolve_l4d2_path(preferred_path)
    if preferred:
        return preferred

    steam_roots = _dedupe(_steam_roots_from_registry() + _common_steam_roots())
    library_roots = []
    for root in steam_roots:
        if os.path.isdir(root):
            library_roots.extend(_library_roots_from_steam(root))

    for root in _dedupe(library_roots):
        manifest = os.path.join(root, "steamapps", "appmanifest_550.acf")
        candidate = os.path.join(root, "steamapps", "common",
                                 "Left 4 Dead 2")
        if os.path.isfile(manifest) or _valid_l4d2_root(candidate):
            resolved = resolve_l4d2_path(candidate)
            if resolved:
                return resolved
    return None


def _safe_addon_id(filename, used, source_key=None, workshop=False):
    base = os.path.splitext(filename)[0]
    if workshop and re.fullmatch(r'[0-9]+', base):
        candidate = base
    else:
        # The identity depends on its source, never on directory enumeration
        # order or which other addons happen to be installed this time.
        canonical = (source_key or filename).replace('\\', '/').lower()
        digest = hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:24]
        safe = re.sub(r'[^a-z0-9_.-]+', '_', base.lower()).strip('._-')[:48] or 'addon'
        candidate = 'local_' + safe + '_' + digest
    if candidate.casefold() in used:
        raise ValueError('Dos fuentes comparten la misma identidad de addon: ' + filename)
    used.add(candidate.casefold())
    return candidate


def list_addons(l4d2):
    addons_path = os.path.join(l4d2, "left4dead2", "addons")
    scan_dirs = [
        os.path.join(addons_path, "workshop"),
        addons_path,
    ]
    out = []
    used_ids = set()
    seen_paths = set()
    for folder in scan_dirs:
        if not os.path.isdir(folder):
            continue
        for filename in sorted(os.listdir(folder), key=str.casefold):
            if filename.lower().endswith(".vpk"):
                path = os.path.join(folder, filename)
                if not os.path.isfile(path):
                    continue
                normalized_path = os.path.normcase(os.path.realpath(os.path.abspath(path)))
                if normalized_path in seen_paths:
                    continue
                seen_paths.add(normalized_path)
                try:
                    info = os.stat(path)
                except FileNotFoundError:
                    continue  # Steam can finish/remove a download mid-scan.
                is_workshop = folder != addons_path
                addon_id = _safe_addon_id(
                    filename, used_ids, os.path.relpath(path, addons_path), is_workshop)
                out.append({
                    "id": addon_id,
                    "path": path,
                    "size": info.st_size,
                    "ctime": info.st_ctime,
                    "mtime_ns": info.st_mtime_ns,
                    "source_kind": 'workshop' if is_workshop else 'local',
                })
    return apply_aliases(l4d2, out)


def fmt_size(value):
    if value > 1048576:
        return "%.1f MB" % (value / 1048576)
    return "%.1f KB" % (value / 1024)


def addon_snapshot(addons):
    return frozenset((addon['id'], os.path.normcase(os.path.abspath(addon['path'])),
                      addon['size'], addon.get('mtime_ns', 0)) for addon in addons)


class GameStatusError(OSError):
    """The process check could not prove that mutating game files is safe."""


def l4d2_running():
    try:
        output = subprocess.check_output(
            ["tasklist", "/FO", "CSV", "/NH"],
            stderr=subprocess.DEVNULL,
            creationflags=0x08000000,
            timeout=3,
        ).decode('utf-8', 'replace')
        rows = list(csv.reader(output.splitlines()))
        names = {row[0].casefold() for row in rows if len(row) >= 2}
        if not names:
            raise ValueError('Respuesta vacia o invalida de tasklist')
    except (OSError, ValueError, subprocess.SubprocessError) as ex:
        raise GameStatusError('No se pudo comprobar si L4D2 esta cerrado; no se modifican archivos.') from ex
    return bool(names & {'left4dead2.exe', 'hl2.exe'})
