import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import l4d2_game


class GamePathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.l4d2 = os.path.join(self.tmp.name, "SteamLibrary",
                                 "steamapps", "common", "Left 4 Dead 2")
        self.left4dead2 = os.path.join(self.l4d2, "left4dead2")
        self.addons = os.path.join(self.left4dead2, "addons")
        self.workshop = os.path.join(self.addons, "workshop")
        os.makedirs(self.workshop, exist_ok=True)
        with open(os.path.join(self.left4dead2, "gameinfo.txt"), "w",
                  encoding="utf-8") as file:
            file.write("GameInfo\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_resolve_accepts_game_root(self):
        self.assertEqual(l4d2_game.resolve_l4d2_path(self.l4d2), self.l4d2)

    def test_resolve_accepts_left4dead2_addons_or_workshop_folder(self):
        self.assertEqual(
            l4d2_game.resolve_l4d2_path(self.left4dead2), self.l4d2)
        self.assertEqual(
            l4d2_game.resolve_l4d2_path(self.addons), self.l4d2)
        self.assertEqual(
            l4d2_game.resolve_l4d2_path(self.workshop), self.l4d2)

    def test_resolve_accepts_steam_library_root(self):
        library = os.path.join(self.tmp.name, "SteamLibrary")
        self.assertEqual(l4d2_game.resolve_l4d2_path(library), self.l4d2)

    def test_find_prefers_manual_path(self):
        self.assertEqual(l4d2_game.find_l4d2(self.workshop), self.l4d2)

    def test_list_addons_reads_workshop_and_root_addons(self):
        workshop_vpk = os.path.join(self.workshop, "12345.vpk")
        root_vpk = os.path.join(self.addons, "my local mod.vpk")
        with open(workshop_vpk, "wb") as file:
            file.write(b"workshop")
        with open(root_vpk, "wb") as file:
            file.write(b"local")

        addons = l4d2_game.list_addons(self.l4d2)
        ids = {addon["id"] for addon in addons}

        self.assertIn("12345", ids)
        local = next(addon for addon in addons if addon['path'] == root_vpk)
        self.assertTrue(local['id'].startswith('local_my_local_mod_'))
        self.assertEqual(local['source_kind'], 'local')
        self.assertEqual(len(ids), 2)


if __name__ == "__main__":
    unittest.main()
