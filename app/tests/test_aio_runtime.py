"""Exercise real PE version reading, game file replacement and recovery.

Only transport and process discovery are substituted; filesystem writes,
hashes, VERSIONINFO parsing, backup records and OS locks are real.
"""
import os
import subprocess
import sys
import os
os.environ.setdefault("DLSS5_AIO_OFFLINE", "1")   # tests never reach the publishers
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "_tools"))
from fake_pe import dll
from core import dlss, dlssupdate as du, gamelock, games, net, pe, prefs


class RuntimeIntegration(unittest.TestCase):
    """Use Windows' actual version-resource reader against owned fixtures."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.game = games.Game("Fixture game", self.root, self.root / "Game.exe", 64, "DX12")
        self.game.exe.write_bytes(dll("1.0.0", size=8192))
        self.builds = self.root / "download-cache"
        self.builds.mkdir()
        self.pref = patch.object(prefs, "FILE", self.root / "settings.json")
        self.pref.start()
        self.watch = patch.object(du, "running", return_value="")
        self.watch.start()
        self.ac = patch.object(du, "anticheat_name", return_value="")
        self.ac.start()
        dlss.forget_walk()

    def tearDown(self):
        self.ac.stop()
        self.watch.stop()
        self.pref.stop()
        self.temp.cleanup()

    def runtime(self, family, version="1.0.0", nested=False):
        """Place an existing game's DLL; never create an integration on update."""
        parent = self.root / "Engine" / "Binaries" if nested else self.root
        parent.mkdir(parents=True, exist_ok=True)
        target = parent / du.FILE_OF[family]
        target.write_bytes(dll(version, size=8192))
        return target

    def catalog(self, *families):
        return {family: [{"url": "https://example.invalid/fixture", "label": "2.0.0 (fixture)",
                          "version": "2.0.0", "raw": du.FILE_OF[family]}] for family in families}

    def resolve(self, build, family, progress=None):
        target = self.builds / du.FILE_OF[family]
        target.write_bytes(dll("2.0.0", size=8192))
        return target

    def test_multivendor_scan_does_not_reuse_nvidia_only_walk(self):
        self.runtime("dlss")
        self.runtime("xess", nested=True)
        self.runtime("fsr31_dx12", nested=True)
        key = (dlss._walk_key(self.root), dlss._walk_key(self.root), tuple(dlss.DLSS_FILES))
        dlss._WALK_CACHE[key] = ["nvngx_dlss.dll"]
        self.assertEqual({entry.family for entry in du.scan(self.game)},
                         {"dlss", "xess", "fsr31_dx12"})

    def test_copy_does_not_reuse_or_remove_an_existing_part_file(self):
        target = self.runtime("xess")
        sentinel = target.with_name(target.name + du.PART_SUFFIX)
        sentinel.write_bytes(b"unclaimed previous file")
        source = self.builds / "source.dll"
        source.write_bytes(dll("2.0.0", size=8192))
        du._copy_whole(source, target)
        self.assertEqual(target.read_bytes(), source.read_bytes())
        self.assertEqual(sentinel.read_bytes(), b"unclaimed previous file")

    def test_hardlinked_lock_never_changes_the_other_file(self):
        folder = self.root / "linked-lock-game"
        folder.mkdir()
        original = self.root / "unowned-empty-file"
        original.touch()
        os.link(original, folder / ".dlss5-aio.lock")
        with self.assertRaisesRegex(OSError, "hard links"):
            with gamelock.locked(folder):
                self.fail("accepted hardlinked lock")
        self.assertEqual(original.read_bytes(), b"")

    def test_game_mutation_also_locks_the_executable_directory(self):
        binary = self.root / "bin"
        binary.mkdir()
        game = games.Game("nested", self.root, binary / "Game.exe", 64, "DX12")
        failures = []
        writes = []
        @gamelock.exclusive
        def mutation(selected):
            writes.append(True)
        def worker():
            try:
                mutation(game)
            except OSError as error:
                failures.append(str(error))
        with gamelock.locked(binary):
            thread = threading.Thread(target=worker)
            thread.start()
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
        self.assertTrue(failures)
        self.assertFalse(writes)

    def test_update_and_offline_restore_all_vendors(self):
        families = ("dlss", "xess", "fsr31_dx12")
        targets = [self.runtime(family, nested=family != "dlss") for family in families]
        original = {path: path.read_bytes() for path in targets}
        with patch.object(du.runtimecatalog, "resolve", side_effect=self.resolve):
            report = du.update(self.game, catalog=self.catalog(*families))
        self.assertFalse(report.error, report.error)
        self.assertEqual(len(report.done), 3)
        for path in targets:
            self.assertEqual(pe.file_version(path), "2.0.0")
            self.assertEqual(du._ours(path).read_bytes(), original[path])
        with patch.object(du.runtimecatalog, "catalog", side_effect=AssertionError("restore fetched network")):
            report = du.restore(self.game)
        self.assertFalse(report.error, report.error)
        for path in targets:
            self.assertEqual(path.read_bytes(), original[path])

    def test_same_version_personal_edit_during_download_is_preserved(self):
        target = self.runtime("xess")
        edited = dll("1.0.0", size=8192) + b"PERSONAL-EDIT"
        def change(build, family, progress=None):
            target.write_bytes(edited)
            return self.resolve(build, family, progress)
        with patch.object(du.runtimecatalog, "resolve", side_effect=change):
            report = du.update(self.game, catalog=self.catalog("xess"))
        self.assertIn("changed while", report.error)
        self.assertEqual(target.read_bytes(), edited)
        self.assertFalse(du._ours(target).exists())

    def test_unknown_abi_and_32bit_files_are_preserved(self):
        target = self.root / "ffx_fsr3upscaler_x64.dll"
        target.write_bytes(dll("1.0.0", size=8192))
        xess = self.runtime("xess")
        xess.write_bytes(dll("1.0.0", machine=0x14C, size=8192))
        self.assertEqual(du.scan(self.game), [])
        self.assertTrue(target.is_file())
        self.assertEqual(pe.exe_bitness(xess), 32)

    def test_same_version_and_size_are_not_proof_of_duplicate_backup(self):
        target = self.runtime("xess")
        backup = du._ours(target)
        backup.write_bytes(target.read_bytes())
        changed = bytearray(target.read_bytes())
        changed[-1] = 88
        target.write_bytes(changed)
        self.assertEqual(pe.file_version(target), pe.file_version(backup))
        self.assertFalse(du._same_build(target, backup))
        self.assertTrue(backup.exists())

    def test_restore_keeps_same_size_personal_edit_as_displaced_file(self):
        target = self.runtime("xess")
        original = target.read_bytes()
        with patch.object(du.runtimecatalog, "resolve", side_effect=self.resolve):
            report = du.update(self.game, catalog=self.catalog("xess"))
        self.assertFalse(report.error, report.error)
        changed = bytearray(target.read_bytes())
        changed[-1] = 88
        target.write_bytes(changed)
        record = du.load_record(self.game)[0]
        self.assertFalse(du._matches(target, pe.file_version(target), record))
        report = du.restore(self.game)
        self.assertFalse(report.error, report.error)
        self.assertEqual(target.read_bytes(), original)
        displaced = list(self.root.glob(target.name + du.DISPLACED_SUFFIX + "*"))
        self.assertEqual(len(displaced), 1)
        self.assertEqual(displaced[0].read_bytes(), bytes(changed))

    def test_split_fsr_requires_matching_loader(self):
        target = self.runtime("fsr4")
        before = target.read_bytes()
        catalog = self.catalog("fsr4")
        catalog["fsr4"][0]["requires"] = {"amd_fidelityfx_loader_dx12.dll": "2.3.0.2740"}
        with patch.object(du.runtimecatalog, "resolve", side_effect=AssertionError("dependency not checked")):
            report = du.update(self.game, catalog=catalog)
        self.assertFalse(report.done)
        self.assertTrue(any("needs" in line for line in report.skipped))
        self.assertEqual(target.read_bytes(), before)

    def test_hash_checked_backup_failure_preserves_destination(self):
        target = self.runtime("dlss")
        before = target.read_bytes()
        actual_copy = du.shutil.copyfile
        def corrupt(source, destination):
            result = actual_copy(source, destination)
            if str(destination).endswith(".aio-part"):
                Path(destination).write_bytes(b"X" * Path(destination).stat().st_size)
            return result
        with patch.object(du.runtimecatalog, "resolve", side_effect=self.resolve), \
                patch.object(du.shutil, "copyfile", side_effect=corrupt):
            report = du.update(self.game, catalog=self.catalog("dlss"))
        self.assertIn("backed up", report.error)
        self.assertEqual(target.read_bytes(), before)
        self.assertFalse(du._ours(target).exists())

    def test_other_process_cannot_write_locked_game(self):
        code = ("from core.gamelock import locked; import sys; "
                "\nwith locked(sys.argv[1]): print('ACQUIRED')")
        with gamelock.locked(self.root):
            result = subprocess.run([sys.executable, "-c", code, str(self.root)], cwd=APP,
                                    text=True, capture_output=True, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Another AIO operation", result.stderr)
        with gamelock.locked(self.root):
            pass

    def test_nested_rollback_lock_is_reentrant_only_on_own_thread(self):
        errors = []
        def other_writer():
            try:
                with gamelock.locked(self.root):
                    errors.append("unexpected acquisition")
            except OSError as error:
                errors.append(str(error))
        with gamelock.locked(self.root):
            with gamelock.locked(self.root):
                worker = threading.Thread(target=other_writer)
                worker.start()
                worker.join(timeout=5)
                self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIn("Another AIO operation", errors[0])


if __name__ == "__main__":
    unittest.main()
