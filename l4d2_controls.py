import flet as ft

import l4d2_core as core
from l4d2_theme import (
    ACCENT,
    ACCENT_SOFT,
    AMBER,
    BORDER,
    BG,
    STAR_ICON,
    STAR_OUTLINE,
    SURFACE,
    SURFACE_2,
    TEXT,
    TEXT_DIM,
    VSCRIPT_BG,
    VSCRIPT_TEXT,
)


def fit_image(path, width, height):
    try:
        return ft.Image(src=path, fit=ft.BoxFit.CONTAIN, border_radius=10,
                        width=width, height=height,
                        fade_in_animation=ft.Animation(300, "easeOut"))
    except TypeError:
        try:
            return ft.Image(src=path, fit=ft.BoxFit.CONTAIN, border_radius=10,
                            expand=True,
                            fade_in_animation=ft.Animation(300, "easeOut"))
        except TypeError:
            return ft.Image(src=path, fit=ft.BoxFit.CONTAIN, border_radius=10,
                            expand=True)


def make_type_badge(addon_type):
    is_vscript = addon_type == "VSCRIPT"
    return ft.Container(
        content=ft.Text(addon_type, size=9, weight=ft.FontWeight.W_700,
                        color=BG if is_vscript else VSCRIPT_TEXT),
        bgcolor=AMBER if is_vscript else VSCRIPT_BG,
        padding=ft.Padding.symmetric(horizontal=6, vertical=2),
        border_radius=4,
    )


def _checkbox_event_value(event):
    # Another queued click can overwrite control.value before this callback runs.
    return event.data is True or event.data == "true"


class ModRow(ft.Container):
    def __init__(self, addon, on_select, on_toggle, active,
                 with_checkbox, fav=False, on_fav=None,
                 show_active_badge=True, on_hover=None, on_leave=None,
                 show_thumbnail=False, checked=False):
        self.addon = addon
        self.on_select = on_select
        self.checkbox = None

        def _hover(e):
            is_over = str(getattr(e, "data", "")).lower() in ("true", "1")
            if is_over and on_hover:
                on_hover(addon)
            elif not is_over and on_leave:
                on_leave(addon)

        parts = []
        if with_checkbox:
            self.checkbox = ft.Checkbox(
                value=checked and not active,
                active_color=ACCENT,
                disabled=active,
                on_change=lambda e: on_toggle(addon, _checkbox_event_value(e)),
            )
            parts.append(self.checkbox)

        if show_thumbnail:
            preview = addon.get("preview_local")
            if preview:
                thumb_content = ft.Image(src=preview, width=72, height=40,
                                         fit=ft.BoxFit.COVER,
                                         border_radius=6)
            else:
                thumb_content = ft.Icon(ft.Icons.IMAGE_OUTLINED, size=18,
                                        color=TEXT_DIM)
            parts.append(ft.Container(
                content=thumb_content,
                width=72,
                height=40,
                bgcolor="#10131A",
                border=ft.Border.all(1, BORDER),
                border_radius=6,
                alignment=ft.Alignment.CENTER,
                clip_behavior=ft.ClipBehavior.HARD_EDGE,
            ))

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

        if active and show_active_badge:
            parts.append(ft.Container(
                content=ft.Text("Activo", size=10,
                                weight=ft.FontWeight.W_700, color=ACCENT),
                bgcolor=ACCENT_SOFT,
                padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                border_radius=6,
            ))

        super().__init__(
            content=ft.Row(parts, spacing=10,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.symmetric(horizontal=12, vertical=9),
            border_radius=8,
            bgcolor=ACCENT_SOFT if active and with_checkbox else SURFACE,
            border=(ft.Border.all(1, ACCENT)
                    if active and with_checkbox else ft.Border.all(1, BORDER)),
            on_click=lambda e: self.on_select(self.addon),
            on_hover=_hover,
            ink=True,
        )

    def set_selected(self, is_selected):
        self.bgcolor = SURFACE_2 if is_selected else SURFACE
        self.border = (ft.Border.all(1, ACCENT) if is_selected
                       else ft.Border.all(1, BORDER))


def dialog_row(addon, with_checkbox=False, value=False, check_cb=None,
               on_hover=None, on_leave=None, status=None, extra_meta=None,
               compact=False, show_status=True):
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
                          on_change=lambda e: check_cb(addon, _checkbox_event_value(e)))

    title = ft.Text(addon.get("title") or addon["id"], size=13,
                    weight=ft.FontWeight.W_500, color=TEXT,
                    max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                    expand=True)
    meta_row = ft.Row(
        [
            ft.Text(addon["id"], size=11, color=TEXT_DIM,
                    max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
            ft.Container(width=3, height=3, bgcolor=BORDER, border_radius=2),
            ft.Text(core.fmt_size(addon["size"]), size=11, color=TEXT_DIM),
        ],
        spacing=7,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    meta_controls = [meta_row]
    if extra_meta:
        meta_controls.append(ft.Text(extra_meta, size=11, color=AMBER,
                                     max_lines=1,
                                     overflow=ft.TextOverflow.ELLIPSIS))
    is_vscript = addon["is_vscript"]
    if status is None:
        status = "No compatible" if is_vscript else "Listo"
    status_text = ft.Text(status, size=10, weight=ft.FontWeight.W_600,
                          color=AMBER if is_vscript else TEXT_DIM)

    parts = []
    if box:
        parts.append(box)
    parts.append(ft.Column(
        [
            title,
            meta_controls[0],
            *(meta_controls[1:] or []),
        ],
        spacing=2, expand=True,
    ))
    if show_status:
        parts.append(ft.Column(
            [
                make_type_badge(addon["type"]),
                status_text,
            ],
            spacing=4,
            horizontal_alignment=ft.CrossAxisAlignment.END,
        ))
    else:
        parts.append(make_type_badge(addon["type"]))

    row = ft.Container(
        content=ft.Row(parts, spacing=10,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding.symmetric(horizontal=12, vertical=9 if compact else 10),
        bgcolor=SURFACE,
        border=ft.Border.all(1, BORDER),
        border_radius=8,
        on_click=lambda e: (on_hover(addon) if on_hover else None),
        on_hover=_hover,
    )
    return row, box


def make_pane(image_height, width, page_ctx=None, desc_lines=6,
              placeholder="Selecciona un addon para ver sus detalles"):
    layer = ft.Container(
        content=ft.Column(
            [
                ft.Icon(ft.Icons.IMAGE_OUTLINED, size=28, color=TEXT_DIM),
                ft.Text(placeholder, size=12, color=TEXT_DIM,
                        text_align=ft.TextAlign.CENTER),
            ],
            spacing=8,
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        width=width, height=image_height,
        alignment=ft.Alignment.CENTER,
    )
    inner = ft.Container(
        content=layer,
        width=width, height=image_height,
        bgcolor="#111118", border_radius=8,
        alignment=ft.Alignment.CENTER,
    )
    ring = ft.Container(
        content=inner,
        border=ft.Border.all(1, BORDER),
        border_radius=8,
    )
    return {
        "img": ring,
        "img_layer": layer,
        "title": ft.Text("", size=13, weight=ft.FontWeight.W_600, color=TEXT,
                         max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
        "meta": ft.Text("", size=10, color=TEXT_DIM),
        "desc": (ft.Text("", size=13, color=TEXT_DIM, max_lines=desc_lines,
                         overflow=ft.TextOverflow.ELLIPSIS) if desc_lines
                 else None),
        "current_id": None,
        "generation": 0,
        "height": image_height,
        "width": width,
    }


def pane_set_img(pane, path, loading=False):
    if path:
        pane["img_layer"].content = fit_image(path, pane["width"],
                                              pane["height"] - 2)
        backdrop = pane.get("backdrop_layer")
        if backdrop:
            width = int(backdrop.width or 720)
            height = int(backdrop.height or (pane["height"] + 42))
            backdrop.content = ft.Stack(
                [
                    ft.Image(
                        src=path,
                        width=width,
                        height=height,
                        fit=ft.BoxFit.COVER,
                        opacity=0.34,
                    ),
                    ft.Image(
                        src=path,
                        width=max(260, int(width * 0.42)),
                        height=height,
                        fit=ft.BoxFit.COVER,
                        opacity=0.22,
                        right=0,
                    ),
                ],
                width=width,
                height=height,
            )
    else:
        pane["img_layer"].content = ft.Text(
            "Cargando preview..." if loading else "Sin preview disponible",
            size=12, color=TEXT_DIM, text_align=ft.TextAlign.CENTER)
        backdrop = pane.get("backdrop_layer")
        if backdrop:
            backdrop.content = None


def pane_clear(pane, placeholder="Selecciona un addon para ver sus detalles"):
    pane["generation"] = pane.get("generation", 0) + 1
    pane["current_id"] = None
    pane["title"].value = ""
    pane["meta"].value = ""
    if pane["desc"]:
        pane["desc"].value = ""
    pane["img_layer"].blur = ft.Blur(0, 0)
    pane["img_layer"].opacity = 1.0
    pane["img_layer"].content = ft.Column(
        [
            ft.Icon(ft.Icons.IMAGE_OUTLINED, size=28, color=TEXT_DIM),
            ft.Text(placeholder, size=12, color=TEXT_DIM,
                    text_align=ft.TextAlign.CENTER),
        ],
        spacing=8,
        alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )
    backdrop = pane.get("backdrop_layer")
    if backdrop:
        backdrop.content = None
