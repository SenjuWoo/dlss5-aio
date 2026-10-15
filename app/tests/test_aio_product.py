"""Product regressions for truthful compatibility, recovery and safe shutdown."""
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
from core import autotune, compare, compareui, dlss, emulators, games, installer, net, ownfg, prefs, profiles
from core.ui.ctl_watch import WatchControl
from core.ui.ctl_game import fault_in_this_folder
from core.ui.ctl_game import GameControl
from core.ui.ctl_library import LibraryControl
from core.ui import app as uiapp

spec = importlib.util.spec_from_file_location("aio_product_entry", APP / "dlss5_aio.py")
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


class ProductTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aio_product_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.enterContext(patch.object(prefs, "FILE", self.root / "settings.json"))
        dlss.forget_walk()

    def _cli(self, game, **kwargs):
        with ExitStack() as stack:
            stack.enter_context(patch.object(entry.gpu, "detect", return_value=(None, None)))
            stack.enter_context(patch.object(entry.gpu, "other_vendor", return_value=None))
            stack.enter_context(patch.object(entry.gpu, "driver_version", return_value=None))
            stack.enter_context(patch.object(entry.community, "cached", return_value={}))
            stack.enter_context(patch.object(entry.prefs, "find_renodx", return_value=(None, [])))
            stack.enter_context(redirect_stdout(io.StringIO()))
            stack.enter_context(redirect_stderr(io.StringIO()))
            return entry.cli(self.root, game=game, remove=False, check=True, **kwargs)

    def test_check_rejects_unreadable_and_impossible_installations(self):
        for game in (games.Game("Invalid", self.root, exe=self.root / "game.exe", error="broken PE"),
                     games.Game("Impossible", self.root, exe=self.root / "game.exe", bitness=64, api="DX8")):
            with self.subTest(game=game.name):
                self.assertEqual(self._cli(game), 1)

    def test_remove_does_not_require_install_compatibility_or_a_gpu(self):
        game = games.Game("Recovery", self.root, exe=self.root / "game.exe", error="broken PE")
        with patch.object(installer, "uninstall", return_value=["dxgi.dll"]) as remove, \
                patch.object(entry.gpu, "detect", side_effect=AssertionError("recovery queried the GPU")), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(entry.cli(self.root, remove=True, check=False, game=game), 0)
        remove.assert_called_once()

    def test_remove_recorded_install_after_game_executable_was_deleted(self):
        (self.root / installer.MANIFEST).write_text(json.dumps({"exe": "gone.exe", "files": []}))
        game = games.Game("Recovery", self.root, error="no executable found")
        with patch.object(installer, "uninstall", return_value=[]) as remove, \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(entry.cli(self.root, remove=True, check=False, game=game), 0)
        remove.assert_called_once()

    def test_streamline_base_reflex_and_frame_generation_are_not_dlss_sr(self):
        for name in ("sl.interposer.dll", "sl.common.dll", "sl.reflex.dll", "sl.dlss_g.dll", "nvngx_dlssg.dll"):
            for nested in (False, True):
                with self.subTest(name=name, nested=nested), tempfile.TemporaryDirectory(dir=self.root) as folder:
                    root = Path(folder)
                    d = root / "bin" if nested else root
                    d.mkdir(exist_ok=True)
                    (d / name).touch()
                    found = dlss.detect(root, root, "DX12", 64, 89)
                    self.assertFalse(found.native_dlss, found.evidence)
                    self.assertNotIn(dlss.NATIVE, found.options)

    def test_dlss_specific_plugin_and_nested_sr_still_offer_native_route(self):
        for name in ("sl.dlss.dll", "nvngx_dlss.dll"):
            for nested in (False, True):
                with self.subTest(name=name, nested=nested), tempfile.TemporaryDirectory(dir=self.root) as folder:
                    root = Path(folder)
                    d = root / "bin" if nested else root
                    d.mkdir(exist_ok=True)
                    (d / name).touch()
                    found = dlss.detect(root, root, "DX12", 64, 89)
                    self.assertTrue(found.native_dlss, found.evidence)
                    self.assertIn(dlss.NATIVE, found.options)

    def test_frame_generation_and_generic_backend_do_not_offer_an_upscaler_hook(self):
        for name in ("libxess_fg.dll", "ffx_backend_dx12_x64.dll"):
            for nested in (False, True):
                with self.subTest(name=name, nested=nested), tempfile.TemporaryDirectory(dir=self.root) as folder:
                    root = Path(folder)
                    d = root / "bin" if nested else root
                    d.mkdir(exist_ok=True)
                    (d / name).touch()
                    found = dlss.detect(root, root, "DX12", 64, 120)
                    self.assertEqual(found.upscaler, "")
                    self.assertNotIn(dlss.OPTI, found.options)

    def test_owned_upscaler_uses_case_insensitive_manifest_but_keeps_original_evidence(self):
        for name in ("libxess.dll", "amd_fidelityfx_dx12.dll"):
            with self.subTest(name=name), tempfile.TemporaryDirectory(dir=self.root) as folder:
                root = Path(folder)
                (root / name).touch()
                (root / installer.MANIFEST).write_text(json.dumps({"files": [name.upper()]}))
                self.assertEqual(dlss.detect(root, root, "DX12", 64, 120).upscaler, "")
                (root / (name + installer.BACKUP_SUFFIX)).touch()
                self.assertTrue(dlss.detect(root, root, "DX12", 64, 120).upscaler)

    def test_crash_module_in_sibling_folder_is_not_attributed_to_this_install(self):
        game = self.root / "Game"
        self.assertTrue(fault_in_this_folder(SimpleNamespace(module=str(game / "hook.dll")), game))
        self.assertFalse(fault_in_this_folder(SimpleNamespace(module=str(self.root / "Game-old" / "hook.dll")), game))
        if sys.platform == "win32":
            import ctypes
            game.mkdir()
            module = game / "hook.dll"
            module.touch()
            short = ctypes.create_unicode_buffer(32768)
            self.assertTrue(ctypes.windll.kernel32.GetShortPathNameW(str(module), short, len(short)))
            self.assertTrue(fault_in_this_folder(SimpleNamespace(module=short.value), game.resolve()))

    def test_quit_waits_for_worker_and_stops_autopilot_before_destroying_window(self):
        control = WatchControl()
        control.busy, control.action = True, "autopilot"
        control.root = SimpleNamespace(after=Mock(), destroy=Mock())
        control.lookout = SimpleNamespace(stop=Mock())
        control.tray = None
        control.shell = SimpleNamespace(status=Mock())
        control.quit()
        control.root.destroy.assert_not_called()
        self.assertTrue(control._auto_stop)
        callback = control.root.after.call_args.args[1]
        control.busy = False
        callback()
        control.root.destroy.assert_called_once()

    def test_game_actions_recheck_busy_after_nested_dialog_events(self):
        for method in ("install", "autopilot", "uninstall"):
            with self.subTest(method=method):
                control = GameControl()
                control.game = games.Game("Fixture", self.root, exe=self.root / "game.exe", bitness=64, api="DX11")
                control.busy, control.support, control.route = False, dlss.Support(), dlss.FEEDER
                control.opts, control.write, control.refresh = Mock(), Mock(), Mock()
                control._community, control.plans = None, {}
                control.game_class, control._autopilot_run = lambda: "", Mock()
                control.shell = SimpleNamespace(ask=Mock())
                def nested_job(*args, **kwargs):
                    control.busy = True
                    return True
                control._anticheat_ok = nested_job
                control.shell.ask.side_effect = nested_job
                with patch.object(installer, "check_supported", return_value=(True, "")), \
                        patch("core.ui.ctl_game.threading.Thread") as thread:
                    getattr(control, method)()
                thread.assert_not_called()
                control.opts.assert_not_called()

    def test_bulk_action_rechecks_busy_after_confirmation(self):
        control = LibraryControl()
        control.busy = False
        control.update_targets = lambda: ([games.Game("Fixture", self.root)], [])
        def nested_job(*args, **kwargs):
            control.busy = True
            return True
        control.shell = SimpleNamespace(ask=nested_job)
        with patch("core.ui.ctl_library.threading.Thread") as thread:
            control.update_all()
        thread.assert_not_called()

    def test_restart_reserves_busy_before_processing_pending_tk_events(self):
        exe = self.root / "cached-update.exe"
        exe.touch()
        control = uiapp.App.__new__(uiapp.App)
        control.busy, control.update_ready = False, exe
        control.shell = SimpleNamespace(banner=Mock())
        control._restart_into = Mock()
        control.root = SimpleNamespace(update=lambda: self.assertTrue(control.busy))
        control.do_update()
        control._restart_into.assert_called_once_with(exe)

    def test_failed_atomic_settings_swap_keeps_old_file_and_logs_failure(self):
        target = self.root / "settings.json"
        target.write_text('{"kept": true}', encoding="utf8")
        with patch.object(prefs, "FILE", target), patch.object(prefs.os, "replace", side_effect=PermissionError("locked")), \
                patch.object(prefs.time, "sleep"), patch("core.log.write") as logged:
            prefs.save({"kept": False})
        self.assertEqual(json.loads(target.read_text()), {"kept": True})
        self.assertTrue(logged.called)
        self.assertFalse(list(self.root.glob("*.tmp")))

    def test_bad_settings_edited_after_good_read_are_preserved_before_save(self):
        target = self.root / "settings.json"
        target.write_text('{"kept": true}', encoding="utf8")
        with patch.object(prefs, "FILE", target):
            self.assertTrue(prefs.load()["kept"])
            target.write_text('{"unfinished personal edit":', encoding="utf8")
            prefs.set_("new", 1)
        backups = list(self.root.glob("settings.json.unreadable*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), '{"unfinished personal edit":')
        self.assertEqual(json.loads(target.read_text()), {"kept": True, "new": 1})

    def test_failed_profile_swap_preserves_previous_settings(self):
        with patch.object(profiles, "DIR", self.root):
            path = profiles.save("Personal", installer.Options(provider=2))
            old = path.read_bytes()
            with patch("os.replace", side_effect=PermissionError("locked")):
                with self.assertRaises(OSError):
                    profiles.save("Personal", installer.Options(provider=3))
            self.assertEqual(path.read_bytes(), old)
        self.assertFalse(list(self.root.glob("*.tmp")))

    def test_sanitized_profile_name_cannot_overwrite_a_different_profile(self):
        with patch.object(profiles, "DIR", self.root):
            path = profiles.save("Personal/Quality", installer.Options(provider=2))
            old = path.read_bytes()
            with self.assertRaisesRegex(ValueError, "conflict"):
                profiles.save("Personal?Quality", installer.Options(provider=3))
            self.assertEqual(path.read_bytes(), old)
            with self.assertRaises(ValueError):
                profiles.load("Personal?Quality")
            with self.assertRaises(ValueError):
                profiles.delete("Personal?Quality")
            self.assertEqual(path.read_bytes(), old)

    def test_concurrent_profile_name_collisions_keep_the_first_complete_profile(self):
        code = r'''
import json, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from core import installer, prefs, profiles
folder, worker = Path(sys.argv[2]), int(sys.argv[3])
prefs.FILE, profiles.DIR = folder / "settings.json", folder / "profiles"
original_replace = profiles.os.replace
def slow_replace(*args):
    time.sleep(.08)
    return original_replace(*args)
profiles.os.replace = slow_replace
(folder / f"ready-{worker}").touch()
while not (folder / "start").exists():
    time.sleep(.005)
name = "Personal" + ("?", "/", "<")[worker] + "Quality"
try:
    profiles.save(name, installer.Options(provider=worker))
    result = "saved"
except ValueError:
    result = "preserved"
(folder / f"result-{worker}").write_text(result)
'''
        children = [subprocess.Popen([sys.executable, "-c", code, str(APP), str(self.root), str(i)],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for i in range(3)]
        try:
            import time
            deadline = time.monotonic() + 20
            while len(list(self.root.glob("ready-*"))) < 3:
                if time.monotonic() >= deadline:
                    self.fail("profile writers did not start")
                time.sleep(.01)
            (self.root / "start").touch()
            for child in children:
                output, error = child.communicate(timeout=30)
                self.assertEqual(child.returncode, 0, output + error)
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.communicate()
        results = [path.read_text() for path in self.root.glob("result-*")]
        self.assertEqual(results.count("saved"), 1)
        self.assertEqual(results.count("preserved"), 2)

    def test_settings_and_layer_lists_survive_concurrent_process_writes(self):
        code = r'''
import sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from core import autotune, prefs
folder, worker = Path(sys.argv[2]), int(sys.argv[3])
prefs.FILE = folder / "settings.json"
original_read = prefs._read
def slow_read():
    answer = original_read()
    time.sleep(.003)
    return answer
prefs._read = slow_read
(folder / f"ready-{worker}").touch()
while not (folder / "start").exists():
    time.sleep(.005)
for index in range(12):
    name = f"{worker}-{index}"
    prefs.set_(name, index)
    prefs.add_vulkan_game(name)
    prefs.add_openxr_game(name)
    autotune.remember(name, autotune.Measured("feeder", 75, fps=60))
'''
        children = [subprocess.Popen([sys.executable, "-c", code, str(APP), str(self.root), str(i)],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    for i in range(3)]
        try:
            import time
            deadline = time.monotonic() + 20
            while len(list(self.root.glob("ready-*"))) < len(children):
                if time.monotonic() >= deadline:
                    self.fail("settings writers did not start")
                time.sleep(.01)
            (self.root / "start").touch()
            for child in children:
                stdout, stderr = child.communicate(timeout=30)
                self.assertEqual(child.returncode, 0, stdout + stderr)
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.communicate()
        data = json.loads((self.root / "settings.json").read_text())
        wanted = {f"{worker}-{index}" for worker in range(3) for index in range(12)}
        self.assertEqual(wanted, set(data) - {"vulkan_games", "openxr_games", "autotune"})
        self.assertEqual(wanted, set(data["vulkan_games"]))
        self.assertEqual(wanted, set(data["openxr_games"]))
        self.assertEqual(wanted, set(data["autotune"]))

    def _own_fg_record(self, live=b"placed DLL", original=None):
        path = self.root / "version.dll"
        path.write_bytes(live)
        files, hashes = [path.name], {path.name: net.sha256(path)}
        if original is not None:
            backup = path.with_name(path.name + installer.BACKUP_SUFFIX)
            backup.write_bytes(original)
            files.append(backup.name)
            hashes[backup.name] = net.sha256(backup)
        return path, {"own_fg": {"recipe": "sm86", "files": [path.name]},
                      "files": files, "hashes": hashes}

    def test_turning_off_own_fg_preserves_later_edits_and_restores_original(self):
        path, record = self._own_fg_record(original=b"game original")
        path.write_bytes(b"personal replacement")
        removed = ownfg.remove_leftovers(self.root, record, "")
        self.assertEqual(path.read_bytes(), b"game original")
        self.assertEqual(path.with_name(path.name + ".dlss5-aio-displaced").read_bytes(), b"personal replacement")
        self.assertIn(path.name, removed)

    def test_turning_off_own_fg_refuses_changed_original_backup_before_touching_live(self):
        path, record = self._own_fg_record(original=b"game original")
        backup = path.with_name(path.name + installer.BACKUP_SUFFIX)
        backup.write_bytes(b"personal backup edit")
        with self.assertRaises(OSError):
            ownfg.remove_leftovers(self.root, record, "")
        self.assertEqual(path.read_bytes(), b"placed DLL")
        self.assertEqual(backup.read_bytes(), b"personal backup edit")

    def test_turning_off_legacy_own_fg_preserves_unproven_live_file(self):
        path, record = self._own_fg_record()
        record.pop("hashes")
        self.assertEqual(ownfg.remove_leftovers(self.root, record, ""), [])
        self.assertEqual(path.read_bytes(), b"placed DLL")

    def test_own_fg_option_off_retry_recognizes_an_already_restored_original(self):
        path, record = self._own_fg_record(original=b"game original")
        backup = path.with_name(path.name + installer.BACKUP_SUFFIX)
        backup.replace(path)
        removed = ownfg.remove_leftovers(self.root, record, "")
        self.assertEqual(path.read_bytes(), b"game original")
        self.assertIn(path.name, removed)
        self.assertIn(backup.name, removed)

    def test_own_fg_option_off_drops_checkpointed_ownership_before_later_uninstall(self):
        path, record = self._own_fg_record(original=b"game original")
        record["files"] = [name.upper() for name in record["files"]]
        record["hashes"] = {name.upper(): digest for name, digest in record["hashes"].items()}
        record.update(path=dlss.OPTI, complete=True)
        (self.root / installer.MANIFEST).write_text(json.dumps(record), encoding="utf8")
        game = games.Game("Fixture", self.root, exe=self.root / "game.exe", bitness=64, api="DX12")
        options = installer.Options(path=dlss.OPTI, own_fg="", gpu_pref=False)
        report = installer.Report(game_root=self.root, written=list(record["files"]),
                                  preinstalled=set(record["files"]), hashes=dict(record["hashes"]))
        report.checkpoint = lambda: installer._write_manifest(self.root, game, options, report, "", "stable", False)
        installer._place_own_fg(self.root, options, report, lambda *_: None, lambda *_: None)
        self.assertEqual(path.read_bytes(), b"game original")
        self.assertTrue(installer._write_manifest(self.root, game, options, report, "", "stable", True))
        installer.uninstall(game)
        self.assertTrue(path.is_file(), "the restored original was recorded as owned and deleted")
        self.assertEqual(path.read_bytes(), b"game original")

    def test_own_fg_store_rejects_unknown_recipe_and_extra_destinations(self):
        source = self.root / "picked.dll"
        source.write_bytes(b"personal file")
        with patch.object(prefs, "FILE", self.root / "profile" / "settings.json"):
            for key, files in (("../outside", {"version.dll": source}),
                               ("sm86", {"../outside.dll": source})):
                with self.subTest(key=key), self.assertRaises(ownfg.OwnFgError):
                    ownfg.store(key, files)
        self.assertFalse((self.root / "profile").exists())

    def test_own_fg_failed_staging_preserves_previous_set(self):
        profile = self.root / "profile"
        old = profile / "own-fg" / "sm86"
        old.mkdir(parents=True)
        (old / "version.dll").write_bytes(b"stored DLL")
        (old / "dlssg_sm86.ini").write_bytes(b"stored settings")
        source = self.root / "picked.dll"
        source.write_bytes(b"new DLL")
        with patch.object(prefs, "FILE", profile / "settings.json"), \
                patch.object(installer, "_atomic_copy", side_effect=OSError("disk full")), \
                self.assertRaises(OSError):
            ownfg.store("sm86", {"version.dll": source, "dlssg_sm86.ini": source})
        self.assertEqual((old / "version.dll").read_bytes(), b"stored DLL")
        self.assertEqual((old / "dlssg_sm86.ini").read_bytes(), b"stored settings")

    def test_forgetting_own_fg_handles_a_malformed_preference_without_touching_other_files(self):
        folder = ownfg.store_dir("sm86")
        folder.mkdir(parents=True)
        (folder / "version.dll").write_bytes(b"tool stored copy")
        other = self.root / "personal.txt"
        other.write_bytes(b"keep")
        prefs.set_(ownfg.FORGOTTEN, True)
        ownfg.forget("sm86")
        self.assertFalse(folder.exists())
        self.assertEqual(prefs.get(ownfg.FORGOTTEN), ["sm86"])
        self.assertEqual(other.read_bytes(), b"keep")

    def test_tune_action_uses_recorded_write_boundary_and_does_not_claim_failed_setting(self):
        control = GameControl()
        control.game = games.Game("Fixture", self.root, exe=self.root / "game.exe", bitness=64, api="DX11")
        control.busy, control.route = False, dlss.FEEDER
        control._tune = autotune.Suggestion(70)
        control.settings, control.write, control.refresh = {"workres": 100}, Mock(), Mock()
        with patch.object(installer, "apply_tune", side_effect=OSError("locked")) as apply, \
                patch("core.ui.ctl_game.feedcfg.write", side_effect=AssertionError("unsafe direct write")):
            control.apply_tune()
        apply.assert_called_once_with(control.game, dlss.FEEDER, 70, on_log=control.write)
        self.assertEqual(control.settings["workres"], 100)
        self.assertIsNotNone(control._tune)

    def test_tune_action_refuses_while_another_job_is_busy(self):
        control = GameControl()
        control.busy, control.game, control._tune = True, object(), autotune.Suggestion(70)
        with patch.object(installer, "apply_tune") as apply:
            control.apply_tune()
        apply.assert_not_called()

    def test_autotune_history_ignores_malformed_settings_rows(self):
        with patch.object(prefs, "FILE", self.root / "settings.json"):
            prefs.set_(autotune.HISTORY_KEY, ["invalid"])
            self.assertEqual(autotune.history(self.root), [])
            autotune.remember(self.root, autotune.Measured("feeder", 75, fps=60))
            self.assertEqual(len(autotune.history(self.root)), 1)
            prefs.set_(autotune.HISTORY_KEY, {str(self.root).lower(): 3})
            autotune.remember(self.root, autotune.Measured("feeder", 75, fps=60))
            self.assertEqual(len(autotune.history(self.root)), 1)

    def test_autotune_ignores_nonfinite_log_numbers_and_history_timestamps(self):
        self.assertIsNone(autotune._num("9" * 400))
        self.assertEqual(autotune._points([{"resolution": 75, "fps": float("inf")}]), [])
        histories = {str(index): [{"at": float("inf")}] for index in range(autotune.MAX_GAMES)}
        prefs.set_(autotune.HISTORY_KEY, histories)
        autotune.remember(self.root, autotune.Measured("feeder", 75, fps=60))
        self.assertEqual(len(prefs.get(autotune.HISTORY_KEY)), autotune.MAX_GAMES)

    def _emulator(self):
        profile = next(p for p in emulators.PROFILES if p.key == "duckstation")
        exe = self.root / "duckstation.exe"
        exe.touch()
        (self.root / "portable.txt").touch()
        config = self.root / "settings.ini"
        self.enterContext(patch.dict(emulators._BACKENDS, {
            "duckstation": replace(emulators._BACKENDS["duckstation"], locate=lambda _exe: [config])}))
        config.write_bytes(b"[GPU]\r\nRenderer = Vulkan\r\n[Audio]\r\nVolume = 75\r\n")
        return profile, exe, config

    def test_emulator_restore_keeps_later_non_backend_settings(self):
        profile, exe, config = self._emulator()
        emulators.set_backend(profile, exe)
        config.write_bytes(config.read_bytes().replace(b"Volume = 75", b"Volume = 42"))
        emulators.restore_backend(profile, exe)
        self.assertEqual(config.read_bytes(), b"[GPU]\r\nRenderer = Vulkan\r\n[Audio]\r\nVolume = 42\r\n")

    def test_emulator_restore_refuses_changed_backup_and_retains_evidence(self):
        profile, exe, config = self._emulator()
        emulators.set_backend(profile, exe)
        before = config.read_bytes()
        backup = config.with_name(config.name + emulators.BACKUP_SUFFIX)
        backup.write_bytes(b"personal backup edit")
        with self.assertRaises(OSError):
            emulators.restore_backend(profile, exe)
        self.assertEqual(config.read_bytes(), before)
        self.assertEqual(backup.read_bytes(), b"personal backup edit")

    def test_emulator_failed_config_swap_preserves_original_and_backup(self):
        profile, exe, config = self._emulator()
        original = config.read_bytes()
        original_copy = installer._atomic_copy
        def refuse_config(source, destination):
            if destination == config:
                raise OSError("locked config")
            return original_copy(source, destination)
        with patch.object(installer, "_atomic_copy", side_effect=refuse_config), self.assertRaises(OSError):
            emulators.set_backend(profile, exe)
        self.assertEqual(config.read_bytes(), original)
        self.assertEqual(config.with_name(config.name + emulators.BACKUP_SUFFIX).read_bytes(), original)

    def test_emulator_restore_error_reaches_caller(self):
        profile, exe, config = self._emulator()
        emulators.set_backend(profile, exe)
        before = config.read_bytes()
        with patch.object(installer, "_atomic_copy", side_effect=OSError("locked config")), self.assertRaises(OSError):
            emulators.restore_backend(profile, exe)
        self.assertEqual(config.read_bytes(), before)
        self.assertTrue(config.with_name(config.name + emulators.BACKUP_SUFFIX).is_file())

    def test_emulator_restore_keeps_later_backend_choice_and_recovery_evidence(self):
        profile, exe, config = self._emulator()
        emulators.set_backend(profile, exe)
        config.write_bytes(config.read_bytes().replace(b"D3D12", b"OpenGL"))
        before = config.read_bytes()
        with self.assertRaises(OSError):
            emulators.restore_backend(profile, exe)
        self.assertEqual(config.read_bytes(), before)
        self.assertTrue(config.with_name(config.name + emulators.BACKUP_SUFFIX).is_file())
        self.assertTrue(config.with_name(config.name + emulators.BACKEND_RECORD_SUFFIX).is_file())

    def test_emulator_unproven_legacy_backup_is_preserved(self):
        profile, exe, config = self._emulator()
        backup = config.with_name(config.name + emulators.BACKUP_SUFFIX)
        backup.write_bytes(b"untracked old settings")
        original = config.read_bytes()
        for action in (emulators.set_backend, emulators.restore_backend):
            with self.subTest(action=action.__name__), self.assertRaises(OSError):
                action(profile, exe)
            self.assertEqual(config.read_bytes(), original)
            self.assertEqual(backup.read_bytes(), b"untracked old settings")

    def test_emulator_retry_finishes_after_interrupted_record_cleanup(self):
        profile, exe, config = self._emulator()
        emulators.set_backend(profile, exe)
        config.write_bytes(config.read_bytes().replace(b"Volume = 75", b"Volume = 42"))
        record = config.with_name(config.name + emulators.BACKEND_RECORD_SUFFIX)
        original_unlink = Path.unlink
        def refuse_record(path, *args, **kwargs):
            if path == record:
                raise OSError("locked record")
            return original_unlink(path, *args, **kwargs)
        with patch.object(Path, "unlink", refuse_record), self.assertRaises(OSError):
            emulators.restore_backend(profile, exe)
        self.assertTrue(record.is_file())
        emulators.restore_backend(profile, exe)
        self.assertFalse(record.exists())
        self.assertIn(b"Volume = 42", config.read_bytes())
        self.assertIn(b"Renderer = Vulkan", config.read_bytes())

    def test_emulator_six_config_formats_round_trip_without_losing_bytes(self):
        samples = {
            "duckstation": b"[GPU]\r\nRenderer = Vulkan ; keep\r\n[Audio]\r\nVolume = 75\r\n",
            "pcsx2": b"[EmuCore/GS]\nRenderer = 14\nupscale_multiplier = 2\n",
            "dolphin": b"[Core]\nGFXBackend = Vulkan\nCPUThread = True\n",
            "ppsspp": b"[Graphics]\nGraphicsBackend = 3 (VULKAN)\nInternalResolution = 3\n",
            "xenia": b'[GPU]\ngpu = "vulkan"\nvsync = true\n',
            "retroarch": b'video_driver = "vulkan"\naudio_driver = "\xff"\n',
        }
        for key, original in samples.items():
            with self.subTest(key=key):
                folder = self.root / key
                folder.mkdir()
                config = folder / "settings.cfg"
                config.write_bytes(original)
                profile = next(p for p in emulators.PROFILES if p.key == key)
                spec = replace(emulators._BACKENDS[key], locate=lambda _exe: [config])
                with patch.dict(emulators._BACKENDS, {key: spec}):
                    emulators.set_backend(profile, folder / "emulator.exe")
                    emulators.restore_backend(profile, folder / "emulator.exe")
                self.assertEqual(config.read_bytes(), original)
                self.assertEqual(list(folder.iterdir()), [config])

    def test_comparison_export_names_do_not_overwrite_an_earlier_export(self):
        with patch.object(compare.time, "strftime", return_value="fixed-second"):
            first = compare.export_name(self.root)
            first.write_bytes(b"personal comparison")
            second = compare.export_name(self.root)
        self.assertNotEqual(first, second)
        self.assertEqual(first.read_bytes(), b"personal comparison")

    def test_comparison_close_cancels_pending_export_and_resize_callbacks(self):
        control = compareui.CompareWindow.__new__(compareui.CompareWindow)
        control._fit_job, control._export_job = "fit", "export"
        control.win = SimpleNamespace(after_cancel=Mock(), destroy=Mock())
        control.close()
        self.assertCountEqual([call.args[0] for call in control.win.after_cancel.call_args_list], ["fit", "export"])
        control.win.destroy.assert_called_once()

    def test_bug_report_redacts_private_game_title_before_constructing_browser_url(self):
        from core import diagnose, reportui
        from urllib.parse import parse_qs, urlsplit
        control = uiapp.App.__new__(uiapp.App)
        control.game = games.Game(str(self.root / "PrivateGame"), self.root)
        control.route, control._last_diag, control._last_crash = dlss.FEEDER, None, None
        control.root = SimpleNamespace()
        control.shell = SimpleNamespace(page=SimpleNamespace(name="game"))
        with patch.object(reportui, "ask", return_value={}), \
                patch.object(diagnose, "issue_body", return_value="reviewed details"), \
                patch.object(uiapp.gpu, "detect", return_value=(None, None)), \
                patch.object(uiapp.gpu, "driver_version", return_value=None), \
                patch.object(uiapp.App, "_reprint_answered"), \
                patch.object(uiapp.webbrowser, "open") as browser:
            control.report_bug()
        title = parse_qs(urlsplit(browser.call_args.args[0]).query)["title"][0]
        self.assertNotIn(str(self.root), title)
        self.assertIn("<local>", title)

    def test_failed_bug_report_review_never_opens_a_prefilled_browser_url(self):
        from core import reportui
        control = uiapp.App.__new__(uiapp.App)
        control.game = None
        control.root = SimpleNamespace()
        control.shell = SimpleNamespace(page=None, error=Mock())
        with patch.object(reportui, "ask", side_effect=RuntimeError("unavailable Tk")), \
                patch.object(uiapp.gpu, "detect", return_value=(None, None)), \
                patch.object(uiapp.gpu, "driver_version", return_value=None), \
                patch.object(uiapp.log, "exception"), \
                patch.object(uiapp.webbrowser, "open") as browser:
            control.report_bug()
        browser.assert_not_called()
        control.shell.error.assert_called_once()


if __name__ == "__main__":
    unittest.main()
