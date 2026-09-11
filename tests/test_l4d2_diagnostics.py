import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import l4d2_diagnostics as diagnostics


class DiagnosticsSnapshotTests(unittest.TestCase):
    def cfg_path(self, name):
        return os.path.join(self.tmp.name, "cfg", name)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def make_game(self):
        l4d2 = os.path.join(self.tmp.name, "Left 4 Dead 2")
        left4dead2 = os.path.join(l4d2, "left4dead2")
        workshop = os.path.join(left4dead2, "addons", "workshop")
        os.makedirs(workshop, exist_ok=True)
        with open(os.path.join(left4dead2, "gameinfo.txt"), "w",
                  encoding="utf-8") as file:
            file.write("GameInfo\n")
        return l4d2

    def test_collect_health_snapshot_reports_missing_game(self):
        state = {
            "l4d2": os.path.join(self.tmp.name, "missing"),
            "addons": [{"id": "1"}],
            "active_ids": {"1"},
            "selected_ids": {"1"},
            "_pending_cleanup_ids": {"2"},
            "_l4d2_was_running": False,
        }

        snapshot = diagnostics.collect_health_snapshot(state, self.cfg_path)

        self.assertFalse(snapshot["game_found"])
        self.assertFalse(snapshot["workshop_exists"])
        self.assertFalse(snapshot["gameinfo_exists"])
        self.assertEqual(snapshot["addon_count"], 1)
        self.assertEqual(snapshot["active_count"], 1)
        self.assertEqual(snapshot["pending_cleanup_count"], 1)
        self.assertEqual(snapshot["vision_state"], "unknown")

    def test_collect_health_snapshot_refreshes_live_game_details(self):
        l4d2 = self.make_game()
        state = {
            "l4d2": l4d2,
            "addons": [{"id": "1"}, {"id": "2"}],
            "active_ids": set(),
            "selected_ids": {"2"},
            "_pending_cleanup_ids": set(),
            "_l4d2_was_running": False,
        }

        with mock.patch.object(diagnostics.core, "l4d2_running",
                               return_value=True), \
                mock.patch.object(diagnostics.core, "currently_enabled",
                                  return_value=["1"]), \
                mock.patch.object(diagnostics.core, "currently_enabled_orphans",
                                  return_value=["9"]), \
                mock.patch.object(diagnostics.core, "vision_state",
                                  return_value="off"):
            snapshot = diagnostics.collect_health_snapshot(
                state, self.cfg_path, refresh_running=True)

        self.assertTrue(snapshot["game_found"])
        self.assertTrue(snapshot["game_running"])
        self.assertTrue(snapshot["workshop_exists"])
        self.assertTrue(snapshot["gameinfo_exists"])
        self.assertTrue(snapshot["gameinfo_writable"])
        self.assertEqual(snapshot["addon_count"], 2)
        self.assertEqual(snapshot["active_count"], 1)
        self.assertEqual(snapshot["selected_count"], 1)
        self.assertEqual(snapshot["pending_cleanup_count"], 1)
        self.assertEqual(snapshot["vision_state"], "off")
        self.assertTrue(state["_l4d2_was_running"])


if __name__ == "__main__":
    unittest.main()
