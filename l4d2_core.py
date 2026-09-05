import os, sys, shutil, re, struct, json, hashlib, tempfile, traceback, difflib, html, stat
import urllib.request
from urllib.parse import urlencode

if sys.platform == "win32":
    import winreg


def find_l4d2():
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
        steam = winreg.QueryValueEx(k, "SteamPath")[0].replace("/", "\\")
        libs = [os.path.join(steam, "steamapps")]
        libf = os.path.join(steam, "steamapps", "libraryfolders.vdf")
        if os.path.isfile(libf):
            txt = open(libf, encoding="utf-8", errors="ignore").read()
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


def currently_enabled(l4d2):
    gi = os.path.join(l4d2, "left4dead2", "gameinfo.txt")
    if not os.path.isfile(gi):
        return []
    txt = open(gi, encoding="utf-8", errors="ignore").read()
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
    lines = open(gi, encoding="utf-8", errors="ignore").read().split("\n")
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
        open(gi, "w", encoding="utf-8").write("\n".join(keep))
    except OSError as ex:
        log("[!] No se pudo escribir gameinfo.txt: %s" % ex)
        return []
    for rid in removed:
        d = os.path.join(l4d2, "mods", rid)
        if os.path.isdir(d):
            try:
                shutil.rmtree(d)
                log("[*] Carpeta mods\\" + rid + " eliminada (huérfano).")
            except OSError as ex:
                log("[!] No se pudo borrar mods\\" + rid + ": %s" % ex)
    log("[OK] Addons huérfanos limpiados: " + ", ".join(removed))
    return removed


def delete_vpk(l4d2, addon_id, log=print):
    wp = os.path.join(l4d2, "left4dead2", "addons", "workshop")
    vpk = os.path.join(wp, addon_id + ".vpk")
    if os.path.isfile(vpk):
        try:
            os.remove(vpk)
            log("[*] VPK %s.vpk eliminado de addons/workshop/." % addon_id)
        except OSError as ex:
            log("[!] No se pudo borrar el VPK: %s" % ex)
            return False
    else:
        log("[!] El VPK %s no existe en addons/workshop/." % addon_id)

    gi = os.path.join(l4d2, "left4dead2", "gameinfo.txt")
    if os.path.isfile(gi):
        _ensure_writable(gi, log)
        lines = open(gi, encoding="utf-8", errors="ignore").read().split("\n")
        keep, removed = [], []
        for l in lines:
            m = re.match(r"Game\s+mods\\([^\s\r\n]+)", l.strip())
            if m and m.group(1) == addon_id:
                removed.append(addon_id)
            else:
                keep.append(l)
        if removed:
            try:
                open(gi, "w", encoding="utf-8").write("\n".join(keep))
                log("[*] %s removido de gameinfo.txt." % addon_id)
            except OSError as ex:
                log("[!] No se pudo escribir gameinfo.txt: %s" % ex)
            d = os.path.join(l4d2, "mods", addon_id)
            if os.path.isdir(d):
                try:
                    shutil.rmtree(d)
                    log("[*] Carpeta mods\\%s eliminada." % addon_id)
                except OSError as ex:
                    log("[!] No se pudo borrar mods\\%s: %s" % (addon_id, ex))
    return True


def restore(l4d2, log=print):
    gi = os.path.join(l4d2, "left4dead2", "gameinfo.txt")
    bak = backup_path(l4d2)
    if os.path.isfile(bak):
        shutil.copy(bak, gi)
        log("[*] gameinfo.txt restaurado desde backup.")
    else:
        log("[!] No existe backup (nada que restaurar).")
    mods = os.path.join(l4d2, "mods")
    if os.path.isdir(mods):
        shutil.rmtree(mods)
        log("[*] Carpeta mods/ eliminada.")
    log("[*] Listo. El juego queda como original (solo addons normales).")


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
    bak = backup_path(l4d2)
    if not os.path.isfile(gi):
        log("[!] No se encontro gameinfo.txt en " + gi)
        return False
    if l4d2_running():
        log("[!] Left 4 Dead 2 esta abierto. Cierra el juego antes de habilitar addons.")
        return False
    _ensure_writable(gi, log)
    if not os.path.isfile(bak):
        shutil.copy(gi, bak)
        log("[*] Backup creado: gameinfo.txt.bak")

    text = open(gi, encoding="utf-8", errors="ignore").read()
    lines = text.split("\n")
    already = set(re.findall(r"Game\s+mods\\([^\s\r\n]+)", text))
    sp_idx = next((i for i, l in enumerate(lines) if "SearchPaths" in l), None)
    if sp_idx is None:
        log("[!] No se encontro SearchPaths en gameinfo.txt")
        return False
    anchor = None
    for i in range(sp_idx + 1, len(lines)):
        if lines[i].strip().startswith("Game"):
            anchor = i
            break
    if anchor is None:
        log("[!] No se encontro linea 'Game' en SearchPaths")
        return False

    mods_root = os.path.join(l4d2, "mods")
    os.makedirs(mods_root, exist_ok=True)

    inserted = []
    for v in selected:
        if v["id"] in already:
            log("[!] " + v["id"] + " ya esta activo, se saltea.")
            continue
        d = os.path.join(mods_root, v["id"])
        os.makedirs(d, exist_ok=True)
        dst = os.path.join(d, "pak01_dir.vpk")
        if not os.path.isfile(dst):
            shutil.copy(v["path"], dst)
        lines.insert(anchor, "Game\t\t\tmods\\" + v["id"])
        anchor += 1
        already.add(v["id"])
        inserted.append(v["id"])

    if not inserted:
        log("[!] Todos los addons indicados ya estaban activos.")
        return True
    try:
        open(gi, "w", encoding="utf-8").write("\n".join(lines))
    except OSError as ex:
        log("[!] No se pudo escribir gameinfo.txt: %s" % ex)
        return False
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
    lines = open(gi, encoding="utf-8", errors="ignore").read().split("\n")
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
        open(gi, "w", encoding="utf-8").write("\n".join(keep))
    except OSError as ex:
        log("[!] No se pudo escribir gameinfo.txt: %s" % ex)
        return False
    for rid in removed:
        d = os.path.join(l4d2, "mods", rid)
        if os.path.isdir(d):
            try:
                shutil.rmtree(d)
                log("[*] Carpeta mods\\" + rid + " eliminada.")
            except OSError as ex:
                log("[!] No se pudo borrar mods\\" + rid + " (archivo en uso?): %s" % ex)
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
    if not preview_url:
        return None
    ext = os.path.splitext(preview_url.split("?")[0])[1] or ".jpg"
    key = hashlib.md5(preview_url.encode()).hexdigest()[:10]
    dest = os.path.join(_cache_dir(), "%s_%s%s" % (workshop_id, key, ext))
    if os.path.isfile(dest):
        return dest
    try:
        req = urllib.request.Request(preview_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        with open(dest, "wb") as f:
            f.write(data)
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
    moved = []
    for name in _VISION_FILES:
        p = os.path.join(d, name)
        if os.path.isfile(p):
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
    restored = []
    for name in _VISION_FILES:
        p_on = os.path.join(d, name)
        p_off = p_on + _VISION_OFF
        if not os.path.isfile(p_on) and os.path.isfile(p_off):
            try:
                os.rename(p_off, p_on)
                restored.append(name)
            except OSError as ex:
                log("[!] No se pudo restaurar %s: %s" % (name, ex))
    if not restored:
        log("[!] No hay archivos de vision por restaurar.")
        return False
    log("[OK] Vision de infectado restaurada: " + ", ".join(restored))
    return True