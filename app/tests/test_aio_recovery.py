"""Real filesystem recovery checks for failed writes, later edits and untrusted records."""
import json
import os
from pathlib import Path
import subprocess
import sys
import os
os.environ.setdefault("DLSS5_AIO_OFFLINE", "1")   # tests never reach the publishers
import tempfile
import unittest
from unittest.mock import patch

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
from core import feedcfg, games, gpupref, installer, net, prefs


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aio-recovery-")
        self.base = Path(self.temp.name)
        self.root = self.base / "game"
        self.root.mkdir()
        self.game = games.Game("Fixture", self.root, bitness=64, api="DX11")
        self.profile = patch.object(prefs, "FILE", self.base / "profile" / "settings.json")
        self.profile.start()
        self.rep = installer.Report(game_root=self.root)
        self.rep.checkpoint = lambda: installer._write_manifest(
            self.root, self.game, installer.Options(path=installer.NATIVE), self.rep,
            "dxgi.dll", installer.STABLE, False)
        self.source = self.base / "component.dll"
        self.source.write_bytes(b"NEW COMPLETE COMPONENT")
        self.destination = self.root / "dxgi.dll"

    def tearDown(self):
        self.profile.stop()
        self.temp.cleanup()

    def record(self, files=(), **extra):
        data = dict(files=list(files), hashes={})
        data.update(extra)
        (self.root / installer.MANIFEST).write_text(json.dumps(data))

    def test_backup_failure_never_replaces_original(self):
        self.destination.write_bytes(b"GAME ORIGINAL")
        real = installer.shutil.copyfile
        def failed(src, dst, *args, **kwargs):
            Path(dst).write_bytes(b"PARTIAL BACKUP")
            raise OSError("injected backup write failure")
        with patch.object(installer.shutil, "copyfile", side_effect=failed):
            with self.assertRaises(OSError):
                installer._copy(self.source, self.destination, self.rep, self.root)
        self.assertEqual(self.destination.read_bytes(), b"GAME ORIGINAL")
        self.assertFalse(Path(str(self.destination) + installer.BACKUP_SUFFIX).exists())
        self.assertTrue((self.root / installer.MANIFEST).is_file())
        self.assertFalse(list(self.root.glob("*.aio-part")))

    def test_interrupted_copy_leaves_existing_destination_whole(self):
        self.destination.write_bytes(b"GAME ORIGINAL")
        def failed(src, dst):
            Path(dst).write_bytes(b"PARTIAL")
            raise OSError("injected interrupted write")
        with patch.object(installer.shutil, "copyfile", side_effect=failed):
            with self.assertRaises(OSError):
                installer._atomic_copy(self.source, self.destination)
        self.assertEqual(self.destination.read_bytes(), b"GAME ORIGINAL")
        self.assertFalse(list(self.root.glob("*.aio-part")))

    def test_short_copy_fails_verification(self):
        self.destination.write_bytes(b"GAME ORIGINAL")
        with patch.object(installer.shutil, "copyfile", side_effect=lambda src, dst: Path(dst).write_bytes(b"SHORT")):
            with self.assertRaisesRegex(OSError, "byte verification"):
                installer._atomic_copy(self.source, self.destination)
        self.assertEqual(self.destination.read_bytes(), b"GAME ORIGINAL")

    def test_source_change_during_staging_is_refused(self):
        self.destination.write_bytes(b"GAME ORIGINAL")
        real = installer.shutil.copyfile
        def raced(src, dst):
            real(src, dst)
            Path(src).write_bytes(b"CHANGED SOURCE")
        with patch.object(installer.shutil, "copyfile", side_effect=raced):
            with self.assertRaisesRegex(OSError, "byte verification"):
                installer._atomic_copy(self.source, self.destination)
        self.assertEqual(self.destination.read_bytes(), b"GAME ORIGINAL")

    def test_external_change_during_staging_is_preserved(self):
        self.destination.write_bytes(b"GAME ORIGINAL")
        real = installer.shutil.copyfile
        def raced(src, dst):
            real(src, dst)
            self.destination.write_bytes(b"LATER PERSONAL EDIT")
        with patch.object(installer.shutil, "copyfile", side_effect=raced):
            with self.assertRaisesRegex(OSError, "changed while"):
                installer._atomic_copy(self.source, self.destination)
        self.assertEqual(self.destination.read_bytes(), b"LATER PERSONAL EDIT")

    def test_failed_checkpoint_blocks_write(self):
        self.destination.write_bytes(b"GAME ORIGINAL")
        self.rep.checkpoint = lambda: False
        with self.assertRaisesRegex(OSError, "recovery record"):
            installer._copy(self.source, self.destination, self.rep, self.root)
        self.assertEqual(self.destination.read_bytes(), b"GAME ORIGINAL")

    def test_vanished_payload_is_incomplete_without_guessing_its_cause(self):
        installer._copy(self.source, self.destination, self.rep, self.root)
        self.destination.unlink()
        with self.assertRaisesRegex(installer.InstallError, "Installation is incomplete"):
            installer._verify_written(self.root, self.rep, lambda *_: None)
        data = json.loads((self.root / installer.MANIFEST).read_text())
        self.assertIs(data["complete"], False)
        self.assertNotIn("false positive", data["warnings"][0])
        self.assertNotIn("exclusions", data["warnings"][0])

    def test_reinstall_keeps_later_personal_bytes(self):
        installer._copy(self.source, self.destination, self.rep, self.root)
        self.destination.write_bytes(b"PERSONAL AFTER INSTALL")
        rep = installer.Report(game_root=self.root, preinstalled={"dxgi.dll"})
        installer._copy(self.source, self.destination, rep, self.root)
        saved = list(self.root.glob("dxgi.dll.dlss5-aio-displaced*"))
        self.assertEqual([p.read_bytes() for p in saved], [b"PERSONAL AFTER INSTALL"])

    def test_existing_untracked_backup_does_not_lose_current_bytes(self):
        self.destination.write_bytes(b"CURRENT PERSONAL")
        Path(str(self.destination) + installer.BACKUP_SUFFIX).write_bytes(b"EARLIER ORIGINAL")
        installer._copy(self.source, self.destination, self.rep, self.root)
        self.assertIn(b"CURRENT PERSONAL", [p.read_bytes() for p in self.root.glob("*.dlss5-aio-displaced*")])
        data = json.loads((self.root / installer.MANIFEST).read_text())
        self.assertNotIn(self.destination.name + installer.BACKUP_SUFFIX, data["hashes"])

    def test_uninstall_preserves_later_edits_and_unowned_helper_files(self):
        installer._copy(self.source, self.destination, self.rep, self.root)
        self.destination.write_bytes(b"LATER PERSONAL")
        host = self.root / installer.HOST_DIR
        host.mkdir()
        (host / "personal.txt").write_bytes(b"KEEP")
        installer.uninstall(self.game)
        self.assertFalse(self.destination.exists())
        self.assertEqual((host / "personal.txt").read_bytes(), b"KEEP")
        self.assertEqual(next(self.root.glob("dxgi.dll.dlss5-aio-displaced*")).read_bytes(), b"LATER PERSONAL")

    def test_uninstall_restores_original_and_preserves_later_edit(self):
        self.destination.write_bytes(b"GAME ORIGINAL")
        installer._copy(self.source, self.destination, self.rep, self.root)
        self.destination.write_bytes(b"LATER PERSONAL")
        installer.uninstall(self.game)
        self.assertEqual(self.destination.read_bytes(), b"GAME ORIGINAL")
        self.assertEqual(next(self.root.glob("dxgi.dll.dlss5-aio-displaced*")).read_bytes(), b"LATER PERSONAL")

    def test_no_manifest_does_not_delete_game_files(self):
        for name in ("nvngx_dlss.dll", "ReShade.ini", "d3d9.dll"):
            (self.root / name).write_bytes(b"USER OWN")
        with self.assertRaisesRegex(installer.InstallError, "No install record"):
            installer.uninstall(self.game)
        for name in ("nvngx_dlss.dll", "ReShade.ini", "d3d9.dll"):
            self.assertEqual((self.root / name).read_bytes(), b"USER OWN")

    def test_malformed_record_does_not_mutate_files(self):
        self.destination.write_bytes(b"USER OWN")
        (self.root / installer.MANIFEST).write_text("[]")
        with self.assertRaises(installer.InstallError):
            installer.uninstall(self.game)
        self.assertEqual(self.destination.read_bytes(), b"USER OWN")

    def test_sidelined_manifest_cannot_escape_game(self):
        outside = self.base / "outside.txt"
        outside.write_bytes(b"CURRENT OUTSIDE")
        moved = Path(str(outside) + installer.SIDELINE_SUFFIX)
        moved.write_bytes(b"EARLIER OUTSIDE")
        self.record(sidelined=["../outside.txt"], sidelined_hashes={"../outside.txt": net.sha256(moved)})
        installer.uninstall(self.game)
        self.assertEqual(outside.read_bytes(), b"CURRENT OUTSIDE")
        self.assertEqual(moved.read_bytes(), b"EARLIER OUTSIDE")

    def test_failed_restore_retains_manifest_and_original_backup(self):
        self.destination.write_bytes(b"GAME ORIGINAL")
        installer._copy(self.source, self.destination, self.rep, self.root)
        original = installer._atomic_copy
        def failed(src, dst):
            if str(src).endswith(installer.BACKUP_SUFFIX):
                raise PermissionError("injected restore refusal")
            return original(src, dst)
        with patch.object(installer, "_atomic_copy", side_effect=failed):
            with self.assertRaisesRegex(installer.InstallError, "incomplete"):
                installer.uninstall(self.game)
        self.assertEqual(self.destination.read_bytes(), b"NEW COMPLETE COMPONENT")
        self.assertEqual(Path(str(self.destination) + installer.BACKUP_SUFFIX).read_bytes(), b"GAME ORIGINAL")
        self.assertTrue((self.root / installer.MANIFEST).is_file())
        installer.uninstall(self.game)
        self.assertEqual(self.destination.read_bytes(), b"GAME ORIGINAL")

    def test_tampered_backup_is_never_restored(self):
        self.destination.write_bytes(b"GAME ORIGINAL")
        installer._copy(self.source, self.destination, self.rep, self.root)
        backup = Path(str(self.destination) + installer.BACKUP_SUFFIX)
        backup.write_bytes(b"CHANGED BACKUP")
        with self.assertRaisesRegex(installer.InstallError, "incomplete"):
            installer.uninstall(self.game)
        self.assertEqual(self.destination.read_bytes(), b"NEW COMPLETE COMPONENT")
        self.assertEqual(backup.read_bytes(), b"CHANGED BACKUP")

    def test_reinstall_refuses_missing_recorded_original_backup(self):
        self.destination.write_bytes(b"GAME ORIGINAL")
        installer._copy(self.source, self.destination, self.rep, self.root)
        Path(str(self.destination) + installer.BACKUP_SUFFIX).unlink()
        previous_record = (self.root / installer.MANIFEST).read_bytes()
        rep = installer.Report(game_root=self.root, preinstalled={self.destination.name})
        self.source.write_bytes(b"NEWER COMPONENT")
        with self.assertRaisesRegex(OSError, "original backup.*missing"):
            installer._copy(self.source, self.destination, rep, self.root)
        self.assertEqual(self.destination.read_bytes(), b"NEW COMPLETE COMPONENT")
        self.assertEqual((self.root / installer.MANIFEST).read_bytes(), previous_record)

    def test_legacy_unknown_files_stay_and_original_backup_is_retained(self):
        self.destination.write_bytes(b"LEGACY COMPONENT")
        backup = Path(str(self.destination) + installer.BACKUP_SUFFIX)
        backup.write_bytes(b"GAME ORIGINAL")
        unknown = self.root / "legacy.addon64"
        unknown.write_bytes(b"UNPROVEN")
        self.record([self.destination.name, backup.name, unknown.name])
        with self.assertRaisesRegex(installer.InstallError, "incomplete"):
            installer.uninstall(self.game)
        self.assertEqual(self.destination.read_bytes(), b"GAME ORIGINAL")
        self.assertEqual(backup.read_bytes(), b"GAME ORIGINAL")
        self.assertEqual(unknown.read_bytes(), b"UNPROVEN")
        self.assertEqual(next(self.root.glob("dxgi.dll.dlss5-aio-displaced*")).read_bytes(), b"LEGACY COMPONENT")

    def test_process_crash_after_replace_can_restore_from_durable_record(self):
        self.destination.write_bytes(b"GAME ORIGINAL")
        code = '''
import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from core import installer as i,games,prefs
root=Path(sys.argv[2]); src=Path(sys.argv[3]); prefs.FILE=root.parent/'childprofile'/'settings.json'
g=games.Game('Fixture',root,bitness=64,api='DX11');rep=i.Report(game_root=root)
rep.checkpoint=lambda:i._write_manifest(root,g,i.Options(path=i.NATIVE),rep,'dxgi.dll',i.STABLE,False)
real=i.os.replace
def crash(src,dst):
    real(src,dst)
    if Path(dst).name=='dxgi.dll':os._exit(97)
i.os.replace=crash
i._copy(src,root/'dxgi.dll',rep,root)
'''
        process = subprocess.run([sys.executable, "-c", code, str(APP), str(self.root), str(self.source)], capture_output=True, text=True)
        self.assertEqual(process.returncode, 97, process.stderr)
        self.assertEqual(self.destination.read_bytes(), b"NEW COMPLETE COMPONENT")
        data = json.loads((self.root / installer.MANIFEST).read_text())
        self.assertEqual(data["hashes"]["dxgi.dll"], net.sha256(self.source))
        installer.uninstall(self.game)
        self.assertEqual(self.destination.read_bytes(), b"GAME ORIGINAL")

    def test_config_failure_is_isolated(self):
        config = self.root / "ReShade.ini"
        config.write_bytes(b"PERSONAL CONFIG")
        def broken(staged):
            (staged / "ReShade.ini").write_bytes(b"PARTIAL")
            raise OSError("injected config failure")
        with self.assertRaises(OSError):
            installer._configure(self.root, self.rep, broken)
        self.assertEqual(config.read_bytes(), b"PERSONAL CONFIG")

    def test_config_false_result_never_commits_partial_output(self):
        config = self.root / "ReShade.ini"
        config.write_bytes(b"PERSONAL CONFIG")
        def broken(staged):
            (staged / "ReShade.ini").write_bytes(b"PARTIAL")
            return False
        self.assertIs(installer._configure(self.root, self.rep, broken), False)
        self.assertEqual(config.read_bytes(), b"PERSONAL CONFIG")

    def test_config_change_during_merge_is_preserved_in_place(self):
        config = self.root / "ReShade.ini"
        config.write_bytes(b"PERSONAL CONFIG")
        def raced(staged):
            config.write_bytes(b"LATER PERSONAL CONFIG")
            (staged / "ReShade.ini").write_bytes(b"NEW CONFIG")
        with self.assertRaisesRegex(OSError, "configuration was being prepared"):
            installer._configure(self.root, self.rep, raced)
        self.assertEqual(config.read_bytes(), b"LATER PERSONAL CONFIG")

    def test_repeated_config_merges_do_not_create_an_original_of_our_own_output(self):
        def configure(staged, text):
            (staged / "ReShade.ini").write_text(text)
        installer._configure(self.root, self.rep, configure, "FIRST OUTPUT")
        installer._configure(self.root, self.rep, configure, "SECOND OUTPUT")
        self.assertFalse((self.root / ("ReShade.ini" + installer.BACKUP_SUFFIX)).exists())
        installer.uninstall(self.game)
        self.assertFalse((self.root / "ReShade.ini").exists())

    def test_preexisting_config_is_restored_exactly_after_multiple_merges(self):
        config = self.root / "ReShade.ini"
        config.write_bytes(b"PERSONAL ORIGINAL CONFIG")
        def configure(staged, text):
            (staged / "ReShade.ini").write_text(text)
        installer._configure(self.root, self.rep, configure, "FIRST OUTPUT")
        installer._configure(self.root, self.rep, configure, "SECOND OUTPUT")
        installer.uninstall(self.game)
        self.assertEqual(config.read_bytes(), b"PERSONAL ORIGINAL CONFIG")

    def test_install_root_cannot_escape_selected_game(self):
        outside = self.base / "another-folder"
        outside.mkdir()
        self.game.install_root = outside
        with self.assertRaises(net.OutsideError):
            installer.uninstall(self.game)

    def test_remix_restores_original_key_and_retains_later_other_settings(self):
        conf = self.root / "rtx.conf"
        key = remix_key = "rtx.neuralUplift.enable"
        conf.write_bytes(b"quality = 2\r\nrtx.neuralUplift.enable = False\r\n")
        self.rep.remix = {"key": key, "conf_final_newline": True}
        installer._remix_option(conf, key, self.rep, self.root)
        conf.write_bytes(conf.read_bytes() + b"personal = 42\r\n")
        self.assertTrue(installer._restore_remix(conf, self.rep.remix))
        self.assertEqual(conf.read_bytes(), b"quality = 2\r\nrtx.neuralUplift.enable = False\r\npersonal = 42\r\n")

    def test_remix_later_key_edit_is_preserved(self):
        conf = self.root / "rtx.conf"
        key = "rtx.neuralUplift.enable"
        conf.write_bytes(b"quality = 2\n")
        self.rep.remix = {"key": key, "conf_final_newline": True}
        installer._remix_option(conf, key, self.rep, self.root)
        conf.write_bytes(b"quality = 2\nrtx.neuralUplift.enable = False\n")
        self.assertFalse(installer._restore_remix(conf, self.rep.remix))
        self.assertEqual(conf.read_bytes(), b"quality = 2\nrtx.neuralUplift.enable = False\n")

    def test_remix_original_missing_final_newline_is_restored(self):
        conf = self.root / "rtx.conf"
        key = "rtx.neuralUplift.enable"
        conf.write_bytes(b"quality = 2")
        self.rep.remix = {"key": key, "conf_final_newline": False}
        installer._remix_option(conf, key, self.rep, self.root)
        installer._restore_remix(conf, self.rep.remix)
        self.assertEqual(conf.read_bytes(), b"quality = 2")

    def test_remix_reinstall_keeps_first_original_option(self):
        conf = self.root / "rtx.conf"
        key = "rtx.neuralUplift.enable"
        original = b"quality = 2\r\nrtx.neuralUplift.enable = False\r\n"
        conf.write_bytes(original)
        self.rep.remix = {"conf": conf.name, "key": key, "conf_final_newline": True}
        installer._remix_option(conf, key, self.rep, self.root)
        self.rep.checkpoint()
        reinstall = installer.Report(game_root=self.root, remix={"conf": conf.name, "key": key, "conf_final_newline": True})
        installer._remix_option(conf, key, reinstall, self.root)
        installer._restore_remix(conf, reinstall.remix)
        self.assertEqual(conf.read_bytes(), original)

    def test_reinstall_carries_prior_sidelined_original(self):
        name = installer.SIDELINE[0]
        original = self.root / name
        original.write_bytes(b"GAME COMPILER ORIGINAL")
        installer._sideline(self.root, self.rep, lambda *_: None)
        reinstall = installer.Report(game_root=self.root)
        self.assertTrue(installer._write_manifest(self.root, self.game, installer.Options(), reinstall, "dxgi.dll", installer.STABLE, True))
        installer.uninstall(self.game)
        self.assertEqual(original.read_bytes(), b"GAME COMPILER ORIGINAL")

    def test_missing_sidelined_original_keeps_failed_recovery_record(self):
        name = installer.SIDELINE[0]
        original = self.root / name
        original.write_bytes(b"GAME COMPILER ORIGINAL")
        installer._sideline(self.root, self.rep, lambda *_: None)
        (self.root / (name + installer.SIDELINE_SUFFIX)).unlink()
        with self.assertRaisesRegex(installer.InstallError, "incomplete"):
            installer.uninstall(self.game)
        self.assertTrue((self.root / installer.MANIFEST).exists())

    def test_sideline_crash_before_rename_accepts_untouched_original(self):
        name = installer.SIDELINE[0]
        original = self.root / name
        original.write_bytes(b"GAME COMPILER ORIGINAL")
        self.record(sidelined=[name], sidelined_hashes={name: net.sha256(original)})
        installer.uninstall(self.game)
        self.assertEqual(original.read_bytes(), b"GAME COMPILER ORIGINAL")

    def test_changed_foreign_addon_survives_cleanup_and_original_restores(self):
        name = installer.BRIDGE_ADDON
        target = self.root / name
        target.write_bytes(b"GAME ORIGINAL ADDON")
        installer._copy(self.source, target, self.rep, self.root)
        target.write_bytes(b"LATER PERSONAL ADDON")
        reinstall = installer.Report(game_root=self.root, preinstalled={name})
        reinstall.checkpoint = lambda: installer._write_manifest(self.root, self.game, installer.Options(), reinstall, "dxgi.dll", installer.STABLE, False)
        installer._purge_foreign_addons(self.root, installer.FEEDER, reinstall, lambda *_: None)
        self.assertFalse(target.exists())
        self.assertEqual(next(self.root.glob(name + ".dlss5-aio-displaced*")).read_bytes(), b"LATER PERSONAL ADDON")
        installer.uninstall(self.game)
        self.assertEqual(target.read_bytes(), b"GAME ORIGINAL ADDON")

    def test_failed_conflicting_addon_checkpoint_stops_install(self):
        target = self.root / installer.BRIDGE_ADDON
        target.write_bytes(b"PERSONAL ADDON")
        self.rep.checkpoint = lambda: False
        with self.assertRaisesRegex(installer.InstallError, "conflicting"):
            installer._purge_foreign_addons(self.root, installer.FEEDER, self.rep, lambda *_: None)
        self.assertEqual(target.read_bytes(), b"PERSONAL ADDON")

    def tune_config(self, route=installer.FEEDER):
        self.rep = installer.Report(game_root=self.root)
        self.rep.checkpoint = lambda: installer._write_manifest(
            self.root, self.game, installer.Options(path=route), self.rep,
            "dxgi.dll", installer.STABLE, False)
        name = feedcfg.NAME if route == installer.FEEDER else installer.optiscaler.INI
        target = self.root / name
        target.write_bytes(b"personal=42\n")
        self.source.write_bytes(b"work_resolution=100\npersonal=42\n" if route == installer.FEEDER else b"[DLSS-NR]\nWorkingScale=1.0\n")
        installer._copy(self.source, target, self.rep, self.root)
        data = json.loads((self.root / installer.MANIFEST).read_text())
        data.update(complete=True, path=route)
        (self.root / installer.MANIFEST).write_text(json.dumps(data))
        return target

    def test_apply_tune_updates_verified_config_and_restores_first_original(self):
        for route in (installer.FEEDER, installer.OPTI):
            with self.subTest(route=route):
                target = self.tune_config(route)
                installer.apply_tune(self.game, route, 75)
                data = json.loads((self.root / installer.MANIFEST).read_text())
                self.assertIs(data["complete"], True)
                self.assertEqual(data["hashes"][target.name], net.sha256(target))
                if route == installer.FEEDER:
                    self.assertEqual(feedcfg.read(target)["work_resolution"], "75")
                    self.assertEqual(feedcfg.read(target)["personal"], "42")
                else:
                    self.assertIn("WorkingScale=0.75", target.read_text())
                installer.uninstall(self.game)
                self.assertEqual(target.read_bytes(), b"personal=42\n")
                target.unlink()

    def test_apply_tune_keeps_later_personal_config(self):
        target = self.tune_config()
        target.write_bytes(b"work_resolution=100\npersonal=99\n")
        installer.apply_tune(self.game, installer.FEEDER, 75)
        self.assertEqual(feedcfg.read(target)["personal"], "99")
        self.assertEqual(next(self.root.glob(target.name + ".dlss5-aio-displaced*")).read_bytes(), b"work_resolution=100\npersonal=99\n")

    def test_apply_tune_refuses_missing_config_and_invalid_scale(self):
        target = self.tune_config()
        target.unlink()
        with self.assertRaisesRegex(installer.InstallError, "ownership"):
            installer.apply_tune(self.game, installer.FEEDER, 75)
        self.assertFalse(target.exists())
        for resolution in (True, 24, 101, 75.0):
            with self.assertRaises(installer.InstallError):
                installer.apply_tune(self.game, installer.FEEDER, resolution)

    def test_apply_tune_final_record_failure_remains_recoverable(self):
        target = self.tune_config()
        real = installer._write_atomic
        def failed(path, text):
            if json.loads(text).get("complete") is True:
                raise OSError("injected final record failure")
            return real(path, text)
        with patch.object(installer, "_write_atomic", side_effect=failed):
            with self.assertRaisesRegex(OSError, "final record"):
                installer.apply_tune(self.game, installer.FEEDER, 75)
        data = json.loads((self.root / installer.MANIFEST).read_text())
        self.assertIs(data["complete"], False)
        installer.uninstall(self.game)
        self.assertEqual(target.read_bytes(), b"personal=42\n")

    def test_layer_unregister_failure_keeps_reference_and_recovery_record(self):
        from core import openxr
        self.record()
        prefs.add_openxr_game(self.root)
        with patch.object(openxr, "unregister", return_value=False), \
                patch.object(openxr, "registrations", return_value=[(self.base / "layer.json", 0)]), \
                patch.object(openxr, "is_ours", return_value=True):
            with self.assertRaisesRegex(installer.InstallError, "incomplete"):
                installer.uninstall(self.game)
        self.assertIn(str(self.root), prefs.openxr_games())
        self.assertTrue((self.root / installer.MANIFEST).exists())

    def test_graphics_write_crash_has_durable_recovery_entry(self):
        self.game.exe = self.root / "Fixture.exe"
        backend = gpupref.Memory()
        real = backend.set
        def crash_after_write(path, value):
            real(path, value)
            raise SystemExit(97)
        with patch.object(gpupref, "backend", backend), patch.object(gpupref, "hybrid", return_value=True), patch.object(backend, "set", side_effect=crash_after_write):
            with self.assertRaises(SystemExit):
                installer._set_gpu_pref(self.root, self.game, installer.Options(gpu_pref=True), self.rep, lambda *_: None)
        data = json.loads((self.root / installer.MANIFEST).read_text())
        self.assertEqual(data["gpu_pref"][0]["exe"], str(self.game.exe))
        self.assertEqual(backend.get(str(self.game.exe)), "GpuPreference=2;")
        with patch.object(gpupref, "backend", backend):
            installer.uninstall(self.game)
        self.assertIsNone(backend.get(str(self.game.exe)))

    def test_forged_graphics_record_cannot_change_outside_program(self):
        outside = self.base / "Outside.exe"
        backend = gpupref.Memory()
        backend.set(str(outside), "GpuPreference=2;")
        self.record(gpu_pref=[{"exe": str(outside), "was": None, "wrote": "GpuPreference=2;"}])
        with patch.object(gpupref, "backend", backend):
            installer.uninstall(self.game)
        self.assertEqual(backend.get(str(outside)), "GpuPreference=2;")

    def test_failed_graphics_restore_retains_recovery_record(self):
        exe = self.root / "Fixture.exe"
        backend = gpupref.Memory()
        backend.set(str(exe), "GpuPreference=2;")
        self.record(gpu_pref=[{"exe": str(exe), "was": None, "wrote": "GpuPreference=2;"}])
        with patch.object(gpupref, "backend", backend), patch.object(backend, "delete", side_effect=PermissionError("injected registry refusal")):
            with self.assertRaisesRegex(installer.InstallError, "graphics recovery"):
                installer.uninstall(self.game)
        self.assertTrue((self.root / installer.MANIFEST).is_file())
        self.assertEqual(backend.get(str(exe)), "GpuPreference=2;")


if __name__ == "__main__":
    unittest.main()
