import asyncio
import glob
import json
import os
import random
import sys
import threading
import time
import unicodedata

import flet as ft

import l4d2_core as core

BG = "#0C0C10"
SURFACE = "#16161C"
SURFACE_2 = "#1E1E26"
BORDER = "#2A2A33"
TEXT = "#F2F2F5"
TEXT_DIM = "#8B8B96"
ACCENT = "#4ADE80"
ACCENT_SOFT = "#1B3A2A"
DANGER = "#F87171"
AMBER = "#F59E0B"
AMBER_SOFT = "#2E2416"
VSCRIPT_BG = "#3A3A46"
VSCRIPT_TEXT = "#D6D6DC"
PREVIEW_GRAD = ft.RadialGradient(
    center=ft.Alignment(0, 0), radius=1.0,
    colors=["#23232E", "#101016"],
)
PARTICLE_COLORS = ["#4ADE80", "#A7F3D0", "#E2E8F0", "#FBBF24"]


class ParticleField:
    def __init__(self, page_ctx, width, height, count=12):
        self.alive = True
        self.page = page_ctx
        self.controls = []
        rnd = random.Random()
        self.stack = ft.Stack([], width=width, height=height)
        for _ in range(count):
            size = rnd.randint(3, 8)
            c = ft.Container(
                width=size, height=size,
                border_radius=size // 2 + 1,
                bgcolor=rnd.choice(PARTICLE_COLORS),
                opacity=rnd.uniform(0.12, 0.4),
                left=rnd.uniform(0, max(1, width - size)),
                top=rnd.uniform(0, max(1, height - size)),
                animate_position=ft.Animation(rnd.randint(4000, 10000), "linear"),
                animate_opacity=ft.Animation(2000, "easeInOut"),
            )
            self.controls.append(c)
            self.stack.controls.append(c)
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self):
        rnd = random.Random()
        while self.alive:
            time.sleep(4.5)
            if not self.alive:
                break
            try:
                for c in self.controls:
                    w = float(c.width or 4)
                    c.left = rnd.uniform(0, max(1, self.stack.width - w))
                    c.top = rnd.uniform(0, max(1, self.stack.height - w))
                    c.opacity = rnd.uniform(0.1, 0.5)
                if hasattr(self.page, "schedule_update"):
                    self.page.schedule_update()
                else:
                    self.page.update()
            except Exception:
                pass

    def stop(self):
        self.alive = False

CATEGORIES = ["Todos", "Favoritos", "Skins", "Armas", "Sonido", "UI",
              "VScripts", "Otro"]

STAR_ICON = "\u2605"
STAR_OUTLINE = "\u2606"


def _unaccent(s):
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def _quant(n, singular, plural):
    return "%d %s" % (n, singular if n == 1 else plural)


def _cfg_path(name):
    d = os.path.join(os.getenv("LOCALAPPDATA") or os.getcwd(), "L4D2ModLoader")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return os.path.join(d, name)

CHECK_MARK = "\u2713"
CROSS_MARK = "\u2715"
WARN_MARK = "\u26A0"


def _asset_path(name):
    dirs = [os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
            else None]
    dirs.append(getattr(sys, "_MEIPASS", None))
    dirs.append(os.path.dirname(os.path.abspath(__file__)))
    for d in dirs:
        if d:
            cand = os.path.join(d, name)
            if os.path.isfile(cand):
                return cand
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), name)


ICONO = _asset_path("icono.png")

RAINBOW = ["#F87171", "#FBBF24", "#FDE047", "#4ADE80", "#38BDF8",
           "#A78BFA", "#F472B6"]



TIKTOK_URL = "https://www.tiktok.com/@tokyossz"


def rgb_spans(text, offset=0):
    return [ft.TextSpan(ch,
                        ft.TextStyle(color=RAINBOW[(i + offset) % len(RAINBOW)],
                                     italic=True))
            for i, ch in enumerate(text)]


def rgb_text(text, size=11):
    return ft.Text(spans=rgb_spans(text, 0), size=size)


def debug_log(msg):
    print(msg)
    dbg("core: " + str(msg))


def dbg(msg):
    try:
        base = os.getenv("LOCALAPPDATA") or os.getcwd()
        d = os.path.join(base, "L4D2ModLoader")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "debug.log"), "a",
                  encoding="utf-8") as f:
            f.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), msg))
    except Exception:
        pass


def _fit_image(path, w, h):
    try:
        return ft.Image(src=path, fit=ft.BoxFit.CONTAIN, border_radius=10,
                        width=w, height=h,
                        fade_in_animation=ft.Animation(300, "easeOut"))
    except TypeError:
        try:
            return ft.Image(src=path, fit=ft.BoxFit.CONTAIN, border_radius=10,
                            expand=True,
                            fade_in_animation=ft.Animation(300, "easeOut"))
        except TypeError:
            return ft.Image(src=path, fit=ft.BoxFit.CONTAIN, border_radius=10,
                            expand=True)


def make_type_badge(a_type):
    is_v = a_type == "VSCRIPT"
    return ft.Container(
        content=ft.Text(a_type, size=9, weight=ft.FontWeight.W_700,
                        color=BG if is_v else VSCRIPT_TEXT),
        bgcolor=AMBER if is_v else VSCRIPT_BG,
        padding=ft.Padding.symmetric(horizontal=6, vertical=2),
        border_radius=4,
    )


class ModRow(ft.Container):
    def __init__(self, addon, on_select, on_toggle, active,
                 with_checkbox, dim, fav=False, on_fav=None, on_leave=None):
        self.addon = addon
        self.on_select = on_select
        self.on_leave = on_leave
        self.checkbox = None
        parts = []
        if with_checkbox:
            self.checkbox = ft.Checkbox(
                value=False,
                active_color=ACCENT,
                disabled=active,
                on_change=lambda e: on_toggle(addon, e.control.value),
            )
            parts.append(self.checkbox)

        title = ft.Text(addon.get("title") or addon["id"], size=14,
                        weight=ft.FontWeight.W_500, color=TEXT,
                        max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                        expand=True)
        meta = ft.Text(
            "%s  ·  %s  ·  %s" % (addon["id"], core.fmt_size(addon["size"]),
                                  addon["category"]),
            size=11, color=TEXT_DIM,
            max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)

        parts.append(ft.Column(
            [
                ft.Row([title, make_type_badge(addon["type"])], spacing=8),
                meta,
            ],
            spacing=2, expand=True,
        ))

        if fav or on_fav:
            parts.append(ft.Container(
                content=ft.Text(STAR_ICON if fav else STAR_OUTLINE,
                                size=14, color=AMBER if fav else TEXT_DIM),
                padding=ft.Padding.symmetric(horizontal=6, vertical=4),
                border_radius=6,
                ink=True,
                tooltip="Favorito",
                on_click=lambda e: on_fav(addon) if on_fav else None,
            ))

        if active:
            parts.append(ft.Container(
                content=ft.Text("ACTIVADO", size=10,
                                weight=ft.FontWeight.W_700, color=ACCENT),
                bgcolor=ACCENT_SOFT,
                padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                border_radius=6,
            ))

        self._target_opacity = 0.55 if dim else 1.0
        super().__init__(
            content=ft.Row(parts, spacing=10,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.symmetric(horizontal=12, vertical=9),
            border_radius=10,
            bgcolor=SURFACE,
            opacity=self._target_opacity,
            animate_opacity=ft.Animation(200, "easeOut"),
            animate_scale=ft.Animation(220, "easeOut"),
            on_click=lambda e: self.on_select(self.addon),
            on_hover=self._on_hover,
            ink=True,
        )

    def _on_hover(self, e):
        data = e.data if hasattr(e, "data") else None
        if str(data).lower() in ("true", "1"):
            self.on_select(self.addon)
        elif self.on_leave:
            self.on_leave(self.addon)

    def set_selected(self, is_selected):
        self.bgcolor = SURFACE_2 if is_selected else SURFACE
        self.border = ft.Border.all(1, ACCENT) if is_selected else None


def dialog_row(addon, with_checkbox=False, value=False, check_cb=None,
               on_hover=None, on_leave=None, status=None, extra_meta=None):
    def _hover(e):
        data = e.data if hasattr(e, "data") else None
        if str(data).lower() in ("true", "1"):
            if on_hover:
                on_hover(addon)
        elif on_leave:
            on_leave(addon)

    box = None
    if with_checkbox:
        box = ft.Checkbox(value=value, active_color=ACCENT,
                          on_change=lambda e: check_cb(addon, e.control.value))

    title = ft.Text(addon.get("title") or addon["id"], size=14,
                    weight=ft.FontWeight.W_500, color=TEXT,
                    max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, expand=True)
    meta_controls = [
        ft.Text("%s  ·  %s" % (addon["id"], core.fmt_size(addon["size"])),
                size=11, color=TEXT_DIM),
    ]
    if extra_meta:
        meta_controls.append(ft.Text(extra_meta, size=11, color=AMBER,
                                     max_lines=1,
                                     overflow=ft.TextOverflow.ELLIPSIS))
    v = addon["is_vscript"]
    if status is None:
        status = "NO COMPATIBLE" if v else "Listo"
    status_text = ft.Text(status, size=10, weight=ft.FontWeight.W_700,
                          color=AMBER if v else TEXT_DIM)

    parts = []
    if box:
        parts.append(box)
    parts.append(ft.Column(
        [
            ft.Row([title, make_type_badge(addon["type"])], spacing=8),
            meta_controls[0],
            *(meta_controls[1:] or []),
        ],
        spacing=2, expand=True,
    ))
    parts.append(status_text)

    row = ft.Container(
        content=ft.Row(parts, spacing=10,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding.symmetric(horizontal=10, vertical=8),
        bgcolor=SURFACE,
        border_radius=8,
        on_click=lambda e: (on_hover(addon) if on_hover else None),
        on_hover=_hover,
    )
    return row, box


def make_pane(image_height, width, page_ctx, desc_lines=6,
              placeholder="Pase el cursor sobre un addon"):
    field = ParticleField(page_ctx, width, image_height)
    layer = ft.Container(
        content=ft.Text(placeholder, size=12, color=TEXT_DIM,
                        text_align=ft.TextAlign.CENTER),
        width=width, height=image_height,
        alignment=ft.Alignment.CENTER,
        animate_opacity=ft.Animation(250, "easeOut"),
        animate_offset=ft.Animation(300, "easeOut"),
    )
    inner = ft.Container(
        content=ft.Stack([field.stack, layer]),
        width=width, height=image_height,
        gradient=PREVIEW_GRAD, border_radius=10,
        alignment=ft.Alignment.CENTER,
    )
    ring = ft.Container(
        content=inner,
        padding=2,
        border=ft.Border.all(2, "#F5F5F7"),
        border_radius=16,
    )
    img = ring
    return {
        "img": img,
        "img_layer": layer,
        "field": field,
        "title": ft.Text("", size=13, weight=ft.FontWeight.W_600, color=TEXT,
                         max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
        "meta": ft.Text("", size=10, color=TEXT_DIM),
        "desc": (ft.Text("", size=13, color=TEXT_DIM, max_lines=desc_lines,
                         overflow=ft.TextOverflow.ELLIPSIS) if desc_lines
                 else None),
        "current_id": None,
        "height": image_height,
        "width": width,
    }


def pane_set_img(pane, path, loading=False):
    if path:
        pane["img_layer"].content = _fit_image(path, pane["width"],
                                               pane["height"] - 2)
    else:
        pane["img_layer"].content = ft.Text(
            "Cargando preview..." if loading else "Sin preview disponible",
            size=12, color=TEXT_DIM, text_align=ft.TextAlign.CENTER)


def pane_clear(pane, placeholder="Pase el cursor sobre un addon"):
    pane["current_id"] = None
    pane["title"].value = ""
    pane["meta"].value = ""
    if pane["desc"]:
        pane["desc"].value = ""
    pane["img_layer"].blur = ft.Blur(0, 0)
    pane["img_layer"].opacity = 1.0
    pane["img_layer"].content = ft.Text(
        placeholder, size=12, color=TEXT_DIM, text_align=ft.TextAlign.CENTER)


def main(page: ft.Page):
    page.title = "L4D2 Mod Loader"
    page.bgcolor = BG
    page.padding = 0
    try:
        page.window.width = 1120
        page.window.height = 700
        page.window.min_width = 1120
        page.window.min_height = 700
        page.window.max_width = 1120
        page.window.max_height = 700
        page.window.resizable = False
        page.window.maximizable = False
        try:
            import ctypes
            _sw = ctypes.windll.user32.GetSystemMetrics(0)
            _sh = ctypes.windll.user32.GetSystemMetrics(1)
            if _sw and _sh:
                page.window.left = (_sw - 1120) // 2
                page.window.top = (_sh - 700) // 2
        except Exception:
            pass
        if os.path.isfile(ICONO):
            page.window.icon = ICONO
    except Exception:
        pass
    page.fonts = {}
    page.theme = ft.Theme(font_family="Segoe UI")

    state = {
        "l4d2": None,
        "addons": [],
        "rows": {},
        "selected_ids": set(),
        "preview_id": None,
        "category": "Todos",
        "query": "",
        "view": "mods",
        "active_ids": set(),
        "deps": core.load_deps(),
        "favs": set(core.load_json(_cfg_path("favs.json"), []) or []),
        "presets": core.load_json(_cfg_path("presets.json"), {}) or {},
        "sort_recent": False,
        "_fresh_scan": False,
        "_disk_ids": set(),
        "_pending_rescan": False,
        "_l4d2_was_running": False,
    }

    def ui_later(delay, fn):
        async def _t():
            await asyncio.sleep(delay)
            try:
                fn()
            except Exception as ex:
                dbg("ui_later ERR %r" % ex)
        try:
            loop = getattr(getattr(getattr(page, "session", None),
                                   "connection", None), "loop", None)
        except Exception:
            loop = None
        ok = loop is not None
        if ok:
            try:
                ok = bool(loop.is_running())
            except Exception:
                ok = False
        if ok:
            try:
                page.run_task(_t)
                return
            except Exception:
                pass
        t = threading.Timer(delay, fn)
        t.daemon = True
        t.start()

    def safe_update():
        try:
            if hasattr(page, "schedule_update"):
                page.schedule_update()
            else:
                page.update()
        except Exception:
            pass

    def show_dlg(dlg):
        if hasattr(page, "open"):
            page.open(dlg)
        elif hasattr(page, "show_dialog"):
            page.show_dialog(dlg)

    def close_dlg():
        if hasattr(page, "close"):
            page.close()
        elif hasattr(page, "pop_dialog"):
            page.pop_dialog()

    def animate_display(cnt):
        dbg("dialog in")
        def _in():
            cnt.scale = 1.0
            cnt.opacity = 1.0
            try:
                page.update()
            except Exception as ex:
                dbg("dialog in ERR %r" % ex)
        ui_later(0.04, _in)

    def close_dialog_anim(cnt, pane=None):
        dbg("dialog out")
        cnt.opacity = 0.0
        cnt.scale = 0.96
        try:
            page.update()
        except Exception as ex:
            dbg("dialog out ERR %r" % ex)

        def _c():
            pane["field"].stop() if pane else None
            close_dlg()
            dbg("dialog closed")

        ui_later(0.16, _c)

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

    def save_favs():
        core.save_json(_cfg_path("favs.json"), sorted(state["favs"]))

    def toggle_fav(addon):
        if addon["id"] in state["favs"]:
            state["favs"].discard(addon["id"])
        else:
            state["favs"].add(addon["id"])
        save_favs()
        refresh_list()
        page.update()

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
            card.opacity = 1.0
            card.scale = 1.0
            try:
                page.update()
            except Exception:
                pass
        ui_later(0.04, _in)

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
            modal_wrap.visible = False
            _modal_card[0] = None
            try:
                page.update()
            except Exception:
                pass
        ui_later(0.14, _final)

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
    counts_text = ft.Text("", size=11, color=TEXT_DIM)
    view_title = ft.Text("Mods en VERSUS", size=18,
                         weight=ft.FontWeight.BOLD, color=TEXT)
    header_actions = ft.Container()

    clear_box = ft.Container(
        content=ft.Icon(ft.Icons.CLOSE if hasattr(ft.Icons, "CLOSE")
                        else "\u2715", color=DANGER, size=16),
        padding=4,
        visible=False,
        ink=True,
        animate_scale=ft.Animation(400, "easeInOut"),
        on_click=lambda e: clear_search(),
        tooltip="Limpiar búsqueda",
    )

    search_field = ft.TextField(
        hint_text="Filtrar por título o ID...",
        border_color=BORDER, focused_border_color=ACCENT,
        color=TEXT, hint_style=ft.TextStyle(color=TEXT_DIM),
        border_radius=8, height=42, content_padding=10,
        prefix_icon=ft.Icons.SEARCH,
        suffix_icon=clear_box,
    )

    _pulse = [False]

    def _pulse_loop():
        while True:
            time.sleep(0.6)
            _pulse[0] = not _pulse[0]

            def _apply():
                try:
                    clear_box.scale = 1.18 if _pulse[0] else 1.0
                    page.update()
                except Exception:
                    pass
            ui_later(0.0, _apply)

    t = threading.Thread(target=_pulse_loop, daemon=True)
    t.start()

    def clear_search():
        search_field.value = ""
        state["query"] = ""
        clear_box.visible = False
        refresh_list()
        page.update()

    list_view = ft.ListView(spacing=6, expand=True,
                            padding=ft.Padding.only(right=4))

    main_pane = make_pane(240, 248, page)

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

        def _fade_in():
            pane["img_layer"].opacity = 1.0
            try:
                page.update()
            except Exception:
                pass

        def _set_text(text):
            pane["img_layer"].blur = ft.Blur(0, 0)
            pane["img_layer"].opacity = 1.0
            pane["img_layer"].content = text

        def _show_image(path):
            pane_set_img(pane, path)
            pane["img_layer"].opacity = 0.0
            try:
                page.update()
            except Exception:
                pass
            ui_later(0.02, _fade_in)

        if lp and os.path.isfile(lp):
            _show_image(lp)
        else:
            url = addon.get("_preview_url")
            if url:
                pane_set_img(pane, None, loading=True)
                _set_text(pane["img_layer"].content)

                def bg():
                    path = core.get_cached_image(addon["id"], url)
                    addon["preview_local"] = path
                    dbg("img_dl %s path=%s" % (addon["id"], path))

                    def _apply():
                        if pane["current_id"] == addon["id"]:
                            _show_image(path)

                    ui_later(0.0, _apply)

                threading.Thread(target=bg, daemon=True).start()
            else:
                msg = ("Descargando datos de Steam..." if state.get("fetching")
                       else "Sin preview disponible")
                _set_text(ft.Text(msg, size=12, color=TEXT_DIM,
                                  text_align=ft.TextAlign.CENTER))

    def make_hover(pane):
        def hov(addon):
            dbg("hover %s" % addon["id"])
            pane_set(pane, addon)
            page.update()
        return hov

    def make_leave(pane):
        def leave(addon):
            if pane["current_id"] != addon["id"]:
                return
            pane_clear(pane)
            page.update()
        return leave

    def show_preview(addon_id, force=False):
        dbg("show_preview %s force=%s" % (addon_id, force))
        if state["preview_id"] == addon_id and not force:
            return
        old = state["preview_id"]
        state["preview_id"] = addon_id
        if old in state["rows"]:
            state["rows"][old].set_selected(False)
        if addon_id in state["rows"]:
            state["rows"][addon_id].set_selected(True)
        addon = next((a for a in state["addons"] if a["id"] == addon_id), None)
        if not addon:
            return
        pane_set(main_pane, addon)
        page.update()

    def clear_preview(addon=None):
        if addon and state["preview_id"] != addon["id"]:
            return
        old = state["preview_id"]
        state["preview_id"] = None
        if old in state["rows"]:
            state["rows"][old].set_selected(False)
        pane_clear(main_pane)
        page.update()

    chip_controls = {}

    def chip_hover(e):
        on = str(getattr(e, "data", "")).lower() in ("true", "1")
        e.control.scale = 1.05 if on else 1.0
        page.update()

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
                       scroll=ft.ScrollMode.AUTO, expand=False)

    def sort_toggled(e=None):
        state["sort_recent"] = not state["sort_recent"]
        sort_btn.text = ("Orden: Reciente primero" if state["sort_recent"]
                         else "Orden: Antiguo primero")
        refresh_list(stagger=True)

    sort_btn = ft.TextButton("Orden: Antiguo primero", on_click=sort_toggled,
                             style=ft.ButtonStyle(color=TEXT_DIM,
                                                  text_style=ft.TextStyle(size=12),
                                                  padding=ft.Padding.symmetric(
                                                      horizontal=8, vertical=6)))

    def clear_selection(e=None):
        state["selected_ids"].clear()
        refresh_list()
        page.update()
        notify("Selección desmarcada.", "ok")

    desmar_btn = ft.TextButton("DESMARCAR SELECCIONADOS",
                               on_click=clear_selection,
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
        refresh_list(stagger=True)
        page.update()

    def nav_item(text, view_name, selected, badge=0):
        content = ft.Row(
            [
                ft.Text(text, size=13,
                        color=TEXT if selected else TEXT_DIM,
                        weight=(ft.FontWeight.W_600 if selected
                                else ft.FontWeight.NORMAL)),
            ],
            spacing=8,
        )
        if badge:
            content.controls.append(ft.Container(
                content=ft.Text(str(badge), size=10,
                                weight=ft.FontWeight.W_700, color=TEXT),
                bgcolor=DANGER,
                padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                border_radius=10,
            ))
        return ft.Container(
            content=content,
            padding=ft.Padding.symmetric(horizontal=14, vertical=10),
            border_radius=8,
            bgcolor=SURFACE_2 if selected else None,
            on_click=lambda e, v=view_name: switch_view(v),
            ink=True,
        )

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
        a = get_addon(state["preview_id"]) if state["preview_id"] else None
        if not a:
            notify("Pase el cursor sobre un addon primero.", "warn")
            return
        launch_external("https://steamcommunity.com/sharedfiles/"
                        "filedetails/?id=%s" % a["id"])

    def open_folder(e):
        a = get_addon(state["preview_id"]) if state["preview_id"] else None
        if not a:
            notify("Pase el cursor sobre un addon primero.", "warn")
            return
        try:
            os.startfile(os.path.dirname(a["path"]))
        except Exception:
            notify("No se pudo abrir la carpeta.", "err")

    tiktok_footer = ft.Container(
        content=rgb_text("made by @tokyossz", size=16),
        padding=ft.Padding.symmetric(horizontal=14, vertical=6),
        on_click=open_tiktok,
        tooltip=TIKTOK_URL,
        ink=True,
    )
    _rgb_off = [0]

    def _rgb_tick():
        while True:
            time.sleep(0.18)
            _rgb_off[0] += 1

            def _apply(o=_rgb_off[0]):
                tiktok_footer.content.spans = rgb_spans("made by @tokyossz", o)
                try:
                    page.update()
                except Exception:
                    pass

            ui_later(0.0, _apply)

    t = threading.Thread(target=_rgb_tick, daemon=True)
    t.start()

    def toggle_vision(e):
        if not state["l4d2"]:
            notify("No se encontró L4D2.", "warn")
            return
        if not require_game_closed():
            return
        st = core.vision_state(state["l4d2"])
        if st == "unknown":
            notify("No hay archivos de visión de infectado en el juego.",
                   "warn")
            return
        if st == "off":
            ok = core.restore_infected_vision(state["l4d2"], log=debug_log)
            msg = ("Visión de infectado restaurada (tinte normal)." if ok
                   else "No se pudo restaurar la visión; ejecute la app "
                        "como administrador y reintente.")
        else:
            ok = core.disable_infected_vision(state["l4d2"], log=debug_log)
            msg = ("Visión de infectado quitada (sin tinte naranja/azul)."
                   if ok else "No se pudo quitar la visión; ejecute la app "
                              "como administrador y reintente.")
        notify(msg, "ok" if ok else "err")
        sidebar_holder.content = build_sidebar()
        page.update()

    def build_sidebar():
        logo = ft.Container(
            content=(_fit_image(ICONO, 76, 76) if os.path.isfile(ICONO)
                     else ft.Text("L4D2", size=20, weight=ft.FontWeight.BOLD,
                                  color=ACCENT)),
            padding=ft.Padding.symmetric(horizontal=14, vertical=4),
            alignment=ft.Alignment.CENTER_LEFT,
        )
        vision_off = bool(state["l4d2"]) and \
            core.vision_state(state["l4d2"]) == "off"

        def _action(text, color, on_click):
            return ft.Container(
                content=ft.Text(text, size=13, color=color, max_lines=2,
                                overflow=ft.TextOverflow.ELLIPSIS),
                padding=ft.Padding.symmetric(horizontal=14, vertical=10),
                border_radius=8,
                bgcolor=SURFACE_2,
                border=ft.Border.all(1, BORDER),
                on_click=on_click,
                ink=True,
            )

        return ft.Column(
            [
                logo,
                ft.Container(height=6),
                ft.FilledButton(
                    "JUGAR",
                    icon=(ft.Icons.PLAY_ARROW if hasattr(ft.Icons, "PLAY_ARROW")
                          else "\u25B6"),
                    on_click=do_play,
                    style=ft.ButtonStyle(bgcolor=ACCENT, color=BG,
                                         shape=ft.RoundedRectangleBorder(radius=8)),
                ),
                ft.Container(height=8),
                nav_item("Mods", "mods", state["view"] == "mods"),
                nav_item("Activos", "activos", state["view"] == "activos"),
                ft.Container(height=8),
                ft.Divider(color=BORDER, height=1),
                ft.Container(height=8),
                _action("Restaurar original", DANGER,
                        lambda e: do_restore()),
                _action("Restaurar Visión de Infectado" if vision_off
                        else "Quitar Visión de Infectado",
                        ACCENT if vision_off else DANGER, toggle_vision),
                _action("Limpiar VPKs", AMBER,
                        lambda e: open_cleanup_vpks(e)),
                _action("Actualizar lista", TEXT_DIM,
                        lambda e: load_addons()),
                ft.Container(expand=True),
                tiktok_footer,
            ],
            spacing=6, width=170,
        )

    sidebar_holder = ft.Container(content=build_sidebar(), padding=18,
                                  bgcolor=SURFACE)

    def switch_view(v):
        dbg("switch_view %s" % v)
        state["view"] = v
        state["preview_id"] = None
        sidebar_holder.content = build_sidebar()
        view_title.value = "Addons ACTIVOS" if v == "activos" else "Mods en VERSUS"
        header_actions.content = build_header_actions()
        list_toolbar.visible = v == "mods"
        center_wrap.opacity = 0.4
        page.update()

        def _fade():
            center_wrap.opacity = 1.0
            try:
                page.update()
            except Exception as ex:
                dbg("view fade ERR %r" % ex)

        ui_later(0.06, _fade)
        refresh_list(stagger=True)
        page.update()

    def build_header_actions():
        style = ft.ButtonStyle(bgcolor=ACCENT, color=BG,
                               text_style=ft.TextStyle(size=13),
                               padding=ft.Padding.symmetric(horizontal=14,
                                                             vertical=10),
                               shape=ft.RoundedRectangleBorder(radius=8))
        if state["view"] == "activos":
            return ft.Row(
                [
                    ft.FilledButton("QUITAR ADDON", on_click=do_quitar_addon,
                                    style=ft.ButtonStyle(
                                        bgcolor=SURFACE_2, color=TEXT,
                                        shape=ft.RoundedRectangleBorder(radius=8))),
                    ft.TextButton("QUITAR TODOS", on_click=do_quitar_todos,
                                  style=ft.ButtonStyle(color=DANGER)),
                ],
                spacing=8,
            )
        return ft.Row(
            [
                ft.Container(
                    content=ft.TextButton("PRESETS", on_click=open_presets,
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
                ft.FilledButton("HABILITAR SELECCIONADOS", on_click=do_enable,
                                style=style),
            ],
            spacing=6,
        )

    def load_addons():
        state["l4d2"] = core.find_l4d2()
        if not state["l4d2"]:
            status_dot.bgcolor = DANGER
            status_text.value = "L4D2 no encontrado"
            counts_text.value = ""
            page.update()
            notify("No se encontró L4D2. Verifique que Steam esté instalado.", "err")
            return
        status_dot.bgcolor = ACCENT
        status_text.value = os.path.basename(state["l4d2"])
        status_text.tooltip = state["l4d2"]
        gi = os.path.join(state["l4d2"], "left4dead2", "gameinfo.txt")
        if os.path.isfile(gi) and not os.access(gi, os.W_OK):
            notify("El archivo gameinfo.txt no es escribible; ejecute la app como administrador.", "warn")
        page.update()

        raw = core.list_addons(state["l4d2"])
        if not raw:
            notify("No hay addons en addons/workshop.", "warn")
        for a in raw:
            info = core.inspect_vpk(a["path"])
            a["title"] = info["title"]
            a["is_vscript"] = info["is_vscript"]
            a["type"] = "VSCRIPT" if a["is_vscript"] else "MOD"
            a["category"] = core.categorize(a["title"] or a["id"], a["id"])
            a["description"] = None
            a["preview_local"] = None
            a["_preview_url"] = None
            a["auto_deps"] = []
        state["fetching"] = True
        state["addons"] = raw
        state["_fresh_scan"] = True
        state["_disk_ids"] = set(a["id"] for a in raw)
        _seed_previews_from_cache()
        sidebar_holder.content = build_sidebar()
        refresh_list(stagger=True)

        if hasattr(page, "run_thread"):
            page.run_thread(fetch_task)
        else:
            threading.Thread(target=fetch_task, daemon=True).start()

    def _seed_previews_from_cache():
        cache_d = os.path.join(os.getenv("LOCALAPPDATA") or os.getcwd(),
                               "L4D2ModLoader", "cache")
        for a in state["addons"]:
            if a.get("preview_local"):
                continue
            hits = glob.glob(os.path.join(cache_d, a["id"] + "_*"))
            if hits:
                a["preview_local"] = hits[0]

    def fetch_task():
        dbg("fetch_task start (%d addons)" % len(state["addons"]))
        try:
            details = core.fetch_workshop_details([a["id"] for a in state["addons"]])
        except Exception as ex:
            details = {}
            dbg("fetch ERR %r" % ex)
        dbg("fetch_task details=%d" % len(details))
        for a in state["addons"]:
            d = details.get(a["id"])
            if not d:
                continue
            if d.get("title"):
                a["title"] = d["title"]
                a["category"] = core.categorize(d["title"], a["id"])
            a["description"] = d.get("description")
            a["description_raw"] = d.get("description_raw")
            url = d.get("preview_url")
            if url:
                a["_preview_url"] = url
                a["preview_local"] = core.get_cached_image(a["id"], url)
        known = set(a["id"] for a in state["addons"])
        titles = {a["id"]: a.get("title") or a["id"] for a in state["addons"]}
        for a in state["addons"]:
            raw = a.get("description_raw") or a.get("description") or ""
            a["auto_deps"] = [s["id"] for s in core.suggest_deps(
                raw, known, titles)
                if s["id"] != a["id"]] if raw else []
        state["fetching"] = False
        dbg("fetch_task done, fetching=False")
        refresh_list()
        if state["preview_id"]:
            show_preview(state["preview_id"], force=True)
        if state["_pending_rescan"]:
            state["_pending_rescan"] = False
            load_addons()

    def watch_workshop():
        while True:
            time.sleep(3)
            try:
                if not state["l4d2"]:
                    continue
                _check_game_closed()
                found = {a["id"] for a in core.list_addons(state["l4d2"])}
                if found != state["_disk_ids"]:
                    dbg("workshop changed: %d -> %d" % (
                        len(state["_disk_ids"]), len(found)))
                    state["_disk_ids"] = found
                    if state["fetching"]:
                        state["_pending_rescan"] = True
                        dbg("fetch in progress, pending rescan")
                    else:
                        ui_later(0.05, load_addons)
            except Exception as ex:
                dbg("watch ERR %r" % ex)

    def _check_game_closed():
        running_now = core.l4d2_running()
        was_running = state["_l4d2_was_running"]
        state["_l4d2_was_running"] = running_now
        if not (was_running and not running_now):
            return
        removed = core.cleanup_orphans(state["l4d2"], log=dbg)
        if removed:
            dbg("cleanup_orphans tras cierre del juego: %s" % ", ".join(removed))
            ui_later(0.05, load_addons)
            ui_later(0.1, lambda: notify(
                "Se quitaron %d addon(s) de los que ya no estás suscrito." % len(removed),
                "warn"))

    def visible_addons(active_ids):
        addons = state["addons"]
        if state["view"] == "activos":
            addons = [a for a in addons if a["id"] in active_ids]
        if state["category"] == "Favoritos":
            addons = [a for a in addons if a["id"] in state["favs"]]
        elif state["category"] == "VScripts":
            addons = [a for a in addons if a["is_vscript"]]
        elif state["category"] != "Todos":
            addons = [a for a in addons if a["category"] == state["category"]]
        q = _unaccent(state["query"].strip())
        if q:
            addons = [a for a in addons
                      if q in _unaccent(a.get("title"))
                      or q in a["id"].lower()]
        addons = sorted(addons, key=lambda a: (a.get("ctime", 0), a["id"]),
                        reverse=bool(state["sort_recent"]))
        return addons

    def update_counts():
        counts_text.value = "Addons: %d  ·  Activos: %d  ·  Sel: %d" % (
            len(state["addons"]), len(state["active_ids"]),
            len(state["selected_ids"]))

    def refresh_list(stagger=False):
        dbg("refresh_list stagger=%s" % stagger)
        state["anim_cancel"] = True
        list_view.controls.clear()
        state["rows"] = {}

        if state["l4d2"] and state["_fresh_scan"]:
            orphans_cleaned = core.cleanup_orphans(state["l4d2"], log=debug_log)
            if orphans_cleaned:
                notify("%s huérfano%s limpio%s (desuscrito del workshop)." % (
                    _quant(len(orphans_cleaned), "addon", "addons"),
                    "" if len(orphans_cleaned) == 1 else "s",
                    "" if len(orphans_cleaned) == 1 else "s"), "warn")
            state["_fresh_scan"] = False

        state["active_ids"] = set(core.currently_enabled(state["l4d2"])) \
            if state["l4d2"] else set()
        active = state["active_ids"]
        addons = visible_addons(active)
        for idx, a in enumerate(addons):
            is_active = a["id"] in active
            in_mods_view = state["view"] == "mods"
            row = ModRow(a,
                         on_select=lambda ad: show_preview(ad["id"]),
                         on_toggle=on_toggle,
                         active=is_active,
                         with_checkbox=in_mods_view,
                         dim=is_active and in_mods_view,
                         fav=a["id"] in state["favs"],
                         on_fav=toggle_fav,
                         on_leave=clear_preview)
            if row.checkbox:
                row.checkbox.value = a["id"] in state["selected_ids"]
            row.set_selected(a["id"] == state["preview_id"])
            if stagger:
                row.opacity = 0.0
                row.scale = 0.92
            state["rows"][a["id"]] = row
            list_view.controls.append(row)
        update_counts()
        safe_update()

        if stagger:
            state["anim_cancel"] = False
            gen = state.get("anim_gen", 0) + 1
            state["anim_gen"] = gen
            for idx, a in enumerate(addons):
                rr = state["rows"].get(a["id"])
                if not rr:
                    continue

                def _reveal(rr2=rr, g=gen):
                    if state.get("anim_cancel") or state["rows"].get(rr2.addon["id"]) is not rr2:
                        dbg("stagger skip %s" % rr2.addon["id"])
                        return
                    rr2.opacity = rr2._target_opacity
                    rr2.scale = 1.0
                    try:
                        page.update()
                    except Exception as ex:
                        dbg("reveal ERR %s %r" % (rr2.addon["id"], ex))

                ui_later(0.03 * idx, _reveal)
            dbg("stagger scheduled gen=%s" % gen)

    def on_toggle(addon, value):
        if value:
            state["selected_ids"].add(addon["id"])
            for d in effective_deps(addon["id"]):
                da = get_addon(d)
                if da and d not in state["active_ids"]:
                    state["selected_ids"].add(d)
                    r = state["rows"].get(d)
                    if r and r.checkbox:
                        r.checkbox.value = True
        else:
            state["selected_ids"].discard(addon["id"])
        update_counts()
        page.update()

    def search_changed(e):
        dbg("search %r" % e.control.value)
        state["query"] = e.control.value
        clear_box.visible = bool(e.control.value)
        refresh_list(stagger=True)

    search_field.on_change = search_changed

    def require_game_closed():
        if core.l4d2_running():
            notify("Cierre el juego (Left 4 Dead 2) antes de modificar los addons.",
                   "err")
            return False
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

    def dialog_content(rows, pane, banner=None, height=200, subtitle=None, width=560):
        kids = []
        if banner:
            kids.append(banner)
        if subtitle:
            kids.append(ft.Text(subtitle, size=11, color=TEXT_DIM))
        kids.append(pane["img"])
        kids.append(pane["title"])
        kids.append(pane["meta"])
        if pane["desc"]:
            kids.append(pane["desc"])
        kids.append(ft.Container(height=2))
        kids.append(ft.ListView(rows, height=height, spacing=4,
                                scroll=ft.ScrollMode.AUTO))
        cnt = ft.Container(content=ft.Column(kids, spacing=4), width=width)
        cnt.animate_scale = ft.Animation(220, "easeOut")
        cnt.animate_opacity = ft.Animation(180, "easeOut")
        cnt.scale = 0.93
        cnt.opacity = 0.0
        return cnt

    def do_enable(e):
        if not require_game_closed():
            return
        chosen = [a for a in state["addons"]
                  if a["id"] in state["selected_ids"]
                  and a["id"] not in state["active_ids"]]
        if not chosen:
            notify("Seleccione al menos un addon para habilitar.", "warn")
            return

        _dw, _img_h, _list_h = dialog_metrics()
        pane = make_pane(int(_img_h), int(_dw), page, desc_lines=1)
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
                                  on_leave=leave, extra_meta=extra)
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
            ok = core.enable(state["l4d2"], compat_addons, log=debug_log)
            close_dialog_anim(cnt, pane)
            if ok:
                for c in compat_addons:
                    state["selected_ids"].discard(c["id"])
                refresh_list()
                msg = "%s habilitado%s correctamente" % (
                    _quant(len(compat_addons), "addon", "addons"),
                    "" if len(compat_addons) == 1 else "s")
                if omitted:
                    msg += "  ·  %d VScript omitido(s)" % omitted
                notify(msg, "ok")
            else:
                notify("No se pudieron habilitar los addons", "err")

        sub = ("Se incluye %d dependencia automáticamente." % n_deps
               if n_deps == 1 else
               "Se incluyen %d dependencias automáticamente." % n_deps
               ) if n_deps else None
        cnt = dialog_content(pane_rows, pane, banner=banner, subtitle=sub,
                             height=int(_list_h), width=int(_dw))
        dlg = ft.AlertDialog(
            title=ft.Text("¿Habilitar los siguientes addons?"),
            content=cnt,
            actions=[
                ft.TextButton("CANCELAR",
                              on_click=lambda ev: close_dialog_anim(cnt, pane)),
                ft.FilledButton("HABILITAR", on_click=lambda ev: confirm_enable(),
                                style=ft.ButtonStyle(bgcolor=ACCENT, color=BG,
                                                     shape=ft.RoundedRectangleBorder(radius=8))),
            ],
            modal=True,
        )

        show_dlg(dlg)
        animate_display(cnt)

    def _short_names(addons, maxn=4):
        names = ", ".join((a.get("title") or a["id"]) for a in addons[:maxn])
        if len(addons) > maxn:
            names += ", ..."
        return names

    def do_quitar_addon(e):
        if not require_game_closed():
            return
        act = [a for a in state["addons"] if a["id"] in state["active_ids"]]
        if not act:
            notify("No hay addons activos para quitar.", "warn")
            return
        checked = set()

        def toggle(ad, val):
            (checked.add if val else checked.discard)(ad["id"])

        _dw, _img_h, _list_h = dialog_metrics()
        pane = make_pane(int(_img_h), int(_dw), page, desc_lines=1)
        hov = make_hover(pane)
        leave = make_leave(pane)
        rows = [dialog_row(a, with_checkbox=True, value=False, check_cb=toggle,
                           on_hover=hov, on_leave=leave)[0] for a in act]

        cnt = dialog_content(rows, pane, height=int(_list_h), width=int(_dw))
        dlg = ft.AlertDialog(
            title=ft.Text("¿Quitar los siguientes addons?"),
            content=cnt,
            actions=[
                ft.TextButton("CANCELAR", on_click=lambda ev: close_dialog_anim(cnt, pane)),
                ft.FilledButton("QUITAR", on_click=lambda ev: confirm_quit(),
                                style=ft.ButtonStyle(bgcolor=DANGER, color=BG,
                                                     shape=ft.RoundedRectangleBorder(radius=8))),
            ],
            modal=True,
        )

        def confirm_quit():
            if not checked:
                close_dialog_anim(cnt, pane)
                notify("Seleccione al menos un addon para quitar.", "warn")
                return
            ids = list(checked)
            extra = deps_sin_uso(ids)
            total = sorted(set(ids) | set(extra))
            ok = core.disable(state["l4d2"], total, log=debug_log)
            close_dialog_anim(cnt, pane)
            if ok:
                state["selected_ids"].difference_update(total)
                refresh_list()
                msg = "%s deshabilitado%s" % (
                    _quant(len(total), "addon", "addons"),
                    "" if len(total) == 1 else "s")
                if extra:
                    msg += "  ·  %s sin uso" % _quant(len(extra),
                                                       "requisito", "requisitos")
                notify(msg, "ok")
            else:
                notify("No se pudieron quitar los addons", "err")

        show_dlg(dlg)
        animate_display(cnt)

    def do_quitar_todos(e):
        if not require_game_closed():
            return
        n = len(state["active_ids"])
        if not n:
            notify("No hay addons activos para quitar.", "warn")
            return

        cnt = ft.Container(
            content=ft.Text(
                "Se quitarán %s. Volverán a estar disponibles en MODS." % _quant(
                    n, "addon", "addons")),
            padding=ft.Padding.symmetric(horizontal=4, vertical=4),
        )
        cnt.animate_scale = ft.Animation(220, "easeOut")
        cnt.animate_opacity = ft.Animation(180, "easeOut")
        cnt.scale = 0.93
        cnt.opacity = 0.0

        dlg = ft.AlertDialog(
            title=ft.Text("¿Quitar todos los addons activos?"),
            content=cnt,
            actions=[
                ft.TextButton("CANCELAR", on_click=lambda ev: close_dialog_anim(cnt)),
                ft.FilledButton("QUITAR TODOS", on_click=lambda ev: confirm_quit_all(),
                                style=ft.ButtonStyle(bgcolor=DANGER, color=BG,
                                                     shape=ft.RoundedRectangleBorder(radius=8))),
            ],
            modal=True,
        )

        def confirm_quit_all():
            ids = list(state["active_ids"])
            ok = core.disable(state["l4d2"], ids, log=debug_log)
            close_dialog_anim(cnt)
            if ok:
                state["selected_ids"].difference_update(ids)
                refresh_list()
                notify("%s deshabilitado%s" % (
                    _quant(len(ids), "addon", "addons"),
                    "" if len(ids) == 1 else "s"), "ok")
            else:
                notify("No se pudieron quitar los addons", "err")

        show_dlg(dlg)
        animate_display(cnt)

    def open_presets(e):
        rows = []
        for name, ids in (state["presets"] or {}).items():
            r = ft.Container(
                content=ft.Row(
                    [
                        ft.Text(name, size=13, color=TEXT, expand=True,
                                max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        ft.Text("%d addons" % len(ids), size=11, color=TEXT_DIM),
                        ft.TextButton("USAR",
                                      on_click=lambda ev, n=name: use_preset(n),
                                      style=ft.ButtonStyle(color=ACCENT)),
                        ft.TextButton("QUITAR",
                                      on_click=lambda ev, n=name: remove_preset(n),
                                      style=ft.ButtonStyle(color=DANGER)),
                    ],
                    spacing=8,
                ),
                padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                bgcolor=SURFACE, border_radius=8,
            )
            rows.append(r)
        if not rows:
            rows.append(ft.Text("Sin presets todavía. Seleccione addons y use "
                                "GUARDAR SELECCIÓN.",
                                size=11, color=TEXT_DIM))
        tf = ft.TextField(hint_text="Nombre del preset...", height=40,
                          border_color=BORDER, focused_border_color=ACCENT,
                          color=TEXT, hint_style=ft.TextStyle(color=TEXT_DIM),
                          border_radius=8, content_padding=10)
        list_height = min(220, max(60, 44 * max(len(rows), 1)))
        card = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text("PRESETS", size=16,
                                    weight=ft.FontWeight.BOLD, color=TEXT),
                            ft.Container(expand=True),
                            ft.TextButton("CERRAR", on_click=lambda ev: hide_card(),
                                          style=ft.ButtonStyle(color=TEXT_DIM,
                                                               text_style=ft.TextStyle(size=12))),
                        ],
                        spacing=8,
                    ),
                    ft.Container(height=4),
                    ft.ListView(rows, height=list_height, spacing=4,
                                scroll=ft.ScrollMode.AUTO),
                    tf,
                    ft.Container(height=2),
                    ft.FilledButton(
                        "GUARDAR SELECCIÓN (%d)" % len(state["selected_ids"]),
                        on_click=lambda ev: save_preset(tf),
                        style=ft.ButtonStyle(bgcolor=ACCENT, color=BG,
                                             shape=ft.RoundedRectangleBorder(radius=8))),
                ],
                spacing=8,
                tight=True,
            ),
            width=380,
            bgcolor=SURFACE_2,
            border_radius=16,
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
        state["presets"][name] = sorted(state["selected_ids"])
        core.save_json(_cfg_path("presets.json"), state["presets"])
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
        state["presets"].pop(name, None)
        core.save_json(_cfg_path("presets.json"), state["presets"])
        hide_card()
        notify("Preset '%s' eliminado" % name, "ok")

    def open_cleanup_vpks(e):
        if not state["l4d2"]:
            notify("No se encontró L4D2.", "warn")
            return
        if not require_game_closed():
            return
        vpks = core.list_addons(state["l4d2"])
        if not vpks:
            notify("No hay VPKs en addons/workshop/ para limpiar.", "warn")
            return
        active = set(state["active_ids"])
        checked = set()
        rows = []
        preview_img = ft.Image(src="", fit=ft.BoxFit.CONTAIN, border_radius=10,
                               width=150, height=200, visible=False)
        preview_msg = ft.Text("Coloca el cursor sobre\nun addon para verlo",
                              size=11, color=TEXT_DIM,
                              text_align=ft.TextAlign.CENTER)

        def show_cleanup_preview(aid):
            a = get_addon(aid)
            lp = (a.get("preview_local") if a else None)
            if lp and os.path.isfile(lp):
                preview_img.src = lp
                preview_img.visible = True
                preview_msg.visible = False
            else:
                preview_img.visible = False
                preview_msg.visible = True
            try:
                page.update()
            except Exception:
                pass

        for v in vpks:
            aid = v["id"]
            a = get_addon(aid)
            title = (a.get("title") if a else None)
            if not title:
                title = core.inspect_vpk(v["path"]).get("title") or aid
            is_active = aid in active
            box = ft.Checkbox(
                value=False, active_color=DANGER,
                on_change=lambda ev, i=aid: (
                    checked.add(i) if ev.control.value else checked.discard(i)),
            )
            badges = [ft.Text(aid, size=11, color=TEXT_DIM)]
            if is_active:
                badges.append(ft.Container(
                    content=ft.Text("ACTIVO", size=9,
                                    weight=ft.FontWeight.W_700, color=AMBER),
                    bgcolor=AMBER_SOFT,
                    padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                    border_radius=4,
                ))
            rows.append(ft.Container(
                content=ft.Row(
                    [
                        box,
                        ft.Column(
                            [
                                ft.Text(title, size=13, color=TEXT,
                                        max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS),
                                ft.Row(badges, spacing=6),
                            ],
                            spacing=2, expand=True,
                        ),
                    ],
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding.symmetric(horizontal=10, vertical=7),
                bgcolor=SURFACE,
                border_radius=8,
                on_hover=lambda ev, i=aid: (
                    show_cleanup_preview(i)
                    if str(getattr(ev, "data", "")).lower() in ("true", "1")
                    else None),
            ))

        def confirm_cleanup():
            if not checked:
                notify("Seleccione al menos un VPK para borrar.", "warn")
                return
            deleted, failed = [], []
            for aid in checked:
                if core.delete_vpk(state["l4d2"], aid, log=debug_log):
                    deleted.append(aid)
                    state["favs"].discard(aid)
                else:
                    failed.append(aid)
            if deleted:
                core.save_json(_cfg_path("favs.json"), sorted(state["favs"]))
                idset = set(deleted)
                state["addons"] = [a for a in state["addons"]
                                   if a["id"] not in idset]
            state["selected_ids"].difference_update(checked)
            state["preview_id"] = None
            hide_card()
            refresh_list()
            if deleted:
                notify("%s borrado%s de addons/workshop/." % (
                    _quant(len(deleted), "VPK", "VPKs"),
                    "" if len(deleted) == 1 else "s"), "ok")
            if failed:
                notify("No se pudo borrar: %s. Cierre el juego si está abierto." % (
                    ", ".join(failed)), "err")

        list_height = min(300, max(90, 44 * min(len(rows), 8)))
        preview_panel = ft.Container(
            content=ft.Stack(
                [
                    preview_img,
                    preview_msg,
                ],
                width=170,
            ),
            width=170,
            height=list_height + 4,
            bgcolor=SURFACE,
            border_radius=10,
            alignment=ft.Alignment.CENTER,
            padding=10,
        )
        card = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text("Limpiar VPKs", size=16,
                                    weight=ft.FontWeight.BOLD, color=TEXT),
                            ft.Container(expand=True),
                            ft.TextButton("CERRAR",
                                          on_click=lambda ev: hide_card(),
                                          style=ft.ButtonStyle(
                                              color=TEXT_DIM,
                                              text_style=ft.TextStyle(size=12))),
                        ],
                        spacing=8,
                    ),
                    ft.Text(
                        "Marque los VPKs que ya no usa (desuscritos del "
                        "workshop). Si están ACTIVO, también se quitan de "
                        "gameinfo.txt. Al volver a suscribirse, Steam los "
                        "descarga de nuevo.",
                        size=11, color=TEXT_DIM, max_lines=3,
                        overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Container(height=2),
                    ft.Row(
                        [
                            ft.ListView(rows, height=list_height, spacing=4,
                                        scroll=ft.ScrollMode.AUTO, expand=True),
                            preview_panel,
                        ],
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                    ft.Container(height=4),
                    ft.FilledButton(
                        "BORRAR SELECCIONADOS (%d)" % len(checked),
                        on_click=lambda ev: confirm_cleanup(),
                        style=ft.ButtonStyle(bgcolor=DANGER, color=BG,
                                             shape=ft.RoundedRectangleBorder(radius=8))),
                ],
                spacing=8,
                tight=True,
            ),
            width=610,
            bgcolor=SURFACE_2,
            border_radius=16,
            padding=18,
            border=ft.Border.all(1, BORDER),
        )
        show_card(card)

    def do_restore():
        if not state["l4d2"]:
            return
        if not require_game_closed():
            return
        if not state["active_ids"]:
            notify("No hay addons activos para quitar.", "warn")
            return
        core.restore(state["l4d2"], log=debug_log)
        state["selected_ids"].clear()
        state["preview_id"] = None
        refresh_list()
        notify("Juego restaurado a su estado original.", "ok")

    header_row = ft.Row(
        [
            ft.Column(
                [
                    view_title,
                    ft.Row([status_dot, status_text], spacing=6),
                    counts_text,
                ],
                spacing=3,
            ),
            ft.Container(expand=True),
            header_actions,
        ],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    list_toolbar = ft.Row(
        [ft.Container(expand=True), sort_btn, desmar_btn],
        spacing=8,
    )

    center_column = ft.Column(
        [
            header_row,
            ft.Container(height=6),
            search_field,
            ft.Container(height=6),
            list_toolbar,
            ft.Container(height=2),
            chips_row,
            ft.Container(height=2),
            ft.Container(height=4),
            list_view,
        ],
        spacing=0,
        expand=True,
    )

    preview_panel = ft.Container(
        content=ft.Column(
            [
                main_pane["img"],
                ft.Container(height=10),
                main_pane["title"],
                main_pane["meta"],
                ft.Container(height=8),
                main_pane["desc"],
                ft.Container(height=4),
                ft.Row(
                    [
                        ft.TextButton(
                            "Workshop", on_click=open_steam,
                            icon=(ft.Icons.OPEN_IN_NEW
                                  if hasattr(ft.Icons, "OPEN_IN_NEW")
                                  else "\u2197"),
                            icon_color=TEXT_DIM,
                            style=ft.ButtonStyle(color=TEXT_DIM)),
                        ft.TextButton(
                            "Carpeta", on_click=open_folder,
                            icon=(ft.Icons.FOLDER_OPEN
                                  if hasattr(ft.Icons, "FOLDER_OPEN")
                                  else "\u25A0"),
                            icon_color=TEXT_DIM,
                            style=ft.ButtonStyle(color=TEXT_DIM)),
                    ],
                    spacing=4,
                ),
            ],
        ),
        width=280, padding=16, bgcolor=SURFACE, border_radius=12,
    )

    center_wrap = ft.Container(
        content=ft.Row([center_column, preview_panel], expand=True,
                       spacing=8,
                       vertical_alignment=ft.CrossAxisAlignment.START),
        animate_opacity=ft.Animation(220, "easeOut"),
        expand=True,
    )

    main_row = ft.Row(
        [
            sidebar_holder,
            ft.Container(
                content=ft.Column([center_wrap], expand=True),
                padding=16, expand=True,
            ),
        ],
        expand=True, spacing=0,
    )

    page.add(ft.Stack([main_row, toast_wrapper, modal_wrap], expand=True))

    header_actions.content = build_header_actions()
    load_addons()
    threading.Thread(target=watch_workshop, daemon=True).start()


if __name__ == "__main__":
    if hasattr(ft, "run"):
        ft.run(main)
    else:
        ft.app(target=main)