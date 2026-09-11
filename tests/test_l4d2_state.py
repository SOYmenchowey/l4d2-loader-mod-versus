import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import l4d2_state


class StateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def cfg_path(self, name):
        return os.path.join(self.tmp.name, name)

    def write_json(self, name, value):
        with open(self.cfg_path(name), "w", encoding="utf-8") as file:
            json.dump(value, file)

    def test_create_initial_state_loads_saved_user_data(self):
        self.write_json("favs.json", ["10", "20"])
        self.write_json("presets.json", {"Mix": ["10"]})
        self.write_json("last_config.json", {"ids": ["20"]})

        with mock.patch.object(l4d2_state.core, "load_deps",
                               return_value={"10": ["20"]}):
            state = l4d2_state.create_initial_state(self.cfg_path)

        self.assertEqual(state["deps"], {"10": ["20"]})
        self.assertEqual(state["favs"], {"10", "20"})
        self.assertEqual(state["presets"], {"Mix": ["10"]})
        self.assertEqual(state["last_config"], {"ids": ["20"]})
        self.assertEqual(state["view"], "mods")
        self.assertFalse(state["_closing"])


if __name__ == "__main__":
    unittest.main()
