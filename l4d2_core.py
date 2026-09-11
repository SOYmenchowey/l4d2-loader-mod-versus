import os, sys, shutil, re, struct, json, hashlib, tempfile, traceback, difflib, html, stat, threading
import urllib.request
from urllib.parse import urlencode

if sys.platform == "win32":
    import winreg

MANAGED_MARKER = ".l4d2_mod_loader_managed"
RESTORE_STATE_VERSION = 1


def find_l4d2():
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
        steam = winreg.QueryValueEx(k, "SteamPath")[0].replace("/", "\\")
        libs = [os.path.join(steam, "steamapps")]
        libf = os.path.join(steam, "steamapps", "libraryfolders.vdf")
        if os.path.isfile(libf):
            txt = _read_text(libf)
            for m in re.finditer(r'"path"\s+"([^"]+)"', txt):
                libs.append(m.group(1).replace("\\\\", "\\"))
        for lib in libs:
            p = os.path.join(lib, "steamapps", "common", "Left 4 Dead 2")
            if os.path.isdir(p):
                return p
    except Exception:
        pass
    for cand in (r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam",
                 r"D:\Steam", r"E:\Steam", r"F:\Steam"):
        p = os.path.join(cand, "steamapps", "common", "Left 4 Dead 2")
        if os.path.isdir(p):
            return p
    return None


def list_addons(l4d2):
    wp = os.path.join(l4d2, "left4dead2", "addons", "workshop")
    out = []
    if os.path.isdir(wp):
        for f in sorted(os.listdir(wp)):
            if f.lower().endswith(".vpk"):
                p = os.path.join(wp, f)
                if not os.path.isfile(p):
                    continue
                ctime = 0.0
                try:
                    ctime = os.path.getctime(p)
                except OSError:
                    pass
                out.append({"id": f[:-4], "path": p, "size": os.path.getsize(p),
                            "ctime": ctime})
    return out


def _read_vpk_tree(path):
    try:
        with open(path, "rb") as f:
            hdr = f.read(12)
            if len(hdr) < 12:
                return None, None
            magic, version, tree_size = struct.unpack("<III", hdr)
            if magic != 0x55AA1234:
                return None, None
            tree = f.read(tree_size)
        return tree, 12 + tree_size
    except Exception:
        return None, None


def detect_vscript(tree):
    if not tree:
        return False
    low = tree.lower()
    return b"vscripts" in low or b"\x00nut\x00" in low


def get_addon_title(path):
    tree, data_start = _read_vpk_tree(path)
    if tree is None:
        return None
    return _title_from_tree(path, tree, data_start)


def _title_from_tree(path, tree, data_start):
    try:
        pos = None
        m = tree.find(b"\x00addoninfo\x00txt\x00")
        if m >= 0:
            pos = m + 1 + len(b"addoninfo\x00txt\x00")
        else:
            m2 = tree.find(b"\x00addoninfo\x00")
            if m2 >= 0:
                pos = m2 + 1 + len("addoninfo") + 1
        if pos is None or pos + 18 > len(tree):
            return None
        crc, pre, arch, off, lng = struct.unpack("<IHHII", tree[pos:pos + 16])
        term = struct.unpack("<H", tree[pos + 16:pos + 18])[0]
        with open(path, "rb") as f2:
            f2.seek(data_start + off)
            chunk = f2.read(max(0, lng - pre))
        content = chunk
        if pre > 0 and pos + 18 + pre <= len(tree):
            content = tree[pos + 18:pos + 18 + pre] + content
        text = content.decode("utf-8", "ignore")
        mt = re.search(r'addontitle"?\s*"([^"]+)"', text, re.IGNORECASE)
        if not mt:
            mt = re.search(r'"title"\s*"([^"]+)"', text, re.IGNORECASE)
        if mt and mt.group(1).strip():
            return mt.group(1).strip()
    except Exception:
        return None
    return None


def inspect_vpk(path):
    tree, data_start = _read_vpk_tree(path)
    if tree is None:
        return {"title": None, "is_vscript": False}
    return {"title": _title_from_tree(path, tree, data_start),
            "is_vscript": detect_vscript(tree)}


def backup_path(l4d2):
    return os.path.join(l4d2, "left4dead2", "gameinfo.txt.bak")


def _app_dir():
    base = os.getenv("LOCALAPPDATA") or tempfile.gettempdir()
    d = os.path.join(base, "L4D2ModLoader")
    os.makedirs(d, exist_ok=True)
    return d


def _managed_manifest_path():
    return os.path.join(_app_dir(), "managed_mods.json")


def _restore_manifest_path():
    return os.path.join(_app_dir(), "restore_state.json")


def _gameinfo_backup_path(l4d2):
    return os.path.join(_app_dir(), "backups", _l4d2_key(l4d2),
                        "gameinfo.txt")


def _l4d2_key(l4d2):
    return hashlib.sha1(os.path.abspath(l4d2).lower().encode("utf-8")).hexdigest()


def _load_managed_manifest():
    try:
        with open(_managed_manifest_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_managed_manifest(data):
    try:
        _atomic_write_text(_managed_manifest_path(),
                           json.dumps(data, ensure_ascii=False, indent=2))
        return True
    except OSError:
        return False


def _load_restore_manifest():
    try:
        with open(_restore_manifest_path(), encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or not isinstance(data.get("games"), dict):
            return {"version": RESTORE_STATE_VERSION, "games": {}}
        return data
    except Exception:
        return {"version": RESTORE_STATE_VERSION, "games": {}}


def _save_restore_manifest(data):
    data["version"] = RESTORE_STATE_VERSION
    try:
        _atomic_write_text(_restore_manifest_path(),
                           json.dumps(data, ensure_ascii=False, indent=2))
        return True
    except OSError:
        return False


def _restore_state(l4d2):
    data = _load_restore_manifest()
    entry = data["games"].get(_l4d2_key(l4d2), {})
    return dict(entry) if isinstance(entry, dict) else {}


def _save_restore_state(l4d2, entry):
    data = _load_restore_manifest()
    key = _l4d2_key(l4d2)
    useful = {k: v for k, v in entry.items()
              if k != "game_path" and v not in (None, False, [], {})}
    if useful:
        entry = dict(entry)
        entry["game_path"] = os.path.abspath(l4d2)
        data["games"][key] = entry
    else:
        data["games"].pop(key, None)
    return _save_restore_manifest(data)


def _managed_ids(l4d2):
    data = _load_managed_manifest()
    raw = data.get(_l4d2_key(l4d2), [])
    ids = set(str(x) for x in raw if _valid_addon_id(str(x)))
    mods = os.path.join(l4d2, "mods")
    if os.path.isdir(mods):
        for name in os.listdir(mods):
            d = os.path.join(mods, name)
            if (os.path.isdir(d) and _valid_addon_id(name)
                    and os.path.isfile(os.path.join(d, MANAGED_MARKER))):
                ids.add(name)
    return ids


def _register_managed(l4d2, addon_ids):
    data = _load_managed_manifest()
    key = _l4d2_key(l4d2)
    ids = set(str(x) for x in data.get(key, []) if _valid_addon_id(str(x)))
    ids.update(str(x) for x in addon_ids if _valid_addon_id(str(x)))
    data[key] = sorted(ids)
    _save_managed_manifest(data)


def _unregister_managed(l4d2, addon_ids):
    data = _load_managed_manifest()
    key = _l4d2_key(l4d2)
    ids = set(str(x) for x in data.get(key, []) if _valid_addon_id(str(x)))
    ids.difference_update(str(x) for x in addon_ids)
    if ids:
        data[key] = sorted(ids)
    else:
        data.pop(key, None)
    _save_managed_manifest(data)


def _valid_addon_id(addon_id):
    return bool(re.match(r"^[A-Za-z0-9_.-]+$", addon_id or ""))


def _atomic_write_text(path, text, encoding="utf-8"):
    folder = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".",
                              suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _atomic_write_bytes(path, data):
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".",
                              suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _ensure_gameinfo_backup(l4d2, gameinfo, log=print):
    entry = _restore_state(l4d2)
    dest = _gameinfo_backup_path(l4d2)
    expected = entry.get("gameinfo_sha256")
    if expected:
        if not os.path.isfile(dest):
            log("[!] Falta el backup seguro registrado de gameinfo.txt.")
            return False
        try:
            with open(dest, "rb") as f:
                current_hash = hashlib.sha256(f.read()).hexdigest()
            if current_hash == expected:
                return True
            log("[!] El backup seguro de gameinfo.txt no coincide con su registro.")
        except OSError as ex:
            log("[!] No se pudo validar el backup seguro: %s" % ex)
        return False

    try:
        with open(gameinfo, "rb") as f:
            original = f.read()
        _atomic_write_bytes(dest, original)
    except OSError as ex:
        log("[!] No se pudo guardar el estado original de gameinfo.txt: %s" % ex)
        return False

    entry["gameinfo_sha256"] = hashlib.sha256(original).hexdigest()
    entry["mods_root_existed"] = os.path.isdir(os.path.join(l4d2, "mods"))
    if not _save_restore_state(l4d2, entry):
        log("[!] No se pudo registrar el backup seguro de gameinfo.txt.")
        return False
    log("[*] Estado original de gameinfo.txt guardado por el loader.")
    return True


def _strip_managed_gameinfo(data, addon_ids):
    ids = set(addon_ids)
    if not ids:
        return data
    kept = []
    for line in data.splitlines(keepends=True):
        decoded = line.decode("utf-8", "ignore").strip()
        match = re.match(r"Game\s+mods\\([^\s\r\n]+)", decoded)
        if not match or match.group(1) not in ids:
            kept.append(line)
    return b"".join(kept)


def _normalized_newlines(data):
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _read_text(path, encoding="utf-8"):
    with open(path, encoding=encoding, errors="ignore") as f:
        return f.read()


def _find_searchpaths_anchor(lines):
    sp_idx = next((i for i, l in enumerate(lines)
                   if re.search(r'"?SearchPaths"?', l)), None)
    if sp_idx is None:
        return None
    depth = 0
    seen_open = False
    for i in range(sp_idx + 1, len(lines)):
        stripped = lines[i].strip()
        depth += stripped.count("{")
        if "{" in stripped:
            seen_open = True
        if seen_open and depth <= 0 and "}" in stripped:
            return None
        if stripped.startswith("Game"):
            return i
        depth -= stripped.count("}")
    return None


def _remove_managed_mod_dir(l4d2, addon_id, log=print):
    if not _valid_addon_id(addon_id):
        log("[!] ID invalido, no se borra carpeta mods: " + str(addon_id))
        return False
    d = os.path.join(l4d2, "mods", addon_id)
    if not os.path.isdir(d):
        _unregister_managed(l4d2, [addon_id])
        return True
    marker = os.path.join(d, MANAGED_MARKER)
    if addon_id not in _managed_ids(l4d2) and not os.path.isfile(marker):
        log("[!] Carpeta mods\\%s no fue creada por el loader; se conserva." % addon_id)
        return False
    try:
        shutil.rmtree(d)
        _unregister_managed(l4d2, [addon_id])
        log("[*] Carpeta mods\\" + addon_id + " eliminada.")
        return True
    except OSError as ex:
        log("[!] No se pudo borrar mods\\%s: %s" % (addon_id, ex))
        return False


def currently_enabled(l4d2):
    gi = os.path.join(l4d2, "left4dead2", "gameinfo.txt")
    if not os.path.isfile(gi):
        return []
    txt = _read_text(gi)
    return re.findall(r'Game\s+mods\\([^\s\r\n]+)', txt)


def currently_enabled_orphans(l4d2):
    wp = os.path.join(l4d2, "left4dead2", "addons", "workshop")
    enabled = currently_enabled(l4d2)
    orphans = []
    for aid in enabled:
        vpk = os.path.join(wp, aid + ".vpk")
        if not os.path.isfile(vpk):
            orphans.append(aid)
    return orphans


def cleanup_orphans(l4d2, log=print):
    gi = os.path.join(l4d2, "left4dead2", "gameinfo.txt")
    if not os.path.isfile(gi):
        return []
    if l4d2_running():
        log("[!] Left 4 Dead 2 esta abierto. Cierra el juego antes de limpiar.")
        return []
    orphans = currently_enabled_orphans(l4d2)
    if not orphans:
        return []
    idset = set(orphans)
    _ensure_writable(gi, log)
    lines = _read_text(gi).split("\n")
    removed = []
    keep = []
    for l in lines:
        m = re.match(r"Game\s+mods\\([^\s\r\n]+)", l.strip())
        if m and m.group(1) in idset:
            removed.append(m.group(1))
        else:
            keep.append(l)
    if not removed:
        return []
    try:
        _atomic_write_text(gi, "\n".join(keep))
    except OSError as ex:
        log("[!] No se pudo escribir gameinfo.txt: %s" % ex)
        return []
    for rid in removed:
        _remove_managed_mod_dir(l4d2, rid, log)
    log("[OK] Addons huérfanos limpiados: " + ", ".join(removed))
    return removed


def restore(l4d2, log=print):
    if l4d2_running():
        log("[!] Left 4 Dead 2 esta abierto. Cierra el juego antes de restaurar.")
        return False

    gi = os.path.join(l4d2, "left4dead2", "gameinfo.txt")
    managed = sorted(_managed_ids(l4d2))
    entry = _restore_state(l4d2)
    safe_backup = _gameinfo_backup_path(l4d2)
    backup_data = None
    legacy_backup = False

    expected_hash = entry.get("gameinfo_sha256")
    if expected_hash:
        if not os.path.isfile(safe_backup):
            log("[!] Falta el backup seguro de gameinfo.txt; no se restaura nada.")
            return False
        try:
            with open(safe_backup, "rb") as f:
                backup_data = f.read()
        except OSError as ex:
            log("[!] No se pudo leer el backup seguro de gameinfo.txt: %s" % ex)
            return False
        if hashlib.sha256(backup_data).hexdigest() != expected_hash:
            log("[!] El backup seguro de gameinfo.txt esta dañado; no se restaura nada.")
            return False
    elif managed and os.path.isfile(backup_path(l4d2)):
        try:
            with open(backup_path(l4d2), "rb") as f:
                backup_data = f.read()
            legacy_backup = True
            log("[*] Se usara el backup compatible de una version anterior.")
        except OSError as ex:
            log("[!] No se pudo leer el backup anterior: %s" % ex)
            return False

    vision_files = [name for name in entry.get("vision_files", [])
                    if name in _VISION_FILES]
    vision_dir = _vision_dir(l4d2)
    for name in vision_files:
        original = os.path.join(vision_dir, name)
        disabled = original + _VISION_OFF
        if os.path.isfile(original) and os.path.isfile(disabled):
            log("[!] Conflicto de vision en %s; no se restaura nada." % name)
            return False
        if not os.path.isfile(original) and not os.path.isfile(disabled):
            log("[!] Falta el archivo de vision %s; no se restaura nada." % name)
            return False

    if os.path.isfile(gi) and (backup_data is not None or managed):
        try:
            with open(gi, "rb") as f:
                current_data = f.read()
            without_loader = _strip_managed_gameinfo(current_data, managed)
            if (backup_data is not None and
                    _normalized_newlines(without_loader) ==
                    _normalized_newlines(backup_data)):
                restored_gameinfo = backup_data
                log("[*] gameinfo.txt coincide con el estado gestionado; "
                    "se restaurara el original exacto.")
            else:
                restored_gameinfo = without_loader
                if backup_data is not None:
                    log("[!] gameinfo.txt contiene cambios externos; se conservan "
                        "y solo se quitan las entradas del loader.")
            _ensure_writable(gi, log)
            _atomic_write_bytes(gi, restored_gameinfo)
        except OSError as ex:
            log("[!] No se pudo restaurar gameinfo.txt: %s" % ex)
            return False
    elif not os.path.isfile(gi) and backup_data is not None:
        try:
            _atomic_write_bytes(gi, backup_data)
        except OSError as ex:
            log("[!] No se pudo recrear gameinfo.txt: %s" % ex)
            return False

    if vision_files and not restore_infected_vision(l4d2, log):
        return False

    removed = []
    for addon_id in managed:
        if _remove_managed_mod_dir(l4d2, addon_id, log):
            removed.append(addon_id)
        else:
            log("[!] La restauracion quedo incompleta.")
            return False
    if removed:
        log("[*] Carpetas gestionadas por el loader eliminadas: " + ", ".join(removed))
    else:
        log("[*] No habia carpetas gestionadas por el loader para borrar.")

    mods_root = os.path.join(l4d2, "mods")
    if entry.get("mods_root_existed") is False and os.path.isdir(mods_root):
        try:
            if not os.listdir(mods_root):
                os.rmdir(mods_root)
                log("[*] Carpeta mods vacia creada por el loader eliminada.")
        except OSError as ex:
            log("[!] No se pudo retirar la carpeta mods vacia: %s" % ex)
            return False

    entry.pop("gameinfo_sha256", None)
    entry.pop("mods_root_existed", None)
    entry.pop("vision_files", None)
    if not _save_restore_state(l4d2, entry):
        log("[!] El juego fue restaurado, pero no se pudo actualizar el registro local.")
        return False
    if expected_hash:
        try:
            os.remove(safe_backup)
            parent = os.path.dirname(safe_backup)
            if os.path.isdir(parent) and not os.listdir(parent):
                os.rmdir(parent)
        except OSError as ex:
            log("[!] El juego fue restaurado; quedo un backup local sin uso: %s" % ex)
    elif legacy_backup:
        log("[*] El backup antiguo se conserva porque no tiene marca de propiedad segura.")

    log("[*] Listo. El juego queda como original sin borrar mods ajenos.")
    return True


def fmt_size(n):
    if n > 1048576:
        return "%.1f MB" % (n / 1048576)
    return "%.1f KB" % (n / 1024)


def l4d2_running():
    try:
        import subprocess
        out = subprocess.check_output(
            ["tasklist", "/FO", "CSV", "/NH"],
            stderr=subprocess.DEVNULL,
            creationflags=0x08000000).decode("utf-8", "ignore").lower()
    except Exception:
        return False
    return "left4dead2.exe" in out or "hl2.exe" in out


def _ensure_writable(path, log=print):
    try:
        if os.path.isfile(path) and not os.access(path, os.W_OK):
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
            log("[*] gameinfo.txt estaba marcado como 'solo lectura'; se destildo.")
    except OSError as ex:
        log("[!] No se pudo quitar el atributo de solo lectura: %s" % ex)


def enable(l4d2, selected, log=print):
    gi = os.path.join(l4d2, "left4dead2", "gameinfo.txt")
    if not os.path.isfile(gi):
        log("[!] No se encontro gameinfo.txt en " + gi)
        return False
    if l4d2_running():
        log("[!] Left 4 Dead 2 esta abierto. Cierra el juego antes de habilitar addons.")
        return False
    _ensure_writable(gi, log)

    text = _read_text(gi)
    lines = text.split("\n")
    already = set(re.findall(r"Game\s+mods\\([^\s\r\n]+)", text))
    anchor = _find_searchpaths_anchor(lines)
    if anchor is None:
        log("[!] No se encontro SearchPaths en gameinfo.txt")
        return False

    candidates = [v for v in selected
                  if _valid_addon_id(v.get("id")) and v["id"] not in already]
    if not candidates:
        log("[!] Todos los addons indicados ya estaban activos o tienen ID invalido.")
        return True
    if not _ensure_gameinfo_backup(l4d2, gi, log):
        return False

    mods_root = os.path.join(l4d2, "mods")
    os.makedirs(mods_root, exist_ok=True)

    inserted = []
    for v in candidates:
        d = os.path.join(mods_root, v["id"])
        os.makedirs(d, exist_ok=True)
        dst = os.path.join(d, "pak01_dir.vpk")
        if not os.path.isfile(dst):
            shutil.copy(v["path"], dst)
        with open(os.path.join(d, MANAGED_MARKER), "w", encoding="utf-8") as f:
            f.write(v["id"] + "\n")
        lines.insert(anchor, "Game\t\t\tmods\\" + v["id"])
        anchor += 1
        already.add(v["id"])
        inserted.append(v["id"])

    try:
        new_text = "\n".join(lines)
        if _find_searchpaths_anchor(new_text.split("\n")) is None:
            log("[!] gameinfo.txt resultante no parece valido; no se escribe.")
            return False
        _atomic_write_text(gi, new_text)
    except OSError as ex:
        log("[!] No se pudo escribir gameinfo.txt: %s" % ex)
        return False
    _register_managed(l4d2, inserted)
    log("[OK] Mods habilitados en gameinfo.txt: " + ", ".join(inserted))
    log("[*] Los addons ya activos se mantuvieron intactos.")
    log("[*] Carpeta mods/ ubicada en: " + mods_root)
    log("[*] Abri L4D2 y unite a una partida Versus -> tus mods cargan.")
    return True


def disable(l4d2, ids, log=print):
    gi = os.path.join(l4d2, "left4dead2", "gameinfo.txt")
    if not os.path.isfile(gi):
        log("[!] No se encontro gameinfo.txt en " + gi)
        return False
    if not ids:
        return False
    if l4d2_running():
        log("[!] Left 4 Dead 2 esta abierto. Cierra el juego antes de quitar addons.")
        return False
    _ensure_writable(gi, log)
    idset = set(ids)
    lines = _read_text(gi).split("\n")
    removed = []
    keep = []
    for l in lines:
        m = re.match(r"Game\s+mods\\([^\s\r\n]+)", l.strip())
        if m and m.group(1) in idset:
            removed.append(m.group(1))
        else:
            keep.append(l)
    if not removed:
        log("[!] Ninguno de los IDs figura activo en gameinfo.txt.")
        return False
    try:
        _atomic_write_text(gi, "\n".join(keep))
    except OSError as ex:
        log("[!] No se pudo escribir gameinfo.txt: %s" % ex)
        return False
    for rid in removed:
        _remove_managed_mod_dir(l4d2, rid, log)
    log("[OK] Addons deshabilitados de gameinfo.txt: " + ", ".join(removed))
    return True


_STEAM_DETAILS_URL = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"

_BBCODE_TAG_RE = re.compile(r"\[/?[a-zA-Z0-9_=?.&#,:;'\"%/ +-]+\]")


def clean_description(text):
    if not text:
        return None
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _BBCODE_TAG_RE.sub("", text)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "\n".join(l.rstrip() for l in text.split("\n")).strip()
    return text or None


def _cache_dir():
    base = os.getenv("LOCALAPPDATA") or tempfile.gettempdir()
    d = os.path.join(base, "L4D2ModLoader", "cache")
    os.makedirs(d, exist_ok=True)
    return d


_IMAGE_CACHE_LOCKS = {}
_IMAGE_CACHE_LOCKS_GUARD = threading.Lock()


def cached_image_path(workshop_id, preview_url):
    if not preview_url:
        return None
    ext = os.path.splitext(preview_url.split("?")[0])[1] or ".jpg"
    key = hashlib.md5(preview_url.encode()).hexdigest()[:10]
    return os.path.join(_cache_dir(), "%s_%s%s" % (workshop_id, key, ext))


def fetch_workshop_details(ids, batch_size=25, timeout=8):
    numeric_ids = [i for i in ids if i.isdigit()]
    result = {}
    for start in range(0, len(numeric_ids), batch_size):
        batch = numeric_ids[start:start + batch_size]
        form = {"itemcount": len(batch)}
        for idx, wid in enumerate(batch):
            form["publishedfileids[%d]" % idx] = wid
        try:
            req = urllib.request.Request(_STEAM_DETAILS_URL, data=urlencode(form).encode())
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8", "ignore"))
        except Exception:
            continue
        details = (data.get("response") or {}).get("publishedfiledetails") or []
        for d in details:
            if d.get("result") != 1:
                continue
            raw_desc = (d.get("description") or d.get("file_description")
                        or "").strip()
            result[d["publishedfileid"]] = {
                "title": d.get("title") or None,
                "description": clean_description(raw_desc),
                "description_raw": raw_desc or None,
                "preview_url": d.get("preview_url") or None,
            }
    return result


def get_cached_image(workshop_id, preview_url, timeout=8):
    dest = cached_image_path(workshop_id, preview_url)
    if not dest:
        return None
    if os.path.isfile(dest):
        return dest
    with _IMAGE_CACHE_LOCKS_GUARD:
        lock = _IMAGE_CACHE_LOCKS.setdefault(dest, threading.Lock())
    with lock:
        if os.path.isfile(dest):
            return dest
        try:
            req = urllib.request.Request(
                preview_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
            _atomic_write_bytes(dest, data)
            return dest
        except Exception:
            return None


CATEGORY_KEYWORDS = {
    "Skins":  ["skin", "reskin", "model", "coach", "ellis", "nick", "rochelle",
               "zoey", "bill", "louis", "francis", "survivor", "outfit"],
    "Armas":  ["weapon", "gun", "rifle", "shotgun", "pistol", "melee",
               "riot shield", "viewmodel", "arma"],
    "Sonido": ["sound", "audio", "music", "voice", "vocalizer", "sonido"],
    "UI":     ["hud", "ui", "menu", "admin", "script", "interface", "system"],
}


def categorize(title, addon_id=""):
    text = (title or addon_id or "").lower()
    for cat, keywords in CATEGORY_KEYWORDS.items():
        if any(k in text for k in keywords):
            return cat
    return "Otro"


def deps_path():
    base = os.getenv("LOCALAPPDATA") or tempfile.gettempdir()
    d = os.path.join(base, "L4D2ModLoader")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "deps.json")


def load_deps():
    try:
        with open(deps_path(), encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {str(k): [str(x) for x in v]
                    for k, v in data.items()
                    if isinstance(v, (list, tuple)) and v}
    except Exception:
        pass
    return {}


def save_deps(deps):
    try:
        with open(deps_path(), "w", encoding="utf-8") as f:
            json.dump(deps, f, indent=2)
        return True
    except Exception:
        return False


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


_REQUIRES_RE = re.compile(
    r"(?:requires|required|need|needs|must have|"
    r"depend(?:s|ent)? on)"
    r"[^.\n]{4,300}", re.IGNORECASE)


def _norm_text(s):
    return re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())


def suggest_deps(description, addon_ids, titles=None):
    if not description:
        return []
    addon_ids = set(addon_ids)
    titles = titles or {}
    found = {}
    segments = [m.group(0) for m in _REQUIRES_RE.finditer(description)]
    for seg in segments:
        for m in re.finditer(r"id=(\d{6,12})", seg):
            wid = m.group(1)
            if wid in addon_ids and wid not in found:
                found[wid] = "link"
    title_items = [(i, t) for i, t in titles.items() if i in addon_ids]
    scored = {}
    for seg in segments:
        seg_norm = " ".join(_norm_text(seg).split())
        if not seg_norm:
            continue
        for wid, t in title_items:
            if wid in found:
                continue
            nt = _norm_text(t).strip()
            if not nt:
                continue
            if re.search(r"(?:^|\s)" + re.escape(nt) + r"(?:$|\s)", seg_norm):
                scored[wid] = max(scored.get(wid, 0.0), 1.0)
    for wid in sorted(scored, key=scored.get, reverse=True):
        found.setdefault(wid, "texto")
    return [{"id": i, "via": v}
            for i, v in sorted(found.items(),
                               key=lambda kv: (kv[1] != "link",))]


def resolve_deps(ids, deps):
    out, seen, queue = [], set(), list(ids)
    while queue:
        i = queue.pop(0)
        if i in seen:
            continue
        seen.add(i)
        out.append(i)
        for d in (deps.get(i) or []):
            if d not in seen:
                queue.append(d)
    return out


_VISION_FILES = ["ghost.pwl.raw", "ghost.raw", "infected.pwl.raw",
                 "infected.raw"]
_VISION_OFF = ".disabled"


def _vision_dir(l4d2):
    return os.path.join(l4d2, "left4dead2", "materials", "correction")


def vision_state(l4d2):
    d = _vision_dir(l4d2)
    on = off = 0
    for name in _VISION_FILES:
        if os.path.isfile(os.path.join(d, name)):
            on += 1
        elif os.path.isfile(os.path.join(d, name + _VISION_OFF)):
            off += 1
    if not on and not off:
        return "unknown"
    if off and not on:
        return "off"
    if on and not off:
        return "on"
    return "partial"


def disable_infected_vision(l4d2, log=print):
    if l4d2_running():
        log("[!] Left 4 Dead 2 esta abierto. Cierra el juego antes de tocar la vision.")
        return False
    d = _vision_dir(l4d2)
    if not os.path.isdir(d):
        log("[!] No existe materials/correction en " + d)
        return False
    candidates = [name for name in _VISION_FILES
                  if os.path.isfile(os.path.join(d, name))]
    if not candidates:
        log("[!] Ningun archivo de vision por renombrar (ya estan quitados?).")
        return False

    entry = _restore_state(l4d2)
    tracked = set(entry.get("vision_files", []))
    tracked.update(candidates)
    entry["vision_files"] = sorted(tracked)
    if not _save_restore_state(l4d2, entry):
        log("[!] No se pudo registrar el cambio de vision; no se modifica el juego.")
        return False

    moved = []
    for name in candidates:
        p = os.path.join(d, name)
        try:
            os.rename(p, p + _VISION_OFF)
            moved.append(name)
        except OSError as ex:
            log("[!] No se pudo renombrar %s: %s" % (name, ex))
    if not moved:
        log("[!] Ningun archivo de vision por renombrar (ya estan quitados?).")
        return False
    log("[OK] Vision de infectado quitada: " + ", ".join(moved))
    return True


def restore_infected_vision(l4d2, log=print):
    if l4d2_running():
        log("[!] Left 4 Dead 2 esta abierto. Cierra el juego antes de tocar la vision.")
        return False
    d = _vision_dir(l4d2)
    if not os.path.isdir(d):
        log("[!] No existe materials/correction en " + d)
        return False
    entry = _restore_state(l4d2)
    tracked = [name for name in entry.get("vision_files", [])
               if name in _VISION_FILES]
    if not tracked:
        tracked = [
            name for name in _VISION_FILES
            if (not os.path.isfile(os.path.join(d, name)) and
                os.path.isfile(os.path.join(d, name + _VISION_OFF)))
        ]
        if not tracked:
            log("[!] No hay archivos de vision por restaurar.")
            return False
        log("[*] No hay registro local de vision; se restauraran los "
            "archivos deshabilitados detectados en disco.")

    for name in tracked:
        p_on = os.path.join(d, name)
        p_off = p_on + _VISION_OFF
        if os.path.isfile(p_on) and os.path.isfile(p_off):
            log("[!] No se restaura %s: existen ambas versiones." % name)
            return False

    restored = []
    completed = []
    for name in tracked:
        p_on = os.path.join(d, name)
        p_off = p_on + _VISION_OFF
        if not os.path.isfile(p_on) and os.path.isfile(p_off):
            try:
                os.rename(p_off, p_on)
                restored.append(name)
                completed.append(name)
            except OSError as ex:
                log("[!] No se pudo restaurar %s: %s" % (name, ex))
        elif os.path.isfile(p_on) and not os.path.isfile(p_off):
            completed.append(name)

    remaining = sorted(set(tracked) - set(completed))
    if remaining:
        entry["vision_files"] = remaining
    else:
        entry.pop("vision_files", None)
    if not _save_restore_state(l4d2, entry):
        log("[!] No se pudo actualizar el registro de vision.")
        return False
    if not restored and completed:
        log("[*] La vision ya estaba en su estado original.")
        return True
    if not restored:
        log("[!] No hay archivos de vision por restaurar.")
        return False
    log("[OK] Vision de infectado restaurada: " + ", ".join(restored))
    return True
