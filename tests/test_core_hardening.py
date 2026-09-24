import multiprocessing
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

import l4d2_core as core


GAMEINFO = b'GameInfo\r\n{\r\n FileSystem\r\n {\r\n  SearchPaths\r\n  {\r\n   Game left4dead2\r\n  }\r\n }\r\n}\r\n'


def _enable_worker(game, addon, start, results):
    core.l4d2_running = lambda: False
    original = core._ensure_gameinfo_backup

    def delayed(*args, **kwargs):
        time.sleep(0.25)
        return original(*args, **kwargs)

    core._ensure_gameinfo_backup = delayed
    start.wait(10)
    try:
        results.put(core.enable(game, [addon], log=lambda _: None))
    except Exception as exc:
        results.put(repr(exc))


class CoreHardeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.game = Path(self.tmp.name) / 'game'
        self.workshop = self.game / 'left4dead2' / 'addons' / 'workshop'
        self.workshop.mkdir(parents=True)
        self.gi = self.game / 'left4dead2' / 'gameinfo.txt'
        self.gi.write_bytes(GAMEINFO)
        patch = mock.patch.dict(os.environ, {'LOCALAPPDATA': str(Path(self.tmp.name) / 'config')})
        patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch.object(core, 'l4d2_running', return_value=False)
        patch.start()
        self.addCleanup(patch.stop)

    def addon(self, aid='123456', local=False):
        source = (self.workshop.parent if local else self.workshop) / (aid + '.vpk')
        source.write_bytes(b'complete VPK payload' * 300)
        return {'id': aid, 'path': str(source), 'size': source.stat().st_size}

    def enable(self, addon):
        return core.enable(str(self.game), [addon], log=lambda _: None)

    def test_foreign_destination_is_never_adopted_or_erased(self):
        addon = self.addon()
        target = self.game / 'mods' / addon['id']
        target.mkdir(parents=True)
        foreign = target / 'notes.txt'
        foreign.write_bytes(b'user data')
        self.assertFalse(self.enable(addon))
        self.assertEqual(self.gi.read_bytes(), GAMEINFO)
        self.assertFalse((target / core.MANAGED_MARKER).exists())
        self.assertTrue(core.restore(str(self.game), log=lambda _: None))
        self.assertEqual(foreign.read_bytes(), b'user data')

    def test_truncated_managed_vpk_is_repaired_before_reenable(self):
        addon = self.addon()
        self.assertTrue(self.enable(addon))
        self.gi.write_bytes(GAMEINFO)
        target = self.game / 'mods' / addon['id'] / 'pak01_dir.vpk'
        target.write_bytes(b'truncated')
        self.assertTrue(self.enable(addon))
        self.assertEqual(target.read_bytes(), Path(addon['path']).read_bytes())

    def test_interrupted_copy_does_not_publish_partial_vpk(self):
        addon = self.addon()

        def interrupt(src, dst, *args, **kwargs):
            Path(dst).write_bytes(b'partial')
            raise OSError('simulated full disk')

        with mock.patch.object(core.shutil, 'copyfile', side_effect=interrupt):
            try:
                result = self.enable(addon)
            except OSError:
                result = False
        self.assertFalse(result)
        target = self.game / 'mods' / addon['id'] / 'pak01_dir.vpk'
        self.assertFalse(target.exists())
        self.assertEqual(self.gi.read_bytes(), GAMEINFO)
        self.assertTrue(self.enable(addon))
        self.assertEqual(target.read_bytes(), Path(addon['path']).read_bytes())

    def test_local_addon_is_not_an_orphan(self):
        addon = self.addon('local_mod', local=True)
        self.assertTrue(self.enable(addon))
        self.assertEqual(core.currently_enabled_orphans(str(self.game)), [])
        self.assertEqual(core.cleanup_orphans(str(self.game), log=lambda _: None), [])
        self.assertIn(addon['id'], core.currently_enabled(str(self.game)))

    def test_external_gameinfo_entry_survives_cleanup_and_disable(self):
        original = GAMEINFO.replace(b'Game left4dead2', b'Game mods\\external\r\n   Game left4dead2')
        self.gi.write_bytes(original)
        self.assertEqual(core.cleanup_orphans(str(self.game), log=lambda _: None), [])
        core.disable(str(self.game), ['external'], log=lambda _: None)
        self.assertEqual(self.gi.read_bytes(), original)

    def test_added_external_files_survive_managed_directory_cleanup(self):
        addon = self.addon()
        self.assertTrue(self.enable(addon))
        foreign = self.game / 'mods' / addon['id'] / 'user.cfg'
        foreign.write_bytes(b'custom data')
        self.assertTrue(core.disable(str(self.game), [addon['id']], log=lambda _: None))
        self.assertEqual(foreign.read_bytes(), b'custom data')

    def test_invalid_ids_cannot_refer_to_parent_directory(self):
        for aid in ('.', '..', 'CON', 'nul', 'trail.'):
            with self.subTest(aid=aid):
                self.assertFalse(core._valid_addon_id(aid))

    def test_manifest_failure_never_reports_enable_success(self):
        addon = self.addon()
        with mock.patch.object(core, '_save_managed_manifest', return_value=False):
            self.assertFalse(self.enable(addon))
        self.assertEqual(self.gi.read_bytes(), GAMEINFO)

    def test_batch_cleanup_has_constant_manifest_reads_and_writes(self):
        addons = [self.addon(str(123456 + i)) for i in range(12)]
        self.assertTrue(core.enable(str(self.game), addons, log=lambda _: None))
        for addon in addons:
            Path(addon['path']).unlink()
        with mock.patch.object(core, '_load_managed_manifest', wraps=core._load_managed_manifest) as reads, \
                mock.patch.object(core, '_save_managed_manifest', wraps=core._save_managed_manifest) as writes:
            removed = core.cleanup_orphans(str(self.game), log=lambda _: None)
        self.assertEqual(set(removed), {a['id'] for a in addons})
        self.assertLessEqual(reads.call_count, 4)
        self.assertLessEqual(writes.call_count, 1)

    def test_two_processes_keep_both_activations(self):
        ctx = multiprocessing.get_context('spawn')
        start, results = ctx.Event(), ctx.Queue()
        addons = [self.addon('123456'), self.addon('234567')]
        workers = [ctx.Process(target=_enable_worker, args=(str(self.game), addon, start, results)) for addon in addons]
        try:
            for worker in workers:
                worker.start()
            start.set()
            for worker in workers:
                worker.join(15)
                self.assertFalse(worker.is_alive())
                self.assertEqual(worker.exitcode, 0)
            self.assertEqual([results.get(timeout=2) for _ in workers], [True, True])
            self.assertEqual(set(core.currently_enabled(str(self.game))), {'123456', '234567'})
            self.assertEqual(core._managed_ids(str(self.game)), {'123456', '234567'})
        finally:
            for worker in workers:
                if worker.is_alive():
                    worker.terminate()
                    worker.join()
            results.close()


if __name__ == '__main__':
    unittest.main()
