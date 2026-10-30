"""Offline fork checks: CLI cannot mutate on malformed input or cross app profiles."""
import importlib.util
import io
import os
import subprocess
import sys
import os
os.environ.setdefault("DLSS5_AIO_OFFLINE", "1")   # tests never reach the publishers
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
from core import community, log, net, prefs, selfupdate, update
from core.ui import app, shell

spec = importlib.util.spec_from_file_location("dlss5_aio", APP / "dlss5_aio.py")
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


class AioShellTests(unittest.TestCase):
    def test_isolated_profile_and_game_only_rail(self):
        self.assertEqual(update.REPO, "SenjuWoo/dlss5-aio")
        self.assertEqual(update.VERSION, "2.2.1")
        self.assertEqual(net.CACHE.parent.name, "dlss5-aio")
        self.assertEqual(prefs.FILE.parent.name, "dlss5-aio")
        self.assertEqual(log.FILE.name, "aio.log")
        self.assertEqual(shell.TITLE, "DLSS 5 AIO")
        self.assertNotIn("video", [item[0] for item in shell.Shell.RAIL_ITEMS])
        self.assertEqual(app.MUTEX_NAME, "Local\\DLSS5AIOWindow")

    def test_no_automatic_upstream_community_reads(self):
        with patch.object(net, "fetch_text", side_effect=AssertionError("unexpected network")):
            self.assertEqual(community.fetch(force=True), {})

    def test_invalid_cli_never_installs(self):
        cases = (["--video"], ["--unknown"], ["--update-dlls"], ["--remove"],
                 ["--route"], ["--route", "typo"], ["--check", "--remove", "game"],
                 ["--scan-dlls", "--route", "feeder", "game"], ["game", "other-game"])
        for args in cases:
            with self.subTest(args=args), patch.object(sys, "argv", ["DLSS5-AIO", *args]), \
                    patch.object(entry, "_console"), patch.object(entry, "cli") as install, \
                    redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as stopped:
                    entry.main()
                self.assertEqual(stopped.exception.code, 2)
                install.assert_not_called()

    def test_debug_is_opt_in_but_failure_is_kept(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(log, "DIR", Path(folder)), \
                patch.object(log, "FILE", Path(folder) / "aio.log"), \
                patch.dict(os.environ, {"DLSS5_AIO_DEBUG": "0"}), patch.object(prefs, "get", return_value=False):
            log.write("quiet detail", "debug")
            log.write("failure cause", "ERROR")
            self.assertEqual(log.FILE.read_text().count("quiet detail"), 0)
            self.assertIn("failure cause", log.FILE.read_text())
            with patch.dict(os.environ, {"DLSS5_AIO_DEBUG": "1"}):
                log.write("resolved choice", "debug")
            self.assertIn("resolved choice", log.FILE.read_text())

    def test_source_entrypoint_subprocess(self):
        for flag, expected in (("--version", "2.2.1"), ("--self-test", '"status": "ok"')):
            with self.subTest(flag=flag):
                result = subprocess.run([sys.executable, str(APP / "dlss5_aio.py"), flag],
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(expected, result.stdout)

    def test_updater_requires_fork_artifact_and_checksum(self):
        with tempfile.TemporaryDirectory() as folder:
            release = {"tag_name": "v2.2.1", "assets": [
                {"name": "DLSS5-AIO.exe", "browser_download_url": "https://example.invalid/app.exe"}]}
            with patch.object(net, "json_get", return_value=release), patch.object(net, "download") as download:
                with self.assertRaisesRegex(selfupdate.UpdateError, "SHA256SUMS"):
                    selfupdate._fetch(Path(folder))
                download.assert_not_called()
            release["assets"] = [
                {"name": "unrelated-tool.exe", "browser_download_url": "https://example.invalid/other.exe"},
                {"name": "SHA256SUMS.txt", "browser_download_url": "https://example.invalid/sums"}]
            with patch.object(net, "json_get", return_value=release), patch.object(net, "download") as download:
                with self.assertRaisesRegex(selfupdate.UpdateError, "no downloadable build"):
                    selfupdate._fetch(Path(folder))
                download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
