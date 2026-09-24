import os, shutil, re, json, hashlib, stat, tempfile
import urllib.request
from l4d2_locking import locked_installation, resource_lock
from l4d2_migrations import migrate_legacy_addons

from l4d2_game import (
    addon_snapshot,
    GameStatusError,
    find_l4d2,
    fmt_size,
    l4d2_running,
    list_addons,
    resolve_l4d2_path,
)
from l4d2_metadata import (
    CATEGORY_KEYWORDS,
    _REQUIRES_RE,
    _norm_text,
    categorize,
    deps_path,
    load_deps,
    resolve_deps,
    save_deps,
    suggest_deps,
    suggest_dependencies,
)
from l4d2_storage import (
    _app_dir,
    _atomic_write_bytes,
    _atomic_write_text,
    load_json,
    save_json,
)
from l4d2_vpk import (
    _read_vpk_tree,
    _title_from_tree,
    detect_vscript,
    get_addon_title,
    inspect_vpk,
)
from l4d2_workshop import (
    cached_image_path,
    clean_description,
    fetch_workshop_details,
    get_cached_image,
)

MANAGED_MARKER = ".l4d2_mod_loader_managed"
RESTORE_STATE_VERSION = 1


def backup_path(l4d2):
    return os.path.join(l4d2, "left4dead2", "gameinfo.txt.bak")


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
        if not isinstance(data, dict):
            raise ValueError('El registro de mods no es un objeto JSON.')
        return data
    except FileNotFoundError:
        return {}
    except (ValueError, OSError) as ex:
        raise OSError('No se pudo leer el registro de mods; se cancela la operacion.') from ex


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
            raise ValueError('Registro de restauracion invalido.')
        return data
    except FileNotFoundError:
        return {"version": RESTORE_STATE_VERSION, "games": {}}
    except (ValueError, OSError) as ex:
        raise OSError('No se pudo leer el registro de restauracion.') from ex


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
    with resource_lock(_restore_manifest_path()):
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


def _plain_path(path):
    """Reject junctions and symbolic links at the managed boundary."""
    if not os.path.lexists(path):
        return True
    info = os.lstat(path)
    return not (stat.S_ISLNK(info.st_mode) or
                getattr(info, 'st_file_attributes', 0) & 0x400)


def _mod_dir(l4d2, addon_id):
    if not _valid_addon_id(addon_id):
        raise ValueError('ID de addon invalido: ' + str(addon_id))
    root = os.path.join(l4d2, 'mods')
    path = os.path.join(root, addon_id)
    if not _plain_path(root) or not _plain_path(path):
        raise OSError('La carpeta de mods contiene un enlace; se conserva.')
    return path


def _marker_record(l4d2, addon_id):
    marker = os.path.join(_mod_dir(l4d2, addon_id), MANAGED_MARKER)
    if not _plain_path(marker):
        raise OSError('Marca de propiedad enlazada; se cancela la operacion.')
    try:
        with open(marker, encoding='utf-8') as file:
            text = file.read(16385)
    except FileNotFoundError:
        return None
    if len(text) > 16384:
        return None
    if text.strip() == addon_id:
        return {}  # Old markers establish ownership, but not payload integrity.
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if isinstance(data, dict) and data.get('id') == addon_id and data.get('version') == 2:
        return data
    return None


def _managed_records(l4d2, data=None):
    if data is None:
        data = _load_managed_manifest()
    raw = data.get(_l4d2_key(l4d2), {})
    if isinstance(raw, list):
        raw = {aid: {} for aid in raw if isinstance(aid, str)}
    if not isinstance(raw, dict):
        raise OSError('Registro de instalacion invalido.')
    records = {}
    root = os.path.join(l4d2, 'mods')
    if not _plain_path(root):
        raise OSError('La carpeta mods es un enlace; se conserva.')
    names = set(raw)
    if os.path.isdir(root):
        names.update(os.listdir(root))
    for aid in names:
        if not _valid_addon_id(aid):
            continue
        path = _mod_dir(l4d2, aid)
        if not os.path.lexists(path):
            if aid in raw:
                records[aid] = raw[aid] if isinstance(raw[aid], dict) else {}
            continue
        if not os.path.isdir(path):
            if aid in raw:
                records[aid] = {'_unverified': True}
            continue
        record = _marker_record(l4d2, aid)
        if record is not None:
            records[aid] = record
        elif aid in raw:
            record = dict(raw[aid]) if isinstance(raw[aid], dict) else {}
            record['_unverified'] = True
            records[aid] = record
    return records


def _managed_ids(l4d2):
    return set(_managed_records(l4d2))


def _register_managed(l4d2, addon_ids):
    with resource_lock(_managed_manifest_path()):
        data = _load_managed_manifest()
        records = _managed_records(l4d2, data)
        for aid in addon_ids:
            if _valid_addon_id(aid):
                records[aid] = _marker_record(l4d2, aid) or {}
        data[_l4d2_key(l4d2)] = records
        return _save_managed_manifest(data)


def _unregister_managed(l4d2, addon_ids):
    with resource_lock(_managed_manifest_path()):
        data = _load_managed_manifest()
        key = _l4d2_key(l4d2)
        raw = data.get(key, {})
        records = dict(raw) if isinstance(raw, dict) else {aid: {} for aid in raw}
        for aid in addon_ids:
            records.pop(aid, None)
        if records:
            data[key] = records
        else:
            data.pop(key, None)
        return _save_managed_manifest(data)


def _valid_addon_id(addon_id):
    return (isinstance(addon_id, str) and len(addon_id) <= 128
            and bool(re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9_.-]*', addon_id))
            and not addon_id.endswith('.')
            and not re.fullmatch(r'(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', addon_id, re.I))


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
    records = addon_ids if isinstance(addon_ids, dict) else {aid: {} for aid in addon_ids}
    ids = set(records)
    if not ids:
        return data
    kept = []
    for line in data.splitlines(keepends=True):
        decoded = line.decode("utf-8", "ignore").strip()
        match = re.match(r'Game\s+mods\\([^\s\r\n]+)', decoded)
        aid = match.group(1) if match else None
        if (aid not in ids or
                (records[aid].get('tagged_entry') and '// L4D2ModLoader' not in decoded)):
            kept.append(line)
    return b"".join(kept)


def _normalized_newlines(data):
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _read_text(path, encoding="utf-8"):
    with open(path, encoding=encoding, errors="surrogateescape", newline='') as f:
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


def _file_hash(path):
    with open(path, 'rb') as file:
        digest = hashlib.sha256()
        for chunk in iter(lambda: file.read(1024 * 1024), b''):
            digest.update(chunk)
        return digest.hexdigest()


def _remove_managed_mod_dir(l4d2, addon_id, log=print, record=None, unregister=True):
    if not _valid_addon_id(addon_id):
        log("[!] ID invalido, no se borra carpeta mods: " + str(addon_id))
        return False
    d = _mod_dir(l4d2, addon_id)
    if not os.path.isdir(d):
        return _unregister_managed(l4d2, [addon_id]) if unregister else True
    marker = os.path.join(d, MANAGED_MARKER)
    if record is None:
        record = _marker_record(l4d2, addon_id)
    if record is None or record.get('_unverified'):
        log("[!] Carpeta mods\\%s no fue creada por el loader; se conserva." % addon_id)
        return False
    marker_removed = False
    try:
        with open(marker, 'rb') as file:
            original_marker = file.read(16385)
        payload = os.path.join(d, 'pak01_dir.vpk')
        expected = record.get('sha256')
        if os.path.exists(payload):
            if expected and _plain_path(payload) and _file_hash(payload) == expected:
                if not os.stat(payload).st_mode & stat.S_IWRITE:
                    os.chmod(payload, stat.S_IREAD | stat.S_IWRITE)
                os.remove(payload)
            else:
                log('[!] Se conserva el VPK sin integridad verificable o modificado: ' + payload)
                return False
        os.remove(marker)
        marker_removed = True
        if not os.listdir(d):
            os.rmdir(d)
        else:
            log('[*] Se conservan archivos externos en mods\\' + addon_id)
        if unregister and not _unregister_managed(l4d2, [addon_id]):
            return False
        return True
    except OSError as ex:
        if marker_removed and os.path.isdir(d):
            try:
                # A locked directory may survive after its contents were removed.
                # Restore the proof of ownership so cleanup can retry later.
                _mod_dir(l4d2, addon_id)
                with open(marker, 'xb') as file:
                    file.write(original_marker)
                    file.flush()
                    os.fsync(file.fileno())
            except FileExistsError:
                pass
            except OSError as recovery_error:
                log('[!] No se pudo recuperar la marca de mods\\%s: %s' % (addon_id, recovery_error))
        log("[!] No se pudo borrar mods\\%s: %s" % (addon_id, ex))
        return False


def currently_enabled(l4d2):
    gi = os.path.join(l4d2, "left4dead2", "gameinfo.txt")
    if not os.path.isfile(gi):
        return []
    txt = _read_text(gi)
    return re.findall(r'Game\s+mods\\([^\s\r\n]+)', txt)


def currently_enabled_orphans(l4d2, records=None):
    records = _managed_records(l4d2) if records is None else records
    orphans = []
    for aid, record in records.items():
        if record.get('_unverified'):
            continue
        source = record.get('source')
        if not source:
            # Unknown legacy sources cannot safely be declared deleted.
            continue
        try:
            os.stat(source)
        except FileNotFoundError:
            orphans.append(aid)
    return orphans


def _remove_managed_batch(l4d2, ids, records, log):
    removed = []
    failed = []
    referenced = {aid.casefold() for aid in currently_enabled(l4d2)}
    for aid in ids:
        if aid.casefold() in referenced:
            log('[!] Se conserva mods\\%s: sigue referenciado fuera de las entradas del loader.' % aid)
            failed.append(aid)
            continue
        if _remove_managed_mod_dir(l4d2, aid, log, records[aid], unregister=False):
            removed.append(aid)
        else:
            failed.append(aid)
    if removed and not _unregister_managed(l4d2, removed):
        raise OSError('No se pudo guardar el registro tras retirar los mods.')
    return removed, failed


@locked_installation
def cleanup_orphans(l4d2, log=print):
    gi = os.path.join(l4d2, "left4dead2", "gameinfo.txt")
    if not os.path.isfile(gi):
        return []
    if l4d2_running():
        log("[!] Left 4 Dead 2 esta abierto. Cierra el juego antes de limpiar.")
        return []
    records = _managed_records(l4d2)
    orphans = currently_enabled_orphans(l4d2, records)
    if not orphans:
        return []
    _ensure_writable(gi, log)
    try:
        with open(gi, 'rb') as file:
            current = file.read()
        cleaned = _strip_managed_gameinfo(current, {aid: records[aid] for aid in orphans})
        if cleaned != current:
            _atomic_write_bytes(gi, cleaned)
    except OSError as ex:
        log("[!] No se pudo escribir gameinfo.txt: %s" % ex)
        return []
    removed, failed = _remove_managed_batch(l4d2, orphans, records, log)
    if failed:
        log('[!] Limpieza parcial; no se pudieron retirar: ' + ', '.join(failed))
    log("[OK] Addons huérfanos limpiados: " + ", ".join(removed))
    return removed


@locked_installation
def restore(l4d2, log=print):
    if l4d2_running():
        log("[!] Left 4 Dead 2 esta abierto. Cierra el juego antes de restaurar.")
        return False

    if migrate_legacy_addons(l4d2, log):
        return False
    gi = os.path.join(l4d2, "left4dead2", "gameinfo.txt")
    records = _managed_records(l4d2)
    managed = sorted(records)
    if any(record.get('_unverified') for record in records.values()):
        log('[!] Falta una marca de propiedad registrada; se conservan archivos y backups para recuperacion.')
        return False
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
            without_loader = _strip_managed_gameinfo(current_data, records)
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

    try:
        import l4d2_glows
        if not l4d2_glows.restore_glows(l4d2, log):
            return False
    except Exception as ex:
        log("[!] Error restaurando glows del loader: %s" % ex)
        return False

    removed, failed = _remove_managed_batch(l4d2, managed, records, log)
    if failed:
        log('[!] La restauracion quedo incompleta: ' + ', '.join(failed))
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


def _ensure_writable(path, log=print):
    try:
        if os.path.isfile(path) and not os.access(path, os.W_OK):
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
            log("[*] gameinfo.txt estaba marcado como 'solo lectura'; se destildo.")
    except OSError as ex:
        log("[!] No se pudo quitar el atributo de solo lectura: %s" % ex)


def _verified_copy(source, destination, expected_hash=None):
    if not _plain_path(destination):
        raise OSError('El destino VPK es un enlace; se conserva.')
    before = os.stat(source)
    digest = _file_hash(source)
    if (os.path.isfile(destination) and os.path.getsize(destination) == before.st_size
            and _file_hash(destination) == digest):
        after = os.stat(source)
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise OSError('El addon cambio durante la verificacion; vuelve a intentarlo.')
        return digest, before.st_size
    fd, temporary = tempfile.mkstemp(prefix='pak01.', suffix='.tmp', dir=os.path.dirname(destination))
    os.close(fd)
    try:
        shutil.copyfile(source, temporary)
        with open(temporary, 'r+b') as file:
            file.flush()
            os.fsync(file.fileno())
        after = os.stat(source)
        if ((before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)
                or os.path.getsize(temporary) != before.st_size or _file_hash(temporary) != digest):
            raise OSError('Copia incompleta o fuente modificada; no se activa el addon.')
        original_mode = None
        if os.path.isfile(destination) and not os.stat(destination).st_mode & stat.S_IWRITE:
            if not expected_hash or _file_hash(destination) != expected_hash:
                raise OSError('El destino de solo lectura no tiene integridad verificable; se conserva.')
            original_mode = os.stat(destination).st_mode
            os.chmod(destination, stat.S_IREAD | stat.S_IWRITE)
        try:
            os.replace(temporary, destination)
        except OSError:
            if original_mode is not None:
                os.chmod(destination, original_mode)
            raise
    finally:
        if os.path.exists(temporary):
            os.chmod(temporary, stat.S_IREAD | stat.S_IWRITE)
            os.remove(temporary)
    return digest, before.st_size


@locked_installation
def enable(l4d2, selected, log=print):
    gi = os.path.join(l4d2, "left4dead2", "gameinfo.txt")
    if not os.path.isfile(gi):
        log("[!] No se encontro gameinfo.txt en " + gi)
        return False
    if l4d2_running():
        log("[!] Left 4 Dead 2 esta abierto. Cierra el juego antes de habilitar addons.")
        return False
    _ensure_writable(gi, log)

    with open(gi, 'rb') as file:
        original = file.read()
    text = original.decode('utf-8', 'surrogateescape')
    lines = text.splitlines(keepends=True)
    already = {aid.casefold() for aid in re.findall(r"Game\s+mods\\([^\s\r\n]+)", text)}
    anchor = _find_searchpaths_anchor(lines)
    if anchor is None:
        log("[!] No se encontro SearchPaths en gameinfo.txt")
        return False

    candidates, seen = [], set()
    for addon in selected:
        aid = addon.get('id')
        if not _valid_addon_id(aid) or aid.casefold() in seen:
            log('[!] ID invalido o repetido: ' + str(aid))
            return False
        seen.add(aid.casefold())
        path = _mod_dir(l4d2, aid)
        if os.path.lexists(path) and _marker_record(l4d2, aid) is None:
            log('[!] Carpeta ajena al loader; no se modifica: ' + path)
            return False
        if aid.casefold() in already and not os.path.isdir(path):
            log('[!] La ruta activa no pertenece al loader: ' + aid)
            return False
        if not os.path.isfile(addon.get('path', '')):
            log('[!] No se encontro la fuente del addon: ' + aid)
            return False
        candidates.append(addon)
    if not candidates:
        log("[!] Todos los addons indicados ya estaban activos o tienen ID invalido.")
        return True
    if not _ensure_gameinfo_backup(l4d2, gi, log):
        return False

    mods_root = os.path.join(l4d2, "mods")
    os.makedirs(mods_root, exist_ok=True)

    inserted = []
    try:
        newline = '\r\n' if b'\r\n' in original else '\n'
        for v in candidates:
            d = _mod_dir(l4d2, v['id'])
            record = _marker_record(l4d2, v['id']) or {}
            source = os.path.realpath(os.path.abspath(v['path']))
            if record.get('source') and os.path.normcase(record['source']) != os.path.normcase(source):
                raise OSError('El ID ya pertenece a otra fuente: ' + v['id'])
            if not os.path.exists(d):
                os.mkdir(d)
                record = {'version': 2, 'id': v['id'], 'source': source, 'tagged_entry': True}
                _atomic_write_text(os.path.join(d, MANAGED_MARKER), json.dumps(record))
            digest, size = _verified_copy(source, os.path.join(d, 'pak01_dir.vpk'), record.get('sha256'))
            record.update(version=2, id=v['id'], source=source, sha256=digest, size=size)
            if v['id'].casefold() not in already:
                record['tagged_entry'] = True
                lines.insert(anchor, 'Game\t\t\tmods\\' + v['id'] + ' // L4D2ModLoader' + newline)
                anchor += 1
            _atomic_write_text(os.path.join(d, MANAGED_MARKER), json.dumps(record))
            inserted.append(v['id'])
        # Ownership must be durable before gameinfo can reference these copies.
        if not _register_managed(l4d2, inserted):
            log('[!] No se pudo registrar la propiedad de los mods; no se activan.')
            return False
        new_text = ''.join(lines)
        if _find_searchpaths_anchor(new_text.split("\n")) is None:
            log("[!] gameinfo.txt resultante no parece valido; no se escribe.")
            return False
        _atomic_write_bytes(gi, new_text.encode('utf-8', 'surrogateescape'))
    except OSError as ex:
        log("[!] No se pudo escribir gameinfo.txt: %s" % ex)
        return False
    log("[OK] Mods habilitados en gameinfo.txt: " + ", ".join(inserted))
    log("[*] Los addons ya activos se mantuvieron intactos.")
    log("[*] Carpeta mods/ ubicada en: " + mods_root)
    log("[*] Abri L4D2 y unite a una partida Versus -> tus mods cargan.")
    return True


@locked_installation
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
    if set(migrate_legacy_addons(l4d2, log)) & set(ids):
        return False
    _ensure_writable(gi, log)
    records = _managed_records(l4d2)
    idset = set(ids) & set(records)
    if any(records[aid].get('_unverified') for aid in idset):
        log('[!] No se pudo verificar la propiedad de todos los mods; se conservan los archivos.')
        return False
    removed = sorted(idset)
    if not removed:
        log("[!] Ninguno de los IDs figura activo en gameinfo.txt.")
        return False
    try:
        with open(gi, 'rb') as file:
            original = file.read()
        updated = _strip_managed_gameinfo(original, {aid: records[aid] for aid in removed})
        if updated != original:
            _atomic_write_bytes(gi, updated)
    except OSError as ex:
        log("[!] No se pudo escribir gameinfo.txt: %s" % ex)
        return False
    removed, failed = _remove_managed_batch(l4d2, removed, records, log)
    if failed:
        log('[!] No se pudieron retirar todas las copias: ' + ', '.join(failed))
        return False
    log("[OK] Addons deshabilitados de gameinfo.txt: " + ", ".join(removed))
    return True


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


@locked_installation
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
    complete = len(moved) == len(candidates)
    log(("[OK]" if complete else "[!] Cambio parcial:") + " Vision de infectado quitada: " + ", ".join(moved))
    return complete


@locked_installation
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
    if remaining:
        log('[!] Restauracion de vision parcial; quedan archivos pendientes: ' + ', '.join(remaining))
        return False
    if not restored and completed:
        log("[*] La vision ya estaba en su estado original.")
        return True
    if not restored:
        log("[!] No hay archivos de vision por restaurar.")
        return False
    log("[OK] Vision de infectado restaurada: " + ", ".join(restored))
    return True
