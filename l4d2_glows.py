import codecs
import os
import re
import tempfile

from l4d2_locking import installation_lock, resource_lock
from l4d2_storage import _atomic_write_bytes, app_dir, load_json, save_json


CFG_NAME = "l4d2_mod_loader_glows.cfg"
STATE_NAME = "glows.json"
AUTOEXEC_BEGIN = "// L4D2 Mod Loader glows BEGIN"
AUTOEXEC_END = "// L4D2 Mod Loader glows END"
_AUTOEXEC_BEGIN_WITH_SEPARATOR = AUTOEXEC_BEGIN + " (separator added)"


GLOW_ITEMS = [
    {
        "key": "survivor_health_high",
        "label": "Sobreviviente alta salud",
        "group": "Sobrevivientes",
        "commands": [
            "cl_glow_survivor_health_high",
            "cl_glow_survivor_health_high_colorblind",
        ],
        "default": "#09AF31",
    },
    {
        "key": "survivor_health_med",
        "label": "Sobreviviente salud media",
        "group": "Sobrevivientes",
        "commands": [
            "cl_glow_survivor_health_med",
            "cl_glow_survivor_health_med_colorblind",
        ],
        "default": "#967A08",
    },
    {
        "key": "survivor_health_low",
        "label": "Sobreviviente baja salud",
        "group": "Sobrevivientes",
        "commands": [
            "cl_glow_survivor_health_low",
            "cl_glow_survivor_health_low_colorblind",
        ],
        "default": "#B23F00",
    },
    {
        "key": "survivor_health_crit",
        "label": "Salud crítica",
        "group": "Sobrevivientes",
        "commands": [
            "cl_glow_survivor_health_crit",
            "cl_glow_survivor_health_crit_colorblind",
        ],
        "default": "#A01818",
    },
    {
        "key": "survivor",
        "label": "Compañero de equipo",
        "group": "Sobrevivientes",
        "commands": ["cl_glow_survivor"],
        "default": "#4C66FF",
    },
    {
        "key": "survivor_hurt",
        "label": "Compañero incapacitado",
        "group": "Sobrevivientes",
        "commands": ["cl_glow_survivor_hurt"],
        "default": "#FF6600",
    },
    {
        "key": "survivor_vomit",
        "label": "Compañero vomitado",
        "group": "Sobrevivientes",
        "commands": ["cl_glow_survivor_vomit"],
        "default": "#FF6600",
    },
    {
        "key": "ability",
        "label": "Survivor agarrado",
        "group": "Infectados",
        "commands": ["cl_glow_ability", "cl_glow_ability_colorblind"],
        "default": "#FF0000",
    },
    {
        "key": "infected",
        "label": "Infectado especial",
        "group": "Infectados",
        "commands": ["cl_glow_infected"],
        "default": "#4C66FF",
    },
    {
        "key": "ghost_infected",
        "label": "Fantasma infectado",
        "group": "Infectados",
        "commands": ["cl_glow_ghost_infected"],
        "default": "#4C66FF",
    },
    {
        "key": "infected_vomit",
        "label": "Sobreviviente vomitado como infectado",
        "group": "Infectados",
        "commands": ["cl_glow_infected_vomit"],
        "default": "#C911B7",
    },
    {
        "key": "witch_angry",
        "label": "Witch agresiva",
        "group": "Infectados",
        "commands": ["cl_witch_glow_angry"],
        "default": "#FF0000",
    },
    {
        "key": "item",
        "label": "Armas, items y objetos",
        "group": "Objetos",
        "commands": ["cl_glow_item"],
        "default": "#B2B2FF",
    },
    {
        "key": "item_far",
        "label": "Armas, items y objetos lejanos",
        "group": "Objetos",
        "commands": ["cl_glow_item_far"],
        "default": "#4C66FF",
    },
    {
        "key": "thirdstrike_item",
        "label": "Objetos de tercer golpe",
        "group": "Objetos",
        "commands": [
            "cl_glow_thirdstrike_item",
            "cl_glow_thirdstrike_item_colorblind",
        ],
        "default": "#FF0000",
    },
]


PRESETS = {
    "Versus claro": {
        item["key"]: item["default"] for item in GLOW_ITEMS
    },
    "Competitivo": {
        "survivor_health_high": "#00FF40",
        "survivor_health_med": "#FFD000",
        "survivor_health_low": "#FF7A00",
        "survivor_health_crit": "#FF1A1A",
        "survivor": "#4D75FF",
        "survivor_hurt": "#FF6200",
        "survivor_vomit": "#FF6200",
        "ability": "#FF1A1A",
        "infected": "#3F64FF",
        "ghost_infected": "#3F64FF",
        "infected_vomit": "#D414C7",
        "witch_angry": "#FF1818",
        "item": "#B8B8FF",
        "item_far": "#3F64FF",
        "thirdstrike_item": "#FF1A1A",
    },
    "Alto contraste": {
        "survivor_health_high": "#00FF66",
        "survivor_health_med": "#FFE600",
        "survivor_health_low": "#FF8800",
        "survivor_health_crit": "#FF0000",
        "survivor": "#00A2FF",
        "survivor_hurt": "#FF4D00",
        "survivor_vomit": "#FF4D00",
        "ability": "#FF0000",
        "infected": "#3366FF",
        "ghost_infected": "#3366FF",
        "infected_vomit": "#FF00D4",
        "witch_angry": "#FF0000",
        "item": "#D6D6FF",
        "item_far": "#3366FF",
        "thirdstrike_item": "#FF0000",
    },
}


def default_colors():
    return {item["key"]: item["default"] for item in GLOW_ITEMS}


def state_path():
    return os.path.join(app_dir(), STATE_NAME)


def load_colors():
    data = load_json(state_path(), {})
    colors = default_colors()
    if isinstance(data, dict):
        saved = data.get("colors")
        if isinstance(saved, dict):
            for key, value in saved.items():
                if key in colors:
                    try:
                        colors[key] = normalize_hex(value)
                    except ValueError:
                        pass
    return colors


def save_colors(colors, preset_name=None, applied=None):
    try:
        path = state_path()
        with resource_lock(path):
            data = load_json(path, {})
            if not isinstance(data, dict):
                data = {}
            data["colors"] = normalized_colors(colors)
            if preset_name is not None:
                data["preset"] = preset_name
            if applied is not None:
                data["applied"] = bool(applied)
            return save_json(path, data)
    except (OSError, ValueError):
        return False


def normalize_hex(value):
    text = str(value or "").strip()
    if not text.startswith("#"):
        text = "#" + text
    if not re.match(r"^#[0-9a-fA-F]{6}$", text):
        raise ValueError("Color inválido: %s" % value)
    return text.upper()


def normalized_colors(colors):
    defaults = default_colors()
    out = {}
    for key, fallback in defaults.items():
        out[key] = normalize_hex(colors.get(key, fallback))
    return out


def hex_to_rgb_values(value):
    text = normalize_hex(value)
    return tuple(int(text[index:index + 2], 16) / 255.0
                 for index in (1, 3, 5))


def _fmt_float(value):
    if abs(value - round(value)) < 0.0000001:
        return str(int(round(value)))
    return ("%.16f" % value).rstrip("0").rstrip(".")


def build_cfg(colors):
    colors = normalized_colors(colors)
    lines = [
        "// Generado por L4D2 Mod Loader",
        "// No edites este archivo mientras la app esté abierta.",
        "",
    ]
    for item in GLOW_ITEMS:
        red, green, blue = hex_to_rgb_values(colors[item["key"]])
        lines.append("// " + item["label"])
        for command in item["commands"]:
            lines.append('%s_r "%s";' % (command, _fmt_float(red)))
            lines.append('%s_g "%s";' % (command, _fmt_float(green)))
            lines.append('%s_b "%s";' % (command, _fmt_float(blue)))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def cfg_path(l4d2):
    return os.path.join(l4d2, "left4dead2", "cfg", CFG_NAME)


def autoexec_path(l4d2):
    return os.path.join(l4d2, "left4dead2", "cfg", "autoexec.cfg")


def _read_optional_bytes(path):
    try:
        with open(path, "rb") as file:
            return file.read()
    except FileNotFoundError:
        return None


def _decode_autoexec(data):
    for bom, encoding in (
            (codecs.BOM_UTF32_LE, "utf-32-le"),
            (codecs.BOM_UTF32_BE, "utf-32-be"),
            (codecs.BOM_UTF16_LE, "utf-16-le"),
            (codecs.BOM_UTF16_BE, "utf-16-be"),
            (codecs.BOM_UTF8, "utf-8")):
        if data.startswith(bom):
            return data[len(bom):].decode(encoding), encoding, bom
    # ASCII markers can be edited through a one-to-one byte mapping, including
    # ANSI and UTF-8 text. Nothing outside the managed lines is transcoded.
    return data.decode("latin-1"), "latin-1", b""


def _read_text(path):
    return _decode_autoexec(_read_optional_bytes(path) or b"")[0]


def _managed_block():
    return "%s\nexec %s\n%s" % (
        AUTOEXEC_BEGIN, os.path.splitext(CFG_NAME)[0], AUTOEXEC_END)


def _remove_managed_block(text):
    kept = []
    in_block = False
    separator_index = None
    for match in re.finditer(r"[^\r\n]*(?:\r\n|\r|\n|$)", text):
        line = match.group()
        marker = line.rstrip("\r\n")
        if marker in (AUTOEXEC_BEGIN, _AUTOEXEC_BEGIN_WITH_SEPARATOR):
            if in_block:
                raise ValueError("Bloque de glows anidado en autoexec.cfg")
            separator_index = (len(kept) - 1
                               if marker == _AUTOEXEC_BEGIN_WITH_SEPARATOR and kept else None)
            in_block = True
        elif marker == AUTOEXEC_END:
            if not in_block:
                raise ValueError("Bloque de glows incompleto en autoexec.cfg")
            in_block = False
            # Recover an unterminated original only when no external text follows.
            if separator_index is not None and match.end() == len(text):
                kept[separator_index] = re.sub(r"(?:\r\n|\r|\n)$", "", kept[separator_index])
            separator_index = None
        elif not in_block:
            kept.append(line)
    if in_block:
        raise ValueError("Bloque de glows incompleto en autoexec.cfg")
    return "".join(kept)


def _with_managed_block(text):
    cleaned = _remove_managed_block(text)
    match = re.search(r"\r\n|\r|\n", cleaned)
    newline = match.group() if match else "\n"
    block = _managed_block().replace("\n", newline) + newline
    # Mark an inserted separator so restore can recover an unterminated last
    # line exactly, while keeping the loader's commands last as before.
    if cleaned and not cleaned.endswith(("\r", "\n")):
        block = block.replace(AUTOEXEC_BEGIN, _AUTOEXEC_BEGIN_WITH_SEPARATOR, 1)
        return cleaned + newline + block
    return cleaned + block


def _edit_autoexec(data, applying):
    text, encoding, bom = _decode_autoexec(data)
    text = _with_managed_block(text) if applying else _remove_managed_block(text)
    return bom + text.encode(encoding)


def _commit_glow_files(changes, save_state, log):
    changes = [(path, before, after) for path, before, after in changes
               if before != after]
    backups = {}
    changed = []
    retained = set()
    try:
        # Prepare every recovery copy before the first game file is changed.
        for path, before, after in changes:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if before is not None:
                fd, backup = tempfile.mkstemp(
                    prefix=os.path.basename(path) + ".recovery-",
                    dir=os.path.dirname(path))
                backups[path] = backup
                with os.fdopen(fd, "wb") as file:
                    file.write(before)
                    file.flush()
                    os.fsync(file.fileno())
        for path, before, after in changes:
            if after is None:
                os.remove(path)
            else:
                _atomic_write_bytes(path, after)
            changed.append(path)
        if not save_state():
            raise OSError("No se pudo guardar la configuracion de glows")
    except Exception:
        for path in reversed(changed):
            try:
                if path in backups:
                    os.replace(backups[path], path)
                else:
                    os.remove(path)
            except OSError as ex:
                if path in backups:
                    retained.add(backups[path])
                    log("[!] Recuperacion pendiente de %s; original en %s: %s"
                        % (path, backups[path], ex))
                else:
                    log("[!] No se pudo retirar el archivo nuevo %s: %s" % (path, ex))
        raise
    finally:
        for backup in backups.values():
            if backup not in retained:
                try:
                    os.remove(backup)
                except FileNotFoundError:
                    pass
                except OSError as ex:
                    log("[!] No se pudo retirar la copia %s: %s" % (backup, ex))
    return bool(changes)


def is_applied(l4d2):
    if not l4d2:
        return False
    with installation_lock(l4d2):
        if _read_optional_bytes(cfg_path(l4d2)) is None:
            return False
        text = _read_text(autoexec_path(l4d2))
        return _remove_managed_block(text) != text


def apply_glows(l4d2, colors, preset_name=None, log=print):
    try:
        with installation_lock(l4d2):
            colors = normalized_colors(colors)
            cfg = cfg_path(l4d2)
            autoexec = autoexec_path(l4d2)
            original = _read_optional_bytes(autoexec)
            cfg_before = _read_optional_bytes(cfg)
            updated = _edit_autoexec(original or b"", applying=True)
            _commit_glow_files([
                (cfg, cfg_before, build_cfg(colors).encode("utf-8")),
                (autoexec, original, updated),
            ], lambda: save_colors(colors, preset_name=preset_name, applied=True), log)
    except (OSError, ValueError) as ex:
        log("[!] No se pudieron aplicar glows: %s" % ex)
        return False
    log("[OK] Glows aplicados en " + cfg)
    return True


def restore_glows(l4d2, log=print):
    try:
        with installation_lock(l4d2):
            cfg = cfg_path(l4d2)
            autoexec = autoexec_path(l4d2)
            original = _read_optional_bytes(autoexec)
            cfg_before = _read_optional_bytes(cfg)
            cleaned = (_edit_autoexec(original, applying=False)
                       if original is not None else None)
            changed = _commit_glow_files([
                (autoexec, original, cleaned),
                (cfg, cfg_before, None),
            ], lambda: save_colors(load_colors(), applied=False), log)
    except (OSError, ValueError) as ex:
        log("[!] No se pudieron restaurar glows: %s" % ex)
        return False
    if changed:
        log("[OK] Glows del loader restaurados.")
    else:
        log("[*] No había glows del loader para restaurar.")
    return True
