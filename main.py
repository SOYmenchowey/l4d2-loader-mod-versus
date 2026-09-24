import asyncio
import glob
import os
import time

import flet as ft

import l4d2_core as core
import l4d2_detail_panel
import l4d2_diagnostics as diagnostics
import l4d2_glows
import l4d2_glows_view
import l4d2_sidebar
import l4d2_state
import l4d2_ui as ui
from l4d2_app_config import (
    DEFAULT_WINDOW_WIDTH,
    cfg_path as _cfg_path,
    dbg,
    debug_log,
    window_geometry,
)
from l4d2_clipboard import copy_text_to_clipboard_async as copy_text_to_clipboard
from l4d2_controls import (
    ModRow,
    dialog_row,
    make_pane,
    pane_clear,
    pane_set_img,
)
from l4d2_dialogs import (
    confirm_dialog_content,
    count_badge,
    dialog_shell,
    modal_header,
    enable_dialog_content,
    progress_dialog_content,
)
from l4d2_theme import (
    ACCENT,
    ACCENT_SOFT,
    AMBER,
    AMBER_SOFT,
    BG,
    BORDER,
    CATEGORIES,
    CHECK_MARK,
    CROSS_MARK,
    DANGER,
    DANGER_SOFT,
    ICONO,
    L4D2_BACKGROUND,
    SURFACE,
    SURFACE_2,
    TEXT,
    TEXT_DIM,
    TIKTOK_URL,
    WARN_MARK,
)


def _quant(n, singular, plural):
    return "%d %s" % (n, singular if n == 1 else plural)


def main(page: ft.Page):
    page.title = "L4D2 Mod Loader"
    page.bgcolor = BG
    page.padding = 0
    try:
        if not page.web:
            for name, value in window_geometry().items():
                setattr(page.window, name, value)
            page.window.resizable = True
            page.window.maximizable = True
            if os.path.isfile(ICONO):
                page.window.icon = ICONO
    except Exception:
        pass
    page.fonts = {}
    page.theme = ft.Theme(font_family="Segoe UI")

    state = l4d2_state.create_initial_state(_cfg_path)
    startup_warning = None
    try:
        state["glow_colors"] = l4d2_glows.load_colors()
    except Exception as ex:
        dbg("load colors ERR %r" % ex)
        state["glow_colors"] = l4d2_glows.default_colors()
        startup_warning = "No se pudo leer la configuración de glows."
    state["glow_dirty"] = False
    state["glow_applied"] = False
    state["glow_preset"] = "Personalizado"
    state["selected_glow_key"] = "survivor_health_high"
    folder_picker = ft.FilePicker()
    try:
        page.services.append(folder_picker)
    except Exception:
        pass

    def track_task(future):
        state["_tasks"].add(future)
        future.add_done_callback(lambda done: state["_tasks"].discard(done))
        return future

    def ui_later(delay, fn):
        async def _t():
            await asyncio.sleep(delay)
            if state["_closing"]:
                return
            try:
                fn()
            except Exception as ex:
                dbg("ui_later ERR %r" % ex)
        try:
            return track_task(page.run_task(_t))
        except Exception:
            return None

    def safe_update():
        try:
            page.update()
        except Exception:
            pass

    dialogs = {}
    closing_dialogs = set()

    def show_dlg(dlg):
        dialogs[id(dlg.content)] = dlg
        on_dismiss = dlg.on_dismiss

        def dismissed(e):
            dialogs.pop(id(dlg.content), None)
            closing_dialogs.discard(id(dlg.content))
            if on_dismiss:
                on_dismiss(e)

        dlg.on_dismiss = dismissed
        if hasattr(page, "open"):
            page.open(dlg)
        elif hasattr(page, "show_dialog"):
            page.show_dialog(dlg)

    def close_dlg(dlg):
        if dlg is None:
            return
        dialogs.pop(id(dlg.content), None)
        closing_dialogs.discard(id(dlg.content))
        dlg.open = False
        try:
            dlg.update()
        except Exception:
            safe_update()

    def animate_display(cnt):
        dbg("dialog in")
        def _in():
            if id(cnt) not in dialogs or id(cnt) in closing_dialogs:
                return
            cnt.scale = 1.0
            cnt.opacity = 1.0
            try:
                page.update()
            except Exception as ex:
                dbg("dialog in ERR %r" % ex)
        if ui_later(0.04, _in) is None:
            _in()

    def close_dialog_anim(cnt, pane=None):
        dlg = dialogs.get(id(cnt))
        if dlg is None or id(cnt) in closing_dialogs:
            return
        closing_dialogs.add(id(cnt))
        if pane:
            pane["generation"] = pane.get("generation", 0) + 1
            pane["current_id"] = None
        dbg("dialog out")
        cnt.opacity = 0.0
        cnt.scale = 0.96
        try:
            page.update()
        except Exception as ex:
            dbg("dialog out ERR %r" % ex)

        def _c():
            close_dlg(dlg)
            dbg("dialog closed")

        if ui_later(0.16, _c) is None:
            _c()

    def get_addon(aid):
        return next((a for a in state["addons"] if a["id"] == aid), None)

    def effective_deps(aid):
        if aid in state["deps"]:
            return [d for d in state["deps"][aid] if d]
        a = get_addon(aid)
        return list(a.get("auto_deps") or []) if a else []

    def deps_map_all():
        d = {}
        for a in state["addons"]:
            x = effective_deps(a["id"])
            if x:
                d[a["id"]] = x
        return d

    def save_config_file(name, data):
        try:
            return bool(core.save_json(_cfg_path(name), data))
        except Exception as ex:
            dbg("save %s ERR %r" % (name, ex))
            return False

    def save_favs():
        return save_config_file("favs.json", sorted(state["favs"]))

    async def save_last_config_async(reason, l4d2):
        try:
            ids = sorted(await asyncio.to_thread(core.currently_enabled, l4d2))
            config = {"ids": ids, "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                      "reason": reason}
            ok = await asyncio.to_thread(save_config_file, "last_config.json", config)
        except Exception as ex:
            dbg("last config ERR %r" % ex)
            ok = False
        if ok:
            state["last_config"] = config
        elif not state["_closing"]:
            notify("No se pudo guardar la configuración anterior.", "warn")
        return ok

    def toggle_fav(addon):
        previous = set(state["favs"])
        if addon["id"] in state["favs"]:
            state["favs"].discard(addon["id"])
        else:
            state["favs"].add(addon["id"])
        if not save_favs():
            state["favs"] = previous
            notify("No se pudieron guardar los favoritos.", "err")
        refresh_list()

    def deps_sin_uso(removed_ids):
        keep = set(state["active_ids"]) - set(removed_ids)
        removed = set(removed_ids)
        extra = set()
        for i in removed:
            for d in effective_deps(i):
                if d in keep:
                    still_needed = any(d in effective_deps(r) for r in keep)
                    if not still_needed:
                        extra.add(d)
        return sorted(extra)

    MAX_TOASTS = 3
    toasts_column = ft.Column(spacing=6, tight=True)
    toast_wrapper = ft.Container(
        bottom=22, left=0, right=0,
        content=ft.Row([toasts_column],
                       alignment=ft.MainAxisAlignment.CENTER),
        visible=False,
    )
    modal_wrap = ft.Container(
        top=0, bottom=0, left=0, right=0, visible=False,
        content=ft.Container(expand=True),
    )
    _modal_card = [None]

    def show_card(card):
        _modal_card[0] = card
        barrier = ft.Container(expand=True, bgcolor="#6B000000",
                               on_click=lambda e: hide_card())
        holder = ft.Container(
            top=0, bottom=0, left=0, right=0,
            content=ft.Row([card], expand=True,
                           alignment=ft.MainAxisAlignment.CENTER,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
        )
        card.opacity = 0.0
        card.scale = 0.94
        card.animate_opacity = ft.Animation(200, "easeOut")
        card.animate_scale = ft.Animation(220, "easeOut")
        modal_wrap.content = ft.Stack([barrier, holder], expand=True)
        modal_wrap.visible = True
        page.update()

        def _in():
            if _modal_card[0] is not card:
                return
            card.opacity = 1.0
            card.scale = 1.0
            try:
                page.update()
            except Exception:
                pass
        if ui_later(0.04, _in) is None:
            _in()

    def hide_card():
        card = _modal_card[0]
        if not card:
            return
        card.opacity = 0.0
        try:
            page.update()
        except Exception:
            pass

        def _final():
            if _modal_card[0] is not card:
                return
            modal_wrap.visible = False
            modal_wrap.content = ft.Container(expand=True)
            _modal_card[0] = None
            try:
                page.update()
            except Exception:
                pass
        if ui_later(0.14, _final) is None:
            _final()

    def notify(msg, kind="ok"):
        icon, color = {"ok": (CHECK_MARK, ACCENT),
                       "err": (CROSS_MARK, DANGER),
                       "warn": (WARN_MARK, AMBER)}[kind]
        pill = ft.Container(
            content=ft.Row(
                [
                    ft.Text(icon, size=14, weight=ft.FontWeight.W_700,
                            color=color),
                    ft.Text(msg, size=13, color=TEXT),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=16, vertical=10),
            bgcolor=SURFACE_2,
            border_radius=12,
            border=ft.Border.all(1, color),
            opacity=0.0,
            offset=(0, 0.25),
            animate_opacity=ft.Animation(250, "easeOut"),
            animate_offset=ft.Animation(250, "easeOut"),
        )
        while len(toasts_column.controls) >= MAX_TOASTS:
            toasts_column.controls.pop(0)
        toasts_column.controls.append(pill)
        toast_wrapper.visible = True
        page.update()
        dbg("toast show: %s" % msg)

        def show_in():
            pill.opacity = 1.0
            pill.offset = (0, 0)
            try:
                page.update()
            except Exception as ex:
                dbg("toast in ERR %r" % ex)

        ui_later(0.03, show_in)

        def hide():
            dbg("toast hide: %s" % msg)
            pill.opacity = 0.0
            pill.offset = (0, 0.25)
            try:
                page.update()
            except Exception as ex:
                dbg("toast fade ERR %r" % ex)

        ui_later(3.0, hide)

        def final():
            try:
                if pill in toasts_column.controls:
                    toasts_column.controls.remove(pill)
                if not toasts_column.controls:
                    toast_wrapper.visible = False
                page.update()
            except Exception as ex:
                dbg("toast final ERR %r" % ex)

        ui_later(3.25, final)

    status_dot = ft.Container(width=8, height=8, border_radius=4,
                              bgcolor=TEXT_DIM)
    status_text = ft.Text("Buscando L4D2...", size=12, color=TEXT_DIM,
                          max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
    counts_text = ft.Text("", size=12, color="#D3D8E3",
                          weight=ft.FontWeight.W_500)
    view_title = ft.Text("Mods en Versus", size=29,
                         weight=ft.FontWeight.W_800, color=TEXT)
    header_actions = ft.Container()
    pending_cleanup_text = ft.Text("", size=11, color=AMBER, expand=True)
    pending_cleanup_banner = ft.Container(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.SCHEDULE, color=AMBER, size=17),
                pending_cleanup_text,
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=AMBER_SOFT,
        border=ft.Border.all(1, AMBER),
        border_radius=8,
        padding=ft.Padding.symmetric(horizontal=12, vertical=9),
        visible=False,
    )

    def set_pending_cleanup(ids, announce=False):
        ids = set(ids)
        previous = set(state["_pending_cleanup_ids"])
        state["_pending_cleanup_ids"] = ids
        pending_cleanup_banner.visible = bool(ids)
        if ids:
            count = len(ids)
            pending_cleanup_text.value = (
                "%s desuscrito%s pendiente%s de limpiar. "
                "Se eliminará%s automáticamente al cerrar L4D2."
                % (_quant(count, "addon", "addons"),
                   "" if count == 1 else "s",
                   "" if count == 1 else "s",
                   "" if count == 1 else "n")
            )
            if announce and ids - previous:
                notify(pending_cleanup_text.value, "warn")
        try:
            sidebar_holder.content = build_sidebar()
        except Exception:
            pass
        safe_update()

    clear_box = ft.Container(
        content=ft.Icon(ft.Icons.CLOSE if hasattr(ft.Icons, "CLOSE")
                        else "\u2715", color=DANGER, size=16),
        padding=4,
        visible=False,
        ink=True,
        on_click=lambda e: clear_search(),
        tooltip="Limpiar búsqueda",
    )

    search_field = ft.TextField(
        hint_text="Buscar mods por título, ID o descripción...",
        border_color=BORDER, focused_border_color=ACCENT,
        color=TEXT, hint_style=ft.TextStyle(color=TEXT_DIM),
        bgcolor="#10131A",
        border_radius=12, height=46, content_padding=12,
        prefix_icon=ft.Icons.SEARCH,
        suffix_icon=clear_box,
    )

    def clear_search():
        state["_search_generation"] += 1
        pending = state.get("_search_task")
        if pending:
            pending.cancel()
        search_field.value = ""
        state["query"] = ""
        clear_box.visible = False
        refresh_list()

    list_view = ft.ListView(spacing=6, expand=True,
                            padding=ft.Padding.only(right=4))

    main_pane = make_pane(178, 244, page)
    workshop_button_ref = [None]
    folder_button_ref = [None]
    copy_id_button_ref = [None]
    detail_status_ref = [None]
    detail_fav_ref = [None]
    footer_left_text = ft.Text("Listo", size=12, color=ACCENT,
                               weight=ft.FontWeight.W_600)
    footer_selection_text = ft.Text("Sin selección", size=12, color=TEXT_DIM)

    preview_workers = {}
    preview_slots = asyncio.Semaphore(4)

    def load_preview(addon, pane):
        url = addon.get("_preview_url")
        if not url:
            return
        pane["generation"] = pane.get("generation", 0) + 1
        generation = pane["generation"]
        aid = addon["id"]
        load_generation = state["_load_generation"]

        async def _load():
            key = (aid, url)
            worker = preview_workers.get(key)
            if worker is None:
                async def download():
                    async with preview_slots:
                        return await asyncio.to_thread(core.get_cached_image, aid, url)

                worker = track_task(asyncio.create_task(download()))
                preview_workers[key] = worker

                def finished(done):
                    if preview_workers.get(key) is done:
                        preview_workers.pop(key, None)
                    if not done.cancelled():
                        done.exception()

                worker.add_done_callback(finished)
            try:
                path = await asyncio.shield(worker)
            except asyncio.CancelledError:
                return
            except Exception as ex:
                dbg("preview ERR %r" % ex)
                path = None
            if (not ui.request_is_current(
                    generation, pane.get("generation"), state["_closing"])
                    or load_generation != state["_load_generation"]
                    or pane["current_id"] != aid):
                return
            current = get_addon(aid)
            if current and current.get("_preview_url") == url:
                current["preview_local"] = path
            pane_set_img(pane, path)
            safe_update()

        try:
            track_task(page.run_task(_load))
        except Exception as ex:
            dbg("preview task ERR %r" % ex)

    def pane_set(pane, addon):
        pane["current_id"] = addon["id"]
        pane["title"].value = addon.get("title") or addon["id"]
        pane["meta"].value = "%s  ·  %s  ·  %s" % (
            addon["id"], core.fmt_size(addon["size"]),
            "VSCRIPT" if addon["is_vscript"] else "MOD")
        if pane["desc"]:
            pane["desc"].value = (addon.get("description")
                                  or "Sin descripción disponible.")
        lp = addon.get("preview_local")
        dbg("pane_set %s local=%s url=%s" % (
            addon["id"], bool(lp and os.path.isfile(lp)), bool(addon.get("_preview_url"))))

        def _set_text(text):
            pane["img_layer"].blur = ft.Blur(0, 0)
            pane["img_layer"].opacity = 1.0
            pane["img_layer"].content = text

        def _show_image(path):
            pane_set_img(pane, path)

        if lp and os.path.isfile(lp):
            _show_image(lp)
        else:
            url = addon.get("_preview_url")
            if url:
                pane_set_img(pane, None, loading=True)
                _set_text(pane["img_layer"].content)
                load_preview(addon, pane)
            else:
                msg = ("Descargando datos de Steam..." if state.get("fetching")
                       else "Sin preview disponible")
                _set_text(ft.Text(msg, size=12, color=TEXT_DIM,
                                  text_align=ft.TextAlign.CENTER))

    def displayed_preview_id():
        hover_id = state.get("hover_preview_id")
        if hover_id and get_addon(hover_id):
            return hover_id
        return state.get("preview_id")

    def displayed_preview_addon():
        addon_id = displayed_preview_id()
        return get_addon(addon_id) if addon_id else None

    def preview_hover(addon):
        if not addon:
            return
        dbg("hover %s" % addon["id"])
        state["hover_preview_id"] = addon["id"]
        pane_set(main_pane, addon)
        update_detail_actions()
        safe_update()

    def preview_leave(addon):
        if not addon or state.get("hover_preview_id") != addon["id"]:
            return
        state["hover_preview_id"] = None
        selected = get_addon(state["preview_id"]) if state["preview_id"] else None
        if selected:
            pane_set(main_pane, selected)
        else:
            pane_clear(main_pane)
        update_detail_actions()
        safe_update()

    def make_hover(pane):
        def hov(addon):
            dbg("hover %s" % addon["id"])
            pane_set(pane, addon)
            safe_update()
        return hov

    def make_leave(pane):
        def leave(addon):
            if pane["current_id"] != addon["id"]:
                return
            pane_clear(pane)
            safe_update()
        return leave

    def show_preview(addon_id, force=False):
        dbg("show_preview %s force=%s" % (addon_id, force))
        if state["preview_id"] == addon_id and not force:
            return
        old = state["preview_id"]
        state["preview_id"] = addon_id
        state["hover_preview_id"] = None
        if old in state["rows"]:
            state["rows"][old].set_selected(False)
        if addon_id in state["rows"]:
            state["rows"][addon_id].set_selected(True)
        addon = next((a for a in state["addons"] if a["id"] == addon_id), None)
        if not addon:
            return
        pane_set(main_pane, addon)
        update_detail_actions()
        safe_update()

    def clear_preview(addon=None):
        if addon and state["preview_id"] != addon["id"]:
            return
        old = state["preview_id"]
        state["preview_id"] = None
        state["hover_preview_id"] = None
        if old in state["rows"]:
            state["rows"][old].set_selected(False)
        pane_clear(main_pane)
        update_detail_actions()
        safe_update()

    chip_controls = {}

    def chip_hover(e):
        on = str(getattr(e, "data", "")).lower() in ("true", "1")
        e.control.scale = 1.05 if on else 1.0
        e.control.update()

    CHIP_SEL_COLOR = {"Favoritos": AMBER}

    def build_chip(name):
        selected = name == state["category"]
        sel_color = CHIP_SEL_COLOR.get(name, ACCENT)
        chip = ft.Container(
            content=ft.Text(name, size=12,
                            color=BG if selected else TEXT_DIM,
                            weight=(ft.FontWeight.W_600 if selected
                                    else ft.FontWeight.NORMAL)),
            padding=ft.Padding.symmetric(horizontal=14, vertical=7),
            border_radius=20,
            bgcolor=sel_color if selected else SURFACE,
            border=None if selected else ft.Border.all(1, BORDER),
            on_click=lambda e, n=name: select_category(n),
            on_hover=chip_hover,
            animate_scale=ft.Animation(150, "easeOut"),
            ink=True,
        )
        chip_controls[name] = chip
        return chip

    chips_row = ft.Row([build_chip(c) for c in CATEGORIES], spacing=8,
                       scroll=ft.ScrollMode.AUTO, expand=True)

    def sort_toggled(e=None):
        state["sort_recent"] = not state["sort_recent"]
        sort_btn.text = ("Reciente primero" if state["sort_recent"]
                         else "Antiguo primero")
        refresh_list()

    sort_btn = ft.TextButton("Antiguo primero", on_click=sort_toggled,
                             icon=ft.Icons.SORT,
                             tooltip="Cambiar orden",
                             style=ft.ButtonStyle(color=TEXT,
                                                  text_style=ft.TextStyle(size=12),
                                                  padding=ft.Padding.symmetric(
                                                      horizontal=8, vertical=6)))

    def clear_selection(e=None):
        state["selected_ids"].clear()
        update_selection_controls()
        safe_update()
        notify("Selección desmarcada.", "ok")

    desmar_btn = ft.TextButton("Desmarcar selección",
                               on_click=clear_selection,
                               visible=False,
                               style=ft.ButtonStyle(color=ACCENT,
                                                    text_style=ft.TextStyle(size=12),
                                                    padding=ft.Padding.symmetric(
                                                        horizontal=8, vertical=6)))

    def select_category(name):
        dbg("category %s" % name)
        state["category"] = name
        for n, c in chip_controls.items():
            sel = n == name
            sel_color = CHIP_SEL_COLOR.get(n, ACCENT)
            c.bgcolor = sel_color if sel else SURFACE
            c.border = None if sel else ft.Border.all(1, BORDER)
            c.content.color = BG if sel else TEXT_DIM
            c.content.weight = (ft.FontWeight.W_600 if sel
                                else ft.FontWeight.NORMAL)
        refresh_list()

    def do_play(e):
        try:
            os.startfile("steam://rungameid/550")
            notify("Lanzando Left 4 Dead 2 mediante Steam...", "ok")
        except Exception:
            notify("No se pudo lanzar Steam.", "err")

    def launch_external(url):
        async def _open():
            try:
                await page.launch_url(url)
            except Exception:
                notify("No se pudo abrir el navegador.", "err")
        try:
            page.run_task(_open)
        except Exception:
            try:
                os.startfile(url)
            except Exception:
                notify("No se pudo abrir el navegador.", "err")

    def open_tiktok(e):
        launch_external(TIKTOK_URL)

    def open_steam(e):
        a = displayed_preview_addon()
        if not a:
            notify("Pase el cursor sobre un addon primero.", "warn")
            return
        launch_external("https://steamcommunity.com/sharedfiles/"
                        "filedetails/?id=%s" % a["id"])

    def open_folder(e):
        a = displayed_preview_addon()
        if not a:
            notify("Pase el cursor sobre un addon primero.", "warn")
            return
        try:
            os.startfile(os.path.dirname(a["path"]))
        except Exception:
            notify("No se pudo abrir la carpeta.", "err")

    async def copy_addon_id(e):
        a = displayed_preview_addon()
        if not a:
            notify("Pase el cursor sobre un addon primero.", "warn")
            return
        if await copy_text_to_clipboard(page, a["id"], log=dbg):
            notify("ID copiado al portapapeles.", "ok")
        else:
            notify("No se pudo copiar el ID.", "err")

    def update_detail_actions():
        addon = displayed_preview_addon()
        if workshop_button_ref[0]:
            workshop_button_ref[0].disabled = not bool(
                addon and addon["id"].isdigit())
        if folder_button_ref[0]:
            folder_button_ref[0].disabled = not bool(
                addon and os.path.isdir(os.path.dirname(addon["path"])))
        if copy_id_button_ref[0]:
            copy_id_button_ref[0].disabled = not bool(addon)
        if detail_status_ref[0]:
            is_active = bool(addon and addon["id"] in state["active_ids"])
            detail_status_ref[0].content.controls[1].value = (
                "Activo" if is_active else "Inactivo")
            detail_status_ref[0].content.controls[0].color = (
                ACCENT if is_active else TEXT_DIM)
            detail_status_ref[0].bgcolor = ACCENT_SOFT if is_active else SURFACE_2
            detail_status_ref[0].border = ft.Border.all(
                1, ACCENT if is_active else BORDER)
        if detail_fav_ref[0]:
            is_fav = bool(addon and addon["id"] in state["favs"])
            detail_fav_ref[0].content.value = "★" if is_fav else "☆"
            detail_fav_ref[0].content.color = AMBER if is_fav else TEXT_DIM

    def collect_health_snapshot(refresh_running=False):
        return diagnostics.collect_health_snapshot(
            state, _cfg_path, refresh_running=refresh_running, log=dbg)

    def do_restore_last_config(e=None):
        if not state["l4d2"]:
            notify("No se encontró L4D2.", "warn")
            return
        if state.get("_glow_status_error"):
            notify("No se pudo comprobar la configuración de glows.", "err")
            return
        if state["_l4d2_was_running"] is True:
            notify("Cierre L4D2 antes de restaurar la configuración.", "warn")
            return
        config = state.get("last_config") or {}
        ids = [str(value) for value in config.get("ids", [])]
        if not ids:
            notify("No hay una última configuración guardada todavía.", "warn")
            return

        installed = {addon["id"] for addon in state["addons"]}
        summary = ui.last_config_summary(config, installed, state["active_ids"])
        missing = [addon_id for addon_id in ids if addon_id not in installed]
        target = [addon_id for addon_id in ids if addon_id in installed]
        current = set(state["active_ids"])
        to_disable = sorted(current - set(target))
        to_enable = [get_addon(addon_id) for addon_id in target
                     if addon_id not in current and get_addon(addon_id)]

        def confirm_last():
            if state.get("_restore_last_busy"):
                return
            state["_restore_last_busy"] = True
            l4d2 = state["l4d2"]
            close_dlg(dlg)
            progress = show_progress("Aplicando última configuración...",
                                     "Actualizando los addons activos de L4D2.")

            async def _run_last():
                error = None
                actual = None
                try:
                    if state.get("_glow_status_error"):
                        raise RuntimeError("No se pudo comprobar la configuración de glows.")
                    if await asyncio.to_thread(core.l4d2_running):
                        raise RuntimeError("Cierre L4D2 antes de aplicar la configuración.")
                    current_ids = set(await asyncio.to_thread(core.currently_enabled, l4d2))
                    disable_ids = sorted(current_ids - set(target))
                    compat = [dict(get_addon(aid)) for aid in target
                              if aid not in current_ids and get_addon(aid)
                              and not get_addon(aid).get("is_vscript")]
                    if disable_ids or compat:
                        await save_last_config_async(
                            "Antes de volver a la última configuración", l4d2)
                    if disable_ids and not await asyncio.to_thread(
                            core.disable, l4d2, disable_ids, debug_log):
                        raise RuntimeError("No se pudieron quitar todos los addons anteriores.")
                    if compat and not await asyncio.to_thread(
                            core.enable, l4d2, compat, debug_log):
                        raise RuntimeError("No se pudieron activar todos los addons guardados.")
                except Exception as ex:
                    error = str(ex)
                    dbg("restore last ERR %r" % ex)
                finally:
                    try:
                        actual = set(await asyncio.to_thread(core.currently_enabled, l4d2))
                    except Exception as ex:
                        error = error or str(ex)
                    state["_restore_last_busy"] = False
                    close_progress(progress)
                if state["_closing"] or state["l4d2"] != l4d2:
                    return
                if actual is not None:
                    state["active_ids"] = actual
                complete = actual == set(ids) and not error
                if complete:
                    state["selected_ids"].clear()
                refresh_list()
                if complete:
                    notify("Última configuración aplicada (%s)." % _quant(
                        len(actual), "addon", "addons"), "ok")
                else:
                    msg = ("No se pudo verificar la configuración activa." if actual is None
                           else "Configuración parcial: %d de %d addons guardados activos." % (
                               len(actual & set(ids)), len(ids)))
                    if missing:
                        msg += " %d no instalado(s)." % len(missing)
                    extra = (actual or set()) - set(ids)
                    if extra:
                        msg += " %d anterior(es) aún activo(s)." % len(extra)
                    if error:
                        msg += " " + error
                    notify(msg, "warn" if actual is not None else "err")

            try:
                track_task(page.run_task(_run_last))
            except Exception as ex:
                state["_restore_last_busy"] = False
                close_progress(progress)
                dbg("restore last task ERR %r" % ex)
                notify("No se pudo iniciar la restauración de configuración.", "err")

        items = [
            "Se intentará volver a %s." % _quant(
                summary["count"], "addon guardado", "addons guardados"),
            "Se activarán %d y se quitarán %d según el estado actual." % (
                len(to_enable), len(to_disable)),
            "Guardada: %s" % (summary["saved_at"] or "sin fecha registrada"),
        ]
        if missing:
            items.append("%d addon(s) ya no están instalados y se omitirán." %
                         len(missing))
        cnt = confirm_dialog_content(
            ft.Icons.RESTORE,
            "Volver a última configuración",
            "Restaura la combinación activa anterior guardada automáticamente.",
            items,
            note=("No se borran VPKs de Workshop. Solo se ajustan entradas "
                  "gestionadas por el loader."),
            width=500,
            color=ACCENT,
        )
        dlg = ft.AlertDialog(
            content=cnt,
            actions=[
                ft.TextButton("Cancelar",
                              on_click=lambda ev: close_dialog_anim(cnt)),
                ft.FilledButton(
                    "Aplicar última config",
                    icon=ft.Icons.RESTORE,
                    on_click=lambda ev: confirm_last(),
                    style=ft.ButtonStyle(
                        bgcolor=ACCENT, color=BG,
                        shape=ft.RoundedRectangleBorder(radius=8))),
            ],
            modal=True,
        )
        show_dlg(dlg)
        animate_display(cnt)

    async def open_diagnostic(e=None):
        generation = state['_load_generation']
        snap = await asyncio.to_thread(
            diagnostics.collect_health_snapshot, dict(state), _cfg_path, True, dbg)
        if state['_closing'] or state['_load_generation'] != generation:
            return
        state['_l4d2_was_running'] = snap['game_running']
        state['_game_status_error'] = snap['game_status_error']
        report = ui.format_diagnostic_report(snap)
        warnings = ui.diagnostic_warnings(snap)

        async def copy_report(ev=None):
            if await copy_text_to_clipboard(page, report, log=dbg):
                notify("Diagnóstico copiado al portapapeles.", "ok")
            else:
                notify("No se pudo copiar el diagnóstico.", "err")

        def metric_card(icon, label, value, color=TEXT):
            return ft.Container(
                content=ft.Row(
                    [
                        ft.Container(
                            content=ft.Icon(icon, size=24, color=ACCENT),
                            width=54,
                            height=54,
                            border_radius=12,
                            bgcolor=ACCENT_SOFT,
                            border=ft.Border.all(1, "#1E8B55"),
                            alignment=ft.Alignment.CENTER,
                        ),
                        ft.Column(
                            [
                                ft.Text(label, size=13, color=TEXT_DIM,
                                        max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS),
                                ft.Text(value, size=24, color=color,
                                        weight=ft.FontWeight.W_800,
                                        max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS),
                            ],
                            spacing=4,
                            expand=True,
                        ),
                    ],
                    spacing=14,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                expand=True,
                height=86,
                bgcolor="#111821",
                border=ft.Border.all(1, "#263747"),
                border_radius=10,
                padding=14,
            )

        def detail_row(icon, label, value, ok=True):
            color = ACCENT if ok else AMBER
            return ft.Row(
                [
                    ft.Container(width=7, height=7,
                                 border_radius=4, bgcolor=color),
                    ft.Icon(icon, size=17, color=TEXT_DIM),
                    ft.Text(label, size=13, color=TEXT_DIM, expand=True,
                            max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(value, size=13, color=TEXT,
                            weight=ft.FontWeight.W_700,
                            max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )

        alert_color = AMBER if warnings else ACCENT
        alert_title = ("Requiere atención" if warnings
                       else "Todo se ve correcto")
        alert_items = warnings[:3] if warnings else [
            "No se detectaron alertas principales."
        ]
        if len(warnings) > 3:
            alert_items.append("+ %d alerta(s) más en el reporte." %
                               (len(warnings) - 3))
        alert_icon = getattr(
            ft.Icons, "WARNING_AMBER_ROUNDED",
            getattr(ft.Icons, "WARNING", ft.Icons.INFO_OUTLINE))
        ok_icon = ft.Icons.CHECK_CIRCLE_OUTLINE if not warnings else alert_icon
        cnt = dialog_shell(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(
                                content=ft.Row(
                                    [
                                        ft.Container(
                                            content=ft.Icon(
                                                getattr(
                                                    ft.Icons,
                                                    "FACT_CHECK_OUTLINED",
                                                    ft.Icons.INFO_OUTLINE),
                                                size=30,
                                                color=ACCENT),
                                            width=62,
                                            height=62,
                                            border_radius=14,
                                            bgcolor=ACCENT_SOFT,
                                            border=ft.Border.all(1, ACCENT),
                                            alignment=ft.Alignment.CENTER,
                                        ),
                                        ft.Column(
                                            [
                                                ft.Text("Diagnóstico", size=24,
                                                        color=TEXT,
                                                        weight=ft.FontWeight.W_800),
                                                ft.Text(
                                                    "Resumen listo para soporte o Discord.",
                                                    size=14,
                                                    color=TEXT_DIM),
                                            ],
                                            spacing=3,
                                            expand=True,
                                        ),
                                    ],
                                    spacing=16,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                                expand=True,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.CLOSE,
                                icon_color=TEXT_DIM,
                                tooltip="Cerrar",
                                on_click=lambda ev: close_dialog_anim(cnt),
                                style=ft.ButtonStyle(
                                    bgcolor=SURFACE,
                                    shape=ft.RoundedRectangleBorder(radius=10)),
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        [
                            metric_card(
                                getattr(ft.Icons, "INVENTORY_2_OUTLINED",
                                        ft.Icons.VIEW_MODULE),
                                "Addons instalados",
                                str(snap["addon_count"]),
                                TEXT),
                            metric_card(ft.Icons.PLAY_ARROW_OUTLINED,
                                        "Activos",
                                        str(snap["active_count"]),
                                        ACCENT),
                            metric_card(
                                getattr(ft.Icons, "MONITOR_HEART_OUTLINED",
                                        ft.Icons.INFO_OUTLINE),
                                "Estado",
                                "Revisar" if warnings else "Correcto",
                                alert_color),
                        ],
                        spacing=14,
                    ),
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Container(
                                    content=ft.Icon(ok_icon, size=42,
                                                    color=alert_color),
                                    width=70,
                                    height=70,
                                    border_radius=36,
                                    bgcolor=(AMBER_SOFT if warnings
                                             else ACCENT_SOFT),
                                    border=ft.Border.all(1, alert_color),
                                    alignment=ft.Alignment.CENTER,
                                ),
                                ft.Column(
                                    [
                                        ft.Text(alert_title, size=13,
                                                color=TEXT,
                                                weight=ft.FontWeight.W_800),
                                        *[
                                            ft.Text(item, size=11,
                                                    color=alert_color,
                                                    max_lines=1,
                                                    overflow=ft.TextOverflow.ELLIPSIS)
                                            for item in alert_items
                                        ],
                                    ],
                                    spacing=3,
                                    expand=True,
                                ),
                            ],
                            spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.START,
                        ),
                        bgcolor=AMBER_SOFT if warnings else ACCENT_SOFT,
                        border=ft.Border.all(1, alert_color),
                        border_radius=10,
                        padding=18,
                    ),
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Column(
                                    [
                                        detail_row(
                                                   getattr(ft.Icons,
                                                           "SPORTS_ESPORTS",
                                                           ft.Icons.INFO_OUTLINE),
                                                   "Juego",
                                                   "Desconocido" if snap["game_running"] is None
                                                   else "Abierto" if snap["game_running"]
                                                   else "Cerrado",
                                                   snap["game_running"] is False),
                                        detail_row(
                                                   getattr(ft.Icons, "STEAM",
                                                           ft.Icons.LINK),
                                                   "Workshop",
                                                   "Detectado" if snap["workshop_exists"]
                                                   else "No detectado",
                                                   snap["workshop_exists"]),
                                        detail_row(
                                                   ft.Icons.DESCRIPTION_OUTLINED,
                                                   "gameinfo.txt",
                                                   "Escribible" if snap["gameinfo_writable"]
                                                   else "Bloqueado",
                                                   snap["gameinfo_writable"]),
                                    ],
                                    spacing=12,
                                    expand=True,
                                ),
                                ft.Container(width=1, height=112,
                                             bgcolor="#263747"),
                                ft.Column(
                                    [
                                        detail_row(
                                                   getattr(ft.Icons,
                                                           "CLEANING_SERVICES",
                                                           ft.Icons.DELETE_OUTLINE),
                                                   "Limpieza",
                                                   str(snap["pending_cleanup_count"]),
                                                   not snap["pending_cleanup_count"]),
                                        detail_row(
                                                   ft.Icons.VISIBILITY_OUTLINED,
                                                   "Visión infectado",
                                                   snap["vision_state"],
                                                   snap["vision_state"] != "off"),
                                        detail_row(
                                                   ft.Icons.LIST_ALT,
                                                   "Seleccionados",
                                                   str(snap["selected_count"]),
                                                   True),
                                    ],
                                    spacing=12,
                                    expand=True,
                                ),
                            ],
                            spacing=22,
                        ),
                        bgcolor="#111821",
                        border=ft.Border.all(1, "#263747"),
                        border_radius=10,
                        padding=16,
                    ),
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Icon(ft.Icons.DESCRIPTION_OUTLINED,
                                                size=18, color=TEXT_DIM),
                                        ft.Text("Reporte técnico", size=16,
                                                color=TEXT,
                                                weight=ft.FontWeight.W_800),
                                        ft.Container(expand=True),
                                        ft.Icon(getattr(ft.Icons, "CONTENT_COPY",
                                                        ft.Icons.COPY),
                                                size=16, color=TEXT_DIM),
                                        ft.Text("Copiable", size=12,
                                                color=TEXT_DIM),
                                    ],
                                    spacing=8,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                                ft.TextField(
                                    value=report,
                                    multiline=True,
                                    read_only=True,
                                    min_lines=8,
                                    max_lines=8,
                                    width=696,
                                    border_color="#263747",
                                    focused_border_color=ACCENT,
                                    color=TEXT,
                                    text_size=12,
                                    text_style=ft.TextStyle(
                                        font_family="Consolas"),
                                    bgcolor="#0C0F16",
                                    border_radius=8,
                                    content_padding=14,
                                ),
                            ],
                            spacing=12,
                        ),
                        bgcolor="#111821",
                        border=ft.Border.all(1, "#263747"),
                        border_radius=10,
                        padding=10,
                    ),
                    ft.Divider(color="#263747", height=1),
                    ft.Row(
                        [
                            ft.Container(expand=True),
                            ft.TextButton(
                                "Cerrar",
                                on_click=lambda ev: close_dialog_anim(cnt),
                                style=ft.ButtonStyle(
                                    color=TEXT,
                                    bgcolor="#1A2633",
                                    padding=ft.Padding.symmetric(
                                        horizontal=28, vertical=14),
                                    shape=ft.RoundedRectangleBorder(radius=10),
                                ),
                            ),
                            ft.FilledButton(
                                "Copiar reporte",
                                icon=getattr(ft.Icons, "CONTENT_COPY",
                                             ft.Icons.COPY),
                                on_click=copy_report,
                                style=ft.ButtonStyle(
                                    bgcolor=ACCENT, color=BG,
                                    padding=ft.Padding.symmetric(
                                        horizontal=28, vertical=14),
                                    shape=ft.RoundedRectangleBorder(radius=10),
                                ),
                            ),
                        ],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                spacing=14,
                tight=True,
            ),
            760,
            padded=True,
        )
        dlg = ft.AlertDialog(
            content=cnt,
            modal=True,
            actions=[],
            bgcolor=SURFACE_2,
            content_padding=0,
            actions_padding=0,
            shape=ft.RoundedRectangleBorder(radius=18),
        )
        show_dlg(dlg)
        animate_display(cnt)

    async def toggle_vision(e):
        if not state["l4d2"]:
            notify("No se encontró L4D2.", "warn")
            return
        if not await require_game_closed():
            return
        if state.get("_vision_busy"):
            return
        state["_vision_busy"] = True
        l4d2 = state["l4d2"]

        async def _run_vision():
            try:
                st = await asyncio.to_thread(core.vision_state, l4d2)
                if st == "unknown":
                    notify("No hay archivos de visión de infectado en el juego.", "warn")
                    return
                operation = core.restore_infected_vision if st == "off" else core.disable_infected_vision
                ok = await asyncio.to_thread(operation, l4d2, log=debug_log)
                if state["_closing"]:
                    return
                if ok:
                    notify("Visión de infectado restaurada (tinte normal)." if st == "off"
                           else "Visión de infectado quitada (sin tinte naranja/azul).", "ok")
                else:
                    notify("No se pudo cambiar la visión de infectado.", "err")
                sidebar_holder.content = build_sidebar()
                safe_update()
            except Exception as ex:
                dbg("vision ERR %r" % ex)
                if not state["_closing"]:
                    notify("No se pudo cambiar la visión de infectado: %s" % ex, "err")
            finally:
                state["_vision_busy"] = False

        try:
            track_task(page.run_task(_run_vision))
        except Exception as ex:
            state["_vision_busy"] = False
            notify("No se pudo iniciar el cambio de visión: %s" % ex, "err")

    async def restore_original_clicked(e):
        await do_restore(e)

    def build_sidebar():
        return l4d2_sidebar.build_sidebar(
            state=state,
            health_snapshot=collect_health_snapshot(),
            icon_path=ICONO,
            on_play=do_play,
            on_nav=lambda view: switch_view(view),
            on_diagnostic=open_diagnostic,
            on_restore_last=do_restore_last_config,
            on_restore_original=restore_original_clicked,
            on_toggle_vision=toggle_vision,
            on_tiktok=open_tiktok,
            tiktok_url=TIKTOK_URL,
        )

    sidebar_holder = ft.Container(content=build_sidebar(), padding=18,
                                  bgcolor="#10131A")

    def switch_view(v):
        if state["view"] == v:
            return
        dbg("switch_view %s" % v)
        state["view"] = v
        state["_render_signature"] = None
        state["preview_id"] = None
        sidebar_holder.content = build_sidebar()
        titles = {
            "mods": "Mods en Versus",
            "activos": "Addons activos",
            "glows": "Glows",
        }
        view_title.value = titles.get(v, "Mods en Versus")
        header_actions.content = build_header_actions()
        refresh_list()

    enable_button_ref = [None]
    remove_button_ref = [None]
    remove_all_button_ref = [None]

    def choose_l4d2_path(e=None):
        async def _pick():
            initial = state.get("manual_l4d2_path") or state.get("l4d2") or ""
            try:
                result = folder_picker.get_directory_path(
                    dialog_title=("Selecciona Left 4 Dead 2, left4dead2, "
                                  "addons, workshop o una Steam Library"),
                    initial_directory=initial if os.path.isdir(initial) else None,
                )
                selected = await result if hasattr(result, "__await__") else result
            except Exception as ex:
                dbg("folder picker ERR %r" % ex)
                notify("No se pudo abrir el selector de carpeta.", "err")
                return
            if not selected:
                return
            resolved = core.resolve_l4d2_path(selected)
            if not resolved:
                notify("Esa carpeta no parece contener Left 4 Dead 2.", "err")
                return
            if not save_config_file("game_path.json", {"path": resolved}):
                notify("No se pudo guardar la ruta de L4D2.", "err")
                return
            state["manual_l4d2_path"] = resolved
            notify("Ruta de L4D2 guardada. Recargando mods...", "ok")
            load_addons()

        try:
            track_task(page.run_task(_pick))
        except Exception as ex:
            dbg("folder picker task ERR %r" % ex)
            notify("No se pudo abrir el selector de carpeta.", "err")

    def build_header_actions():
        style = ft.ButtonStyle(bgcolor=ACCENT, color=BG,
                               text_style=ft.TextStyle(size=13),
                               padding=ft.Padding.symmetric(horizontal=14,
                                                             vertical=10),
                               shape=ft.RoundedRectangleBorder(radius=8))
        style.bgcolor = {
            ft.ControlState.DEFAULT: ACCENT,
            ft.ControlState.DISABLED: BORDER,
        }
        style.color = {
            ft.ControlState.DEFAULT: BG,
            ft.ControlState.DISABLED: TEXT_DIM,
        }
        if state["view"] == "glows":
            return ft.Row([], spacing=8)
        if state["view"] == "activos":
            remove_button_ref[0] = ft.FilledButton(
                "Quitar addon", on_click=do_quitar_addon,
                disabled=not state["active_ids"],
                style=ft.ButtonStyle(
                    bgcolor=SURFACE_2, color=TEXT,
                    shape=ft.RoundedRectangleBorder(radius=8)))
            remove_all_button_ref[0] = ft.TextButton(
                "Quitar todos", on_click=do_quitar_todos,
                disabled=not state["active_ids"],
                style=ft.ButtonStyle(color=DANGER))
            return ft.Row(
                [
                    remove_button_ref[0],
                    remove_all_button_ref[0],
                ],
                spacing=8,
            )
        enable_button_ref[0] = ft.FilledButton(
            "Habilitar",
            icon=ft.Icons.CHECK_CIRCLE_OUTLINE,
            on_click=do_enable,
            disabled=not state["selected_ids"],
            tooltip="Habilitar addons seleccionados",
            style=style,
        )
        return ft.Row(
            [
                ft.Container(
                    content=ft.TextButton(
                        "Buscar ruta",
                        icon=(ft.Icons.FOLDER_OPEN if hasattr(
                            ft.Icons, "FOLDER_OPEN") else ft.Icons.FOLDER),
                        on_click=choose_l4d2_path,
                        style=ft.ButtonStyle(
                            color=TEXT,
                            text_style=ft.TextStyle(size=12),
                            padding=ft.Padding.symmetric(
                                horizontal=10, vertical=6),
                        ),
                    ),
                    bgcolor=SURFACE_2,
                    border_radius=8,
                    border=ft.Border.all(1, BORDER),
                    ink=True,
                ),
                ft.Container(
                    content=ft.TextButton("Presets", on_click=open_presets,
                                          style=ft.ButtonStyle(
                                              color=ACCENT,
                                              text_style=ft.TextStyle(size=12),
                                              padding=ft.Padding.symmetric(
                                                  horizontal=10, vertical=6))),
                    bgcolor=SURFACE_2,
                    border_radius=8,
                    border=ft.Border.all(1, BORDER),
                    ink=True,
                ),
                enable_button_ref[0],
            ],
            spacing=6,
        )

    def load_addons():
        state["_load_generation"] += 1
        generation = state["_load_generation"]
        state["fetching"] = True
        if state.get("_load_progress"):
            close_progress(state["_load_progress"])
        load_progress = show_progress(
            "Cargando mods...",
            "Escaneando addons instalados y datos del Workshop.",
        )
        state["_load_progress"] = load_progress

        def finish_load_progress():
            progress = load_progress
            if state.get("_load_progress") is progress:
                state["_load_progress"] = None
            close_progress(progress)

        async def _scan():
            l4d2 = await asyncio.to_thread(
                core.find_l4d2, state.get("manual_l4d2_path"))
            if not ui.request_is_current(
                    generation, state["_load_generation"], state["_closing"]):
                finish_load_progress()
                return
            state["l4d2"] = l4d2
            if not l4d2:
                state["fetching"] = False
                finish_load_progress()
                status_dot.bgcolor = DANGER
                status_text.value = "L4D2 no encontrado"
                counts_text.value = ""
                safe_update()
                notify("No se encontró L4D2. Verifique que Steam esté instalado.",
                       "err")
                return

            try:
                state["glow_applied"] = await asyncio.to_thread(l4d2_glows.is_applied, l4d2)
                state["_glow_status_error"] = None
            except (OSError, ValueError) as ex:
                state["glow_applied"] = None
                state["_glow_status_error"] = str(ex) or type(ex).__name__
                notify("No se pudo comprobar la configuración de glows. "
                       "Recarga los mods tras corregir el archivo: %s" % ex, "warn")
            status_dot.bgcolor = ACCENT
            status_text.value = os.path.basename(l4d2)
            status_text.tooltip = l4d2
            gi = os.path.join(l4d2, "left4dead2", "gameinfo.txt")
            if os.path.isfile(gi) and not os.access(gi, os.W_OK):
                notify("El archivo gameinfo.txt no es escribible; ejecute la "
                       "app como administrador.", "warn")

            pending_legacy = await asyncio.to_thread(core.migrate_legacy_addons, l4d2, debug_log)
            if pending_legacy:
                notify('Hay addons antiguos sin origen verificable; se conservaron sus archivos.', 'warn')
            raw = await asyncio.to_thread(core.list_addons, l4d2)
            for addon in raw:
                info = await asyncio.to_thread(core.inspect_vpk, addon["path"])
                addon["title"] = info["title"]
                addon["is_vscript"] = info["is_vscript"]
                addon["type"] = "VSCRIPT" if addon["is_vscript"] else "MOD"
                addon["category"] = core.categorize(
                    addon["title"] or addon["id"], addon["id"])
                addon["description"] = None
                addon["preview_local"] = None
                addon["_preview_url"] = None
                addon["auto_deps"] = []

            if not ui.request_is_current(
                    generation, state["_load_generation"], state["_closing"]):
                finish_load_progress()
                return
            state["addons"] = raw
            l4d2_state.reconcile_addon_ids(state, raw)
            state["_disk_ids"] = {addon["id"] for addon in raw}
            state["_disk_snapshot"] = core.addon_snapshot(raw)
            state["_row_cache"].clear()
            state["_render_signature"] = None
            _seed_previews_from_cache()
            await cleanup_orphans_async(l4d2, generation)
            if not ui.request_is_current(
                    generation, state["_load_generation"], state["_closing"]):
                return
            active = await asyncio.to_thread(core.currently_enabled, l4d2)
            if not ui.request_is_current(
                    generation, state["_load_generation"], state["_closing"]):
                return
            state["active_ids"] = set(active)
            sidebar_holder.content = build_sidebar()
            refresh_list()
            return [addon["id"] for addon in raw]

        async def _load():
            try:
                ids = await _scan()
                finish_load_progress()
                if ids is not None and ui.request_is_current(
                        generation, state["_load_generation"], state["_closing"]):
                    await fetch_task(generation, ids)
            except asyncio.CancelledError:
                raise
            except Exception as ex:
                dbg("load ERR %r" % ex)
                if ui.request_is_current(
                        generation, state["_load_generation"], state["_closing"]):
                    notify("No se pudo completar la carga de mods: %s" % ex, "err")
            finally:
                finish_load_progress()
                if generation == state["_load_generation"]:
                    state["fetching"] = False
                    safe_update()
                    if state["_pending_rescan"] and not state["_closing"]:
                        state["_pending_rescan"] = False
                        load_addons()

        try:
            track_task(page.run_task(_load))
        except Exception as ex:
            state["fetching"] = False
            finish_load_progress()
            dbg("load task ERR %r" % ex)
            notify("No se pudo iniciar la carga de mods.", "err")

    def _seed_previews_from_cache():
        cache_d = os.path.join(os.getenv("LOCALAPPDATA") or os.getcwd(),
                               "L4D2ModLoader", "cache")
        for a in state["addons"]:
            if a.get("preview_local"):
                continue
            hits = glob.glob(os.path.join(cache_d, a["id"] + "_*"))
            if hits:
                a["preview_local"] = hits[0]

    async def fetch_task(generation, ids):
        dbg("fetch_task start (%d addons)" % len(ids))
        try:
            details = await asyncio.to_thread(core.fetch_workshop_details, ids)
        except Exception as ex:
            details = {}
            dbg("fetch ERR %r" % ex)
        dbg("fetch_task details=%d" % len(details))

        if not ui.request_is_current(
                generation, state["_load_generation"], state["_closing"]):
            return
        by_id = {addon["id"]: addon for addon in state["addons"]}
        for aid, detail in details.items():
            addon = by_id.get(aid)
            if not addon:
                continue
            if detail.get("title"):
                addon["title"] = detail["title"]
                addon["category"] = core.categorize(detail["title"], aid)
            addon["description"] = detail.get("description")
            addon["description_raw"] = detail.get("description_raw")
            addon["_preview_url"] = detail.get("preview_url")
        suggestions = await asyncio.to_thread(
            core.suggest_dependencies, [dict(addon) for addon in state["addons"]])
        if not ui.request_is_current(
                generation, state["_load_generation"], state["_closing"]):
            return
        for addon in state["addons"]:
            addon["auto_deps"] = suggestions.get(addon["id"], [])
        state["fetching"] = False
        state["_row_cache"].clear()
        state["_render_signature"] = None
        dbg("fetch_task done, fetching=False")
        if state["preview_id"]:
            previewed = get_addon(state["preview_id"])
            if previewed:
                pane_set(main_pane, previewed)
        refresh_list()

    cleanup_lock = asyncio.Lock()

    async def cleanup_orphans_async(l4d2, generation):
        removed, pending, error = [], None, None
        async with cleanup_lock:
            if not ui.request_is_current(
                    generation, state["_load_generation"], state["_closing"]) \
                    or state.get("_glow_status_error"):
                return
            try:
                running = None
                running = await asyncio.to_thread(core.l4d2_running)
                state["_l4d2_was_running"] = running
                if not running:
                    removed = await asyncio.to_thread(core.cleanup_orphans, l4d2, debug_log)
            except Exception as ex:
                if running is None:
                    state["_l4d2_was_running"] = None
                error = ex
                dbg("cleanup ERR %r" % ex)
            try:
                pending = set(await asyncio.to_thread(core.currently_enabled_orphans, l4d2))
            except Exception as ex:
                error = error or ex
            if not ui.request_is_current(
                    generation, state["_load_generation"], state["_closing"]):
                return
            if pending is not None:
                set_pending_cleanup(pending, announce=bool(state["_l4d2_was_running"]))
            if error:
                notify("No se pudo completar la limpieza de huérfanos: %s" % error, "warn")
            elif pending and not state["_l4d2_was_running"]:
                notify("Limpieza parcial: %d addon(s) pendiente(s)." % len(pending), "warn")
            elif removed:
                notify("Se limpiaron %d addon(s) desuscrito(s)." % len(removed), "warn")

    async def watch_workshop():
        while not state["_closing"]:
            await asyncio.sleep(10)
            try:
                if not state["l4d2"]:
                    continue
                await _check_game_closed()
                disk_addons = await asyncio.to_thread(
                    core.list_addons, state["l4d2"])
                snapshot = core.addon_snapshot(disk_addons)
                if snapshot != state.get("_disk_snapshot"):
                    dbg("workshop files changed")
                    state["_disk_snapshot"] = snapshot
                    if state["fetching"]:
                        state["_pending_rescan"] = True
                        dbg("fetch in progress, pending rescan")
                    else:
                        load_addons()
            except asyncio.CancelledError:
                return
            except Exception as ex:
                dbg("watch ERR %r" % ex)

    async def _check_game_closed():
        try:
            running_now = await asyncio.to_thread(core.l4d2_running)
        except Exception as ex:
            if state["_l4d2_was_running"] is not None:
                notify("No se pudo comprobar el estado de L4D2.", "warn")
            state["_l4d2_was_running"] = None
            dbg("game status ERR %r" % ex)
            return
        was_running = state["_l4d2_was_running"]
        state["_l4d2_was_running"] = running_now
        if running_now != was_running:
            sidebar_holder.content = build_sidebar()
            safe_update()
        if not (was_running and not running_now):
            return
        generation, l4d2 = state["_load_generation"], state["l4d2"]
        await cleanup_orphans_async(l4d2, generation)
        active = await asyncio.to_thread(core.currently_enabled, l4d2)
        if ui.request_is_current(generation, state["_load_generation"], state["_closing"]):
            state["active_ids"] = set(active)
            refresh_list()

    def visible_addons(active_ids):
        return ui.visible_addons(
            state["addons"], active_ids, state["favs"],
            view=state["view"], category=(state["category"]
                                        if state["view"] == "mods" else "Todos"),
            query=state["query"], sort_recent=state["sort_recent"],
        )

    def update_counts():
        counts_text.value = "Addons: %d  |  Activos: %d  |  Seleccionados: %d" % (
            len(state["addons"]), len(state["active_ids"]),
            len(state["selected_ids"]))
        footer_selection_text.value = (
            "%d mods seleccionados" % len(state["selected_ids"])
            if state["selected_ids"] else "Sin selección")

    def update_selection_controls():
        selectable = {
            addon["id"] for addon in state["addons"]
            if addon["id"] not in state["active_ids"]
        }
        state["selected_ids"].intersection_update(selectable)
        for aid, row in state["rows"].items():
            if row.checkbox:
                row.checkbox.value = aid in state["selected_ids"]
        selected = bool(state["selected_ids"])
        desmar_btn.visible = selected and state["view"] == "mods"
        desmar_btn.text = "Desmarcar selección (%d)" % len(
            state["selected_ids"])
        if enable_button_ref[0]:
            enable_button_ref[0].disabled = not selected
        update_counts()

    def make_empty_state():
        title, detail = ui.empty_state_message(
            state["view"], (state["category"] if state["view"] == "mods" else "Todos"), state["query"],
            bool(state["addons"]),
        )
        return ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.SEARCH_OFF, size=30, color=TEXT_DIM),
                    ft.Text(title, size=15, weight=ft.FontWeight.W_600,
                            color=TEXT),
                    ft.Text(detail, size=12, color=TEXT_DIM,
                            text_align=ft.TextAlign.CENTER),
                ],
                spacing=6,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            alignment=ft.Alignment.CENTER,
            padding=36,
        )

    def refresh_list(sync_active=False):
        dbg("refresh_list")

        if state["view"] == "glows":
            render_glows_view()
            safe_update()
            return

        search_field.visible = True
        filters_row.visible = state["view"] == "mods"
        list_toolbar.visible = state["view"] == "mods"
        preview_panel.visible = True

        if sync_active:
            state["active_ids"] = set(core.currently_enabled(state["l4d2"])) \
                if state["l4d2"] else set()
        active = state["active_ids"]
        addons = visible_addons(active)
        signatures = tuple(
            ui.row_signature(
                addon, addon["id"] in active,
                addon["id"] in state["favs"], state["view"])
            for addon in addons
        )
        render_signature = (
            signatures,
            state["view"], state["category"], state["query"],
            state["sort_recent"],
        )

        if render_signature != state["_render_signature"]:
            rows = {}
            controls = []
            cache = state["_row_cache"]
            for addon, signature in zip(addons, signatures):
                cached = cache.get(addon["id"])
                row = cached[1] if cached and cached[0] == signature else None
                if row is None:
                    is_active = addon["id"] in active
                    in_mods_view = state["view"] == "mods"
                    row = ModRow(
                        addon,
                        on_select=lambda ad: show_preview(ad["id"]),
                        on_toggle=on_toggle,
                        active=is_active,
                        with_checkbox=in_mods_view,
                        checked=addon["id"] in state["selected_ids"],
                        fav=addon["id"] in state["favs"],
                        on_fav=toggle_fav,
                        show_active_badge=in_mods_view,
                        on_hover=preview_hover,
                        on_leave=preview_leave,
                        show_thumbnail=True,
                    )
                    cache[addon["id"]] = (signature, row)
                rows[addon["id"]] = row
                controls.append(row)
            state["rows"] = rows
            list_view.controls = controls if controls else [make_empty_state()]
            state["_render_signature"] = render_signature

        visible_ids = [addon["id"] for addon in addons]
        if state.get("hover_preview_id") not in visible_ids:
            state["hover_preview_id"] = None
        preview_panel.visible = bool(visible_ids)
        if visible_ids:
            target = (state["preview_id"] if state["preview_id"] in visible_ids
                      else visible_ids[0])
            if state["preview_id"] != target:
                state["preview_id"] = target
                pane_set(main_pane, get_addon(target))
        else:
            state["preview_id"] = None
            pane_clear(main_pane, "No hay un addon visible para mostrar")

        for aid, row in state["rows"].items():
            row.set_selected(aid == state["preview_id"])
        update_detail_actions()
        update_selection_controls()
        if remove_button_ref[0]:
            remove_button_ref[0].disabled = not active
        if remove_all_button_ref[0]:
            remove_all_button_ref[0].disabled = not active
        safe_update()

    def on_toggle(addon, value):
        if value:
            state["selected_ids"].add(addon["id"])
            for dependency in effective_deps(addon["id"]):
                dependency_addon = get_addon(dependency)
                if dependency_addon and dependency not in state["active_ids"]:
                    state["selected_ids"].add(dependency)
        else:
            state["selected_ids"].discard(addon["id"])
        update_selection_controls()
        safe_update()

    def search_changed(e):
        value = e.control.value or ""
        dbg("search %r" % value)
        clear_box.visible = bool(value)
        state["_search_generation"] += 1
        generation = state["_search_generation"]
        previous = state.get("_search_task")
        if previous:
            previous.cancel()

        async def _debounced_search():
            try:
                await asyncio.sleep(0.18)
            except asyncio.CancelledError:
                return
            if not ui.request_is_current(
                    generation, state["_search_generation"],
                    state["_closing"]):
                return
            state["query"] = value
            refresh_list()

        try:
            state["_search_task"] = track_task(page.run_task(
                _debounced_search))
        except Exception:
            state["query"] = value
            refresh_list()
        safe_update()

    search_field.on_change = search_changed

    async def require_game_closed():
        if state.get("_glow_status_error"):
            notify("No se puede modificar L4D2 hasta comprobar su configuración de glows.", "err")
            return False
        if state.get('_checking_game'):
            return False
        generation, game = state['_load_generation'], state['l4d2']
        state['_checking_game'] = True
        try:
            running = await asyncio.to_thread(core.l4d2_running)
            if (state['_closing'] or state['_load_generation'] != generation
                    or state['l4d2'] != game):
                return False
            state["_l4d2_was_running"] = running
        except Exception as ex:
            state["_l4d2_was_running"] = None
            dbg("game status ERR %r" % ex)
            notify("No se pudo comprobar si L4D2 está cerrado. Inténtalo de nuevo.", "err")
            return False
        finally:
            state['_checking_game'] = False
        if running:
            notify("Cierre el juego (Left 4 Dead 2) antes de modificar los addons.",
                   "err")
            return False
        return True

    async def sync_active_state(game, generation):
        try:
            active = set(await asyncio.to_thread(core.currently_enabled, game))
        except Exception as ex:
            notify('No se pudo releer el estado de addons: %s' % ex, 'err')
            return False
        if (state['_closing'] or state['_load_generation'] != generation
                or state['l4d2'] != game):
            return False
        state['active_ids'] = active
        refresh_list()
        return True

    def win_size():
        w = getattr(page, "width", None) or 1040.0
        h = getattr(page, "height", None) or 680.0
        return float(w), float(h)

    def dialog_metrics():
        ww, wh = win_size()
        dw = max(480.0, min(700.0, ww * 0.48))
        img_h = max(110.0, min(140.0, wh * 0.20))
        list_h = max(150.0, min(340.0, wh - 320 - img_h))
        return dw, img_h, list_h

    def show_progress(title, subtitle):
        cnt = progress_dialog_content(title, subtitle)
        dlg = ft.AlertDialog(content=cnt, actions=[], modal=True)
        progress = {"content": cnt, "dialog": dlg, "closed": False}
        show_dlg(dlg)
        animate_display(cnt)
        return progress

    def close_progress(progress):
        if not progress or progress.get("closed"):
            return
        progress["closed"] = True
        if progress.get("content"):
            close_dialog_anim(progress["content"])

    def on_glow_color_changed(key, value):
        state["selected_glow_key"] = key
        state["glow_colors"][key] = value
        state["glow_dirty"] = True
        counts_text.value = "Glows: cambios sin aplicar"
        footer_selection_text.value = "Glows pendientes"
        safe_update()

    def select_glow_color(key, rebuild=True):
        state["selected_glow_key"] = key
        if rebuild:
            render_glows_view()
        safe_update()

    def open_glow_color_picker(key, label):
        state["selected_glow_key"] = key
        current = state["glow_colors"].get(
            key, l4d2_glows.default_colors().get(key, "#FFFFFF"))
        try:
            current = l4d2_glows.normalize_hex(current)
        except ValueError:
            current = "#FFFFFF"
        selected_value = [current]
        preview = ft.Container(
            width=156,
            height=112,
            bgcolor=current,
            border_radius=12,
            border=ft.Border.all(1, "#FFFFFF33"),
            shadow=ft.BoxShadow(
                blur_radius=20,
                color=current + "66",
                offset=ft.Offset(0, 0),
            ),
        )
        current_chip = ft.Container(
            width=42,
            height=28,
            bgcolor=current,
            border_radius=7,
            border=ft.Border.all(1, "#FFFFFF33"),
        )
        new_color_text = ft.Text(current, size=12, color=TEXT_DIM,
                                 weight=ft.FontWeight.W_700)
        custom_visible = [False]
        slider_controls = []
        slider_value_labels = []
        hex_field = ft.TextField(
            value=current,
            label="HEX",
            width=156,
            height=44,
            text_size=13,
            color=TEXT,
            bgcolor="#10131A",
            border_color=BORDER,
            focused_border_color=ACCENT,
            content_padding=ft.Padding.symmetric(horizontal=10, vertical=8),
        )

        def _apply_preview(value):
            try:
                normalized = l4d2_glows.normalize_hex(value)
            except ValueError:
                hex_field.border_color = DANGER
                return None
            hex_field.border_color = BORDER
            selected_value[0] = normalized
            preview.bgcolor = normalized
            preview.shadow = ft.BoxShadow(
                blur_radius=20,
                color=normalized + "66",
                offset=ft.Offset(0, 0),
            )
            new_color_text.value = normalized
            _refresh_swatch_borders(normalized)
            rgb_values = [int(round(v * 255))
                          for v in l4d2_glows.hex_to_rgb_values(normalized)]
            for slider, label_ctrl, rgb_value in zip(
                    slider_controls, slider_value_labels, rgb_values):
                slider.value = rgb_value
                label_ctrl.value = str(rgb_value)
            return normalized

        def _hex_changed(e=None):
            _apply_preview(hex_field.value)
            try:
                page.update()
            except Exception:
                pass

        hex_field.on_change = _hex_changed

        swatch_values = [
            "#FF1A1A", "#FF6200", "#FFD000", "#00FF40",
            "#20D97B", "#00A2FF", "#4D75FF", "#9B5CFF",
            "#FF00D4", "#D414C7", "#B2B2FF", "#FFFFFF",
            "#8A93A3", "#242936", "#10131A", "#000000",
        ]
        swatch_controls = []
        rgb = [int(round(value * 255))
               for value in l4d2_glows.hex_to_rgb_values(current)]

        def _refresh_swatch_borders(active_color):
            for swatch, value in swatch_controls:
                swatch.border = ft.Border.all(
                    2, ACCENT if value == active_color else "#FFFFFF22")

        def _choose_swatch(value):
            hex_field.value = value
            _apply_preview(value)
            try:
                page.update()
            except Exception:
                pass

        def _make_swatch(value):
            swatch = ft.Container(
                width=34,
                height=34,
                bgcolor=value,
                border_radius=8,
                border=ft.Border.all(
                    2, ACCENT if value == current else "#FFFFFF22"),
                ink=True,
                tooltip=value,
                on_click=lambda e, color=value: _choose_swatch(color),
            )
            swatch_controls.append((swatch, value))
            return swatch

        def _swatch_row(values):
            return ft.Row(
                [_make_swatch(value) for value in values],
                spacing=8,
                alignment=ft.MainAxisAlignment.START,
            )

        palette = ft.Column(
            [
                _swatch_row(swatch_values[:8]),
                _swatch_row(swatch_values[8:]),
            ],
            spacing=8,
        )

        def _hex_from_rgb():
            return "#%02X%02X%02X" % tuple(
                int(round(slider.value or 0)) for slider in slider_controls)

        def _slider_changed(e=None):
            value = _hex_from_rgb()
            hex_field.value = value
            _apply_preview(value)
            try:
                page.update()
            except Exception:
                pass

        def _slider_row(name, value, color):
            value_label = ft.Text(str(value), width=32, size=11,
                                  color=TEXT_DIM,
                                  weight=ft.FontWeight.W_700)
            slider = ft.Slider(
                min=0,
                max=255,
                value=value,
                divisions=255,
                label="{value}",
                active_color=color,
                on_change=_slider_changed,
            )
            slider_controls.append(slider)
            slider_value_labels.append(value_label)
            return ft.Row(
                [
                    ft.Text(name, width=18, size=12, color=TEXT_DIM,
                            weight=ft.FontWeight.W_700),
                    slider,
                    value_label,
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )

        custom_panel = ft.Container(
            content=ft.Column(
                [
                    _slider_row("R", rgb[0], "#FF4D4D"),
                    _slider_row("G", rgb[1], ACCENT),
                    _slider_row("B", rgb[2], "#4D75FF"),
                ],
                spacing=0,
            ),
            visible=False,
            bgcolor="#0B0E14",
            border=ft.Border.all(1, BORDER),
            border_radius=10,
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
        )
        custom_button_label = ft.Text(
            "Custom", size=12, color=TEXT,
            weight=ft.FontWeight.W_700)

        def _toggle_custom(e=None):
            custom_visible[0] = not custom_visible[0]
            custom_panel.visible = custom_visible[0]
            custom_button_label.value = (
                "Ocultar custom" if custom_visible[0] else "Custom")
            try:
                page.update()
            except Exception:
                pass

        custom_button = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.TUNE, size=15, color=TEXT),
                    custom_button_label,
                ],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            height=34,
            padding=ft.Padding.symmetric(horizontal=11, vertical=6),
            bgcolor=SURFACE_2,
            border=ft.Border.all(1, BORDER),
            border_radius=8,
            ink=True,
            on_click=_toggle_custom,
            tooltip="Ajustar con sliders RGB",
        )

        def confirm_color():
            normalized = _apply_preview(hex_field.value)
            if not normalized:
                notify("Color inválido. Usa formato #RRGGBB.", "err")
                return
            on_glow_color_changed(key, normalized)
            render_glows_view()
            close_dialog_anim(cnt)
            safe_update()

        cnt = ft.Container(
            content=ft.Column(
                [
                    modal_header(
                        ft.Icons.PALETTE_OUTLINED
                        if hasattr(ft.Icons, "PALETTE_OUTLINED")
                        else ft.Icons.COLOR_LENS,
                        "Elegir color",
                        label,
                        ACCENT,
                    ),
                    ft.Row(
                        [
                            preview,
                            ft.Column(
                                [
                                    ft.Row(
                                        [
                                            current_chip,
                                            ft.Column(
                                                [
                                                    ft.Text(
                                                        "Actual",
                                                        size=10,
                                                        color=TEXT_DIM,
                                                    ),
                                                    ft.Text(
                                                        current,
                                                        size=12,
                                                        color=TEXT,
                                                        weight=ft.FontWeight.W_700,
                                                    ),
                                                ],
                                                spacing=1,
                                            ),
                                        ],
                                        spacing=10,
                                        vertical_alignment=(
                                            ft.CrossAxisAlignment.CENTER),
                                    ),
                                    hex_field,
                                    new_color_text,
                                ],
                                spacing=8,
                                expand=True,
                            ),
                        ],
                        spacing=14,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Text("Colores rápidos", size=11,
                                                color=TEXT_DIM,
                                                weight=ft.FontWeight.W_700),
                                        ft.Container(expand=True),
                                        custom_button,
                                    ],
                                    vertical_alignment=(
                                        ft.CrossAxisAlignment.CENTER),
                                ),
                                palette,
                                custom_panel,
                            ],
                            spacing=10,
                        ),
                        bgcolor="#10131A",
                        border=ft.Border.all(1, BORDER),
                        border_radius=10,
                        padding=12,
                    ),
                    ft.Row(
                        [
                            ft.Container(expand=True),
                            ft.TextButton(
                                "Cancelar",
                                on_click=lambda ev: close_dialog_anim(cnt),
                                style=ft.ButtonStyle(
                                    color="#A7C7FF",
                                    padding=ft.Padding.symmetric(
                                        horizontal=12, vertical=10),
                                ),
                            ),
                            ft.FilledButton(
                                "Usar color",
                                icon=ft.Icons.CHECK,
                                on_click=lambda ev: confirm_color(),
                                style=ft.ButtonStyle(
                                    bgcolor=ACCENT,
                                    color=BG,
                                    shape=ft.RoundedRectangleBorder(radius=8),
                                    padding=ft.Padding.symmetric(
                                        horizontal=16, vertical=10),
                                ),
                            ),
                        ],
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                spacing=16,
                tight=True,
            ),
            width=460,
            padding=20,
            bgcolor="#24282F",
            border_radius=18,
        )
        dlg = ft.AlertDialog(
            content=cnt,
            actions=[],
            modal=True,
        )
        show_dlg(dlg)
        animate_display(cnt)

    def apply_glow_preset(name):
        preset = l4d2_glows.PRESETS.get(name)
        if not preset:
            return
        state["glow_colors"] = dict(preset)
        state["glow_preset"] = name
        state["glow_dirty"] = True
        render_glows_view()
        safe_update()

    def render_glows_view():
        search_field.visible = False
        filters_row.visible = False
        list_toolbar.visible = False
        preview_panel.visible = False
        state["_render_signature"] = None
        counts_text.value = (
            "Edita colores y aplica el cfg gestionado por el loader"
        )
        footer_selection_text.value = (
            "Cambios sin aplicar" if state["glow_dirty"]
            else "Glows aplicados" if state["glow_applied"]
            else "Glows sin aplicar"
        )
        list_view.controls = [
            l4d2_glows_view.build_glows_view(
                state["glow_colors"],
                state["glow_applied"],
                state["glow_dirty"],
                on_change=on_glow_color_changed,
                on_apply=do_apply_glows,
                on_restore=do_restore_glows,
                on_preset=apply_glow_preset,
                on_pick_color=open_glow_color_picker,
                on_select_color=select_glow_color,
                selected_key=state.get("selected_glow_key"),
            )
        ]

    async def do_apply_glows(e=None):
        if not state["l4d2"]:
            notify("No se encontró L4D2.", "warn")
            return
        if not await require_game_closed():
            return
        try:
            colors = l4d2_glows.normalized_colors(state["glow_colors"])
        except ValueError as ex:
            notify(str(ex), "err")
            return
        progress = show_progress(
            "Aplicando glows...",
            "Creando cfg y enlazándolo desde autoexec.cfg.",
        )

        async def _run():
            try:
                ok = await asyncio.to_thread(
                    l4d2_glows.apply_glows,
                    state["l4d2"],
                    colors,
                    state.get("glow_preset"),
                    debug_log,
                )
            except Exception as ex:
                ok = False
                dbg("apply glows ERR %r" % ex)
            if state["_closing"]:
                return
            close_progress(progress)
            if ok:
                state["glow_colors"] = colors
                state["glow_dirty"] = False
                state["glow_applied"] = True
                render_glows_view()
                notify("Glows aplicados. Reinicia L4D2 si estaba abierto.",
                       "ok")
            else:
                notify("No se pudieron aplicar los glows.", "err")
            safe_update()

        try:
            track_task(page.run_task(_run))
        except Exception as ex:
            dbg("apply glows task ERR %r" % ex)
            close_progress(progress)
            notify("No se pudieron aplicar los glows.", "err")

    async def do_restore_glows(e=None):
        if not state["l4d2"]:
            notify("No se encontró L4D2.", "warn")
            return
        if not await require_game_closed():
            return
        progress = show_progress(
            "Restaurando glows...",
            "Quitando únicamente el cfg y bloque creados por el loader.",
        )

        async def _run():
            try:
                ok = await asyncio.to_thread(
                    l4d2_glows.restore_glows, state["l4d2"], debug_log)
            except Exception as ex:
                ok = False
                dbg("restore glows ERR %r" % ex)
            if state["_closing"]:
                return
            close_progress(progress)
            if ok:
                state["glow_dirty"] = False
                state["glow_applied"] = False
                render_glows_view()
                notify("Glows restaurados; se conservaron configs ajenas.",
                       "ok")
            else:
                notify("No se pudieron restaurar los glows.", "err")
            safe_update()

        try:
            track_task(page.run_task(_run))
        except Exception as ex:
            dbg("restore glows task ERR %r" % ex)
            close_progress(progress)
            notify("No se pudieron restaurar los glows.", "err")

    async def do_enable(e):
        if not await require_game_closed():
            return
        chosen = [a for a in state["addons"]
                  if a["id"] in state["selected_ids"]
                  and a["id"] not in state["active_ids"]]
        if not chosen:
            notify("Seleccione al menos un addon para habilitar.", "warn")
            return

        _dw, _img_h, _list_h = dialog_metrics()
        _dw = max(640.0, min(780.0, win_size()[0] * 0.70))
        _img_h = max(120.0, min(148.0, win_size()[1] * 0.21))
        pane = make_pane(int(_img_h), 230, page, desc_lines=0)
        hov = make_hover(pane)
        leave = make_leave(pane)
        extra_deps = {}
        rows = []
        seen_ids = set()
        vscripts = []

        def add_row(a, is_dep, parents=None):
            if a["id"] in seen_ids:
                return
            seen_ids.add(a["id"])
            if a["is_vscript"]:
                vscripts.append(a)
            extra = None
            if parents:
                extra = "Requisito de: " + ", ".join(parents)
            row, box = dialog_row(a, with_checkbox=True, value=True,
                                  check_cb=lambda ad, v: None, on_hover=hov,
                                  on_leave=leave, extra_meta=extra,
                                  compact=True)
            rows.append((a, box))
            pane_rows.append(row)

        pane_rows = []
        for a in chosen:
            add_row(a, False)
            for d in effective_deps(a["id"]):
                da = get_addon(d)
                if not da or da["id"] in state["active_ids"]:
                    continue
                extra_deps.setdefault(d, []).append(
                    a.get("title") or a["id"])
        for d, parents in extra_deps.items():
            da = get_addon(d)
            if da:
                add_row(da, True, parents)

        n_deps = len(extra_deps)
        banner = None
        if vscripts:
            names = _short_names(vscripts)
            banner = ft.Container(
                content=ft.Text(
                    "Los VScripts NO funcionan con este método de habilitación;\n"
                    "se omitirán: " + names,
                    size=11, color=AMBER),
                bgcolor=AMBER_SOFT,
                border=ft.Border.all(1, AMBER),
                border_radius=8,
                padding=ft.Padding.symmetric(horizontal=10, vertical=8),
            )

        def confirm_enable():
            sel_ids = [a["id"] for a, box in rows if box and box.value]
            if not sel_ids:
                close_dialog_anim(cnt, pane)
                notify("Ningún addon seleccionado.", "warn")
                return
            final_ids = core.resolve_deps(sel_ids, deps_map_all())
            compat_addons, omitted = [], 0
            for i in final_ids:
                da = get_addon(i)
                if not da:
                    continue
                if da["is_vscript"]:
                    omitted += 1
                else:
                    compat_addons.append(da)
            if not compat_addons:
                close_dialog_anim(cnt, pane)
                notify("Ningún addon compatible seleccionado.", "warn")
                return
            close_dlg(dlg)
            progress = show_progress(
                "Activando addons...",
                "Aplicando la selección en la configuración de L4D2.",
            )

            async def _run_enable():
                try:
                    await save_last_config_async("Antes de habilitar addons", state["l4d2"])
                    ok = await asyncio.to_thread(
                        core.enable, state["l4d2"], compat_addons, debug_log)
                except Exception as ex:
                    ok = False
                    dbg("enable async ERR %r" % ex)
                if state["_closing"]:
                    return
                close_progress(progress)
                if ok:
                    for c in compat_addons:
                        state["selected_ids"].discard(c["id"])
                    refresh_list(sync_active=True)
                    msg = "%s habilitado%s correctamente" % (
                        _quant(len(compat_addons), "addon", "addons"),
                        "" if len(compat_addons) == 1 else "s")
                    if omitted:
                        msg += "  ·  %d VScript omitido(s)" % omitted
                    notify(msg, "ok")
                else:
                    notify("No se pudieron habilitar los addons", "err")

            try:
                track_task(page.run_task(_run_enable))
            except Exception as ex:
                dbg("enable task ERR %r" % ex)
                close_progress(progress)
                notify("No se pudieron habilitar los addons", "err")

        sub = ("Se incluye %d dependencia automáticamente." % n_deps
               if n_deps == 1 else
               "Se incluyen %d dependencias automáticamente." % n_deps
               ) if n_deps else None
        if pane_rows:
            pane_set(pane, rows[0][0])
        cnt = enable_dialog_content(
            pane_rows, pane, len(rows), n_deps, banner=banner,
            height=int(_list_h), width=int(_dw),
            current_addon=rows[0][0] if rows else None)
        dlg = ft.AlertDialog(
            content=cnt,
            actions=[
                ft.TextButton("Cancelar",
                              on_click=lambda ev: close_dialog_anim(cnt, pane)),
                ft.FilledButton("Habilitar", on_click=lambda ev: confirm_enable(),
                                style=ft.ButtonStyle(bgcolor=ACCENT, color=BG,
                                                    shape=ft.RoundedRectangleBorder(radius=8))),
            ],
            modal=True,
            bgcolor=SURFACE_2,
            content_padding=0,
            actions_padding=ft.Padding.only(left=22, right=22, bottom=18, top=4),
            shape=ft.RoundedRectangleBorder(radius=16),
        )

        show_dlg(dlg)
        animate_display(cnt)

    def _short_names(addons, maxn=4):
        names = ", ".join((a.get("title") or a["id"]) for a in addons[:maxn])
        if len(addons) > maxn:
            names += ", ..."
        return names

    async def do_quitar_addon(e):
        if not await require_game_closed():
            return
        act = [a for a in state["addons"] if a["id"] in state["active_ids"]]
        if not act:
            notify("No hay addons activos para quitar.", "warn")
            return
        checked = set()

        _dw, _img_h, _list_h = dialog_metrics()
        _dw = max(640.0, min(780.0, win_size()[0] * 0.70))
        _img_h = max(120.0, min(148.0, win_size()[1] * 0.21))
        pane = make_pane(int(_img_h), 230, page, desc_lines=0)
        hov = make_hover(pane)
        leave = make_leave(pane)
        remove_list = ft.ListView(height=int(_list_h), spacing=6,
                                  scroll=ft.ScrollMode.AUTO)
        selected_count = count_badge("0 seleccionados", AMBER)
        visible_count = ft.Text("", size=11, color=TEXT_DIM)
        remove_button_ref_local = [None]

        def update_remove_controls():
            n = len(checked)
            selected_count.content.value = _quant(
                n, "seleccionado", "seleccionados")
            selected_count.bgcolor = ACCENT if n else AMBER_SOFT
            selected_count.border = None if n else ft.Border.all(1, AMBER)
            selected_count.content.color = BG if n else AMBER
            if remove_button_ref_local[0]:
                remove_button_ref_local[0].disabled = not bool(checked)

        def toggle(ad, val):
            (checked.add if val else checked.discard)(ad["id"])
            update_remove_controls()
            safe_update()

        def empty_remove_state(query):
            message = ("No hay coincidencias para quitar."
                       if query.strip() else "No hay addons activos visibles.")
            detail = ("Prueba otro nombre o ID."
                      if query.strip() else
                      "Los addons activos aparecerán aquí.")
            return ft.Container(
                content=ft.Column(
                    [
                        ft.Icon(ft.Icons.SEARCH_OFF, size=28, color=TEXT_DIM),
                        ft.Text(message, size=13,
                                weight=ft.FontWeight.W_600, color=TEXT),
                        ft.Text(detail, size=11, color=TEXT_DIM,
                                text_align=ft.TextAlign.CENTER),
                    ],
                    spacing=6,
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                alignment=ft.Alignment.CENTER,
                padding=24,
            )

        def rebuild_remove_rows(query=""):
            matches = ui.filter_addons_by_name(act, query)
            visible_count.value = "%d visible%s" % (
                len(matches), "" if len(matches) == 1 else "s")
            if matches:
                rows = []
                for addon in matches:
                    row, _box = dialog_row(
                        addon,
                        with_checkbox=True,
                        value=addon["id"] in checked,
                        check_cb=toggle,
                        on_hover=hov,
                        on_leave=leave,
                        compact=True,
                        show_status=False,
                    )
                    rows.append(row)
                remove_list.controls = rows
                current_ids = {addon["id"] for addon in matches}
                if pane["current_id"] not in current_ids:
                    pane_set(pane, matches[0])
            else:
                remove_list.controls = [empty_remove_state(query)]
                pane_clear(pane, "No hay un addon activo para mostrar")
            update_remove_controls()

        def search_remove_changed(e):
            rebuild_remove_rows(e.control.value or "")
            safe_update()

        remove_search = ft.TextField(
            hint_text="Buscar addon activo por nombre o ID...",
            border_color=BORDER,
            focused_border_color=DANGER,
            color=TEXT,
            hint_style=ft.TextStyle(color=TEXT_DIM),
            border_radius=8,
            height=42,
            content_padding=10,
            prefix_icon=ft.Icons.SEARCH,
            on_change=search_remove_changed,
        )

        pane["title"].size = 15
        pane["title"].weight = ft.FontWeight.W_700
        pane["meta"].size = 11
        backdrop_height = int(pane["height"] + 42)
        pane["backdrop_layer"] = ft.Container(
            width=int(_dw) - 36,
            height=backdrop_height,
            opacity=1.0,
        )
        remove_overlay = ft.Container(
            width=int(_dw) - 36,
            height=backdrop_height,
            gradient=ft.LinearGradient(
                begin=ft.Alignment(-1, 0),
                end=ft.Alignment(1, 0),
                colors=["#11131AF2", "#11131AC8", "#11131A96"],
            ),
        )
        remove_wash = ft.Container(
            width=int(_dw) - 36,
            height=backdrop_height,
            gradient=ft.LinearGradient(
                begin=ft.Alignment(-1, -1),
                end=ft.Alignment(1, 1),
                colors=["#55351D24", "#0011131A", "#3311131A"],
            ),
            opacity=0.82,
        )
        top = ft.Container(
            content=ft.Stack(
                [
                    pane["backdrop_layer"],
                    remove_wash,
                    remove_overlay,
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Container(
                                    content=pane["img"],
                                    bgcolor="#0E0F15",
                                    border=ft.Border.all(1, BORDER),
                                    border_radius=8,
                                    padding=8,
                                ),
                                ft.Container(
                                    content=ft.Column(
                                        [
                                            pane["title"],
                                            pane["meta"],
                                            ft.Row(
                                                [
                                                    count_badge(_quant(
                                                        len(act), "activo",
                                                        "activos"), AMBER),
                                                    selected_count,
                                                ],
                                                spacing=8,
                                                wrap=True,
                                            ),
                                            ft.Row(
                                                [
                                                    ft.Icon(
                                                        ft.Icons.INFO_OUTLINE,
                                                        size=16,
                                                        color=TEXT_DIM),
                                                    ft.Text(
                                                        "Pasa el mouse por un "
                                                        "addon para revisar su "
                                                        "preview antes de "
                                                        "quitarlo.",
                                                        size=12,
                                                        color=TEXT_DIM,
                                                        max_lines=2,
                                                        overflow=ft.TextOverflow.ELLIPSIS,
                                                        expand=True,
                                                    ),
                                                ],
                                                spacing=8,
                                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                            ),
                                        ],
                                        spacing=8,
                                    ),
                                    expand=True,
                                    padding=ft.Padding.only(left=10, top=2),
                                ),
                            ],
                            spacing=12,
                            vertical_alignment=ft.CrossAxisAlignment.START,
                        ),
                        padding=12,
                    ),
                ],
                width=int(_dw) - 36,
                height=backdrop_height,
            ),
            bgcolor="#11131A",
            border=ft.Border.all(1, "#4B2F36"),
            border_radius=8,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

        cnt = dialog_shell(
            ft.Column(
                [
                    modal_header(ft.Icons.REMOVE_CIRCLE_OUTLINE,
                                 "Quitar addons",
                                 "Selecciona solo lo que dejará de cargarse.",
                                 DANGER),
                    top,
                    remove_search,
                    ft.Row(
                        [
                            ft.Text("Addons activos", size=12,
                                    weight=ft.FontWeight.W_700, color=TEXT),
                            ft.Container(expand=True),
                            visible_count,
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(
                        content=remove_list,
                        border=ft.Border.all(1, BORDER),
                        border_radius=8,
                        padding=6,
                        bgcolor="#111116",
                    ),
                ],
                spacing=12,
            ),
            int(_dw),
            padded=True,
        )

        def confirm_quit():
            if not checked:
                notify("Seleccione al menos un addon para quitar.", "warn")
                return
            ids = list(checked)
            extra = deps_sin_uso(ids)
            total = sorted(set(ids) | set(extra))
            game, generation = state['l4d2'], state['_load_generation']
            close_dlg(dlg)
            progress = show_progress(
                "Quitando addons...",
                "Actualizando la configuración activa de L4D2.",
            )

            async def _run_disable():
                try:
                    await save_last_config_async("Antes de quitar addons", game)
                    ok = await asyncio.to_thread(
                        core.disable, game, total, debug_log)
                except Exception as ex:
                    ok = False
                    dbg("disable async ERR %r" % ex)
                if state["_closing"]:
                    return
                close_progress(progress)
                if not await sync_active_state(game, generation):
                    return
                if ok:
                    state["selected_ids"].difference_update(total)
                    refresh_list()
                    msg = "%s deshabilitado%s" % (
                        _quant(len(total), "addon", "addons"),
                        "" if len(total) == 1 else "s")
                    if extra:
                        msg += "  ·  %s sin uso" % _quant(
                            len(extra), "requisito", "requisitos")
                    notify(msg, "ok")
                else:
                    notify("Desactivación incompleta. Se actualizó el estado real de los addons.", "err")

            try:
                track_task(page.run_task(_run_disable))
            except Exception as ex:
                dbg("disable task ERR %r" % ex)
                close_progress(progress)
                notify("No se pudieron quitar los addons", "err")

        remove_button_ref_local[0] = ft.FilledButton(
            "Quitar",
            icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
            on_click=lambda ev: confirm_quit(),
            disabled=True,
            style=ft.ButtonStyle(bgcolor=DANGER, color=BG,
                                 shape=ft.RoundedRectangleBorder(radius=8)),
        )

        rebuild_remove_rows()
        dlg = ft.AlertDialog(
            content=cnt,
            actions=[
                ft.TextButton("Cancelar",
                              on_click=lambda ev: close_dialog_anim(cnt, pane)),
                remove_button_ref_local[0],
            ],
            modal=True,
            bgcolor=SURFACE_2,
            content_padding=0,
            actions_padding=ft.Padding.only(left=22, right=22, bottom=18, top=4),
            shape=ft.RoundedRectangleBorder(radius=16),
        )

        show_dlg(dlg)
        animate_display(cnt)

    async def do_quitar_todos(e):
        if not await require_game_closed():
            return
        n = len(state["active_ids"])
        if not n:
            notify("No hay addons activos para quitar.", "warn")
            return

        cnt = confirm_dialog_content(
            ft.Icons.DELETE_SWEEP,
            "Quitar todos los activos",
            "Se deshabilitarán todos los addons cargados por el loader.",
            [
                "Se quitarán %s." % _quant(n, "addon activo", "addons activos"),
                "Volverán a estar disponibles en la vista Mods.",
                "No se borrarán los VPK originales de Workshop.",
            ],
            width=450,
            color=DANGER,
        )

        dlg = ft.AlertDialog(
            content=cnt,
            actions=[
                ft.TextButton("Cancelar", on_click=lambda ev: close_dialog_anim(cnt)),
                ft.FilledButton("Quitar todos", on_click=lambda ev: confirm_quit_all(),
                                style=ft.ButtonStyle(bgcolor=DANGER, color=BG,
                                                     shape=ft.RoundedRectangleBorder(radius=8))),
            ],
            modal=True,
        )

        def confirm_quit_all():
            ids = list(state["active_ids"])
            game, generation = state['l4d2'], state['_load_generation']
            close_dlg(dlg)
            progress = show_progress(
                "Quitando addons...",
                "Deshabilitando todos los addons activos.",
            )

            async def _run_disable_all():
                try:
                    await save_last_config_async("Antes de quitar todos", game)
                    ok = await asyncio.to_thread(
                        core.disable, game, ids, debug_log)
                except Exception as ex:
                    ok = False
                    dbg("disable all async ERR %r" % ex)
                if state["_closing"]:
                    return
                close_progress(progress)
                if not await sync_active_state(game, generation):
                    return
                if ok:
                    state["selected_ids"].difference_update(ids)
                    refresh_list()
                    notify("%s deshabilitado%s" % (
                        _quant(len(ids), "addon", "addons"),
                        "" if len(ids) == 1 else "s"), "ok")
                else:
                    notify("Desactivación incompleta. Se actualizó el estado real de los addons.", "err")

            try:
                track_task(page.run_task(_run_disable_all))
            except Exception as ex:
                dbg("disable all task ERR %r" % ex)
                close_progress(progress)
                notify("No se pudieron quitar los addons", "err")

        show_dlg(dlg)
        animate_display(cnt)

    def open_presets(e):
        rows = []
        for name, ids in (state["presets"] or {}).items():
            r = ft.Container(
                content=ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text(name, size=13, color=TEXT,
                                        weight=ft.FontWeight.W_600,
                                        max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS),
                                ft.Text(_quant(len(ids), "addon", "addons"),
                                        size=11, color=TEXT_DIM),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                        ft.TextButton("Usar",
                                      on_click=lambda ev, n=name: use_preset(n),
                                      style=ft.ButtonStyle(color=ACCENT)),
                        ft.TextButton("Quitar",
                                      on_click=lambda ev, n=name: remove_preset(n),
                                      style=ft.ButtonStyle(color=DANGER)),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding.symmetric(horizontal=12, vertical=9),
                bgcolor=SURFACE,
                border=ft.Border.all(1, BORDER),
                border_radius=8,
            )
            rows.append(r)
        if not rows:
            rows.append(ft.Container(
                content=ft.Column(
                    [
                        ft.Icon(ft.Icons.SAVE_OUTLINED, size=24,
                                color=TEXT_DIM),
                        ft.Text("Sin presets guardados", size=13,
                                color=TEXT,
                                weight=ft.FontWeight.W_600),
                        ft.Text("Selecciona addons y guarda una combinación "
                                "para usarla después.",
                                size=11, color=TEXT_DIM,
                                text_align=ft.TextAlign.CENTER),
                    ],
                    spacing=6,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                height=118,
                alignment=ft.Alignment.CENTER,
            ))
        tf = ft.TextField(hint_text="Nombre del preset...", height=40,
                          border_color=BORDER, focused_border_color=ACCENT,
                          color=TEXT, hint_style=ft.TextStyle(color=TEXT_DIM),
                          border_radius=8, content_padding=10)
        list_height = min(230, max(120, 56 * max(len(rows), 1)))
        card = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(
                                content=modal_header(
                                    ft.Icons.SAVE_OUTLINED,
                                    "Presets",
                                    "Guarda y reutiliza selecciones de addons.",
                                    ACCENT),
                                expand=True,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.CLOSE,
                                icon_color=TEXT_DIM,
                                tooltip="Cerrar",
                                on_click=lambda ev: hide_card(),
                            ),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                    ft.Container(
                        content=ft.ListView(rows, height=list_height, spacing=6,
                                            scroll=ft.ScrollMode.AUTO),
                        bgcolor="#111116",
                        border=ft.Border.all(1, BORDER),
                        border_radius=8,
                        padding=6,
                    ),
                    tf,
                    ft.FilledButton(
                        "Guardar selección (%d)" % len(state["selected_ids"]),
                        icon=ft.Icons.SAVE_OUTLINED,
                        on_click=lambda ev: save_preset(tf),
                        disabled=not state["selected_ids"],
                        style=ft.ButtonStyle(bgcolor=ACCENT, color=BG,
                                             shape=ft.RoundedRectangleBorder(radius=8))),
                ],
                spacing=12,
                tight=True,
            ),
            width=430,
            bgcolor=SURFACE_2,
            border_radius=8,
            padding=18,
            border=ft.Border.all(1, BORDER),
        )
        show_card(card)

    def save_preset(tf):
        if not state["selected_ids"]:
            notify("Seleccione al menos un addon para guardar el preset.", "warn")
            return
        name = (tf.value or "").strip() or ("Preset %d" % (
            len(state["presets"]) + 1))
        n = len(state["selected_ids"])
        presets = dict(state["presets"])
        presets[name] = sorted(state["selected_ids"])
        if not save_config_file("presets.json", presets):
            notify("No se pudo guardar el preset.", "err")
            return
        state["presets"] = presets
        state["selected_ids"].clear()
        hide_card()
        refresh_list()
        notify("Preset '%s' guardado (%s) · selección desmarcada." % (
            name, _quant(n, "addon", "addons")), "ok")

    def use_preset(name):
        hide_card()
        ids = [i for i in (state["presets"].get(name) or [])
               if get_addon(i) and i not in state["active_ids"]]
        state["selected_ids"] = set(ids)
        refresh_list()
        notify("Preset aplicado: %s seleccionado%s" % (
            _quant(len(ids), "addon", "addons"),
            "" if len(ids) == 1 else "s"), "ok")

    def remove_preset(name):
        presets = dict(state["presets"])
        presets.pop(name, None)
        if not save_config_file("presets.json", presets):
            notify("No se pudo eliminar el preset guardado.", "err")
            return
        state["presets"] = presets
        hide_card()
        notify("Preset '%s' eliminado" % name, "ok")

    async def do_restore(e=None):
        if not state["l4d2"]:
            notify("No se encontró L4D2.", "warn")
            return
        if not await require_game_closed():
            return

        async def confirm_restore(e=None):
            if not await require_game_closed():
                return
            game, generation = state['l4d2'], state['_load_generation']
            close_dlg(dlg)
            progress = show_progress(
                "Restaurando original...",
                "Revirtiendo cambios del loader de forma segura.",
            )

            async def _run_restore():
                try:
                    await save_last_config_async("Antes de restaurar original", game)
                    ok = await asyncio.to_thread(
                        core.restore, game, debug_log)
                except Exception as ex:
                    ok = False
                    dbg("restore async ERR %r" % ex)
                if state["_closing"]:
                    return
                close_progress(progress)
                if not await sync_active_state(game, generation):
                    return
                if not ok:
                    notify("No se pudo completar la restauración. No se tocaron "
                           "archivos ajenos; revise el registro de depuración.",
                           "err")
                    return
                state["selected_ids"].clear()
                state["preview_id"] = None
                set_pending_cleanup(set())
                sidebar_holder.content = build_sidebar()
                refresh_list()
                notify("L4D2 fue restaurado al estado anterior al loader.", "ok")

            try:
                track_task(page.run_task(_run_restore))
            except Exception as ex:
                dbg("restore task ERR %r" % ex)
                close_progress(progress)
                notify("No se pudo completar la restauración.", "err")

        cnt = confirm_dialog_content(
            ft.Icons.RESTORE,
            "Restaurar configuración original",
            "L4D2 volverá al estado previo a los cambios del loader.",
            [
                "Se restaurará gameinfo.txt desde el respaldo seguro.",
                "Se revertirá la visión de infectado modificada por el loader.",
                "Se quitará el cfg de glows y su bloque gestionado en autoexec.cfg.",
                "Se eliminarán únicamente copias de mods creadas por el loader.",
            ],
            note=("Los VPK de Workshop, mods externos y cambios ajenos al "
                  "programa se conservarán."),
            width=500,
            color=DANGER,
        )

        dlg = ft.AlertDialog(
            content=cnt,
            actions=[
                ft.TextButton("Cancelar",
                              on_click=lambda ev: close_dialog_anim(cnt)),
                ft.FilledButton(
                    "Restaurar original",
                    icon=ft.Icons.RESTORE,
                    on_click=confirm_restore,
                    style=ft.ButtonStyle(
                        bgcolor=DANGER, color=BG,
                        shape=ft.RoundedRectangleBorder(radius=8))),
            ],
            modal=True,
        )
        show_dlg(dlg)
        animate_display(cnt)

    header_layers = []
    if os.path.isfile(L4D2_BACKGROUND):
        header_layers.append(ft.Image(src=L4D2_BACKGROUND, width=1200,
                                      height=154, fit=ft.BoxFit.COVER,
                                      opacity=0.48))
    header_layers.extend([
        ft.Container(
            width=1200,
            height=154,
            gradient=ft.LinearGradient(
                begin=ft.Alignment(-1, 0),
                end=ft.Alignment(1, 0),
                colors=["#0C0F16F5", "#0C0F16C9", "#0C0F1680"],
            ),
        ),
        ft.Container(
            width=1200,
            height=154,
            gradient=ft.LinearGradient(
                begin=ft.Alignment(0, -1),
                end=ft.Alignment(0, 1),
                colors=["#0B101A18", "#080B12B8", "#070A10FA"],
            ),
        ),
        ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Column(
                            [
                                view_title,
                                ft.Row(
                                    [
                                        ft.Icon(getattr(ft.Icons, "SPORTS_ESPORTS",
                                                ft.Icons.INFO_OUTLINE),
                                                size=17, color=TEXT),
                                        ft.Text("Left 4 Dead 2", size=14,
                                                color=TEXT,
                                                weight=ft.FontWeight.W_700),
                                    ],
                                    spacing=7,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                                counts_text,
                            ],
                            spacing=6,
                        ),
                        padding=ft.Padding.only(left=0, right=18, top=4,
                                                bottom=6),
                        gradient=ft.LinearGradient(
                            begin=ft.Alignment(-1, 0),
                            end=ft.Alignment(1, 0),
                            colors=["#05070DCF", "#05070D72", "#05070D00"],
                        ),
                        border_radius=10,
                        expand=True,
                    ),
                    header_actions,
                ],
                vertical_alignment=ft.CrossAxisAlignment.END,
            ),
            padding=ft.Padding.only(left=22, right=22, top=22, bottom=18),
        ),
    ])

    header_row = ft.Container(
        content=ft.Stack(header_layers, height=154),
        height=154,
        border=ft.Border.only(bottom=ft.BorderSide(1, BORDER)),
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
    )

    sort_group = ft.Container(
        content=ft.Row(
            [
                ft.Text("Ordenar", size=12, color=TEXT_DIM),
                sort_btn,
            ],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=SURFACE,
        border=ft.Border.all(1, BORDER),
        border_radius=10,
        padding=ft.Padding.only(left=10, right=4, top=2, bottom=2),
    )

    filters_row = ft.Row(
        [chips_row],
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    list_toolbar = ft.Row(
        [sort_group, ft.Container(expand=True), desmar_btn],
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    center_column = ft.Column(
        [
            header_row,
            pending_cleanup_banner,
            ft.Container(
                content=search_field,
                padding=ft.Padding.only(left=18, right=18, top=14),
            ),
            ft.Container(
                content=filters_row,
                padding=ft.Padding.only(left=18, right=18, top=8, bottom=10),
            ),
            ft.Container(
                content=list_toolbar,
                padding=ft.Padding.only(left=18, right=18, bottom=10),
            ),
            ft.Container(
                content=list_view,
                padding=ft.Padding.only(left=18, right=8, bottom=8),
                expand=True,
            ),
        ],
        spacing=0,
        expand=True,
    )

    detail_parts = l4d2_detail_panel.build_detail_panel(
        main_pane,
        on_open_workshop=open_steam,
        on_open_folder=open_folder,
        on_copy_id=copy_addon_id,
        on_toggle_fav=toggle_fav,
        get_current_addon=displayed_preview_addon,
    )
    workshop_button_ref[0] = detail_parts["workshop_button"]
    folder_button_ref[0] = detail_parts["folder_button"]
    copy_id_button_ref[0] = detail_parts["copy_id_button"]
    detail_status_ref[0] = detail_parts["status"]
    detail_fav_ref[0] = detail_parts["favorite"]
    preview_panel = detail_parts["panel"]

    center_wrap = ft.Container(
        content=ft.Row([center_column, preview_panel], expand=True,
                       spacing=12,
                       vertical_alignment=ft.CrossAxisAlignment.START),
        expand=True,
    )

    bottom_bar = ft.Container(
        content=ft.Row(
            [
                ft.Row(
                    [
                        ft.Container(
                            content=ft.Icon(ft.Icons.CHECK, size=13,
                                            color=BG),
                            width=19,
                            height=19,
                            bgcolor=ACCENT,
                            border_radius=10,
                            alignment=ft.Alignment.CENTER,
                        ),
                        footer_left_text,
                        ft.Container(width=12),
                        footer_selection_text,
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(expand=True),
                ft.Row([status_dot, status_text], spacing=7,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        height=34,
        padding=ft.Padding.symmetric(horizontal=18, vertical=6),
        bgcolor="#0D1118",
        border=ft.Border.only(top=ft.BorderSide(1, BORDER)),
    )

    main_row = ft.Row(
        [
            sidebar_holder,
            ft.Container(
                content=ft.Column([center_wrap, bottom_bar], expand=True,
                                  spacing=0),
                padding=0, expand=True,
            ),
        ],
        expand=True, spacing=0,
    )

    def shutdown(e=None):
        if state["_closing"]:
            return
        state["_closing"] = True
        state["_load_generation"] += 1
        main_pane["generation"] += 1
        for future in list(state["_tasks"]):
            try:
                future.cancel()
            except Exception:
                pass
        state["_tasks"].clear()
        for dlg in list(dialogs.values()):
            close_dlg(dlg)
        modal_wrap.visible = False

    def apply_responsive_layout():
        width = float(getattr(page, "width", None) or DEFAULT_WINDOW_WIDTH)
        compact = width < 1000
        sidebar_holder.padding = 14 if compact else 18
        sidebar_holder.content.width = 172 if compact else 190
        preview_panel.width = 268 if compact else 286

    def resize_changed(e=None):
        pending = state.get("_resize_task")
        if pending:
            pending.cancel()

        async def _resize():
            try:
                await asyncio.sleep(0.08)
            except asyncio.CancelledError:
                return
            if not state["_closing"]:
                apply_responsive_layout()
                safe_update()

        try:
            state["_resize_task"] = track_task(page.run_task(_resize))
        except Exception:
            apply_responsive_layout()

    def window_event(e):
        if getattr(e, "type", None) == ft.WindowEventType.CLOSE:
            shutdown()
        elif getattr(e, "type", None) in (
                ft.WindowEventType.RESIZE, ft.WindowEventType.RESIZED):
            resize_changed()

    page.on_resize = resize_changed
    try:
        page.window.on_event = window_event
    except Exception:
        pass

    header_actions.content = build_header_actions()
    page.add(ft.Stack([main_row, toast_wrapper, modal_wrap], expand=True))
    if startup_warning:
        notify(startup_warning, "warn")
    apply_responsive_layout()
    ui_later(0.05, lambda: (apply_responsive_layout(), safe_update()))
    load_addons()
    try:
        state["_watch_task"] = track_task(page.run_task(watch_workshop))
    except Exception as ex:
        dbg("watch task ERR %r" % ex)


if __name__ == "__main__":
    if hasattr(ft, "run"):
        ft.run(main)
    else:
        ft.app(target=main)
