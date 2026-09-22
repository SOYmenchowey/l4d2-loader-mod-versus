import json
import os
import re

from l4d2_storage import app_dir


CATEGORY_KEYWORDS = {
    "Skins":  ["skin", "reskin", "model", "coach", "ellis", "nick",
               "rochelle", "zoey", "bill", "louis", "francis", "survivor",
               "outfit"],
    "Armas":  ["weapon", "gun", "rifle", "shotgun", "pistol", "melee",
               "riot shield", "viewmodel", "arma"],
    "Sonido": ["sound", "audio", "music", "voice", "vocalizer", "sonido"],
    "UI":     ["hud", "ui", "menu", "admin", "script", "interface",
               "system"],
}


def categorize(title, addon_id=""):
    text = (title or addon_id or "").lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return category
    return "Otro"


def deps_path():
    return os.path.join(app_dir(), "deps.json")


def load_deps():
    try:
        with open(deps_path(), encoding="utf-8") as file:
            data = json.load(file)
        if isinstance(data, dict):
            return {
                str(key): [str(item) for item in value]
                for key, value in data.items()
                if isinstance(value, (list, tuple)) and value
            }
    except Exception:
        pass
    return {}


def save_deps(deps):
    try:
        with open(deps_path(), "w", encoding="utf-8") as file:
            json.dump(deps, file, indent=2)
        return True
    except Exception:
        return False


_REQUIRES_RE = re.compile(
    r"(?:requires|required|need|needs|must have|"
    r"depend(?:s|ent)? on)"
    r"[^.\n]{4,300}", re.IGNORECASE)


def _norm_text(value):
    return re.sub(r"[^a-z0-9 ]", " ", (value or "").lower())


def suggest_deps(description, addon_ids, titles=None):
    if not description:
        return []
    addon_ids = set(addon_ids)
    titles = titles or {}
    found = {}
    segments = [match.group(0) for match in _REQUIRES_RE.finditer(description)]
    for segment in segments:
        for match in re.finditer(r"id=(\d{6,12})", segment):
            workshop_id = match.group(1)
            if workshop_id in addon_ids and workshop_id not in found:
                found[workshop_id] = "link"
    title_items = [
        (workshop_id, title)
        for workshop_id, title in titles.items()
        if workshop_id in addon_ids
    ]
    scored = {}
    for segment in segments:
        segment_norm = " ".join(_norm_text(segment).split())
        if not segment_norm:
            continue
        for workshop_id, title in title_items:
            if workshop_id in found:
                continue
            normalized_title = _norm_text(title).strip()
            if not normalized_title:
                continue
            pattern = r"(?:^|\s)" + re.escape(normalized_title) + r"(?:$|\s)"
            if re.search(pattern, segment_norm):
                scored[workshop_id] = max(scored.get(workshop_id, 0.0), 1.0)
    for workshop_id in sorted(scored, key=scored.get, reverse=True):
        found.setdefault(workshop_id, "texto")
    return [
        {"id": workshop_id, "via": via}
        for workshop_id, via in sorted(found.items(),
                                       key=lambda item: (item[1] != "link",))
    ]


def resolve_deps(ids, deps):
    out, seen, queue = [], set(), list(ids)
    while queue:
        addon_id = queue.pop(0)
        if addon_id in seen:
            continue
        seen.add(addon_id)
        out.append(addon_id)
        for dep_id in (deps.get(addon_id) or []):
            if dep_id not in seen:
                queue.append(dep_id)
    return out
