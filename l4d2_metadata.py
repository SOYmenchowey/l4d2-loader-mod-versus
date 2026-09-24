import json
import os
import re
from collections import deque

from l4d2_storage import app_dir, save_json


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
    return save_json(deps_path(), deps)


_REQUIRES_RE = re.compile(
    r"(?:requires|required|need|needs|must have|"
    r"depend(?:s|ent)? on)"
    r"[^\n]{4,300}", re.IGNORECASE)


def _norm_text(value):
    return re.sub(r"[^a-z0-9 ]", " ", (value or "").lower())


class DependencyIndex:
    def __init__(self, addon_ids, titles):
        self.ids = set(addon_ids)
        self.trie = {}
        self.order = {}
        for aid, title in titles.items():
            if aid not in self.ids:
                continue
            words = _norm_text(title).split()
            if not words:
                continue
            self.order[aid] = len(self.order)
            node = self.trie
            for word in words:
                node = node.setdefault(word, {})
            node.setdefault(None, []).append(aid)

    def matches(self, segment):
        words = _norm_text(segment).split()
        found = set()
        for start in range(len(words)):
            node = self.trie
            for end in range(start, len(words)):
                node = node.get(words[end])
                if node is None:
                    break
                found.update(node.get(None, ()))
        return sorted(found, key=self.order.__getitem__)


def suggest_deps(description, addon_ids, titles=None, index=None):
    if not description:
        return []
    index = index or DependencyIndex(addon_ids, titles or {})
    addon_ids = index.ids
    found = {}
    segments = [match.group(0) for match in _REQUIRES_RE.finditer(description)]
    for segment in segments:
        for match in re.finditer(r"id=(\d{6,12})", segment):
            workshop_id = match.group(1)
            if workshop_id in addon_ids and workshop_id not in found:
                found[workshop_id] = "link"
    for segment in segments:
        for workshop_id in index.matches(segment):
            found.setdefault(workshop_id, 'texto')
    return [
        {"id": workshop_id, "via": via}
        for workshop_id, via in sorted(found.items(),
                                       key=lambda item: (item[1] != "link",))
    ]


def suggest_dependencies(addons):
    ids = {addon['id'] for addon in addons}
    titles = {addon['id']: addon.get('title') or addon['id'] for addon in addons}
    index = DependencyIndex(ids, titles)
    return {
        addon['id']: [entry['id'] for entry in suggest_deps(
            addon.get('description_raw') or addon.get('description') or '', ids, index=index)
            if entry['id'] != addon['id']]
        for addon in addons
    }


def resolve_deps(ids, deps):
    out, seen, queue = [], set(), deque(ids)
    while queue:
        addon_id = queue.popleft()
        if addon_id in seen:
            continue
        seen.add(addon_id)
        out.append(addon_id)
        for dep_id in (deps.get(addon_id) or []):
            if dep_id not in seen:
                queue.append(dep_id)
    return out
