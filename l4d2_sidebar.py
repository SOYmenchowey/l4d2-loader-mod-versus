import os

import flet as ft

import l4d2_core as core
import l4d2_ui as ui
from l4d2_controls import fit_image
from l4d2_theme import (
    ACCENT,
    ACCENT_SOFT,
    AMBER,
    AMBER_SOFT,
    BG,
    BORDER,
    DANGER,
    DANGER_SOFT,
    SURFACE_2,
    TEXT,
    TEXT_DIM,
)


def build_nav_item(text, view_name, selected, on_nav, badge=0, icon=None):
    content = ft.Row(
        [
            ft.Icon(icon or ft.Icons.CIRCLE_OUTLINED, size=17,
                    color=TEXT if selected else TEXT_DIM),
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
        padding=ft.Padding.symmetric(horizontal=14, vertical=11),
        border_radius=8,
        bgcolor=SURFACE_2 if selected else None,
        border=(ft.Border.all(1, "#2F3A46") if selected else None),
        on_click=lambda e, view=view_name: on_nav(view),
        ink=True,
    )


def build_sub_nav_item(text, view_name, selected, on_nav, icon=None):
    return ft.Container(
        content=ft.Row(
            [
                ft.Container(width=1, height=22, bgcolor=BORDER),
                ft.Container(width=8),
                ft.Icon(icon or ft.Icons.CIRCLE_OUTLINED, size=15,
                        color=TEXT if selected else TEXT_DIM),
                ft.Text(
                    text,
                    size=12,
                    color=TEXT if selected else TEXT_DIM,
                    weight=(ft.FontWeight.W_600 if selected
                            else ft.FontWeight.NORMAL),
                ),
            ],
            spacing=7,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        margin=ft.Margin.only(left=14),
        padding=ft.Padding.symmetric(horizontal=10, vertical=9),
        border_radius=8,
        bgcolor=SURFACE_2 if selected else None,
        border=(ft.Border.all(1, "#2F3A46") if selected else None),
        on_click=lambda e, view=view_name: on_nav(view),
        ink=True,
    )


def build_health_row(label, ok, warn_text=None):
    color = ACCENT if ok else AMBER
    value = "OK" if ok else (warn_text or "Revisar")
    return ft.Row(
        [
            ft.Container(width=7, height=7, border_radius=4, bgcolor=color),
            ft.Text(label, size=11, color=TEXT_DIM, expand=True,
                    max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
            ft.Text(value, size=10, color=color, weight=ft.FontWeight.W_700),
        ],
        spacing=7,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def build_health_card(snapshot):
    warnings = ui.diagnostic_warnings(snapshot)
    severe = (
        not snapshot["game_found"] or snapshot["game_running"] or
        (snapshot["game_found"] and not snapshot["gameinfo_writable"])
    )
    badge_color = DANGER if severe else (AMBER if warnings else ACCENT)
    badge_text = "Revisar" if warnings else "Correcto"

    return ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("Salud", size=12, color=TEXT,
                                weight=ft.FontWeight.W_700),
                        ft.Container(expand=True),
                        ft.Container(
                            content=ft.Text(
                                badge_text, size=9, color=badge_color,
                                weight=ft.FontWeight.W_700),
                            bgcolor=(DANGER_SOFT if severe else
                                     AMBER_SOFT if warnings else
                                     ACCENT_SOFT),
                            border=ft.Border.all(1, badge_color),
                            border_radius=6,
                            padding=ft.Padding.symmetric(
                                horizontal=6, vertical=2),
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                build_health_row("L4D2", snapshot["game_found"], "No"),
                build_health_row("Juego", not snapshot["game_running"],
                                 "Abierto"),
                build_health_row("gameinfo", snapshot["gameinfo_writable"],
                                 "Bloq."),
                build_health_row("Workshop", snapshot["workshop_exists"],
                                 "No"),
                build_health_row(
                    "Limpieza",
                    not snapshot["pending_cleanup_count"],
                    str(snapshot["pending_cleanup_count"]),
                ),
            ],
            spacing=7,
            tight=True,
        ),
        bgcolor="#121218",
        border=ft.Border.all(1, BORDER),
        border_radius=8,
        padding=10,
    )


def _section(text):
    return ft.Container(
        content=ft.Text(text, size=11, color=TEXT_DIM,
                        weight=ft.FontWeight.W_600),
        padding=ft.Padding.only(left=14, top=8, bottom=2),
    )


def _action(text, color, icon, on_click, subtle=False):
    return ft.Container(
        content=ft.Row(
            [
                ft.Icon(icon, size=17, color=color),
                ft.Text(text, size=12, color=color, max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS, expand=True),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding.symmetric(horizontal=14, vertical=10),
        border_radius=8,
        bgcolor=SURFACE_2 if not subtle else None,
        border=ft.Border.all(1, BORDER) if not subtle else None,
        on_click=on_click,
        ink=True,
    )


def build_sidebar(state, health_snapshot, icon_path, on_play, on_nav,
                  on_diagnostic, on_restore_last, on_restore_original,
                  on_toggle_vision, on_tiktok, tiktok_url):
    logo = ft.Container(
        content=ft.Column(
            [
                (fit_image(icon_path, 104, 104) if os.path.isfile(icon_path)
                 else ft.Text("L4D2", size=24, weight=ft.FontWeight.BOLD,
                              color=ACCENT)),
                ft.Text("L4D2", size=24, weight=ft.FontWeight.W_800,
                        color=TEXT),
                ft.Text("MOD LOADER", size=11, color=TEXT_DIM,
                        weight=ft.FontWeight.W_600),
            ],
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding.only(top=8, bottom=10),
        alignment=ft.Alignment.CENTER,
    )
    vision_off = bool(state["l4d2"]) and \
        core.vision_state(state["l4d2"]) == "off"
    tiktok_footer = ft.Container(
        content=ft.Text("made by @tokyossz", size=13, color=TEXT_DIM,
                        italic=True),
        padding=ft.Padding.symmetric(horizontal=14, vertical=6),
        on_click=on_tiktok,
        tooltip=tiktok_url,
        ink=True,
    )

    return ft.Column(
        [
            logo,
            ft.FilledButton(
                "JUGAR",
                icon=(ft.Icons.PLAY_ARROW if hasattr(ft.Icons, "PLAY_ARROW")
                      else "\u25B6"),
                on_click=on_play,
                style=ft.ButtonStyle(
                    bgcolor=ACCENT, color=BG,
                    shape=ft.RoundedRectangleBorder(radius=8)),
            ),
            ft.Container(height=10),
            build_nav_item(
                "Mods",
                "mods",
                state["view"] in ("mods", "activos"),
                on_nav,
                icon=getattr(ft.Icons, "EXTENSION", ft.Icons.VIEW_MODULE),
            ),
            build_sub_nav_item(
                "Activos",
                "activos",
                state["view"] == "activos",
                on_nav,
                icon=getattr(ft.Icons, "INVENTORY_2_OUTLINED",
                             ft.Icons.CHECK_BOX_OUTLINE_BLANK),
            ),
            build_nav_item(
                "Glows", "glows", state["view"] == "glows", on_nav,
                icon=getattr(ft.Icons, "PALETTE_OUTLINED",
                             ft.Icons.COLOR_LENS)),
            ft.Container(height=8),
            ft.Divider(color=BORDER, height=1),
            _section("HERRAMIENTAS"),
            _action("Diagnóstico", TEXT, getattr(
                ft.Icons, "FACT_CHECK_OUTLINED", ft.Icons.INFO_OUTLINE),
                on_diagnostic, subtle=True),
            _action("Última config", TEXT, ft.Icons.RESTORE,
                    on_restore_last, subtle=True),
            ft.Container(height=6),
            ft.Divider(color=BORDER, height=1),
            _section("SISTEMA"),
            build_health_card(health_snapshot),
            ft.Container(height=6),
            ft.Divider(color=BORDER, height=1),
            _action("Restaurar original", DANGER, ft.Icons.RESTORE,
                    on_restore_original, subtle=True),
            _action(
                "Restaurar Visión de Infectado" if vision_off
                else "Quitar Visión de Infectado",
                ACCENT if vision_off else DANGER,
                ft.Icons.VISIBILITY if vision_off else ft.Icons.VISIBILITY_OFF,
                on_toggle_vision,
                subtle=True,
            ),
            ft.Container(expand=True),
            tiktok_footer,
        ],
        spacing=6, width=190,
    )
