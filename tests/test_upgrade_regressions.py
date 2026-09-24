import codecs
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import l4d2_core as core
import l4d2_glows as glows
import l4d2_migrations as migrations
import l4d2_state as state_module
import l4d2_ui as ui


GAMEINFO = b'GameInfo\n{\n FileSystem\n {\n SearchPaths\n {\n Game left4dead2\n }\n }\n}\n'


class UpgradeRegressions(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.game = self.root / 'game'
        self.addons = self.game / 'left4dead2' / 'addons'
        (self.addons / 'workshop').mkdir(parents=True)
        self.gi = self.game / 'left4dead2' / 'gameinfo.txt'
        self.gi.write_bytes(GAMEINFO)
        self.enterContext(patch.dict(os.environ, {'LOCALAPPDATA': str(self.root / 'settings')}))
        self.enterContext(patch.object(core, 'l4d2_running', return_value=False))

    def legacy(self, aid='my_skin', source_name='my_skin.vpk'):
        source = self.addons / source_name
        source.write_bytes(b'original payload')
        managed = self.game / 'mods' / aid
        managed.mkdir(parents=True)
        (managed / 'pak01_dir.vpk').write_bytes(source.read_bytes())
        (managed / core.MANAGED_MARKER).write_text(aid + '\n', encoding='utf-8')
        self.gi.write_bytes(GAMEINFO.replace(b'Game left4dead2',
                           ('Game mods\\' + aid + '\n Game left4dead2').encode()))
        core._save_managed_manifest({core._l4d2_key(str(self.game)): [aid]})
        return source, managed

    def test_legacy_local_keeps_active_identity_and_can_restore(self):
        source, managed = self.legacy()
        before = self.gi.read_bytes()
        self.assertEqual(core.migrate_legacy_addons(str(self.game)), [])
        addons = core.list_addons(str(self.game))
        active = core.currently_enabled(str(self.game))
        self.assertEqual([a['id'] for a in ui.visible_addons(addons, active, set(), view='activos')], ['my_skin'])
        self.assertEqual(self.gi.read_bytes(), before)
        self.assertTrue(core.restore(str(self.game), log=lambda _: None))
        self.assertFalse(managed.exists())
        self.assertTrue(source.exists())
        self.assertEqual(core.list_addons(str(self.game))[0]['id'], 'my_skin')
        self.assertEqual(self.gi.read_bytes(), GAMEINFO)
        self.assertEqual(core.migrate_legacy_addons(str(self.game)), [])

    def test_numeric_workshop_marker_is_upgraded_on_disable(self):
        source, managed = self.legacy('12345', 'workshop/12345.vpk')
        self.assertTrue(core.disable(str(self.game), ['12345'], log=lambda _: None))
        self.assertFalse(managed.exists())
        self.assertTrue(source.exists())

    def test_changed_legacy_payload_is_not_adopted_or_removed(self):
        source, managed = self.legacy()
        (managed / 'pak01_dir.vpk').write_bytes(b'external edit')
        before = self.gi.read_bytes()
        self.assertFalse(core.restore(str(self.game), log=lambda _: None))
        self.assertEqual(self.gi.read_bytes(), before)
        self.assertEqual((managed / 'pak01_dir.vpk').read_bytes(), b'external edit')

    def test_ambiguous_legacy_source_is_not_guessed(self):
        source, managed = self.legacy()
        (self.addons / 'workshop' / source.name).write_bytes(source.read_bytes())
        before = self.gi.read_bytes()
        self.assertEqual(core.migrate_legacy_addons(str(self.game), log=lambda _: None), ['my_skin'])
        self.assertFalse(core.restore(str(self.game), log=lambda _: None))
        self.assertEqual(self.gi.read_bytes(), before)

    def test_failed_identity_write_leaves_legacy_marker_untouched(self):
        _, managed = self.legacy()
        marker = managed / core.MANAGED_MARKER
        with patch.object(migrations, 'atomic_write_text', side_effect=OSError('full disk')):
            with self.assertRaises(OSError):
                core.migrate_legacy_addons(str(self.game))
        self.assertEqual(marker.read_text(), 'my_skin\n')
        self.assertEqual(core.migrate_legacy_addons(str(self.game)), [])

    def test_saved_selections_and_dependencies_resolve_to_persistent_ids(self):
        self.legacy()
        core.migrate_legacy_addons(str(self.game))
        addons = core.list_addons(str(self.game))
        canonical = addons[0]['_canonical_id']
        state = dict(selected_ids={canonical}, favs={'my_skin'}, presets={'one': [canonical]},
                     last_config={'ids': [canonical]}, deps={canonical: ['other']})
        state_module.reconcile_addon_ids(state, addons)
        self.assertEqual(state['selected_ids'], {'my_skin'})
        self.assertEqual(state['favs'], {'my_skin'})
        self.assertEqual(state['presets']['one'], ['my_skin'])
        self.assertEqual(state['last_config']['ids'], ['my_skin'])
        self.assertEqual(state['deps'], {'my_skin': ['other']})

    def test_readonly_source_enables_without_leaving_temps(self):
        source = self.addons / 'workshop' / '12345.vpk'
        source.write_bytes(b'A' * 8192)
        source.chmod(stat.S_IREAD)
        try:
            addon = dict(id='12345', path=str(source), size=8192)
            for _ in range(2):
                self.assertTrue(core.enable(str(self.game), [addon], log=lambda _: None))
            managed = self.game / 'mods' / '12345'
            self.assertEqual(list(managed.glob('pak01.*.tmp')), [])
            self.assertEqual((managed / 'pak01_dir.vpk').read_bytes(), source.read_bytes())
        finally:
            source.chmod(stat.S_IREAD | stat.S_IWRITE)

    def test_failed_readonly_copy_cleans_its_temp(self):
        source = self.root / 'source.vpk'
        source.write_bytes(b'A' * 8192)
        original = core.shutil.copyfile
        def fail(src, dst):
            original(src, dst)
            os.chmod(dst, stat.S_IREAD)
            raise OSError('interrupted')
        with patch.object(core.shutil, 'copyfile', side_effect=fail):
            for _ in range(2):
                with self.assertRaises(OSError):
                    core._verified_copy(str(source), str(self.root / 'pak01_dir.vpk'))
        self.assertEqual(list(self.root.glob('pak01.*.tmp')), [])

    def test_readonly_managed_payload_can_update_and_disable(self):
        source = self.addons / 'workshop' / '12345.vpk'
        source.write_bytes(b'old')
        addon = dict(id='12345', path=str(source), size=3)
        self.assertTrue(core.enable(str(self.game), [addon], log=lambda _: None))
        payload = self.game / 'mods' / '12345' / 'pak01_dir.vpk'
        try:
            payload.chmod(stat.S_IREAD)
            source.write_bytes(b'new')
            self.assertTrue(core.enable(str(self.game), [addon], log=lambda _: None))
            self.assertEqual(payload.read_bytes(), b'new')
            payload.chmod(stat.S_IREAD)
            self.assertTrue(core.disable(str(self.game), ['12345'], log=lambda _: None))
            self.assertFalse(payload.exists())
        finally:
            if payload.exists():
                payload.chmod(stat.S_IREAD | stat.S_IWRITE)

    def test_unverified_readonly_destination_is_preserved(self):
        source, destination = self.root / 'source', self.root / 'destination'
        source.write_bytes(b'new')
        destination.write_bytes(b'external')
        destination.chmod(stat.S_IREAD)
        try:
            with self.assertRaises(OSError):
                core._verified_copy(str(source), str(destination), 'not-the-file-hash')
            self.assertEqual(destination.read_bytes(), b'external')
            self.assertEqual(list(self.root.glob('pak01.*.tmp')), [])
        finally:
            destination.chmod(stat.S_IREAD | stat.S_IWRITE)

    def test_glow_restore_preserves_commands_appended_after_block(self):
        auto = Path(glows.autoexec_path(str(self.game)))
        auto.parent.mkdir()
        for prefix, codec, newline in ((b'', 'utf-8', '\n'), (b'', 'latin-1', '\r\n'),
                                        (codecs.BOM_UTF16_LE, 'utf-16-le', '\r\n')):
            with self.subTest(codec=codec):
                auto.write_bytes(prefix + 'echo before'.encode(codec))
                self.assertTrue(glows.apply_glows(str(self.game), glows.default_colors(), log=lambda _: None))
                auto.write_bytes(auto.read_bytes() + ('echo after' + newline).encode(codec))
                self.assertTrue(glows.restore_glows(str(self.game), log=lambda _: None))
                result = auto.read_bytes()[len(prefix):].decode(codec)
                self.assertEqual(result.splitlines(), ['echo before', 'echo after'])

    def test_reapply_does_not_join_external_commands(self):
        text = glows._with_managed_block('echo before') + 'echo after\n'
        result = glows._remove_managed_block(glows._with_managed_block(text))
        self.assertEqual(result, 'echo before\necho after\n')


if __name__ == '__main__':
    unittest.main()
