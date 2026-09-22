import os

import flet as ft

import l4d2_glows
from l4d2_theme import (
    ACCENT,
    ACCENT_SOFT,
    AMBER,
    BG,
    BORDER,
    DANGER,
    SURFACE,
    SURFACE_2,
    TEXT,
    TEXT_DIM,
    asset_path,
)

SURVIVOR_PREVIEW_IMAGES = {
    "survivor_health_high": asset_path(os.path.join(
        "assets", "glows", "survivors", "ELLIS salud alta.png")),
    "survivor_health_med": asset_path(os.path.join(
        "assets", "glows", "survivors", "ELLIS salud media.png")),
    "survivor_health_low": asset_path(os.path.join(
        "assets", "glows", "survivors", "ELLIS VIDA BAJA.png")),
    "survivor_health_crit": asset_path(os.path.join(
        "assets", "glows", "survivors", "ELLIS SALUD CRITICA.png")),
    "survivor": asset_path(os.path.join(
        "assets", "glows", "survivors", "COMPAÑEROS DE EQUIPO GLOW.png")),
    "survivor_hurt": asset_path(os.path.join(
        "assets", "glows", "survivors", "ELLIS INCAPACITADO GLOW.png")),
    "survivor_vomit": asset_path(os.path.join(
        "assets", "glows", "survivors", "ELLIS GLOW VOMITADO.png")),
}
DEFAULT_SURVIVOR_PREVIEW = asset_path(os.path.join(
    "assets", "glows", "survivors", "ELLIS salud alta.png"))

INFECTED_PREVIEW_IMAGES = {
    "ability": asset_path(os.path.join(
        "assets", "glows", "infected", "HUNTER glow dominante.png")),
    "infected": asset_path(os.path.join(
        "assets", "glows", "infected", "HUNTER GLOW INFECTADO ESPECIAL.png")),
    "ghost_infected": asset_path(os.path.join(
        "assets", "glows", "infected", "HUNTER GLOW INFECTADO ESPECIAL.png")),
    "infected_vomit": asset_path(os.path.join(
        "assets", "glows", "infected",
        "GLOW SUPERVIVIENTE VOMITADO COMO INFECTADO.png")),
    "witch_angry": asset_path(os.path.join(
        "assets", "glows", "infected", "WICH AGRESVIA GLOW.png")),
}
DEFAULT_INFECTED_PREVIEW = asset_path(os.path.join(
    "assets", "glows", "infected", "HUNTER GLOW INFECTADO ESPECIAL.png"))
INFECTED_OUTLINE_IMAGES = {
    "ability": asset_path(os.path.join(
        "assets", "glows", "infected", "HUNTER dominante glow mask.png")),
    "witch_angry": asset_path(os.path.join(
        "assets", "glows", "infected", "WITCH agresiva glow mask.png")),
}

OBJECT_PREVIEW_IMAGES = {
    "item": asset_path(os.path.join(
        "assets", "glows", "objects", "GLOW ITEMS SIN MESA.png")),
    "item_far": asset_path(os.path.join(
        "assets", "glows", "objects", "GLOW ITEMS SIN MESA.png")),
    "thirdstrike_item": asset_path(os.path.join(
        "assets", "glows", "objects", "GLOW ITEMS SIN MESA.png")),
}
DEFAULT_OBJECT_PREVIEW = asset_path(os.path.join(
    "assets", "glows", "objects", "GLOW ITEMS SIN MESA.png"))


def _safe_color(value, fallback):
    try:
        return l4d2_glows.normalize_hex(value)
    except ValueError:
        return l4d2_glows.normalize_hex(fallback)


def _button(text, icon, on_click, primary=False, danger=False):
    color = DANGER if danger else ACCENT
    return ft.FilledButton(
        text,
        icon=icon,
        on_click=on_click,
        style=ft.ButtonStyle(
            bgcolor=color if primary or danger else SURFACE_2,
            color=BG if primary or danger else TEXT,
            shape=ft.RoundedRectangleBorder(radius=8),
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
        ),
    )


def _status_badge(applied, dirty):
    if dirty:
        text, color, bg = "Cambios sin aplicar", AMBER, "#2B2110"
    elif applied:
        text, color, bg = "Aplicado", ACCENT, ACCENT_SOFT
    else:
        text, color, bg = "Sin aplicar", TEXT_DIM, SURFACE_2
    return ft.Container(
        content=ft.Text(text, size=11, color=color,
                        weight=ft.FontWeight.W_700),
        bgcolor=bg,
        border=ft.Border.all(1, color if dirty or applied else BORDER),
        border_radius=8,
        padding=ft.Padding.symmetric(horizontal=9, vertical=5),
    )


def _glow_card(item, colors, on_change, on_pick_color, on_select_color,
               selected=False):
    value = colors.get(item["key"], item["default"])
    try:
        l4d2_glows.normalize_hex(value)
        is_valid = True
    except ValueError:
        is_valid = False
    display_color = _safe_color(value, item["default"])
    field = ft.TextField(
        value=value,
        height=36,
        width=96,
        text_size=12,
        color=TEXT,
        bgcolor="#10131A",
        border_color=BORDER if is_valid else DANGER,
        focused_border_color=ACCENT,
        content_padding=ft.Padding.symmetric(horizontal=9, vertical=6),
        on_change=lambda e, key=item["key"]: on_change(key, e.control.value),
        on_focus=lambda e, key=item["key"]: on_select_color(key),
        on_click=lambda e, key=item["key"]: on_select_color(key),
    )
    return ft.Container(
        content=ft.Row(
            [
                ft.Container(
                    content=ft.Container(
                        width=34,
                        height=34,
                        bgcolor=display_color,
                        border_radius=8,
                        border=ft.Border.all(1, "#FFFFFF22"),
                        shadow=ft.BoxShadow(
                            blur_radius=12,
                            color=display_color + "66",
                            offset=ft.Offset(0, 0),
                        ),
                    ),
                    padding=2,
                    border_radius=10,
                    border=ft.Border.all(1, ACCENT_SOFT),
                    ink=True,
                    tooltip="Elegir color",
                    on_click=lambda e, key=item["key"], label=item["label"]:
                        on_pick_color(key, label),
                ),
                ft.Column(
                    [
                        ft.Text(item["label"], size=13, color=TEXT,
                                weight=ft.FontWeight.W_700,
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS),
                        ft.Text(item["commands"][0], size=10, color=TEXT_DIM,
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS),
                    ],
                    spacing=2,
                    expand=True,
                ),
                field,
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor="#12131A",
        border=ft.Border.all(1, ACCENT if selected else BORDER),
        border_radius=8,
        padding=10,
        ink=True,
        on_click=lambda e, key=item["key"]: on_select_color(key),
    )


def _glow_preview(title, items, colors, selected_key, on_select_color,
                  preview_images, default_preview, outline_images=None,
                  stack_size=(230, 286), image_size=(202, 262),
                  image_offset=(18, 12)):
    selected = next((item for item in items if item["key"] == selected_key),
                    items[0])
    color = _safe_color(
        colors.get(selected["key"], selected["default"]),
        selected["default"],
    )
    preview_image = preview_images.get(selected["key"], default_preview)
    outline_image = (outline_images or {}).get(selected["key"], preview_image)
    image_exists = os.path.isfile(preview_image)
    outline_exists = os.path.isfile(outline_image)
    stack_w, stack_h = stack_size
    img_w, img_h = image_size
    base_left, base_top = image_offset
    outline_offsets = [
        (-4, 0), (4, 0), (0, -4), (0, 4),
        (-3, -3), (3, -3), (-3, 3), (3, 3),
        (-7, 0), (7, 0), (0, -7), (0, 7),
        (-5, -5), (5, -5), (-5, 5), (5, 5),
    ]
    outline_layers = [
        ft.Image(
            src=outline_image,
            width=img_w,
            height=img_h,
            fit=ft.BoxFit.CONTAIN,
            color=color,
            color_blend_mode=ft.BlendMode.SRC_IN,
            opacity=0.76 if abs(dx) + abs(dy) <= 8 else 0.38,
            left=base_left + dx,
            top=base_top + dy,
            visible=outline_exists,
        )
        for dx, dy in outline_offsets
    ]
    image_stack = ft.Stack(
        [
            ft.Container(
                width=stack_w,
                height=stack_h,
                bgcolor="#0B0E14",
            ),
            *outline_layers,
            ft.Image(
                src=preview_image,
                width=img_w,
                height=img_h,
                fit=ft.BoxFit.CONTAIN,
                left=base_left,
                top=base_top,
                visible=image_exists,
            ),
            ft.Container(
                content=ft.Text("Preview no encontrado", size=12,
                                color=TEXT_DIM,
                                text_align=ft.TextAlign.CENTER),
                alignment=ft.Alignment.CENTER,
                width=stack_w,
                height=stack_h,
                visible=not image_exists,
            ),
        ],
        width=stack_w,
        height=stack_h,
        alignment=ft.Alignment.CENTER,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
    )
    chips = []
    for item in items:
        item_color = _safe_color(
            colors.get(item["key"], item["default"]),
            item["default"],
        )
        chips.append(ft.Container(
            width=20,
            height=20,
            bgcolor=item_color,
            border_radius=7,
            border=ft.Border.all(
                2, ACCENT if item["key"] == selected["key"] else BORDER),
            ink=True,
            tooltip=item["label"],
            on_click=lambda e, key=item["key"]: on_select_color(key),
        ))
    return ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.VISIBILITY, size=17, color=ACCENT),
                        ft.Text(title, size=13, color=TEXT,
                                weight=ft.FontWeight.W_800),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                image_stack,
                ft.Text(selected["label"], size=13, color=TEXT,
                        weight=ft.FontWeight.W_700,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(color, size=12, color=TEXT_DIM),
                ft.Row(chips, spacing=7, wrap=True),
            ],
            spacing=9,
        ),
        width=286,
        bgcolor="#0F1219",
        border=ft.Border.all(1, BORDER),
        border_radius=8,
        padding=12,
    )


def _group_section(group, items, colors, on_change, on_pick_color,
                   on_select_color, selected_key):
    cards = ft.Column(
        [_glow_card(
            item, colors, on_change, on_pick_color, on_select_color,
            selected=item["key"] == selected_key,
        ) for item in items],
        spacing=7,
        expand=True,
    )
    body = cards
    if group == "Sobrevivientes":
        body = ft.Row(
            [
                _glow_preview(
                    "Preview survivor",
                    items,
                    colors,
                    selected_key,
                    on_select_color,
                    SURVIVOR_PREVIEW_IMAGES,
                    DEFAULT_SURVIVOR_PREVIEW,
                ),
                cards,
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
    elif group == "Infectados":
        body = ft.Row(
            [
                _glow_preview(
                    "Preview infectado",
                    items,
                    colors,
                    selected_key,
                    on_select_color,
                    INFECTED_PREVIEW_IMAGES,
                    DEFAULT_INFECTED_PREVIEW,
                    INFECTED_OUTLINE_IMAGES,
                ),
                cards,
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
    elif group == "Objetos":
        body = ft.Row(
            [
                _glow_preview(
                    "Preview objetos",
                    items,
                    colors,
                    selected_key,
                    on_select_color,
                    OBJECT_PREVIEW_IMAGES,
                    DEFAULT_OBJECT_PREVIEW,
                    stack_size=(230, 190),
                    image_size=(222, 154),
                    image_offset=(4, 18),
                ),
                cards,
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
    return ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(group, size=15, color=TEXT,
                                weight=ft.FontWeight.W_800),
                        ft.Container(expand=True),
                        ft.Text("%d glows" % len(items), size=11,
                                color=TEXT_DIM),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                body,
            ],
            spacing=10,
        ),
        bgcolor=SURFACE,
        border=ft.Border.all(1, BORDER),
        border_radius=8,
        padding=12,
    )


def build_glows_view(colors, applied, dirty, on_change, on_apply, on_restore,
                     on_preset, on_pick_color, on_select_color,
                     selected_key=None):
    groups = []
    for item in l4d2_glows.GLOW_ITEMS:
        if item["group"] not in groups:
            groups.append(item["group"])
    preset_buttons = [
        ft.Container(
            content=ft.Text(name, size=12, color=TEXT,
                            weight=ft.FontWeight.W_600),
            bgcolor=SURFACE_2,
            border=ft.Border.all(1, BORDER),
            border_radius=18,
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            ink=True,
            on_click=lambda e, preset=name: on_preset(preset),
        )
        for name in l4d2_glows.PRESETS
    ]
    return ft.Container(
        content=ft.Column(
            [
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Column(
                                        [
                                            ft.Text("Glows", size=22,
                                                    color=TEXT,
                                                    weight=ft.FontWeight.W_800),
                                            ft.Text(
                                                "Personaliza contornos de L4D2 sin editar cfg a mano.",
                                                size=12,
                                                color=TEXT_DIM,
                                            ),
                                        ],
                                        spacing=2,
                                        expand=True,
                                    ),
                                    _status_badge(applied, dirty),
                                ],
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Row(
                                [
                                    _button("Aplicar glows", ft.Icons.CHECK,
                                            on_apply, primary=True),
                                    _button("Restaurar glows",
                                            ft.Icons.RESTORE,
                                            on_restore,
                                            danger=True),
                                ],
                                spacing=8,
                            ),
                            ft.Row(
                                preset_buttons,
                                spacing=8,
                                wrap=True,
                            ),
                        ],
                        spacing=12,
                    ),
                    bgcolor="#10131A",
                    border=ft.Border.all(1, BORDER),
                    border_radius=8,
                    padding=14,
                ),
                *[
                    _group_section(
                        group,
                        [item for item in l4d2_glows.GLOW_ITEMS
                         if item["group"] == group],
                        colors,
                        on_change,
                        on_pick_color,
                        on_select_color,
                        selected_key,
                    )
                    for group in groups
                ],
            ],
            spacing=12,
        ),
        padding=ft.Padding.only(bottom=18),
    )
