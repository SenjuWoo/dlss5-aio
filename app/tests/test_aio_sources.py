"""Keep injection and DLL maintenance on the same authenticated NVIDIA builds."""
import sys
import os
os.environ.setdefault("DLSS5_AIO_OFFLINE", "1")   # tests never reach the publishers
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "_tools"))
from fake_pe import dll
from core import installer, net, runtimecatalog, sources


class InstallerRuntimeSources(unittest.TestCase):
    def test_only_exact_github_api_host_is_classified_as_rate_limited(self):
        urls = (
            ("https://api.github.com/repos/example/repo/releases", True),
            ("https://API.GITHUB.COM/repos/example/repo/releases", True),
            ("https://api.github.com.example.invalid/releases", False),
            ("https://example.invalid/api.github.com/releases", False),
            ("https://example.invalid/?next=api.github.com", False),
        )
        for read in (sources._get, net.fetch_text):
            for code in (403, 429):
                for url, api in urls:
                    with self.subTest(read=read.__name__, code=code, url=url), \
                            patch.object(net, "ssl_context", return_value=None), \
                            patch.object(net.urllib.request, "urlopen",
                                         side_effect=urllib.error.HTTPError(url, code, "fixture", None, None)):
                        expected = sources.RateLimited if api else urllib.error.HTTPError
                        with self.assertRaises(expected):
                            read(url)

    def test_embedded_credential_host_spoof_is_rejected_before_transport(self):
        for read in (sources._get, net.fetch_text):
            with self.subTest(read=read.__name__), patch.object(net.urllib.request, "urlopen") as transport:
                with self.assertRaises(ValueError):
                    read("https://api.github.com@example.invalid/releases")
                transport.assert_not_called()

    def test_auto_uses_newest_verified_runtime_and_keeps_sdk_choice(self):
        with patch.object(sources, "latest_tag", side_effect=AssertionError("network")):
            catalog = sources.nvidia_dlss()
        for family in ("dlss", "dlssd", "dlssg"):
            entries = catalog[family]
            latest = sources.pick(entries, None)
            self.assertEqual(latest["version"], "310.9.16")
            self.assertEqual(latest["verified_family"], family)
            self.assertEqual(sources.pick(entries, "310.9.1 (NVIDIA SDK)")["version"], "310.9.1")
        catalog["dlss"][0]["version"] = "0.0.0"
        self.assertEqual(sources.nvidia_dlss()["dlss"][0]["version"], "310.9.16")

    def test_authenticated_file_is_copied_and_original_retained(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, dest = root / "download.dll", root / "nvngx_dlss.dll"
            source.write_bytes(dll("310.9.16", size=262144))
            original = dll("310.9.1", size=8192)
            dest.write_bytes(original)
            entry = sources.nvidia_dlss()["dlss"][0]
            report = installer.Report()
            with patch.object(runtimecatalog, "resolve", return_value=source) as resolve:
                installer._place_entry(entry, dest, report, root,
                                       lambda *_: self.fail("unverified transport"),
                                       dest.name, "unused.zip")
            resolve.assert_called_once_with(entry, "dlss")
            self.assertEqual(dest.read_bytes(), source.read_bytes())
            self.assertEqual(dest.with_name(dest.name + installer.BACKUP_SUFFIX).read_bytes(), original)
            self.assertIn(dest.name, report.written)

    def test_failed_authentication_never_backs_up_or_changes_game(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            dest = root / "nvngx_dlss.dll"
            dest.write_bytes(b"original")
            with patch.object(runtimecatalog, "resolve", side_effect=ValueError("SHA256 differs")):
                with self.assertRaisesRegex(ValueError, "SHA256"):
                    installer._place_entry(sources.nvidia_dlss()["dlss"][0], dest,
                                           installer.Report(), root, None, dest.name, "unused.zip")
            self.assertEqual(dest.read_bytes(), b"original")
            self.assertFalse(dest.with_name(dest.name + installer.BACKUP_SUFFIX).exists())


if __name__ == "__main__":
    unittest.main()
