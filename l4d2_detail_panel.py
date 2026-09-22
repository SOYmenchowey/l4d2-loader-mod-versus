import flet as ft

from l4d2_theme import ACCENT, BG, BORDER, SURFACE_2, TEXT, TEXT_DIM


def _detail_action_button(text, icon, on_click, primary=False):
    return ft.TextButton(
        text,
        icon=icon,
        on_click=on_click,
        icon_color=ACCENT if primary else TEXT_DIM,
        disabled=True,
        style=ft.ButtonStyle(
            color=TEXT if not primary else BG,
            bgcolor=ACCENT if primary else SURFACE_2,
            padding=ft.Padding.symmetric(horizontal=10, vertical=8),
            shape=ft.RoundedRectangleBorder(radius=8),
        ),
    )


def build_detail_panel(main_pane, on_open_workshop, on_open_folder,
                       on_copy_id, on_toggle_fav, get_current_addon):
    workshop_button = _detail_action_button(
        "Workshop",
        (ft.Icons.OPEN_IN_NEW if hasattr(ft.Icons, "OPEN_IN_NEW")
         else ft.Icons.LINK),
        on_open_workshop,
    )
    folder_button = _detail_action_button(
        "Abrir carpeta",
        (ft.Icons.FOLDER_OPEN if hasattr(ft.Icons, "FOLDER_OPEN")
         else ft.Icons.FOLDER),
        on_open_folder,
    )
    copy_id_button = _detail_action_button(
        "Copiar ID",
        getattr(ft.Icons, "CONTENT_COPY", ft.Icons.COPY),
        on_copy_id,
    )
    status = ft.Container(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.KEY, size=15, color=TEXT_DIM),
                ft.Text("Inactivo", size=12, color=TEXT,
                        weight=ft.FontWeight.W_700),
            ],
            spacing=7,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=SURFACE_2,
        border=ft.Border.all(1, BORDER),
        border_radius=8,
        padding=ft.Padding.symmetric(horizontal=10, vertical=8),
    )
    favorite = ft.Container(
        content=ft.Text("☆", size=20, color=TEXT_DIM),
        width=38,
        height=38,
        bgcolor=SURFACE_2,
        border=ft.Border.all(1, BORDER),
        border_radius=8,
        alignment=ft.Alignment.CENTER,
        ink=True,
        tooltip="Marcar favorito",
        on_click=lambda e: (
            on_toggle_fav(get_current_addon()) if get_current_addon() else None
        ),
    )
    panel = ft.Container(
        content=ft.Column(
            [
                main_pane["img"],
                ft.Container(height=8),
                main_pane["title"],
                main_pane["meta"],
                ft.Container(height=6),
                ft.Row(
                    [
                        status,
                        ft.Container(expand=True),
                        favorite,
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Container(
                                content=ft.Text("Información", size=12,
                                                color=ACCENT,
                                                weight=ft.FontWeight.W_700),
                                border=ft.Border.only(
                                    bottom=ft.BorderSide(2, ACCENT)),
                                padding=ft.Padding.only(bottom=8),
                            ),
                            ft.Text("Archivos", size=12, color=TEXT_DIM),
                            ft.Text("Capturas", size=12, color=TEXT_DIM),
                        ],
                        spacing=18,
                    ),
                    padding=ft.Padding.only(top=8),
                ),
                ft.Divider(color=BORDER, height=1),
                ft.Text("Descripción", size=12, color=TEXT,
                        weight=ft.FontWeight.W_700),
                main_pane["desc"],
                ft.Container(height=2),
                workshop_button,
                folder_button,
                copy_id_button,
            ],
            spacing=7,
        ),
        width=286,
        padding=12,
        bgcolor="#10131A",
        border=ft.Border.all(1, BORDER),
        border_radius=8,
    )
    return {
        "panel": panel,
        "workshop_button": workshop_button,
        "folder_button": folder_button,
        "copy_id_button": copy_id_button,
        "status": status,
        "favorite": favorite,
    }
