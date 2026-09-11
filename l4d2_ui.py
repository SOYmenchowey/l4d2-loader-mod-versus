import unicodedata


def request_is_current(expected_generation, current_generation, closing=False):
    return not closing and expected_generation == current_generation


def normalize_search(value):
    normalized = unicodedata.normalize("NFD", value or "")
    return "".join(
        char for char in normalized
        if unicodedata.category(char) != "Mn"
    ).lower()


def addon_matches_query(addon, query):
    needle = normalize_search((query or "").strip())
    if not needle:
        return True
    return (
        needle in normalize_search(addon.get("title"))
        or needle in str(addon.get("id", "")).lower()
    )


def filter_addons_by_name(addons, query):
    return [addon for addon in addons if addon_matches_query(addon, query)]


def _yes_no(value):
    return "Si" if value else "No"


def diagnostic_warnings(snapshot):
    warnings = []
    if not snapshot.get("game_found"):
        warnings.append("L4D2 no fue detectado.")
    if snapshot.get("game_running"):
        warnings.append("L4D2 esta abierto; cierre el juego antes de modificar addons.")
    if snapshot.get("game_found") and not snapshot.get("workshop_exists"):
        warnings.append("No se detecto la carpeta addons/workshop.")
    if snapshot.get("game_found") and not snapshot.get("gameinfo_exists"):
        warnings.append("No se encontro gameinfo.txt.")
    elif snapshot.get("game_found") and not snapshot.get("gameinfo_writable"):
        warnings.append("gameinfo.txt no parece escribible.")
    pending = int(snapshot.get("pending_cleanup_count") or 0)
    if pending:
        warnings.append("%d addon(s) desuscrito(s) pendientes de limpiar." % pending)
    if snapshot.get("vision_state") == "off":
        warnings.append("La vision de infectado esta quitada.")
    return warnings


def format_diagnostic_report(snapshot):
    warnings = diagnostic_warnings(snapshot)
    lines = [
        "L4D2 Mod Loader - Diagnostico",
        "",
        "Ruta L4D2: %s" % (snapshot.get("l4d2_path") or "No detectado"),
        "Juego detectado: %s" % _yes_no(snapshot.get("game_found")),
        "Juego abierto: %s" % _yes_no(snapshot.get("game_running")),
        "Workshop detectado: %s" % _yes_no(snapshot.get("workshop_exists")),
        "gameinfo.txt existe: %s" % _yes_no(snapshot.get("gameinfo_exists")),
        "gameinfo.txt escribible: %s" % _yes_no(snapshot.get("gameinfo_writable")),
        "Addons instalados: %d" % int(snapshot.get("addon_count") or 0),
        "Addons activos: %d" % int(snapshot.get("active_count") or 0),
        "Seleccionados en UI: %d" % int(snapshot.get("selected_count") or 0),
        "Limpieza pendiente: %d" % int(snapshot.get("pending_cleanup_count") or 0),
        "Vision infectado: %s" % (snapshot.get("vision_state") or "unknown"),
        "Log local: %s" % (snapshot.get("debug_log_path") or "No disponible"),
        "",
        "Alertas:",
    ]
    if warnings:
        lines.extend("- " + warning for warning in warnings)
    else:
        lines.append("- Sin alertas detectadas.")
    return "\n".join(lines)


def last_config_summary(config, installed_ids=None, active_ids=None):
    ids = [str(value) for value in (config or {}).get("ids", [])]
    installed_ids = set(installed_ids or [])
    active_ids = set(active_ids or [])
    missing = [addon_id for addon_id in ids if addon_id not in installed_ids]
    already_active = [addon_id for addon_id in ids if addon_id in active_ids]
    return {
        "count": len(ids),
        "missing_count": len(missing),
        "already_active_count": len(already_active),
        "saved_at": (config or {}).get("saved_at") or "",
        "reason": (config or {}).get("reason") or "",
    }


def visible_addons(addons, active_ids, favs, view="mods", category="Todos",
                   query="", sort_recent=False):
    active_ids = set(active_ids)
    favs = set(favs)
    visible = list(addons)

    if view == "activos":
        visible = [addon for addon in visible if addon["id"] in active_ids]
    if category == "Favoritos":
        visible = [addon for addon in visible if addon["id"] in favs]
    elif category == "VScripts":
        visible = [addon for addon in visible if addon.get("is_vscript")]
    elif category != "Todos":
        visible = [addon for addon in visible
                   if addon.get("category") == category]

    needle = normalize_search(query.strip())
    if needle:
        visible = filter_addons_by_name(visible, needle)

    return sorted(
        visible,
        key=lambda addon: (addon.get("ctime", 0), addon["id"]),
        reverse=bool(sort_recent),
    )


def row_signature(addon, active, favorite, view):
    return (
        addon["id"],
        addon.get("title"),
        addon.get("size"),
        addon.get("category"),
        addon.get("type"),
        bool(active),
        bool(favorite),
        view,
    )


def empty_state_message(view, category, query, has_any_addons):
    if not has_any_addons:
        return (
            "No hay addons instalados",
            "Suscríbete a un addon de Workshop y aparecerá aquí automáticamente.",
        )
    if query.strip():
        return (
            "No hay coincidencias",
            "Prueba otro título o ID, o limpia la búsqueda.",
        )
    if view == "activos":
        return (
            "No hay addons activos",
            "Los addons que habilites para Versus aparecerán en esta vista.",
        )
    if category != "Todos":
        return (
            "Esta categoría está vacía",
            "Elige otra categoría para ver tus addons.",
        )
    return ("No hay resultados", "Cambia los filtros para continuar.")
