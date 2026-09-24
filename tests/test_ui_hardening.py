import asyncio
import concurrent.futures
import ctypes
import inspect
import os
from pathlib import Path
import sys
import threading
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import flet as ft
from flet.messaging.session import Session
import main as app
import l4d2_clipboard as clipboard
from l4d2_app_config import APP_VERSION, VERSION_LABEL


class FakePage:
    def __init__(self, web=True):
        self.web = web
        self.width, self.height = 1152, 944
        self.window = SimpleNamespace()
        self.services = []
        self.tasks = []
        self.dialogs = []
        self.controls = []

    def run_task(self, fn, *args):
        future = concurrent.futures.Future()
        self.tasks.append((fn, args, future))
        return future

    def show_dialog(self, dialog):
        dialog.open = True
        self.dialogs.append(dialog)

    def pop_dialog(self):
        for dialog in reversed(self.dialogs):
            if dialog.open:
                dialog.open = False
                return dialog

    def add(self, *controls):
        self.controls.extend(controls)

    def update(self):
        pass

    async def run_named(self, name):
        index = next(i for i, (fn, _, _) in enumerate(self.tasks)
                     if fn.__name__ == name)
        fn, args, future = self.tasks.pop(index)
        try:
            result = await fn(*args)
        finally:
            if not future.done():
                future.set_result(None)
        return result

    async def animations(self):
        with mock.patch.object(app.asyncio, "sleep", new=mock.AsyncMock()):
            while True:
                index = next((i for i, (fn, _, _) in enumerate(self.tasks)
                              if fn.__name__ == "_t" and
                              inspect.getclosurevars(fn).nonlocals["delay"] < 0.25), None)
                if index is None:
                    break
                fn, args, future = self.tasks.pop(index)
                await fn(*args)
                if not future.done():
                    future.set_result(None)


def descendants(control):
    yield control
    content = getattr(control, "content", None)
    if isinstance(content, ft.Control):
        yield from descendants(content)
    for child in getattr(control, "controls", []) or []:
        yield from descendants(child)


class UIHardeningTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        for name, value in (("load_json", mock.DEFAULT), ("load_deps", {}),
                            ("currently_enabled", set()),
                            ("currently_enabled_orphans", set()),
                            ("cleanup_orphans", []), ("migrate_legacy_addons", []), ("l4d2_running", False),
                            ("save_json", True), ("enable", True),
                            ("disable", True)):
            patched = self.patches.enter_context(mock.patch.object(
                app.core, name, return_value=value))
            if name == "load_json":
                patched.side_effect = lambda path, default: default
        self.patches.enter_context(mock.patch.object(app, "dbg"))
        self.patches.enter_context(mock.patch.object(app, "debug_log"))
        self.patches.enter_context(mock.patch.object(
            app, "_cfg_path", side_effect=lambda name: str(ROOT / "unused" / name)))
        self.patches.enter_context(mock.patch.object(
            app.l4d2_glows, "load_colors", return_value=app.l4d2_glows.default_colors()))
        self.patches.enter_context(mock.patch.object(
            app.l4d2_glows, "is_applied", return_value=False))
        self.patches.enter_context(mock.patch.object(
            app.core, "suggest_dependencies", wraps=app.core.suggest_dependencies))
        self.patches.enter_context(mock.patch.object(
            ft.Control, "update", return_value=None))
        self.page = FakePage()
        self.ui = self.start()
        self.state = self.ui["state"]

    def start(self, page=None):
        captured = {}
        previous = sys.getprofile()

        def profile(frame, event, arg):
            if event == "return" and frame.f_code is app.main.__code__:
                captured.update(frame.f_locals)

        sys.setprofile(profile)
        try:
            app.main(page or self.page)
        finally:
            sys.setprofile(previous)
        return captured

    def addon(self, aid="1", **values):
        return dict(id=aid, path="unused.vpk", size=20, ctime=1,
                    mtime_ns=1, title="Test addon", is_vscript=False,
                    category="Otro", description=None, type="MOD", **values)

    def messages(self):
        return [pill.content.controls[1].value
                for pill in self.ui["toasts_column"].controls]

    async def test_version_visible_and_in_copied_diagnostic(self):
        self.assertEqual(VERSION_LABEL, 'Version %s' % APP_VERSION)
        labels = [c.value for c in descendants(self.ui['sidebar_holder'])
                  if isinstance(c, ft.Text)]
        self.assertIn(VERSION_LABEL, labels)
        await self.ui['open_diagnostic']()
        controls = list(descendants(self.page.dialogs[-1].content))
        report = next(c.value for c in controls if isinstance(c, ft.TextField)
                      and 'L4D2 Mod Loader - Diagnostico' in (c.value or ''))
        self.assertEqual(report.splitlines()[1], VERSION_LABEL)
        button = next(c for c in controls if
                      getattr(getattr(c, 'on_click', None), '__name__', '') == 'copy_report')
        with mock.patch.object(app, 'copy_text_to_clipboard',
                               new=mock.AsyncMock(return_value=True)) as copy:
            await button.on_click(None)
        self.assertEqual(copy.await_args.args[1], report)

    async def dispatch_queued_checks(self, initial, changes):
        self.state.update(addons=[self.addon('1'), self.addon('2')],
                          selected_ids=set(initial), fetching=False)
        self.ui['refresh_list']()
        session = Session(SimpleNamespace(
            pubsubhub=mock.Mock(), send_message=mock.Mock(),
            loop=asyncio.get_running_loop()))
        session.page.controls.append(self.ui['list_view'])
        session.get_page_patch()
        self.page.update = session.page.update
        tasks = []
        for aid, value in changes:
            checkbox = self.state['rows'][aid].checkbox
            self.assertIs(session.index[checkbox._i], checkbox)
            # Buffered socket messages can apply both patches before callbacks run.
            session.apply_patch(checkbox._i, {'value': value})
            tasks.append(asyncio.create_task(
                session.dispatch_event(checkbox._i, 'change', value)))
        await asyncio.gather(*tasks)
        expected = set(initial)
        for aid, value in changes:
            if value:
                expected.add(aid)
            else:
                expected.discard(aid)
        self.assertEqual(self.state['selected_ids'], expected)
        for aid, row in self.state['rows'].items():
            self.assertEqual(row.checkbox.value, aid in expected)

    async def test_queued_checks_keep_both_selections(self):
        await self.dispatch_queued_checks(set(), [('1', True), ('2', True)])

    async def test_queued_unchecks_clear_both_selections(self):
        await self.dispatch_queued_checks({'1', '2'}, [('1', False), ('2', False)])

    async def test_queued_mixed_clicks_keep_last_intent(self):
        await self.dispatch_queued_checks(
            set(), [('1', True), ('2', True), ('1', False)])

    async def test_new_rows_start_with_authoritative_selection(self):
        self.state.update(addons=[self.addon()], selected_ids={'1'})
        constructor = app.ModRow
        initial_values = []
        def capture(*args, **kwargs):
            row = constructor(*args, **kwargs)
            initial_values.append(row.checkbox.value)
            return row
        with mock.patch.object(app, 'ModRow', side_effect=capture):
            self.ui['refresh_list']()
        self.assertEqual(initial_values, [True])

    async def test_selection_survives_resize_filter_and_cache_rebuild(self):
        selected = {str(i) for i in range(0, 550, 3)}
        self.state.update(addons=[self.addon(str(i)) for i in range(550)],
                          selected_ids=set(selected), fetching=False)
        self.ui['refresh_list']()
        self.ui['resize_changed']()
        await self.page.run_named('_resize')
        self.state['query'] = '0'
        self.ui['refresh_list']()
        self.state['query'] = ''
        self.state['_row_cache'].clear()
        self.state['_render_signature'] = None
        self.ui['refresh_list']()
        self.ui['safe_update']()
        self.assertEqual(self.state['selected_ids'], selected)
        for aid, row in self.state['rows'].items():
            self.assertEqual(row.checkbox.value, aid in selected)

    async def test_dialog_checkbox_uses_event_value_not_mutable_control(self):
        callback = mock.Mock()
        _, checkbox = app.dialog_row(self.addon(), with_checkbox=True,
                                     check_cb=callback)
        for value in (True, False, 'true', 'false'):
            expected = value is True or value == 'true'
            checkbox.value = not expected
            checkbox.on_change(SimpleNamespace(control=checkbox, data=value))
            self.assertEqual(callback.call_args.args[1], expected)

    async def test_scan_failure_releases_modal_and_fetching(self):
        with mock.patch.object(app.core, "find_l4d2", side_effect=OSError("scan denied")):
            try:
                await self.page.run_named("_load")
            except OSError:
                pass
        await self.page.animations()
        self.assertFalse(self.state["fetching"])
        self.assertIsNone(self.state["_load_progress"])
        self.assertFalse(any(d.open for d in self.page.dialogs))
        self.assertTrue(self.messages())

    async def test_delayed_close_targets_original_dialog(self):
        original = self.page.dialogs[-1]
        self.ui["close_dialog_anim"](original.content)
        replacement = ft.AlertDialog(content=ft.Text("replacement"))
        self.ui["show_dlg"](replacement)
        await self.page.animations()
        self.assertFalse(original.open)
        self.assertTrue(replacement.open)

    async def test_failed_animation_scheduling_never_leaves_invisible_dialog(self):
        with mock.patch.object(self.page, "run_task", side_effect=RuntimeError("closed executor")):
            progress = self.ui["show_progress"]("Test", "Test")
            self.assertEqual(progress["content"].opacity, 1.0)
            self.ui["close_progress"](progress)
        self.assertFalse(progress["dialog"].open)

    async def test_unknown_status_diagnostic_still_opens(self):
        app.core.l4d2_running.side_effect = OSError("tasklist unavailable")
        await self.ui["open_diagnostic"]()
        self.assertIsNone(self.state["_l4d2_was_running"])

    async def test_diagnostic_snapshot_preserves_unknown_status(self):
        app.core.l4d2_running.side_effect = OSError("tasklist unavailable")
        snapshot = app.diagnostics.collect_health_snapshot(
            self.state, app._cfg_path, refresh_running=True)
        self.assertIsNone(snapshot["game_running"])
        self.assertIn("tasklist", snapshot["game_status_error"])
        cached = app.diagnostics.collect_health_snapshot(self.state, app._cfg_path)
        self.assertIsNone(cached["game_running"])

    async def test_vision_lock_timeout_reports_failure(self):
        self.state["l4d2"] = "unused"
        with mock.patch.object(app.core, "vision_state", return_value="on"), \
                mock.patch.object(app.core, "disable_infected_vision", side_effect=TimeoutError("locked")):
            await self.ui["toggle_vision"](None)
            vision_jobs = [fn for fn, _, _ in self.page.tasks if fn.__name__ == "_run_vision"]
            if vision_jobs:
                await self.page.run_named("_run_vision")
        self.assertTrue(any("locked" in m for m in self.messages()))

    async def test_card_close_cannot_hide_replacement(self):
        self.ui["show_card"](ft.Container())
        self.ui["hide_card"]()
        replacement = ft.Container()
        self.ui["show_card"](replacement)
        await self.page.animations()
        self.assertTrue(self.ui["modal_wrap"].visible)
        self.assertIs(self.ui["_modal_card"][0], replacement)

    async def test_metadata_does_not_hold_scan_modal(self):
        progress = self.state["_load_progress"]
        original = self.page.dialogs[-1]
        entered, release = threading.Event(), threading.Event()

        def fetch(ids):
            entered.set()
            release.wait(3)
            return {}

        with mock.patch.object(app.core, "find_l4d2", return_value="unused"), \
                mock.patch.object(app.core, "list_addons", return_value=[]), \
                mock.patch.object(app.core, "fetch_workshop_details", side_effect=fetch):
            task = asyncio.create_task(self.page.run_named("_load"))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                await self.page.animations()
                self.assertFalse(self.state["_load_progress"] is progress)
                self.assertFalse(original.open)
            finally:
                release.set()
                await task

    async def test_refresh_does_not_cleanup_on_ui_thread(self):
        self.state.update(l4d2="unused", _fresh_scan=True)
        self.ui["refresh_list"]()
        app.core.cleanup_orphans.assert_not_called()

    async def test_restore_last_runs_workers_and_reports_partial_failure(self):
        self.ui["close_progress"](self.state["_load_progress"])
        await self.page.animations()
        self.state.update(l4d2="unused", addons=[self.addon("1"), self.addon("2")],
                          active_ids={"2"}, last_config={"ids": ["1"]})
        app.core.currently_enabled.return_value = {"2"}
        calls = []
        ui_thread = threading.get_ident()
        app.core.disable.side_effect = lambda *a, **k: calls.append(threading.get_ident()) or True
        app.core.enable.side_effect = OSError("locked")
        self.ui["do_restore_last_config"]()
        self.page.dialogs[-1].actions[-1].on_click(None)
        self.assertEqual(calls, [], "confirmation must return before disk work")
        await self.page.run_named("_run_last")
        await self.page.animations()
        self.assertTrue(calls)
        self.assertNotIn(ui_thread, calls)
        self.assertTrue(any("parcial" in m.lower() for m in self.messages()))
        self.assertFalse(any(d.open for d in self.page.dialogs))

    async def test_restore_opening_does_not_probe_process_on_ui_thread(self):
        self.state.update(l4d2="unused", addons=[self.addon()], last_config={"ids": ["1"]})
        calls = []
        app.core.l4d2_running.side_effect = lambda: calls.append(threading.get_ident()) or False
        self.ui["do_restore_last_config"]()
        self.assertEqual(calls, [])
        self.assertTrue(self.page.dialogs[-1].open)

    async def test_save_preset_false_does_not_claim_success_or_lose_selection(self):
        self.state["selected_ids"] = {"1"}
        app.core.save_json.return_value = False
        self.ui["save_preset"](SimpleNamespace(value="New"))
        self.assertEqual(self.state["selected_ids"], {"1"})
        self.assertNotIn("New", self.state["presets"])
        self.assertFalse(any("guardado" in m for m in self.messages()))

    async def test_remove_preset_exception_preserves_preset(self):
        self.state["presets"] = {"Existing": ["1"]}
        app.core.save_json.side_effect = OSError("denied")
        self.ui["remove_preset"]("Existing")
        self.assertEqual(self.state["presets"], {"Existing": ["1"]})
        self.assertFalse(any("eliminado" in m for m in self.messages()))

    async def test_last_config_failure_preserves_saved_state(self):
        self.state.update(l4d2="unused", last_config={"ids": ["old"]})
        app.core.save_json.return_value = False
        self.assertFalse(await self.ui["save_last_config_async"]("test", "unused"))
        self.assertEqual(self.state["last_config"], {"ids": ["old"]})

    async def test_favorites_failure_preserves_state(self):
        self.state["favs"] = {"1"}
        app.core.save_json.return_value = False
        self.ui["toggle_fav"](self.addon())
        self.assertEqual(self.state["favs"], {"1"})

    async def test_game_path_save_exception_keeps_previous_path(self):
        app.core.save_json.side_effect = PermissionError("denied")
        with mock.patch.object(ft.FilePicker, "get_directory_path", new=mock.AsyncMock(return_value="unused")), \
                mock.patch.object(app.core, "resolve_l4d2_path", return_value="unused"):
            self.ui["choose_l4d2_path"]()
            await self.page.run_named("_pick")
        self.assertIsNone(self.state["manual_l4d2_path"])
        self.assertFalse(any("guardada" in msg for msg in self.messages()))

    async def test_config_directory_error_does_not_crash_startup(self):
        with mock.patch.object(app.l4d2_glows, "load_colors", side_effect=PermissionError("denied")):
            ui = self.start(FakePage())
        self.assertTrue(ui["state"]["glow_colors"])

    async def test_preview_requests_are_shared(self):
        addon = self.addon(_preview_url="https://example.invalid/image")
        self.state["addons"] = [addon]
        panes = [{"current_id": "1", "generation": 0} for _ in range(2)]
        entered, release = threading.Event(), threading.Event()

        def download(*args):
            entered.set()
            release.wait(3)
            return "cached.png"

        with mock.patch.object(app.core, "get_cached_image", side_effect=download) as fetch, \
                mock.patch.object(app, "pane_set_img") as paint:
            for pane in panes:
                self.ui["load_preview"](addon, pane)
            preview_jobs = [(fn, args) for fn, args, _ in self.page.tasks
                            if fn.__name__ == "_load" and fn.__qualname__.endswith("load_preview.<locals>._load")]
            jobs = [asyncio.create_task(fn(*args)) for fn, args in preview_jobs]
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                await asyncio.sleep(0.03)
                self.assertEqual(fetch.call_count, 1)
            finally:
                release.set()
                await asyncio.gather(*jobs)
            self.assertEqual(paint.call_count, 2)

    async def test_hex_focus_preserves_field_identity(self):
        self.ui["switch_view"]("glows")
        root = self.ui["list_view"].controls[0]
        field = next(c for c in descendants(root) if isinstance(c, ft.TextField))
        if field.on_focus:
            field.on_focus(SimpleNamespace(control=field))
        self.assertTrue(self.ui["list_view"].controls[0] is root)
        self.assertTrue(any(c is field for c in descendants(root)))

    async def test_active_view_ignores_hidden_category(self):
        self.state.update(addons=[self.addon()], active_ids={"1"},
                          category="Armas", view="activos")
        self.assertEqual([a["id"] for a in self.ui["visible_addons"]({"1"})], ["1"])

    async def test_small_screen_window_fits(self):
        page = FakePage(web=False)
        user32 = SimpleNamespace(GetSystemMetrics=lambda n: (1366, 768)[n])
        with mock.patch.object(ctypes, "windll", SimpleNamespace(user32=user32), create=True):
            self.start(page)
        self.assertLessEqual(page.window.height, 768)
        self.assertGreaterEqual(page.window.top, 0)
        self.assertLessEqual(page.window.min_height, page.window.height)

    async def test_unknown_game_status_blocks_mutations(self):
        app.core.l4d2_running.side_effect = OSError("tasklist unavailable")
        self.assertFalse(await self.ui["require_game_closed"]())

    async def test_game_guard_runs_outside_event_loop(self):
        entered, release = threading.Event(), threading.Event()
        threads = []
        def slow_check():
            threads.append(threading.get_ident())
            entered.set()
            release.wait(1)
            return False
        app.core.l4d2_running.side_effect = slow_check
        job = asyncio.create_task(self.ui['require_game_closed']())
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 1))
            self.assertFalse(job.done())
            self.assertNotIn(threading.get_ident(), threads)
        finally:
            release.set()
            self.assertTrue(await job)

    async def test_partial_disable_all_refreshes_actual_active_ids(self):
        self.state.update(l4d2='unused', addons=[self.addon()], active_ids={'1'}, view='activos')
        active = {'1'}
        app.core.currently_enabled.side_effect = lambda *_: set(active)
        def partial(*args):
            active.clear()
            return False
        app.core.disable.side_effect = partial
        await self.ui['do_quitar_todos'](None)
        self.page.dialogs[-1].actions[-1].on_click(None)
        await self.page.run_named('_run_disable_all')
        self.assertEqual(self.state['active_ids'], set())
        self.assertTrue(any('incompleta' in m for m in self.messages()))

    async def test_disable_exception_refreshes_actual_active_ids(self):
        self.state.update(l4d2='unused', addons=[self.addon()], active_ids={'1'})
        app.core.disable.side_effect = OSError('partial write')
        await self.ui['do_quitar_todos'](None)
        self.page.dialogs[-1].actions[-1].on_click(None)
        await self.page.run_named('_run_disable_all')
        self.assertEqual(self.state['active_ids'], set())

    async def test_stale_reconciliation_does_not_overwrite_other_installation(self):
        self.state.update(l4d2='other', active_ids={'other'})
        self.assertFalse(await self.ui['sync_active_state']('old', self.state['_load_generation']))
        self.assertEqual(self.state['active_ids'], {'other'})

    async def test_unreadable_glows_keeps_local_list_and_blocks_mutations(self):
        with mock.patch.object(app.core, "find_l4d2", return_value="unused"), \
                mock.patch.object(app.core, "list_addons", return_value=[self.addon()]), \
                mock.patch.object(app.core, "inspect_vpk", return_value={"title": "Test", "is_vscript": False}), \
                mock.patch.object(app.core, "fetch_workshop_details", return_value={}), \
                mock.patch.object(app.l4d2_glows, "is_applied", side_effect=OSError("unreadable")):
            await self.page.run_named("_load")
        self.assertEqual([a["id"] for a in self.state["addons"]], ["1"])
        self.assertFalse(await self.ui["require_game_closed"]())

    async def test_orphan_cleanup_worker_reports_remaining(self):
        self.state["l4d2"] = "unused"
        ui_thread = threading.get_ident()
        threads = []
        app.core.cleanup_orphans.side_effect = lambda *a, **k: threads.append(threading.get_ident()) or ["1"]
        app.core.currently_enabled_orphans.return_value = {"2"}
        await self.ui["cleanup_orphans_async"]("unused", self.state["_load_generation"])
        self.assertTrue(threads)
        self.assertNotIn(ui_thread, threads)
        self.assertEqual(self.state["_pending_cleanup_ids"], {"2"})
        self.assertTrue(any("parcial" in m.lower() for m in self.messages()))

    async def test_cleanup_unknown_process_clears_cached_closed_status(self):
        self.state.update(l4d2="unused", _l4d2_was_running=False)
        app.core.l4d2_running.side_effect = OSError("tasklist failed")
        await self.ui["cleanup_orphans_async"]("unused", self.state["_load_generation"])
        self.assertIsNone(self.state["_l4d2_was_running"])
        app.core.cleanup_orphans.assert_not_called()

    async def test_cancelled_scan_does_not_leave_overlay(self):
        async def cancelled(*args, **kwargs):
            raise asyncio.CancelledError()
        with mock.patch.object(app.asyncio, "to_thread", side_effect=cancelled):
            with self.assertRaises(asyncio.CancelledError):
                await self.page.run_named("_load")
        await self.page.animations()
        self.assertFalse(self.state["fetching"])
        self.assertFalse(any(d.open for d in self.page.dialogs))

    async def test_stale_scan_failure_cannot_close_new_scan(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def failed(*args, **kwargs):
            entered.set()
            await release.wait()
            raise OSError("stale scan")
        original = self.page.dialogs[-1]
        with mock.patch.object(app.asyncio, "to_thread", side_effect=failed):
            task = asyncio.create_task(self.page.run_named("_load"))
            await entered.wait()
            self.ui["load_addons"]()
            replacement = self.page.dialogs[-1]
            release.set()
            await task
        await self.page.animations()
        self.assertFalse(original.open)
        self.assertTrue(replacement.open)
        self.assertTrue(self.state["fetching"])

    async def test_dependency_helper_runs_once_off_loop(self):
        self.state["addons"] = [self.addon()]
        ui_thread = threading.get_ident()
        worker_threads = []
        def suggest(addons):
            worker_threads.append(threading.get_ident())
            return {"1": ["2"]}
        app.core.suggest_dependencies.side_effect = suggest
        with mock.patch.object(app.core, "fetch_workshop_details", return_value={}):
            await self.ui["fetch_task"](self.state["_load_generation"], ["1"])
        self.assertEqual(len(worker_threads), 1)
        self.assertNotIn(ui_thread, worker_threads)
        self.assertEqual(self.state["addons"][0]["auto_deps"], ["2"])

    async def test_failed_async_clipboard_does_not_report_success(self):
        page = SimpleNamespace(clipboard=SimpleNamespace(set=mock.AsyncMock(side_effect=OSError("denied"))))
        with mock.patch.object(clipboard, "_copy_text_with_windows_clipboard", return_value=False), \
                mock.patch.object(clipboard, "_copy_text_with_powershell", return_value=False), \
                mock.patch.object(clipboard, "_copy_text_with_clip_exe", return_value=False):
            self.assertFalse(await clipboard.copy_text_to_clipboard_async(page, "test", prefer_native=False))

    async def test_preview_workers_are_limited_to_four(self):
        release = threading.Event()
        threads = []
        def download(*args):
            threads.append(threading.get_ident())
            release.wait(3)
            return None
        with mock.patch.object(app.core, "get_cached_image", side_effect=download), \
                mock.patch.object(app, "pane_set_img"):
            for i in range(8):
                addon = self.addon(str(i), _preview_url="https://example.invalid/%d" % i)
                self.ui["load_preview"](addon, {"current_id": str(i), "generation": 0})
            jobs = [asyncio.create_task(fn(*args)) for fn, args, _ in self.page.tasks
                    if fn.__qualname__.endswith("load_preview.<locals>._load")]
            try:
                for _ in range(50):
                    if len(threads) >= 4:
                        break
                    await asyncio.sleep(0.01)
                self.assertEqual(len(threads), 4)
            finally:
                release.set()
                await asyncio.gather(*jobs)

    async def test_watcher_detects_same_id_file_replacement(self):
        addon = self.addon()
        self.state.update(l4d2="unused", _disk_ids={"1"},
                          _disk_snapshot=app.core.addon_snapshot([addon]), fetching=False)
        addon["mtime_ns"] = 2
        polls = []
        async def sleep(delay):
            polls.append(delay)
            if len(polls) > 1:
                raise asyncio.CancelledError()
        with mock.patch.object(app.core, "list_addons", return_value=[addon]), \
                mock.patch.object(app.asyncio, "sleep", side_effect=sleep):
            try:
                await self.ui["watch_workshop"]()
            except asyncio.CancelledError:
                pass
        self.assertGreaterEqual(polls[0], 10)
        self.assertEqual(self.state["_load_generation"], 2)
        app.core.currently_enabled_orphans.assert_not_called()


class ClipboardAndRequirementsTests(unittest.TestCase):
    def test_flet_clipboard_is_awaited(self):
        setter = mock.AsyncMock()
        page = SimpleNamespace(clipboard=SimpleNamespace(set=setter))
        self.assertTrue(clipboard.copy_text_to_clipboard(page, "test", prefer_native=False))
        setter.assert_awaited_once_with("test")

    def test_desktop_dependency_is_explicit(self):
        requirements = (ROOT / "requirements.txt").read_text()
        self.assertTrue("flet[desktop]==0.86.5" in requirements or
                        "flet-desktop==0.86.5" in requirements)


if __name__ == "__main__":
    unittest.main()
