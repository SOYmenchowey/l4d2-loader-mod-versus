import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import l4d2_clipboard as clipboard


class FakeClipboard:
    def __init__(self):
        self.value = None

    def set(self, value):
        self.value = value


class FakePage:
    def __init__(self):
        self.clipboard = FakeClipboard()


class ClipboardTests(unittest.TestCase):
    def test_copy_text_to_clipboard_uses_flet_clipboard_api_when_requested(self):
        page = FakePage()
        self.assertTrue(clipboard.copy_text_to_clipboard(
            page, "diagnostico", prefer_native=False))
        self.assertEqual(page.clipboard.value, "diagnostico")

    def test_copy_text_to_clipboard_prefers_native_clipboard(self):
        page = FakePage()
        with mock.patch.object(
                clipboard, "_copy_text_with_windows_clipboard",
                return_value=True) as native:
            self.assertTrue(clipboard.copy_text_to_clipboard(
                page, "diagnostico"))
        native.assert_called_once_with("diagnostico", log=None)
        self.assertIsNone(page.clipboard.value)

    def test_copy_text_to_clipboard_falls_back_when_native_fails(self):
        page = FakePage()
        with mock.patch.object(clipboard, "_copy_text_with_windows_clipboard",
                               return_value=False), \
                mock.patch.object(clipboard, "_copy_text_with_powershell",
                                  return_value=False), \
                mock.patch.object(clipboard, "_copy_text_with_clip_exe",
                                  return_value=False):
            self.assertTrue(clipboard.copy_text_to_clipboard(
                page, "diagnostico"))
        self.assertEqual(page.clipboard.value, "diagnostico")


if __name__ == "__main__":
    unittest.main()
