import os
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch

import flet_desktop


HOOK = Path(__file__).resolve().parents[1] / 'packaging_hooks' / 'pyi_rth_flet_desktop.py'


class PackagedRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.desktop = self.root / 'flet_desktop' / 'app' / 'flet'
        for name in ('flet.exe', 'flutter_windows.dll', 'data/app.so', 'data/icudtl.dat'):
            file = self.desktop / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.touch()

    def run_hook(self):
        with patch.object(sys, 'frozen', True, create=True), \
                patch.object(sys, '_MEIPASS', str(self.root), create=True), \
                patch.object(sys, 'platform', 'win32'):
            runpy.run_path(str(HOOK))

    def test_clean_profile_uses_bundled_client_without_network(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(Path, 'home', return_value=self.root / 'empty-profile'), \
                patch('os.getcwd', return_value=str(self.root)), \
                patch('urllib.request.urlopen', side_effect=AssertionError('Network forbidden')) as network, \
                patch.object(flet_desktop, 'is_windows', return_value=True):
            self.run_hook()
            locate = getattr(flet_desktop, '__locate_and_unpack_flet_view')
            args, env, _ = locate('tcp://127.0.0.1:12345', None, False)
            self.assertEqual(args[0], str(self.desktop / 'flet.exe'))
            self.assertEqual(env['FLET_VIEW_PATH'], str(self.desktop))
            network.assert_not_called()
            self.assertFalse((self.root / 'empty-profile').exists())

    def test_packaged_client_does_not_use_external_override(self):
        with patch.dict(os.environ, {'FLET_VIEW_PATH': 'unrelated-runtime'}):
            self.run_hook()
            self.assertEqual(os.environ['FLET_VIEW_PATH'], str(self.desktop))

    def test_incomplete_bundle_fails_instead_of_downloading(self):
        (self.desktop / 'flutter_windows.dll').unlink()
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'flutter_windows.dll'):
                self.run_hook()
            self.assertNotIn('FLET_VIEW_PATH', os.environ)

    def test_source_execution_is_unchanged(self):
        with patch.object(sys, 'frozen', False, create=True), \
                patch.dict(os.environ, {'FLET_VIEW_PATH': 'developer-runtime'}):
            runpy.run_path(str(HOOK))
            self.assertEqual(os.environ['FLET_VIEW_PATH'], 'developer-runtime')


if __name__ == '__main__':
    unittest.main()
