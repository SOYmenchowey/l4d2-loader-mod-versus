import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import l4d2_glows
import l4d2_glows_view


class GlowViewTests(unittest.TestCase):
    def test_invalid_saved_color_does_not_break_view_build(self):
        colors = l4d2_glows.default_colors()
        colors["survivor"] = "not-a-color"

        view = l4d2_glows_view.build_glows_view(
            colors,
            applied=False,
            dirty=True,
            on_change=lambda *args: None,
            on_apply=lambda *args: None,
            on_restore=lambda *args: None,
            on_preset=lambda *args: None,
            on_pick_color=lambda *args: None,
            on_select_color=lambda *args: None,
            selected_key="survivor",
        )

        self.assertIsNotNone(view)
        self.assertEqual(
            l4d2_glows_view._safe_color("not-a-color", "#4C66FF"),
            "#4C66FF",
        )


if __name__ == "__main__":
    unittest.main()
