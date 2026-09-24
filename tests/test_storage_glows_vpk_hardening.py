import builtins
import codecs
import os
from pathlib import Path
import struct
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import l4d2_glows as glows
import l4d2_storage as storage
import l4d2_vpk as vpk


class TemporaryFiles(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        environment = mock.patch.dict(os.environ, {
            "LOCALAPPDATA": str(self.root / "settings")})
        environment.start()
        self.addCleanup(environment.stop)
        self.game = str(self.root / "game")
        self.autoexec = Path(glows.autoexec_path(self.game))
        self.cfg = Path(glows.cfg_path(self.game))
        self.cfg.parent.mkdir(parents=True)
        self.messages = []

    def apply(self, colors=None):
        return glows.apply_glows(self.game, colors or glows.default_colors(),
                                 log=self.messages.append)

    def restore(self):
        return glows.restore_glows(self.game, log=self.messages.append)


class StorageHardeningTests(TemporaryFiles):
    def test_json_serialization_failure_preserves_existing_bytes(self):
        path = self.root / "state.json"
        before = b'{"previous": true}\r\n'
        path.write_bytes(before)
        self.assertFalse(storage.save_json(path, {"bad": object()}))
        self.assertEqual(path.read_bytes(), before)

    def test_json_replace_failure_reports_failure_and_preserves_previous(self):
        path = self.root / "state.json"
        path.write_bytes(b'{"previous": true}')
        with mock.patch.object(storage.os, "replace", side_effect=PermissionError("denied")):
            result = storage.save_json(path, {"next": True})
        self.assertFalse(result)
        self.assertEqual(path.read_bytes(), b'{"previous": true}')
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_json_creates_parent_and_returns_true_only_after_save(self):
        path = self.root / "new" / "state.json"
        self.assertTrue(storage.save_json(path, {"name": "caf\u00e9"}))
        self.assertEqual(storage.load_json(path, None), {"name": "caf\u00e9"})

    def test_denied_config_directory_allows_defaults_but_not_save(self):
        with mock.patch.object(storage.os, "makedirs", side_effect=PermissionError("denied")):
            self.assertEqual(storage.app_dir(), str(self.root / "settings" / "L4D2ModLoader"))
            self.assertEqual(glows.load_colors(), glows.default_colors())
            self.assertFalse(glows.save_colors(glows.default_colors()))


class GlowHardeningTests(TemporaryFiles):
    def test_managed_exec_follows_external_commands(self):
        before = b'cl_glow_item_r "0.1"\r\ncl_glow_item_g "0.2"'
        self.autoexec.write_bytes(before)
        self.assertTrue(self.apply())
        applied = self.autoexec.read_bytes()
        self.assertTrue(applied.startswith(before))
        self.assertGreater(applied.index(b'exec l4d2_mod_loader_glows'),
                           applied.index(b'cl_glow_item_g'))
        self.assertTrue(self.restore())
        self.assertEqual(self.autoexec.read_bytes(), before)

    def test_apply_restore_preserve_external_bytes_encodings_and_newlines(self):
        samples = [
            b' \t// caf\xe9 \xff\x81\r\nbind x "say hola"\r\n\r\n',
            b'\n\n// UTF-8 caf\xc3\xa9\n\tbind x "a"  ',
            b'// classic\rbind x "a"\r',
            b'',
            codecs.BOM_UTF8 + b'// utf8\r\nlast',
            codecs.BOM_UTF16_LE + '// wide\r\nlast'.encode('utf-16-le'),
            codecs.BOM_UTF16_BE + '// wide\nlast'.encode('utf-16-be'),
            codecs.BOM_UTF32_LE + '// wide\r\nlast'.encode('utf-32-le'),
            codecs.BOM_UTF32_BE + '// wide\nlast'.encode('utf-32-be'),
        ]
        for original in samples:
            with self.subTest(original=original):
                self.autoexec.write_bytes(original)
                self.assertTrue(self.apply())
                applied = self.autoexec.read_bytes()
                self.assertTrue(self.apply())
                self.assertEqual(self.autoexec.read_bytes(), applied)
                self.assertTrue(glows.is_applied(self.game))
                self.assertTrue(self.restore())
                self.assertEqual(self.autoexec.read_bytes(), original)

    def test_restore_unmanaged_text_is_a_byte_exact_noop(self):
        before = b' \r\n// caf\xe9\r\nbind x "a"  '
        self.autoexec.write_bytes(before)
        self.assertTrue(self.restore())
        self.assertEqual(self.autoexec.read_bytes(), before)

    def test_marker_inside_external_quoted_line_is_not_removed(self):
        before = ('echo "' + glows.AUTOEXEC_BEGIN + ' keep ' +
                  glows.AUTOEXEC_END + '"\r\n').encode()
        self.autoexec.write_bytes(before)
        self.assertTrue(self.restore())
        self.assertEqual(self.autoexec.read_bytes(), before)

    def test_read_failure_aborts_apply_and_restore_before_any_game_change(self):
        self.autoexec.write_bytes(b'// original\r\n')
        self.cfg.write_bytes(b'// old cfg\r\n')
        real_open = builtins.open

        def denied(path, mode="r", *args, **kwargs):
            if os.fspath(path) == str(self.autoexec) and "r" in mode:
                raise PermissionError("autoexec read denied")
            return real_open(path, mode, *args, **kwargs)

        for operation in (self.apply, self.restore):
            with self.subTest(operation=operation.__name__):
                with mock.patch("builtins.open", side_effect=denied):
                    result = operation()
                self.assertFalse(result)
                self.assertEqual(self.autoexec.read_bytes(), b'// original\r\n')
                self.assertEqual(self.cfg.read_bytes(), b'// old cfg\r\n')

    def test_invalid_color_is_reported_without_escaping(self):
        colors = glows.default_colors()
        colors["ability"] = "bad color"
        self.assertFalse(self.apply(colors))
        self.assertFalse(self.cfg.exists())

    def test_state_save_failure_rolls_back_apply_and_restore(self):
        self.autoexec.write_bytes(b'// original\r\n')
        self.cfg.write_bytes(b'// old cfg\r\n')
        with mock.patch.object(glows, "save_colors", return_value=False):
            result = self.apply()
        self.assertFalse(result)
        self.assertEqual(self.autoexec.read_bytes(), b'// original\r\n')
        self.assertEqual(self.cfg.read_bytes(), b'// old cfg\r\n')
        self.assertTrue(self.apply())
        applied = self.autoexec.read_bytes(), self.cfg.read_bytes()
        with mock.patch.object(glows, "save_colors", return_value=False):
            result = self.restore()
        self.assertFalse(result)
        self.assertEqual((self.autoexec.read_bytes(), self.cfg.read_bytes()), applied)

    def test_restore_state_save_failure_is_reported_and_recoverable(self):
        self.autoexec.write_bytes(b'// original\r\n')
        self.assertTrue(self.apply())
        before = self.autoexec.read_bytes(), self.cfg.read_bytes()
        with mock.patch.object(glows, "save_colors", return_value=False):
            result = self.restore()
        self.assertFalse(result)
        self.assertEqual((self.autoexec.read_bytes(), self.cfg.read_bytes()), before)
        self.assertTrue(self.restore())
        self.assertEqual(self.autoexec.read_bytes(), b'// original\r\n')

    def test_failed_apply_leaves_no_new_game_files(self):
        with mock.patch.object(glows, "save_colors", return_value=False):
            self.assertFalse(self.apply())
        self.assertFalse(self.autoexec.exists())
        self.assertFalse(self.cfg.exists())

    def test_failed_rollback_keeps_exact_recovery_copy_and_reports_path(self):
        self.autoexec.write_bytes(b'// original\r\n')
        self.cfg.write_bytes(b'// previous cfg')
        real_replace = os.replace

        def denied(source, destination):
            if (os.fspath(destination) == str(self.autoexec) or
                    (os.fspath(destination) == str(self.cfg) and
                     '.recovery-' in os.fspath(source))):
                raise PermissionError("replace denied")
            return real_replace(source, destination)

        with mock.patch.object(storage.os, "replace", side_effect=denied):
            self.assertFalse(self.apply())
        backups = list(self.cfg.parent.glob('*.recovery-*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), b'// previous cfg')
        self.assertTrue(any(str(backups[0]) in message for message in self.messages))

    def test_autoexec_write_failure_rolls_back_existing_cfg(self):
        self.autoexec.write_bytes(b'// original\r\n')
        self.cfg.write_bytes(b'// previous cfg')
        real_replace = os.replace

        def denied(source, destination):
            if os.fspath(destination) == str(self.autoexec):
                raise PermissionError("autoexec replace denied")
            return real_replace(source, destination)

        with mock.patch.object(storage.os, "replace", side_effect=denied):
            self.assertFalse(self.apply())
        self.assertEqual(self.cfg.read_bytes(), b'// previous cfg')
        self.assertEqual(self.autoexec.read_bytes(), b'// original\r\n')

    def test_cfg_delete_failure_rolls_back_autoexec(self):
        self.autoexec.write_bytes(b'// original\r\n')
        self.assertTrue(self.apply())
        before = self.autoexec.read_bytes()
        real_remove = os.remove

        def denied(path):
            if os.fspath(path) == str(self.cfg):
                raise PermissionError("cfg delete denied")
            return real_remove(path)

        with mock.patch.object(glows.os, "remove", side_effect=denied):
            self.assertFalse(self.restore())
        self.assertEqual(self.autoexec.read_bytes(), before)
        self.assertTrue(self.cfg.exists())

    def test_incomplete_managed_marker_aborts_without_changes(self):
        before = (glows.AUTOEXEC_BEGIN + '\n// user text\n').encode()
        self.autoexec.write_bytes(before)
        for operation in (self.apply, self.restore):
            with self.subTest(operation=operation.__name__):
                self.assertFalse(operation())
                self.assertEqual(self.autoexec.read_bytes(), before)
                self.assertFalse(self.cfg.exists())

    def test_restore_preserves_external_edits_after_managed_block(self):
        before = b'// caf\xe9\r\n'
        added = b'\r\nbind x "say nuevo"  '
        self.autoexec.write_bytes(before)
        self.assertTrue(self.apply())
        with self.autoexec.open('ab') as file:
            file.write(added)
        self.assertTrue(self.restore())
        self.assertEqual(self.autoexec.read_bytes(), before + added)

    def test_invalid_bom_encoding_aborts_without_changes(self):
        before = codecs.BOM_UTF16_LE + b'\x00'
        self.autoexec.write_bytes(before)
        for operation in (self.apply, self.restore):
            self.assertFalse(operation())
            self.assertEqual(self.autoexec.read_bytes(), before)
            self.assertFalse(self.cfg.exists())

    def test_same_installation_mutations_wait_and_lock_is_reentrant(self):
        from l4d2_locking import installation_lock

        self.autoexec.write_bytes(b'// original\r\n')
        first_saving = threading.Event()
        finish_first = threading.Event()
        second_started = threading.Event()
        second_reading = threading.Event()
        results = []
        errors = []
        real_save = glows.save_colors
        real_read = glows._read_optional_bytes

        def save(*args, **kwargs):
            if threading.current_thread().name == 'apply-test':
                first_saving.set()
                if not finish_first.wait(3):
                    raise TimeoutError('test did not release apply')
            return real_save(*args, **kwargs)

        def read(path):
            if threading.current_thread().name == 'restore-test':
                second_reading.set()
            return real_read(path)

        def run(operation, started=None):
            try:
                if started:
                    started.set()
                results.append(operation())
            except Exception as ex:
                errors.append(ex)

        with mock.patch.object(glows, 'save_colors', side_effect=save), \
                mock.patch.object(glows, '_read_optional_bytes', side_effect=read):
            first = threading.Thread(target=run, args=(self.apply,), name='apply-test')
            second = threading.Thread(target=run, args=(self.restore, second_started),
                                      name='restore-test')
            first.start()
            try:
                self.assertTrue(first_saving.wait(3))
                second.start()
                self.assertTrue(second_started.wait(3))
                self.assertFalse(second_reading.wait(0.15))
            finally:
                finish_first.set()
                first.join(4)
                if second.ident is not None:
                    second.join(4)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(results, [True, True])
        self.assertTrue(second_reading.is_set())
        self.assertEqual(self.autoexec.read_bytes(), b'// original\r\n')
        self.assertFalse(self.cfg.exists())
        with installation_lock(self.game):
            self.assertTrue(self.apply())
            self.assertTrue(self.restore())

    def test_lock_failure_does_not_allow_mutation(self):
        self.autoexec.write_bytes(b'// original\r\n')
        self.cfg.write_bytes(b'// previous cfg')
        with mock.patch.object(glows, 'installation_lock',
                               side_effect=TimeoutError('busy')):
            self.assertFalse(self.apply())
            self.assertFalse(self.restore())
        self.assertEqual(self.autoexec.read_bytes(), b'// original\r\n')
        self.assertEqual(self.cfg.read_bytes(), b'// previous cfg')


def vpk_tree(content=b'', preload=b'', length=None, offset=0, archive=0x7fff,
             terminator=0xffff, extension=b'txt', directory=b' ', name=b'addoninfo'):
    entry = struct.pack('<IHHIIH', 0, len(preload), archive, offset,
                        len(content) if length is None else length, terminator)
    return (extension + b'\0' + directory + b'\0' + name + b'\0' + entry +
            preload + b'\0\0\0')


class VpkHardeningTests(TemporaryFiles):
    def write_vpk(self, tree, content=b'', version=1, sections=None):
        path = self.root / 'addon.vpk'
        header = struct.pack('<III', 0x55AA1234, version, len(tree))
        if version == 2:
            header += struct.pack('<IIII', *(sections or (len(content), 0, 0, 0)))
        path.write_bytes(header + tree + content)
        return path

    def test_valid_v1_v2_and_preload_titles(self):
        for version in (1, 2):
            for preload in (b'', b'"addontitle" ', b'"addontitle" "Preloaded"'):
                with self.subTest(version=version, preload=preload):
                    content = b'"addontitle" "Fixture"' if not preload else (
                        b'"Fixture"' if preload.endswith(b' ') else b'')
                    path = self.write_vpk(vpk_tree(content, preload), content, version)
                    self.assertEqual(vpk.get_addon_title(path),
                                     'Preloaded' if not content else 'Fixture')

    def test_truncated_tree_and_unsupported_version_rejected(self):
        path = self.root / 'addon.vpk'
        for version, size, data in ((1, 100, b'x'), (99, 1, b'\0')):
            with self.subTest(version=version):
                path.write_bytes(struct.pack('<III', 0x55AA1234, version, size) + data)
                self.assertEqual(vpk._read_vpk_tree(path), (None, None))

    def test_untrusted_sizes_never_reach_large_read_or_seek(self):
        requests = []
        real_open = builtins.open

        class GuardedFile:
            def __init__(self, file):
                self.file = file

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return self.file.__exit__(*args)

            def __getattr__(self, name):
                return getattr(self.file, name)

            def read(self, size=-1):
                requests.append(('read', size))
                if size < 0 or size > 16 * 1024 * 1024:
                    raise OSError('guard prevented oversized allocation')
                return self.file.read(size)

            def seek(self, offset, whence=0):
                requests.append(('seek', offset))
                if offset > 16 * 1024 * 1024:
                    raise OSError('guard prevented oversized seek')
                return self.file.seek(offset, whence)

        def guarded(*args, **kwargs):
            return GuardedFile(real_open(*args, **kwargs))

        path = self.root / 'addon.vpk'
        fixtures = [struct.pack('<III', 0x55AA1234, 1, 0xffffffff)]
        for length, offset in ((0xffffffff, 0), (1, 0xffffffff)):
            tree = vpk_tree(length=length, offset=offset)
            fixtures.append(struct.pack('<III', 0x55AA1234, 1, len(tree)) + tree)
        for fixture in fixtures:
            with self.subTest(fixture=fixture):
                path.write_bytes(fixture)
                requests.clear()
                with mock.patch('builtins.open', side_effect=guarded):
                    vpk.inspect_vpk(path)
                self.assertTrue(all(0 <= size <= 16 * 1024 * 1024
                                    for _, size in requests), requests)

    def test_invalid_entries_do_not_yield_titles(self):
        content = b'"addontitle" "Must not be accepted"'
        cases = [
            vpk_tree(content, terminator=0),
            vpk_tree(content, archive=0),
            vpk_tree(content, length=len(content) + 20),
            vpk_tree(content, directory=b'not-root'),
            vpk_tree(content, extension=b'bin'),
            vpk_tree(content)[:-1],
        ]
        for tree in cases:
            with self.subTest(tree=tree):
                self.assertIsNone(vpk.get_addon_title(self.write_vpk(tree, content)))

    def test_v2_sections_must_fit_file_and_cannot_be_read_as_entry_data(self):
        content = b'"addontitle" "Not file data"'
        tree = vpk_tree(content)
        path = self.write_vpk(tree, content, 2, (0, len(content), 0, 0))
        self.assertIsNone(vpk.get_addon_title(path))
        path = self.write_vpk(tree, content, 2, (0xffffffff, 0, 0, 0))
        self.assertEqual(vpk._read_vpk_tree(path), (None, None))

    def test_nut_first_extension_and_preload_false_positive(self):
        path = self.write_vpk(vpk_tree(extension=b'nut', directory=b'scripts', name=b'logic'))
        self.assertTrue(vpk.inspect_vpk(path)['is_vscript'])
        path = self.write_vpk(vpk_tree(preload=b'not actually vscripts'))
        self.assertFalse(vpk.inspect_vpk(path)['is_vscript'])

    def test_inspection_limits_apply_even_when_declared_sizes_fit_file(self):
        content = b'"addontitle" "Oversized"' + b' ' * 128
        path = self.write_vpk(vpk_tree(content), content)
        with mock.patch.object(vpk, 'MAX_ADDONINFO_BYTES', 64):
            self.assertIsNone(vpk.get_addon_title(path))
        with mock.patch.object(vpk, 'MAX_TREE_BYTES', 16):
            self.assertEqual(vpk._read_vpk_tree(path), (None, None))
        with mock.patch.object(vpk, 'MAX_NAME_BYTES', 4):
            self.assertEqual(vpk._read_vpk_tree(path), (None, None))
        with mock.patch.object(vpk, 'MAX_TREE_ENTRIES', 0):
            self.assertEqual(vpk._read_vpk_tree(path), (None, None))

    def test_truncated_preload_and_every_partial_header_are_rejected(self):
        tree = vpk_tree(preload=b'"addontitle" "Preloaded"')
        path = self.write_vpk(tree)
        complete = path.read_bytes()
        for size in range(len(complete)):
            with self.subTest(size=size):
                path.write_bytes(complete[:size])
                self.assertEqual(vpk.inspect_vpk(path),
                                 {'title': None, 'is_vscript': False})


if __name__ == '__main__':
    unittest.main()
