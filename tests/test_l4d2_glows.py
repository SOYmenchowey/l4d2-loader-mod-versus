import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import l4d2_glows as glows


class GlowConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_localappdata = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = os.path.join(self.tmp.name, "localappdata")
        self.l4d2 = os.path.join(self.tmp.name, "Left 4 Dead 2")
        self.cfg = os.path.join(self.l4d2, "left4dead2", "cfg")
        os.makedirs(self.cfg, exist_ok=True)

    def tearDown(self):
        if self.old_localappdata is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self.old_localappdata
        self.tmp.cleanup()

    def read_autoexec(self):
        with open(os.path.join(self.cfg, "autoexec.cfg"),
                  encoding="utf-8") as file:
            return file.read()

    def test_hex_to_source_rgb_values(self):
        self.assertEqual(glows.hex_to_rgb_values("#FF0000"), (1.0, 0.0, 0.0))
        self.assertEqual(glows.normalize_hex("00ff40"), "#00FF40")

    def test_build_cfg_writes_rgb_commands_for_each_mapped_command(self):
        colors = glows.default_colors()
        colors["ability"] = "#FF0000"

        text = glows.build_cfg(colors)

        self.assertIn('cl_glow_ability_r "1";', text)
        self.assertIn('cl_glow_ability_g "0";', text)
        self.assertIn('cl_glow_ability_colorblind_b "0";', text)

    def test_apply_and_restore_preserve_external_autoexec_content(self):
        autoexec = os.path.join(self.cfg, "autoexec.cfg")
        with open(autoexec, "w", encoding="utf-8") as file:
            file.write("mat_monitorgamma 1.6\n")

        self.assertTrue(glows.apply_glows(
            self.l4d2, glows.default_colors(), log=lambda msg: None))
        self.assertTrue(os.path.isfile(glows.cfg_path(self.l4d2)))
        self.assertIn(glows.AUTOEXEC_BEGIN, self.read_autoexec())
        self.assertIn("mat_monitorgamma 1.6", self.read_autoexec())

        self.assertTrue(glows.restore_glows(
            self.l4d2, log=lambda msg: None))
        self.assertFalse(os.path.exists(glows.cfg_path(self.l4d2)))
        restored = self.read_autoexec()
        self.assertNotIn(glows.AUTOEXEC_BEGIN, restored)
        self.assertIn("mat_monitorgamma 1.6", restored)


if __name__ == "__main__":
    unittest.main()
