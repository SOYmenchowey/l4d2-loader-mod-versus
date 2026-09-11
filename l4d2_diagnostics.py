import os

import l4d2_core as core


def collect_health_snapshot(state, cfg_path, refresh_running=False, log=None):
    l4d2 = state.get("l4d2")
    game_found = bool(l4d2 and os.path.isdir(l4d2))
    running = bool(state.get("_l4d2_was_running"))
    if refresh_running:
        running = core.l4d2_running()
        state["_l4d2_was_running"] = running

    gameinfo = (os.path.join(l4d2, "left4dead2", "gameinfo.txt")
                if game_found else "")
    workshop = (os.path.join(l4d2, "left4dead2", "addons", "workshop")
                if game_found else "")
    gameinfo_exists = bool(gameinfo and os.path.isfile(gameinfo))
    pending = set(state.get("_pending_cleanup_ids") or set())
    active_ids = set(state.get("active_ids") or set())
    vision = "unknown"

    if game_found:
        try:
            pending = set(core.currently_enabled_orphans(l4d2))
        except Exception as ex:
            if log:
                log("health orphan ERR %r" % ex)
        try:
            active_ids = set(core.currently_enabled(l4d2))
        except Exception as ex:
            if log:
                log("health active ERR %r" % ex)
        try:
            vision = core.vision_state(l4d2)
        except Exception as ex:
            if log:
                log("health vision ERR %r" % ex)

    return {
        "l4d2_path": l4d2,
        "game_found": game_found,
        "game_running": running,
        "workshop_exists": bool(workshop and os.path.isdir(workshop)),
        "gameinfo_exists": gameinfo_exists,
        "gameinfo_writable": bool(gameinfo_exists and os.access(
            gameinfo, os.W_OK)),
        "addon_count": len(state.get("addons") or []),
        "active_count": len(active_ids),
        "selected_count": len(state.get("selected_ids") or set()),
        "pending_cleanup_count": len(pending),
        "vision_state": vision,
        "debug_log_path": cfg_path("debug.log"),
    }
