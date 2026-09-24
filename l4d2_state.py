import l4d2_core as core


def reconcile_addon_ids(state, addons):
    aliases = {a.get('_canonical_id', a['id']): a['id'] for a in addons}
    def mapped(ids):
        return list(dict.fromkeys(aliases.get(aid, aid) for aid in ids))
    for key in ('selected_ids', 'favs'):
        state[key] = set(mapped(state[key]))
    state['presets'] = {name: mapped(ids) for name, ids in state['presets'].items()}
    if state['last_config'].get('ids'):
        state['last_config'] = dict(state['last_config'], ids=mapped(state['last_config']['ids']))
    deps = {}
    for aid, required in state['deps'].items():
        key = aliases.get(aid, aid)
        deps[key] = mapped(deps.get(key, []) + required)
    state['deps'] = deps


def _saved_game_path(cfg_path):
    data = core.load_json(cfg_path("game_path.json"), {}) or {}
    return data.get("path") if isinstance(data, dict) else None


def create_initial_state(cfg_path):
    return {
        "l4d2": None,
        "addons": [],
        "rows": {},
        "selected_ids": set(),
        "preview_id": None,
        "hover_preview_id": None,
        "category": "Todos",
        "query": "",
        "view": "mods",
        "active_ids": set(),
        "deps": core.load_deps(),
        "favs": set(core.load_json(cfg_path("favs.json"), []) or []),
        "presets": core.load_json(cfg_path("presets.json"), {}) or {},
        "last_config": core.load_json(cfg_path("last_config.json"), {}) or {},
        "manual_l4d2_path": _saved_game_path(cfg_path),
        "sort_recent": False,
        "_fresh_scan": False,
        "_disk_ids": set(),
        "_pending_rescan": False,
        "_pending_cleanup_ids": set(),
        "_l4d2_was_running": False,
        "_closing": False,
        "_load_generation": 0,
        "_row_cache": {},
        "_render_signature": None,
        "_tasks": set(),
        "_search_task": None,
        "_search_generation": 0,
        "_resize_task": None,
        "_watch_task": None,
        "_load_progress": None,
        "fetching": False,
    }
