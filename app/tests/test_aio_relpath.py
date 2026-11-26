"""A game named by a relative path reads the same versions as an absolute one.

2.2.4: `DLSS5-AIO.exe "Game" --scan-dlls` printed "version": "" for every
runtime and `--update-dlls` reported "3.7.20" as "is current". The release's
PyInstaller bootloader calls SetDllDirectoryW, which drops the working folder
from the DLL search path, and Windows' version API resolves a relative file
name through that path. A source run never sees it, so the reproducer makes the
same SetDllDirectoryW call in this process.
"""
import ctypes
import os
os.environ.setdefault("DLSS5_AIO_OFFLINE", "1")   # tests never reach the publishers
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "_tools"))
from fake_pe import dll  # noqa: E402
from core import dlss, dlssupdate as du, games, pe, prefs  # noqa: E402


@unittest.skipUnless(os.name == "nt", "Windows version API")
class RelativeTargetLikeTheRelease(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "Fixture Game" / "bin").mkdir(parents=True)
        self.dll = self.root / "Fixture Game" / "bin" / "nvngx_dlss.dll"
        self.dll.write_bytes(dll("3.7.20", size=8192))
        self.cwd = os.getcwd()
        os.chdir(self.root)
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.SetDllDirectoryW.argtypes = [ctypes.c_wchar_p]
        self.k32 = k32
        # What the frozen app's bootloader does before any app code runs.
        self.assertTrue(k32.SetDllDirectoryW(str(self.root / "elsewhere")))

    def tearDown(self):
        self.k32.SetDllDirectoryW(None)          # the default search order again
        os.chdir(self.cwd)
        self.temp.cleanup()

    def test_relative_path_reads_the_stamp(self):
        rel = Path("Fixture Game") / "bin" / "nvngx_dlss.dll"
        self.assertEqual(pe.file_version(rel), "3.7.20")
        self.assertEqual(pe.file_version(str(rel)), pe.file_version(self.dll))

    def test_relative_game_scans_with_versions(self):
        g = games.Game("Fixture Game", Path("Fixture Game"), Path("Fixture Game") / "bin" / "Game.exe",
                       64, "DX12")
        g.exe.write_bytes(dll("1.0.0", size=8192))
        with patch.object(prefs, "FILE", self.root / "settings.json"):
            dlss.forget_walk()
            rows = du.scan(g, fresh=True)
        self.assertEqual([(r.family, r.version) for r in rows], [("dlss", "3.7.20")])


class UnreadableVersionIsNotCurrent(unittest.TestCase):
    """A runtime whose stamp cannot be read is left alone and says so."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.game = games.Game("Fixture game", self.root, self.root / "Game.exe", 64, "DX12")
        self.game.exe.write_bytes(dll("1.0.0", size=8192))
        (self.root / du.FILE_OF["dlss"]).write_bytes(dll("", size=8192))   # no VERSIONINFO
        self.patches = [patch.object(prefs, "FILE", self.root / "settings.json"),
                        patch.object(du, "running", return_value=""),
                        patch.object(du, "anticheat_name", return_value="")]
        for p in self.patches:
            p.start()
        dlss.forget_walk()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def test_update_reports_unknown_not_current(self):
        before = (self.root / du.FILE_OF["dlss"]).read_bytes()
        catalog = {"dlss": [{"url": "https://example.invalid/fixture", "label": "2.0.0 (fixture)",
                             "version": "2.0.0", "raw": du.FILE_OF["dlss"]}]}
        with patch.object(du.runtimecatalog, "resolve", side_effect=AssertionError("downloaded")):
            report = du.update(self.game, catalog=catalog)
        self.assertFalse(report.error, report.error)
        self.assertEqual(report.done, [])
        self.assertEqual(len(report.skipped), 1, report.skipped)
        self.assertIn("no version could be read", report.skipped[0])
        self.assertNotIn("is current", report.skipped[0])
        self.assertEqual((self.root / du.FILE_OF["dlss"]).read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
