"""Independent review regressions; all files and game paths are temporary."""

import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import l4d2_core as core
import l4d2_locking as locking


GAMEINFO = (b'GameInfo\r\n{\r\n FileSystem\r\n {\r\n  SearchPaths\r\n'
            b'  {\r\n   Game left4dead2\r\n  }\r\n }\r\n}\r\n')


def _manifest_writer(game, addon_id, start, results):
    managed_load = core._load_managed_manifest
    restore_load = core._load_restore_manifest

    def delayed(load):
        def read():
            data = load()
            time.sleep(0.1)
            return data
        return read

    core._load_managed_manifest = delayed(managed_load)
    core._load_restore_manifest = delayed(restore_load)
    if not start.wait(5):
        results.put('start timeout')
        return
    try:
        registered = core._register_managed(game, [addon_id])
        saved = core._save_restore_state(game, {'review_token': addon_id})
        results.put((registered, saved))
    except Exception as ex:
        results.put(repr(ex))


class CoreReviewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        patch = mock.patch.dict(os.environ, {'LOCALAPPDATA': str(self.root / 'settings')})
        patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch.object(core, 'l4d2_running', return_value=False)
        patch.start()
        self.addCleanup(patch.stop)
        self.game = self.make_game('first')
        self.gi = self.game / 'left4dead2' / 'gameinfo.txt'
        self.logs = []

    def make_game(self, name):
        game = self.root / name
        (game / 'left4dead2' / 'addons' / 'workshop').mkdir(parents=True)
        (game / 'left4dead2' / 'gameinfo.txt').write_bytes(GAMEINFO)
        return game

    def addon(self, aid='123456', game=None):
        game = game or self.game
        source = game / 'left4dead2' / 'addons' / 'workshop' / (aid + '.vpk')
        source.write_bytes(b'original source VPK ' + aid.encode())
        return {'id': aid, 'path': str(source), 'size': source.stat().st_size}

    def enable(self, addon):
        return core.enable(str(self.game), [addon], log=self.logs.append)

    def restore_or_reject(self):
        try:
            return core.restore(str(self.game), log=self.logs.append)
        except OSError:
            return False

    def test_missing_marker_cannot_finish_restore_and_discard_recovery(self):
        addon = self.addon()
        self.assertTrue(self.enable(addon))
        marker = self.game / 'mods' / addon['id'] / core.MANAGED_MARKER
        marker.unlink()
        backup = Path(core._gameinfo_backup_path(str(self.game)))
        self.assertTrue(backup.exists())
        result = self.restore_or_reject()
        remaining = core.currently_enabled(str(self.game))
        recovery_kept = (backup.exists() and
                         bool(core._restore_state(str(self.game)).get('gameinfo_sha256')))
        self.assertFalse(result and bool(remaining), (result, remaining, recovery_kept))
        if remaining:
            self.assertTrue(recovery_kept)

    def test_legacy_manifest_only_cannot_report_restore_success_while_still_active(self):
        addon = self.addon()
        managed = self.game / 'mods' / addon['id']
        managed.mkdir(parents=True)
        (managed / 'pak01_dir.vpk').write_bytes(Path(addon['path']).read_bytes())
        self.gi.write_bytes(GAMEINFO.replace(b'Game left4dead2',
                            b'Game mods\\123456\r\n   Game left4dead2'))
        Path(core.backup_path(str(self.game))).write_bytes(GAMEINFO)
        self.assertTrue(core._save_managed_manifest({core._l4d2_key(str(self.game)): [addon['id']]}))
        result = self.restore_or_reject()
        self.assertFalse(result and addon['id'] in core.currently_enabled(str(self.game)),
                         'Restore reported success but left the legacy loader entry active')

    def test_legacy_disable_does_not_strand_an_unrecognizable_loader_copy(self):
        addon = self.addon()
        managed = self.game / 'mods' / addon['id']
        managed.mkdir(parents=True)
        payload = managed / 'pak01_dir.vpk'
        payload.write_bytes(Path(addon['path']).read_bytes())
        (managed / core.MANAGED_MARKER).write_text(addon['id'] + '\n', encoding='utf-8')
        self.gi.write_bytes(GAMEINFO.replace(b'Game left4dead2',
                            b'Game mods\\123456\r\n   Game left4dead2'))
        self.assertTrue(core._save_managed_manifest({core._l4d2_key(str(self.game)): [addon['id']]}))
        try:
            result = core.disable(str(self.game), [addon['id']], log=self.logs.append)
        except OSError:
            result = False
        if result:
            self.assertTrue(self.enable(addon),
                            'Successful legacy disable removed ownership but left a blocking VPK')
        else:
            self.assertTrue(payload.exists())
            self.assertTrue((managed / core.MANAGED_MARKER).exists())

    def test_disable_keeps_payload_referenced_by_external_untagged_entry(self):
        addon = self.addon()
        self.assertTrue(self.enable(addon))
        external = b'   Game mods\\123456 // externally maintained reference\r\n'
        with self.gi.open('ab') as file:
            file.write(external)
        try:
            core.disable(str(self.game), [addon['id']], log=self.logs.append)
        except OSError:
            pass
        self.assertIn(external, self.gi.read_bytes())
        payload = self.game / 'mods' / addon['id'] / 'pak01_dir.vpk'
        self.assertTrue(payload.exists(), 'External gameinfo entry now points to a deleted VPK')

    def test_partial_vision_restore_preserves_pending_record_and_reports_failure(self):
        addon = self.addon()
        self.assertTrue(self.enable(addon))
        directory = Path(core._vision_dir(str(self.game)))
        directory.mkdir(parents=True)
        for name in core._VISION_FILES:
            (directory / name).write_bytes(('original ' + name).encode())
        self.assertTrue(core.disable_infected_vision(str(self.game), log=self.logs.append))
        failed_name = core._VISION_FILES[-1]
        blocked = directory / (failed_name + core._VISION_OFF)
        real_rename = os.rename

        def partial(source, destination):
            if os.fspath(source) == str(blocked):
                raise PermissionError('fixture: one vision file is locked')
            return real_rename(source, destination)

        with mock.patch.object(core.os, 'rename', side_effect=partial):
            result = core.restore(str(self.game), log=self.logs.append)
        pending = core._restore_state(str(self.game)).get('vision_files', [])
        self.assertTrue(blocked.exists())
        self.assertEqual((result, failed_name in pending), (False, True))

    def test_partial_cleanup_retries_payload_after_gameinfo_entry_was_removed(self):
        removed_addon = self.addon('123456')
        blocked_addon = self.addon('234567')
        self.assertTrue(core.enable(str(self.game), [removed_addon, blocked_addon],
                                   log=self.logs.append))
        for addon in (removed_addon, blocked_addon):
            Path(addon['path']).unlink()
        pending_dir = self.game / 'mods' / blocked_addon['id']
        payload = pending_dir / 'pak01_dir.vpk'
        original = payload.read_bytes()
        real_remove = os.remove

        def partial(path):
            if os.fspath(path) == str(payload):
                raise PermissionError('fixture: VPK is locked')
            return real_remove(path)

        with mock.patch.object(core.os, 'remove', side_effect=partial):
            removed = core.cleanup_orphans(str(self.game), log=self.logs.append)
        self.assertEqual(removed, [removed_addon['id']])
        self.assertEqual(core.currently_enabled(str(self.game)), [])
        self.assertEqual(payload.read_bytes(), original)
        self.assertTrue((pending_dir / core.MANAGED_MARKER).exists())
        self.assertIn(blocked_addon['id'], core._managed_records(str(self.game)))

        self.assertEqual(core.cleanup_orphans(str(self.game), log=self.logs.append),
                         [blocked_addon['id']])
        self.assertFalse(pending_dir.exists())
        self.assertEqual(core._managed_records(str(self.game)), {})

    def test_cleanup_retries_after_empty_directory_removal_failure(self):
        addon = self.addon()
        self.assertTrue(self.enable(addon))
        Path(addon['path']).unlink()
        pending_dir = self.game / 'mods' / addon['id']
        real_rmdir = os.rmdir

        def partial(path, *args, **kwargs):
            if os.fspath(path) == str(pending_dir):
                raise PermissionError('fixture: directory is locked')
            return real_rmdir(path, *args, **kwargs)

        with mock.patch.object(core.os, 'rmdir', side_effect=partial):
            self.assertEqual(core.cleanup_orphans(str(self.game), log=self.logs.append), [])
        self.assertEqual(core.currently_enabled(str(self.game)), [])
        self.assertTrue(pending_dir.exists())
        self.assertIn(addon['id'], core._managed_records(str(self.game)))

        self.assertEqual(core.cleanup_orphans(str(self.game), log=self.logs.append),
                         [addon['id']])
        self.assertFalse(pending_dir.exists())
        self.assertEqual(core._managed_records(str(self.game)), {})

    def test_unmanaged_regular_file_in_mods_does_not_block_restore(self):
        addon = self.addon()
        self.assertTrue(self.enable(addon))
        readme = self.game / 'mods' / 'README.txt'
        readme.write_bytes(b'user notes')
        self.assertTrue(core.restore(str(self.game), log=self.logs.append))
        self.assertEqual(readme.read_bytes(), b'user notes')
        self.assertEqual(core.currently_enabled(str(self.game)), [])

    def test_mods_junction_is_rejected_without_changing_target(self):
        external = self.root / 'external'
        external.mkdir()
        sentinel = external / 'sentinel.txt'
        sentinel.write_bytes(b'foreign data')
        junction = self.game / 'mods'
        if os.name == 'nt':
            import _winapi
            _winapi.CreateJunction(str(external), str(junction))
        else:
            junction.symlink_to(external, target_is_directory=True)
        self.addCleanup(lambda: os.rmdir(junction) if os.name == 'nt' else junction.unlink())
        addon = self.addon()
        try:
            result = self.enable(addon)
        except OSError:
            result = False
        self.assertFalse(result)
        self.assertEqual(self.gi.read_bytes(), GAMEINFO)
        self.assertEqual(sentinel.read_bytes(), b'foreign data')
        self.assertEqual(sorted(p.name for p in external.iterdir()), ['sentinel.txt'])

    def test_different_installations_keep_both_shared_manifest_entries(self):
        other = self.make_game('second')
        games = [(self.game, '123456'), (other, '234567')]
        for game, aid in games:
            managed = game / 'mods' / aid
            managed.mkdir(parents=True)
            (managed / core.MANAGED_MARKER).write_text(aid + '\n', encoding='utf-8')
        context = multiprocessing.get_context('spawn')
        start, results = context.Event(), context.Queue()
        workers = [context.Process(target=_manifest_writer,
                   args=(str(game), aid, start, results)) for game, aid in games]
        try:
            for worker in workers:
                worker.start()
            start.set()
            for worker in workers:
                worker.join(8)
                self.assertFalse(worker.is_alive())
                self.assertEqual(worker.exitcode, 0)
            self.assertEqual([results.get(timeout=2) for _ in workers], [(True, True)] * 2)
            managed = core._load_managed_manifest()
            restored = core._load_restore_manifest()['games']
            for game, aid in games:
                self.assertIn(aid, managed[core._l4d2_key(str(game))])
                self.assertEqual(restored[core._l4d2_key(str(game))]['review_token'], aid)
        finally:
            for worker in workers:
                if worker.is_alive():
                    worker.terminate()
                    worker.join()
            results.close()

    def test_reentrant_lock_releases_after_inner_exception(self):
        with self.assertRaisesRegex(RuntimeError, 'fixture'):
            with locking.installation_lock(str(self.game), timeout=0.2):
                with locking.installation_lock(str(self.game), timeout=0.2):
                    raise RuntimeError('fixture')
        with locking.installation_lock(str(self.game), timeout=0.2):
            pass


if __name__ == '__main__':
    unittest.main()
