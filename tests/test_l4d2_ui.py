import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import l4d2_ui as ui


def addon(addon_id, title, category="Otro", vscript=False, ctime=0):
    return {
        "id": addon_id,
        "title": title,
        "category": category,
        "is_vscript": vscript,
        "ctime": ctime,
        "size": 1,
        "type": "VSCRIPT" if vscript else "MOD",
    }


class VisibleAddonsTests(unittest.TestCase):
    def setUp(self):
        self.addons = [
            addon("10", "Árbol HD", "Skins", ctime=1),
            addon("20", "Rifle limpio", "Armas", ctime=3),
            addon("30", "Admin Script", "UI", vscript=True, ctime=2),
        ]

    def ids(self, **kwargs):
        values = ui.visible_addons(
            self.addons,
            kwargs.pop("active_ids", set()),
            kwargs.pop("favs", set()),
            **kwargs,
        )
        return [value["id"] for value in values]

    def test_search_is_accent_insensitive_and_accepts_ids(self):
        self.assertEqual(self.ids(query="arbol"), ["10"])
        self.assertEqual(self.ids(query="20"), ["20"])

    def test_filter_addons_by_name_reuses_search_rules(self):
        values = ui.filter_addons_by_name(self.addons, "rifle")
        self.assertEqual([value["id"] for value in values], ["20"])
        values = ui.filter_addons_by_name(self.addons, "ARBOL")
        self.assertEqual([value["id"] for value in values], ["10"])

    def test_filters_active_favorites_categories_and_vscripts(self):
        self.assertEqual(self.ids(view="activos", active_ids={"20"}), ["20"])
        self.assertEqual(self.ids(category="Favoritos", favs={"10"}), ["10"])
        self.assertEqual(self.ids(category="Armas"), ["20"])
        self.assertEqual(self.ids(category="VScripts"), ["30"])

    def test_sort_direction_is_stable(self):
        self.assertEqual(self.ids(sort_recent=False), ["10", "30", "20"])
        self.assertEqual(self.ids(sort_recent=True), ["20", "30", "10"])

    def test_empty_state_prioritizes_search_context(self):
        title, detail = ui.empty_state_message(
            "activos", "Armas", "missing", True)
        self.assertEqual(title, "No hay coincidencias")
        self.assertIn("búsqueda", detail)

    def test_row_signature_changes_only_for_visible_row_content(self):
        value = self.addons[0]
        original = ui.row_signature(value, False, False, "mods")
        self.assertEqual(original, ui.row_signature(
            dict(value), False, False, "mods"))
        self.assertNotEqual(original, ui.row_signature(
            value, True, False, "mods"))
        self.assertNotEqual(original, ui.row_signature(
            {**value, "title": "Otro título"}, False, False, "mods"))

    def test_request_generation_rejects_stale_or_closed_results(self):
        self.assertTrue(ui.request_is_current(3, 3))
        self.assertFalse(ui.request_is_current(2, 3))
        self.assertFalse(ui.request_is_current(3, 3, closing=True))

    def test_diagnostic_report_includes_counts_and_warnings(self):
        snapshot = {
            "l4d2_path": r"C:\Steam\Left 4 Dead 2",
            "game_found": True,
            "game_running": True,
            "workshop_exists": True,
            "gameinfo_exists": True,
            "gameinfo_writable": False,
            "addon_count": 12,
            "active_count": 4,
            "selected_count": 2,
            "pending_cleanup_count": 1,
            "vision_state": "off",
            "debug_log_path": r"C:\Temp\debug.log",
        }
        report = ui.format_diagnostic_report(snapshot)
        self.assertIn("Addons instalados: 12", report)
        self.assertIn("Addons activos: 4", report)
        self.assertIn("L4D2 esta abierto", report)
        self.assertIn("gameinfo.txt no parece escribible", report)
        self.assertIn("pendientes de limpiar", report)

    def test_diagnostic_report_can_be_clean(self):
        report = ui.format_diagnostic_report({
            "game_found": True,
            "workshop_exists": True,
            "gameinfo_exists": True,
            "gameinfo_writable": True,
            "pending_cleanup_count": 0,
            "game_running": False,
        })
        self.assertIn("Sin alertas detectadas", report)

    def test_last_config_summary_counts_missing_and_active(self):
        summary = ui.last_config_summary(
            {"ids": ["10", "20", "90"], "saved_at": "2026-09-09 21:30:00"},
            installed_ids={"10", "20"},
            active_ids={"20", "30"},
        )
        self.assertEqual(summary["count"], 3)
        self.assertEqual(summary["missing_count"], 1)
        self.assertEqual(summary["already_active_count"], 1)
        self.assertEqual(summary["saved_at"], "2026-09-09 21:30:00")


if __name__ == "__main__":
    unittest.main()
