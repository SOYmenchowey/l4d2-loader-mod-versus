import os
from pathlib import Path
import subprocess
import json
import tempfile
import threading
import time
import unittest
from unittest import mock

import l4d2_game as game
import l4d2_metadata as metadata
import l4d2_workshop as workshop


class DiscoveryHardeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'game'
        self.addons = self.root / 'left4dead2' / 'addons'
        self.workshop = self.addons / 'workshop'
        self.workshop.mkdir(parents=True)

    def scan(self):
        return {Path(a['path']).name: a for a in game.list_addons(str(self.root))}

    def test_local_id_does_not_change_when_colliding_name_disappears(self):
        first, second = self.addons / 'my mod.vpk', self.addons / 'my@mod.vpk'
        first.write_bytes(b'first')
        second.write_bytes(b'second')
        before = self.scan()[second.name]['id']
        first.unlink()
        self.assertEqual(self.scan()[second.name]['id'], before)

    def test_ids_are_unique_under_windows_case_rules(self):
        (self.addons / 'mod.vpk').write_bytes(b'local')
        (self.workshop / 'MOD.vpk').write_bytes(b'workshop')
        ids = [a['id'].casefold() for a in self.scan().values()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_distinct_unicode_windows_names_are_not_collapsed(self):
        (self.addons / '\u00df.vpk').write_bytes(b'first')
        (self.addons / 'ss.vpk').write_bytes(b'second')
        self.assertEqual(len(self.scan()), 2)

    def test_local_numeric_name_never_impersonates_workshop(self):
        local = self.addons / '123456.vpk'
        local.write_bytes(b'local')
        first_id = self.scan()[local.name]['id']
        self.assertNotEqual(first_id, '123456')
        (self.workshop / '123456.vpk').write_bytes(b'remote')
        local_info = next(a for a in game.list_addons(str(self.root)) if a['path'] == str(local))
        self.assertEqual(local_info['id'], first_id)

    def test_scan_detects_replacement_preserving_name_and_size(self):
        file = self.workshop / '123456.vpk'
        file.write_bytes(b'first')
        before = self.scan()
        file.write_bytes(b'other')
        later = file.stat().st_mtime_ns + 1000000
        os.utime(file, ns=(later, later))
        after = self.scan()
        self.assertNotEqual(before[file.name].get('mtime_ns'), after[file.name].get('mtime_ns'))

    def test_process_failure_is_not_treated_as_closed(self):
        with mock.patch('subprocess.check_output', side_effect=OSError('tasklist unavailable')):
            with self.assertRaises(OSError):
                game.l4d2_running()

    def test_process_query_has_timeout_and_exact_names(self):
        with mock.patch('subprocess.check_output', return_value=b'"not_left4dead2.exe","42"\r\n') as call:
            self.assertFalse(game.l4d2_running())
        self.assertGreater(call.call_args.kwargs.get('timeout', 0), 0)
        self.assertLessEqual(call.call_args.kwargs['timeout'], 5)

    def test_process_timeout_cannot_authorize_modification(self):
        with mock.patch('subprocess.check_output', side_effect=subprocess.TimeoutExpired('tasklist', 3)):
            with self.assertRaises(OSError):
                game.l4d2_running()


class DependencyHardeningTests(unittest.TestCase):
    def test_550_addons_do_not_rebuild_title_patterns_quadratically(self):
        addons = [{'id': str(100000 + i), 'title': 'Unique addon title %d' % i,
                   'description': 'Requires Unique addon title %d.' % ((i + 1) % 550)}
                  for i in range(550)]
        known = {a['id'] for a in addons}
        titles = {a['id']: a['title'] for a in addons}
        started = time.process_time()
        with mock.patch.object(metadata, '_norm_text', wraps=metadata._norm_text) as normalize:
            if hasattr(metadata, 'suggest_dependencies'):
                result = metadata.suggest_dependencies(addons)
            else:
                result = {a['id']: [x['id'] for x in metadata.suggest_deps(a['description'], known, titles)] for a in addons}
        elapsed = time.process_time() - started
        print('\n550-addon dependency CPU: %.3fs; normalizations: %d' % (elapsed, normalize.call_count))
        self.assertEqual(result['100000'], ['100001'])
        self.assertEqual(result['100549'], ['100000'])
        self.assertLessEqual(normalize.call_count, len(addons) * 3)
        self.assertLess(elapsed, 2.0)

    def test_dependency_links_survive_dots_in_url(self):
        self.assertEqual(metadata.suggest_deps(
            'Requires https://steamcommunity.com/sharedfiles/filedetails/?id=123456.', {'123456'}, {}),
            [{'id': '123456', 'via': 'link'}])

    def test_save_dependencies_preserves_existing_file_on_serialization_error(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'deps.json'
            path.write_bytes(b'{"old": ["dependency"]}')
            with mock.patch.object(metadata, 'deps_path', return_value=str(path)):
                self.assertFalse(metadata.save_deps({'new': object()}))
            self.assertEqual(path.read_bytes(), b'{"old": ["dependency"]}')


class WorkshopHardeningTests(unittest.TestCase):
    def test_offline_library_does_not_retry_every_batch(self):
        with mock.patch.object(workshop.urllib.request, 'urlopen', side_effect=TimeoutError('offline')) as call:
            self.assertEqual(workshop.fetch_workshop_details([str(100000 + i) for i in range(550)]), {})
        self.assertLessEqual(call.call_count, 4)

    def test_metadata_returns_partial_results_within_total_budget(self):
        started = threading.Event()
        release = threading.Event()

        def slow(batch, timeout):
            started.set()
            release.wait(2)
            return {}

        before = time.monotonic()
        try:
            with mock.patch.object(workshop, '_fetch_details_batch', side_effect=slow):
                self.assertEqual(workshop.fetch_workshop_details(
                    [str(100000 + i) for i in range(550)], budget=0.08), {})
                self.assertTrue(started.is_set())
                self.assertLess(time.monotonic() - before, 0.75)
                # Repeated scans cannot fill an unbounded queue behind slow workers.
                self.assertEqual(workshop.fetch_workshop_details(['999999'], budget=0.08), {})
        finally:
            release.set()
            self.assertTrue(workshop._DETAILS_FETCH_LOCK.acquire(timeout=2))
            workshop._DETAILS_FETCH_LOCK.release()

    def test_successful_batches_are_bounded_and_keep_all_results(self):
        active, peak = 0, 0
        lock = threading.Lock()

        def fetch(batch, timeout):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            try:
                time.sleep(0.01)
                return {aid: {'title': aid} for aid in batch}
            finally:
                with lock:
                    active -= 1

        ids = [str(100000 + i) for i in range(550)]
        with mock.patch.object(workshop, '_fetch_details_batch', side_effect=fetch):
            result = workshop.fetch_workshop_details(ids)
        self.assertEqual(set(result), set(ids))
        self.assertGreater(peak, 1)
        self.assertLessEqual(peak, 4)

    def test_workshop_response_is_bounded_and_ignores_unrequested_ids(self):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps({'response': {'publishedfiledetails': [
            {'result': 1, 'publishedfileid': '123456', 'title': 'Expected'},
            {'result': 1, 'publishedfileid': '999999', 'title': 'Other'},
        ]}}).encode()
        with mock.patch.object(workshop.urllib.request, 'urlopen', return_value=response):
            result = workshop._fetch_details_batch(['123456'], 1)
        self.assertEqual(set(result), {'123456'})
        self.assertEqual(response.read.call_args.args, (workshop._MAX_DETAILS_BYTES + 1,))


if __name__ == '__main__':
    unittest.main()
