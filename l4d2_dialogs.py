import os

import flet as ft

from l4d2_controls import pane_set_img
from l4d2_theme import (
    ACCENT,
    ACCENT_SOFT,
    AMBER,
    AMBER_SOFT,
    BG,
    BORDER,
    DANGER,
    DANGER_SOFT,
    SURFACE,
    SURFACE_2,
    TEXT,
    TEXT_DIM,
)


def _quant(count, singular, plural):
    return "%d %s" % (count, singular if count == 1 else plural)


def dialog_shell(content, width, padded=False):
    container = ft.Container(
        content=content,
        width=width,
        bgcolor=SURFACE_2 if padded else None,
        border=ft.Border.all(1, BORDER) if padded else None,
        border_radius=12 if padded else None,
        padding=18 if padded else None,
    )
    container.animate_scale = ft.Animation(220, "easeOut")
    container.animate_opacity = ft.Animation(180, "easeOut")
    container.scale = 0.93
    container.opacity = 0.0
    return container


def modal_header(icon, title, subtitle, color=ACCENT):
    soft = ACCENT_SOFT if color == ACCENT else (
        DANGER_SOFT if color == DANGER else AMBER_SOFT)
    return ft.Row(
        [
            ft.Container(
                content=ft.Icon(icon, size=20, color=color),
                width=36,
                height=36,
                border_radius=8,
                bgcolor=soft,
                border=ft.Border.all(1, color),
                alignment=ft.Alignment.CENTER,
            ),
            ft.Column(
                [
                    ft.Text(title, size=17, weight=ft.FontWeight.W_700,
                            color=TEXT),
                    ft.Text(subtitle, size=11, color=TEXT_DIM,
                            max_lines=2,
                            overflow=ft.TextOverflow.ELLIPSIS),
                ],
                spacing=2,
                expand=True,
            ),
        ],
        spacing=10,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def count_badge(text, color=ACCENT):
    return ft.Container(
        content=ft.Text(text, size=11,
                        color=BG if color == ACCENT else color,
                        weight=ft.FontWeight.W_700),
        bgcolor=ACCENT if color == ACCENT else AMBER_SOFT,
        border=None if color == ACCENT else ft.Border.all(1, color),
        border_radius=6,
        padding=ft.Padding.symmetric(horizontal=8, vertical=4),
    )


def addon_review_dialog_content(rows, pane, header, summary, list_title,
                                height=240, width=640, banner=None,
                                color=ACCENT, current_addon=None):
    list_icon = getattr(ft.Icons, "LAYERS", ft.Icons.LIST)
    pane["title"].size = 15
    pane["title"].weight = ft.FontWeight.W_700
    pane["meta"].size = 11
    backdrop_height = int(pane["height"] + 42)
    pane["backdrop_layer"] = ft.Container(
        width=width - 36,
        height=backdrop_height,
        opacity=1.0,
    )
    overlay = ft.Container(
        width=width - 36,
        height=backdrop_height,
        gradient=ft.LinearGradient(
            begin=ft.Alignment(-1, 0),
            end=ft.Alignment(1, 0),
            colors=["#F20C0C10", "#C911131A", "#7A11131A"],
        ),
    )
    accent_wash = ft.Container(
        width=width - 36,
        height=backdrop_height,
        gradient=ft.LinearGradient(
            begin=ft.Alignment(-1, -1),
            end=ft.Alignment(1, 1),
            colors=[
                "#551B3A2A" if color == ACCENT else "#55351D24",
                "#0011131A",
                "#3311131A",
            ],
        ),
        opacity=0.8,
    )
    content_row = ft.Container(
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
                            ft.Row(summary, spacing=8, wrap=True),
                            ft.Container(height=2),
                            ft.Row(
                                [
                                    ft.Icon(ft.Icons.INFO_OUTLINE,
                                            size=16, color=TEXT_DIM),
                                    ft.Text("Pasa el mouse por un addon "
                                            "para ver su preview antes de "
                                            "confirmar.",
                                            size=12, color=TEXT_DIM,
                                            max_lines=2,
                                            overflow=ft.TextOverflow.ELLIPSIS,
                                            expand=True),
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
    )
    top = ft.Container(
        content=ft.Stack(
            [
                pane["backdrop_layer"],
                accent_wash,
                overlay,
                content_row,
            ],
            width=width - 36,
            height=backdrop_height,
        ),
        bgcolor="#11131A",
        border=ft.Border.all(1, "#334155" if color == ACCENT else BORDER),
        border_radius=8,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
    )
    kids = [header]
    if banner:
        kids.append(banner)
    kids.extend([
        top,
        ft.Row(
            [
                ft.Icon(list_icon, size=18, color=color),
                ft.Text(list_title, size=16, weight=ft.FontWeight.W_700,
                        color=TEXT, expand=True),
                ft.Container(expand=True),
                ft.Text("%d en lista" % len(rows), size=11,
                        color=TEXT_DIM),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        ft.Container(
            content=ft.ListView(rows, height=height, spacing=6,
                                scroll=ft.ScrollMode.AUTO),
            border=ft.Border.all(1, "#334155" if color == ACCENT else BORDER),
            border_radius=8,
            padding=6,
            bgcolor="#0E0F15",
        ),
    ])
    current_preview = (current_addon or {}).get("preview_local")
    if current_preview and os.path.isfile(current_preview):
        pane_set_img(pane, current_preview)
    return dialog_shell(ft.Column(kids, spacing=14), width, padded=True)


def confirm_dialog_content(icon, title, subtitle, items, note=None,
                           width=470, color=DANGER):
    list_items = [
        ft.Row(
            [
                ft.Container(width=5, height=5, bgcolor=color,
                             border_radius=3),
                ft.Text(item, size=12, color=TEXT_DIM, expand=True),
            ],
            spacing=9,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        for item in items
    ]
    kids = [
        modal_header(icon, title, subtitle, color=color),
        ft.Container(
            content=ft.Column(list_items, spacing=7),
            bgcolor=SURFACE,
            border=ft.Border.all(1, BORDER),
            border_radius=8,
            padding=12,
        ),
    ]
    if note:
        kids.append(ft.Container(
            content=ft.Text(note, size=11, color=AMBER),
            bgcolor=AMBER_SOFT,
            border=ft.Border.all(1, AMBER),
            border_radius=8,
            padding=10,
        ))
    return dialog_shell(ft.Column(kids, spacing=12, tight=True), width)


def enable_dialog_content(rows, pane, count, dep_count, banner=None,
                          height=240, width=640, current_addon=None):
    summary_parts = [count_badge(_quant(count, "addon", "addons"))]
    if dep_count:
        summary_parts.append(count_badge(
            _quant(dep_count, "dependencia", "dependencias"), AMBER))
    return addon_review_dialog_content(
        rows,
        pane,
        modal_header(ft.Icons.CHECK_CIRCLE_OUTLINE,
                     "Confirmar habilitación",
                     "Los cambios se aplicarán cuando confirmes.",
                     ACCENT),
        summary_parts,
        "Addons a habilitar",
        height=height,
        width=width,
        banner=banner,
        color=ACCENT,
        current_addon=current_addon,
    )


def progress_dialog_content(title, subtitle, width=420):
    container = ft.Container(
        content=ft.Column(
            [
                modal_header(
                    getattr(ft.Icons, "HOURGLASS_TOP", ft.Icons.SCHEDULE),
                    title, subtitle, ACCENT),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.ProgressBar(
                                width=width - 48,
                                color=ACCENT,
                                bgcolor=BORDER,
                                value=None,
                            ),
                            ft.Text("Mantén esta ventana abierta hasta terminar.",
                                    size=11, color=TEXT_DIM),
                        ],
                        spacing=10,
                    ),
                    bgcolor=SURFACE,
                    border=ft.Border.all(1, BORDER),
                    border_radius=8,
                    padding=14,
                ),
            ],
            spacing=12,
            tight=True,
        ),
        width=width,
    )
    container.animate_scale = ft.Animation(220, "easeOut")
    container.animate_opacity = ft.Animation(180, "easeOut")
    container.scale = 0.93
    container.opacity = 0.0
    return container
