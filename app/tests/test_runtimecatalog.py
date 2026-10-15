"""Offline checks for runtime provenance, exact ABI names and hostile archives.

Synthetic PE fixtures are never loaded or executed; all cache writes stay temporary.
"""
import hashlib
import stat
import struct
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import runtimecatalog as catalog


def dll(machine=0x8664, flags=0x2000):
    data = bytearray(1024)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", data, 0x84, machine)
    struct.pack_into("<HH", data, 0x96, flags, 0x20B)
    return bytes(data)


class RuntimeCatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cache = patch.object(catalog.net, "CACHE", self.root)
        self.cache.start()
        self.logging = patch.object(catalog.log, "write")
        self.logging.start()
        self.old_catalog = catalog._CATALOG
        catalog._CATALOG = None

    def tearDown(self):
        catalog._CATALOG = self.old_catalog
        self.logging.stop()
        self.cache.stop()
        self.tmp.cleanup()

    def build(self, path, raw=True):
        entry = {"member": "nvngx_dlss.dll", "raw": raw,
                 "url": "https://github.com/RankFTW/rhi-repo/releases/download/dlss-test/runtime.zip",
                 "size": path.stat().st_size if raw else 0}
        entry["sha256" if raw else "archive_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        if not raw:
            entry["archive_size"] = path.stat().st_size
        return entry

    def archive(self, members):
        path = self.root / "source.zip"
        with zipfile.ZipFile(path, "w") as zipped:
            for name, value in members:
                zipped.writestr(name, value)
        return path

    def resolve(self, path, entry=None):
        with patch.object(catalog.net, "download", return_value=path):
            return catalog.resolve(entry or self.build(path), "dlss")

    def test_catalog_contains_only_exact_distinct_filenames_and_hashes(self):
        data = catalog.catalog()
        self.assertEqual(len(catalog.FILE_OF), 12)
        self.assertEqual(len(set(catalog.FILE_OF.values())), 12)
        self.assertNotIn("ffx_fsr3upscaler_x64.dll", catalog.FILE_OF.values())
        for family, entries in data.items():
            self.assertTrue(entries)
            for entry in entries:
                self.assertEqual(entry["member"], catalog.FILE_OF[family])
                self.assertRegex(entry.get("sha256") or entry.get("archive_sha256"), r"^[0-9a-f]{64}$")
        self.assertIn("community", data["dlss"][0]["source"])
        self.assertEqual(data["xess"][0]["version"], "2.0.2.68")
        self.assertEqual(data["fsr4"][0]["requires"], {"amd_fidelityfx_loader_dx12.dll": "2.3.0.2740"})
        data["dlss"].clear()
        self.assertTrue(catalog.catalog()["dlss"])

    def test_raw_hash_and_x64_dll_are_verified(self):
        path = self.root / "source.dll"
        path.write_bytes(dll())
        self.assertEqual(self.resolve(path), path)

    def test_windows_file_version_must_match_release_label(self):
        path = self.root / "source.dll"
        path.write_bytes(dll())
        entry = dict(self.build(path), version="310.9.16")
        with patch.object(catalog.os, "name", "nt"), \
                patch.object(catalog.pe, "file_version", return_value="310.9.16.0"):
            self.assertEqual(self.resolve(path, entry), path)
        for version in ("310.9.1", ""):
            path.write_bytes(dll())
            with self.subTest(version=version), patch.object(catalog.os, "name", "nt"), \
                    patch.object(catalog.pe, "file_version", return_value=version):
                with self.assertRaisesRegex(ValueError, "FileVersion"):
                    self.resolve(path, entry)
                self.assertFalse(path.exists())

    def test_modified_cached_raw_file_is_rejected(self):
        path = self.root / "source.dll"
        path.write_bytes(dll())
        entry = self.build(path)
        path.write_bytes(dll() + b"tampered")
        with self.assertRaisesRegex(ValueError, "SHA256/size"):
            self.resolve(path, entry)
        self.assertFalse(path.exists())

    def test_different_game_threads_serialize_shared_runtime_downloads(self):
        path = self.root / "source.dll"
        path.write_bytes(dll())
        entry = self.build(path)
        start = threading.Barrier(2)
        active = maximum = 0
        def download(*args, **kwargs):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            time.sleep(0.03)
            active -= 1
            return path
        def resolve():
            start.wait(timeout=5)
            return catalog.resolve(entry, "dlss")
        with patch.object(catalog.net, "download", side_effect=download), \
                ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(resolve) for _ in range(2)]
            self.assertEqual([job.result(timeout=5) for job in jobs], [path, path])
        self.assertEqual(maximum, 1)

    def test_x86_and_executable_masquerading_as_dll_are_rejected(self):
        for data in (dll(0x14C), dll(flags=0), b"MZ" + bytes(1022)):
            with self.subTest(data=data[:2]):
                path = self.root / "source.dll"
                path.write_bytes(data)
                with self.assertRaises((ValueError, catalog.pe.PEError)):
                    self.resolve(path)

    def test_family_missing_hash_bad_size_and_insecure_host_are_rejected_before_download(self):
        entry = catalog.catalog()["dlss"][0]
        for change in ({"member": "nvngx_dlssg.dll"}, {"archive_sha256": ""},
                       {"archive_size": 0}, {"url": "http://github.com/runtime.zip"},
                       {"url": "https://github.com.evil.invalid/runtime.zip"},
                       {"url": "https://github.com:443/runtime.zip"}):
            with self.subTest(change=change), patch.object(catalog.net, "download") as download:
                with self.assertRaises(ValueError):
                    catalog.resolve(dict(entry, **change), "dlss")
                download.assert_not_called()

    def test_archive_exact_member_is_extracted_without_using_its_path(self):
        path = self.archive([("folder/nvngx_dlss.dll", dll()), ("LICENSE.txt", b"notice")])
        out = self.resolve(path, self.build(path, raw=False))
        self.assertEqual(out.parent, self.root)
        self.assertEqual(out.read_bytes(), dll())
        out.write_bytes(b"modified cached output")
        self.assertEqual(self.resolve(path, self.build(path, raw=False)).read_bytes(), dll())

    def test_archive_hash_mismatch_fails_before_extraction(self):
        path = self.archive([("nvngx_dlss.dll", dll())])
        entry = self.build(path, raw=False)
        entry["archive_sha256"] = "0" * 64
        with patch.object(catalog, "_extract") as extract:
            with self.assertRaisesRegex(ValueError, "SHA256/size"):
                self.resolve(path, entry)
            extract.assert_not_called()

    def test_authenticated_extracted_cache_avoids_download_and_rejects_tampering(self):
        path = self.archive([("nvngx_dlss.dll", dll())])
        entry = self.build(path, raw=False)
        entry.update(sha256=hashlib.sha256(dll()).hexdigest(), size=len(dll()))
        dest = self.resolve(path, entry)
        with patch.object(catalog.net, "download") as download:
            self.assertEqual(catalog.resolve(entry, "dlss"), dest)
            download.assert_not_called()
        dest.write_bytes(b"tampered")
        self.assertEqual(self.resolve(path, entry).read_bytes(), dll())

    def test_archive_traversal_duplicate_wrong_name_and_foreign_payload_are_rejected(self):
        cases = (
            [("../nvngx_dlss.dll", dll())],
            [("C:/nvngx_dlss.dll", dll())],
            [("/nvngx_dlss.dll", dll())],
            [("nested\\..\\nvngx_dlss.dll", dll())],
            [("one/nvngx_dlss.dll", dll()), ("two/nvngx_dlss.dll", dll())],
            [("nvngx_dlss.dll", dll()), ("NVNGX_DLSS.DLL", dll())],
            [("evilnvngx_dlss.dll", dll())],
            [("nvngx_dlss.dll", dll()), ("helper.exe", dll())],
        )
        for members in cases:
            with self.subTest(names=[name for name, _ in members]):
                path = self.archive(members)
                with self.assertRaises(ValueError):
                    self.resolve(path, self.build(path, raw=False))

    def test_archive_symlink_and_zip_bomb_are_rejected(self):
        symlink = zipfile.ZipInfo("nvngx_dlss.dll")
        symlink.create_system = 3
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        path = self.archive([(symlink, b"target")])
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            self.resolve(path, self.build(path, raw=False))
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
            zipped.writestr("nvngx_dlss.dll", dll() + bytes(1000000))
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            self.resolve(path, self.build(path, raw=False))

    def test_refresh_resolves_a_release_asset_digest_and_retains_pins_on_failure(self):
        new = catalog._rhi_build("dlss", "310.10.0", 1234, "a" * 64)
        feed = {"dlss": [{"version": new["version"], "url": new["url"]}]}
        def get(url):
            if url == catalog.RHI_FEED:
                return feed
            return {"assets": [{"browser_download_url": new["url"], "size": 1234,
                                 "digest": "sha256:" + "a" * 64}]}
        with patch.object(catalog.net, "json_get", side_effect=get):
            result = catalog.catalog(refresh=True)
        self.assertEqual(result["dlss"][0]["version"], "310.10.0")
        with patch.object(catalog.net, "json_get", side_effect=OSError("offline")):
            self.assertEqual(catalog.catalog(refresh=True), result)

    def test_refresh_untrusted_url_or_missing_digest_cannot_replace_pins(self):
        expected = catalog.catalog()
        item = {"version": "999.0.0", "url": "https://evil.invalid/dlss.zip"}
        with patch.object(catalog.net, "json_get", return_value={"dlss": [item]}):
            self.assertEqual(catalog.catalog(refresh=True), expected)
        item = catalog._rhi_build("dlss", "999.0.0", 1234, "")
        with patch.object(catalog.net, "json_get", side_effect=lambda url:
                          {"dlss": [item]} if url == catalog.RHI_FEED else
                          {"assets": [{"browser_download_url": item["url"], "size": 1234}]}):
            self.assertEqual(catalog.catalog(refresh=True), expected)


if __name__ == "__main__":
    unittest.main()
