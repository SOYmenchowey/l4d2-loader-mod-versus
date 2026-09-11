import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import l4d2_core as core


GAMEINFO = """GameInfo
{
    FileSystem
    {
        SearchPaths
        {
            Game            left4dead2
        }
    }
}
"""


class CoreFileFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_localappdata = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = os.path.join(self.tmp.name, "localappdata")
        self.old_running = core.l4d2_running
        core.l4d2_running = lambda: False

        self.l4d2 = os.path.join(self.tmp.name, "Left 4 Dead 2")
        self.left4dead2 = os.path.join(self.l4d2, "left4dead2")
        self.workshop = os.path.join(self.left4dead2, "addons", "workshop")
        os.makedirs(self.workshop, exist_ok=True)
        with open(os.path.join(self.left4dead2, "gameinfo.txt"), "w",
                  encoding="utf-8") as f:
            f.write(GAMEINFO)

    def tearDown(self):
        core.l4d2_running = self.old_running
        if self.old_localappdata is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self.old_localappdata
        self.tmp.cleanup()

    def write_vpk(self, addon_id, data=b"fake-vpk"):
        path = os.path.join(self.workshop, addon_id + ".vpk")
        with open(path, "wb") as f:
            f.write(data)
        return {"id": addon_id, "path": path, "size": len(data)}

    def read_gameinfo(self):
        with open(os.path.join(self.left4dead2, "gameinfo.txt"),
                  encoding="utf-8") as f:
            return f.read()

    def write_vision_files(self):
        correction = os.path.join(self.left4dead2, "materials", "correction")
        os.makedirs(correction, exist_ok=True)
        for name in core._VISION_FILES:
            with open(os.path.join(correction, name), "wb") as f:
                f.write(("original-" + name).encode("ascii"))
        return correction

    def test_enable_marks_managed_folder_and_disable_removes_only_that_folder(self):
        addon = self.write_vpk("12345")

        self.assertTrue(core.enable(self.l4d2, [addon], log=lambda msg: None))
        managed_dir = os.path.join(self.l4d2, "mods", "12345")
        self.assertTrue(os.path.isfile(os.path.join(managed_dir, "pak01_dir.vpk")))
        self.assertTrue(os.path.isfile(os.path.join(managed_dir,
                                                   core.MANAGED_MARKER)))
        self.assertEqual(core.currently_enabled(self.l4d2), ["12345"])

        self.assertTrue(core.disable(self.l4d2, ["12345"], log=lambda msg: None))
        self.assertFalse(os.path.exists(managed_dir))
        self.assertEqual(core.currently_enabled(self.l4d2), [])

    def test_restore_preserves_unmanaged_mods_folder(self):
        addon = self.write_vpk("12345")
        self.assertTrue(core.enable(self.l4d2, [addon], log=lambda msg: None))

        manual_dir = os.path.join(self.l4d2, "mods", "manual_mod")
        os.makedirs(manual_dir, exist_ok=True)
        with open(os.path.join(manual_dir, "pak01_dir.vpk"), "wb") as f:
            f.write(b"manual")

        self.assertTrue(core.restore(self.l4d2, log=lambda msg: None))
        self.assertTrue(os.path.isdir(manual_dir))
        self.assertFalse(os.path.isdir(os.path.join(self.l4d2, "mods", "12345")))
        self.assertNotIn("mods\\12345", self.read_gameinfo())

    def test_restore_recovers_exact_gameinfo_and_tracked_vision(self):
        gi = os.path.join(self.left4dead2, "gameinfo.txt")
        original = GAMEINFO.replace("\n", "\r\n").encode("utf-8")
        with open(gi, "wb") as f:
            f.write(original)
        correction = self.write_vision_files()
        addon = self.write_vpk("12345")

        self.assertTrue(core.enable(self.l4d2, [addon], log=lambda msg: None))
        self.assertTrue(core.disable_infected_vision(
            self.l4d2, log=lambda msg: None))
        self.assertTrue(core.restore(self.l4d2, log=lambda msg: None))

        with open(gi, "rb") as f:
            self.assertEqual(f.read(), original)
        for name in core._VISION_FILES:
            self.assertTrue(os.path.isfile(os.path.join(correction, name)))
            self.assertFalse(os.path.exists(
                os.path.join(correction, name + core._VISION_OFF)))
        self.assertFalse(os.path.exists(os.path.join(self.l4d2, "mods")))

    def test_restore_preserves_external_gameinfo_edits(self):
        addon = self.write_vpk("12345")
        self.assertTrue(core.enable(self.l4d2, [addon], log=lambda msg: None))
        gi = os.path.join(self.left4dead2, "gameinfo.txt")
        with open(gi, "ab") as f:
            f.write(b"\nGame            custom\\external\n")

        self.assertTrue(core.restore(self.l4d2, log=lambda msg: None))

        restored = self.read_gameinfo()
        self.assertIn("custom\\external", restored)
        self.assertNotIn("mods\\12345", restored)

    def test_restore_does_not_touch_untracked_disabled_vision_file(self):
        correction = os.path.join(self.left4dead2, "materials", "correction")
        os.makedirs(correction, exist_ok=True)
        disabled = os.path.join(correction,
                                core._VISION_FILES[0] + core._VISION_OFF)
        with open(disabled, "wb") as f:
            f.write(b"external")

        self.assertTrue(core.restore(self.l4d2, log=lambda msg: None))

        self.assertTrue(os.path.isfile(disabled))
        self.assertFalse(os.path.exists(
            os.path.join(correction, core._VISION_FILES[0])))

    def test_restore_infected_vision_recovers_disabled_files_without_manifest(self):
        correction = os.path.join(self.left4dead2, "materials", "correction")
        os.makedirs(correction, exist_ok=True)
        for name in core._VISION_FILES:
            with open(os.path.join(correction, name + core._VISION_OFF),
                      "wb") as f:
                f.write(b"disabled")

        self.assertEqual(core.vision_state(self.l4d2), "off")
        self.assertTrue(core.restore_infected_vision(
            self.l4d2, log=lambda msg: None))

        self.assertEqual(core.vision_state(self.l4d2), "on")
        for name in core._VISION_FILES:
            self.assertTrue(os.path.isfile(os.path.join(correction, name)))
            self.assertFalse(os.path.exists(
                os.path.join(correction, name + core._VISION_OFF)))

    def test_restore_changes_nothing_while_game_is_running(self):
        addon = self.write_vpk("12345")
        self.assertTrue(core.enable(self.l4d2, [addon], log=lambda msg: None))
        before = self.read_gameinfo()
        managed_dir = os.path.join(self.l4d2, "mods", "12345")
        core.l4d2_running = lambda: True

        self.assertFalse(core.restore(self.l4d2, log=lambda msg: None))

        self.assertEqual(self.read_gameinfo(), before)
        self.assertTrue(os.path.isdir(managed_dir))

    def test_cleanup_orphans_does_not_delete_unmanaged_folder(self):
        gi = os.path.join(self.left4dead2, "gameinfo.txt")
        with open(gi, "w", encoding="utf-8") as f:
            f.write(GAMEINFO.replace("Game            left4dead2",
                                     "Game            mods\\missing\n"
                                     "            Game            left4dead2"))
        unmanaged = os.path.join(self.l4d2, "mods", "missing")
        os.makedirs(unmanaged, exist_ok=True)

        removed = core.cleanup_orphans(self.l4d2, log=lambda msg: None)

        self.assertEqual(removed, ["missing"])
        self.assertTrue(os.path.isdir(unmanaged))
        self.assertNotIn("mods\\missing", self.read_gameinfo())

    def test_orphan_waits_until_game_closes_before_cleanup(self):
        addon = self.write_vpk("12345")
        self.assertTrue(core.enable(self.l4d2, [addon], log=lambda msg: None))
        os.remove(addon["path"])
        managed_dir = os.path.join(self.l4d2, "mods", "12345")

        core.l4d2_running = lambda: True
        self.assertEqual(core.currently_enabled_orphans(self.l4d2), ["12345"])
        self.assertEqual(core.cleanup_orphans(self.l4d2,
                                              log=lambda msg: None), [])
        self.assertTrue(os.path.isdir(managed_dir))
        self.assertIn("mods\\12345", self.read_gameinfo())

        core.l4d2_running = lambda: False
        self.assertEqual(core.cleanup_orphans(self.l4d2,
                                              log=lambda msg: None), ["12345"])
        self.assertFalse(os.path.isdir(managed_dir))
        self.assertNotIn("mods\\12345", self.read_gameinfo())

    def test_resolve_deps_handles_cycles(self):
        deps = {"a": ["b"], "b": ["c"], "c": ["a"]}
        self.assertEqual(core.resolve_deps(["a"], deps), ["a", "b", "c"])

    def test_preview_cache_downloads_once_and_reuses_atomic_file(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return b"preview-bytes"

        url = "https://example.invalid/preview.jpg?version=1"
        with mock.patch.object(core.urllib.request, "urlopen",
                               return_value=Response()) as urlopen:
            first = core.get_cached_image("12345", url)
            second = core.get_cached_image("12345", url)

        self.assertEqual(first, second)
        self.assertEqual(urlopen.call_count, 1)
        with open(first, "rb") as cached:
            self.assertEqual(cached.read(), b"preview-bytes")
        leftovers = [name for name in os.listdir(os.path.dirname(first))
                     if name.endswith(".tmp")]
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
