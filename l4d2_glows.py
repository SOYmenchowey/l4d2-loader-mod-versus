import os
import re

from l4d2_storage import _atomic_write_text, app_dir, load_json, save_json


CFG_NAME = "l4d2_mod_loader_glows.cfg"
STATE_NAME = "glows.json"
AUTOEXEC_BEGIN = "// L4D2 Mod Loader glows BEGIN"
AUTOEXEC_END = "// L4D2 Mod Loader glows END"


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
    data = load_json(state_path(), {})
    if not isinstance(data, dict):
        data = {}
    data["colors"] = normalized_colors(colors)
    if preset_name is not None:
        data["preset"] = preset_name
    if applied is not None:
        data["applied"] = bool(applied)
    return save_json(state_path(), data)


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


def _read_text(path):
    try:
        with open(path, encoding="utf-8", errors="ignore") as file:
            return file.read()
    except OSError:
        return ""


def _managed_block():
    return "%s\nexec %s\n%s" % (
        AUTOEXEC_BEGIN, os.path.splitext(CFG_NAME)[0], AUTOEXEC_END)


def _remove_managed_block(text):
    pattern = re.compile(
        r"\n?%s.*?%s\n?" % (re.escape(AUTOEXEC_BEGIN),
                            re.escape(AUTOEXEC_END)),
        re.DOTALL,
    )
    return pattern.sub("\n", text).strip() + ("\n" if text.strip() else "")


def _with_managed_block(text):
    cleaned = _remove_managed_block(text).rstrip()
    block = _managed_block()
    return (cleaned + "\n\n" + block + "\n") if cleaned else block + "\n"


def is_applied(l4d2):
    if not l4d2:
        return False
    return (os.path.isfile(cfg_path(l4d2))
            and AUTOEXEC_BEGIN in _read_text(autoexec_path(l4d2)))


def apply_glows(l4d2, colors, preset_name=None, log=print):
    colors = normalized_colors(colors)
    cfg = cfg_path(l4d2)
    autoexec = autoexec_path(l4d2)
    try:
        os.makedirs(os.path.dirname(cfg), exist_ok=True)
        _atomic_write_text(cfg, build_cfg(colors))
        _atomic_write_text(autoexec, _with_managed_block(_read_text(autoexec)))
        save_colors(colors, preset_name=preset_name, applied=True)
    except (OSError, ValueError) as ex:
        log("[!] No se pudieron aplicar glows: %s" % ex)
        return False
    log("[OK] Glows aplicados en " + cfg)
    return True


def restore_glows(l4d2, log=print):
    cfg = cfg_path(l4d2)
    autoexec = autoexec_path(l4d2)
    changed = False
    try:
        if os.path.isfile(autoexec):
            original = _read_text(autoexec)
            cleaned = _remove_managed_block(original)
            if cleaned != original:
                _atomic_write_text(autoexec, cleaned)
                changed = True
        if os.path.isfile(cfg):
            os.remove(cfg)
            changed = True
        save_colors(load_colors(), applied=False)
    except OSError as ex:
        log("[!] No se pudieron restaurar glows: %s" % ex)
        return False
    if changed:
        log("[OK] Glows del loader restaurados.")
    else:
        log("[*] No había glows del loader para restaurar.")
    return True
