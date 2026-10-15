"""Exercise real cache/archive/recovery boundaries with isolated offline files."""
import hashlib
import io
import json
import os
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import community, net, optiscaler, remixdl, selfupdate
from core.reportprivacy import public_text


class Response(io.BytesIO):
    status = 200

    def __init__(self, data, declared=True, final="https://publisher.invalid/file"):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))} if declared else {}
        self.final = final

    def geturl(self):
        return self.final


class NetworkBoundaries(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.cache = patch.object(net, "CACHE", self.root / "cache")
        self.cache.start()
        self.ssl = patch.object(net, "ssl_context", return_value=None)
        self.ssl.start()

    def tearDown(self):
        self.ssl.stop()
        self.cache.stop()
        self.temporary.cleanup()

    def zipped(self, members, name="fixture.zip"):
        path = self.root / name
        with zipfile.ZipFile(path, "w") as archive:
            for key, value in members:
                archive.writestr(key, value)
        return path

    def game(self):
        path = self.root / "game"
        path.mkdir()
        return path

    def test_cache_is_bound_to_url_and_preserves_prior_bytes_on_failed_refresh(self):
        with patch.object(net.urllib.request, "urlopen", return_value=Response(b"MZfirst")) as transport:
            first = net.download("https://one.invalid/a.dll", "a.dll", attempts=1)
            self.assertEqual(first.read_bytes(), b"MZfirst")
        with patch.object(net.urllib.request, "urlopen", side_effect=AssertionError("cache miss")):
            self.assertEqual(net.download("https://one.invalid/a.dll", "a.dll").read_bytes(), b"MZfirst")
        with patch.object(net.urllib.request, "urlopen", return_value=Response(b"MZsecond")) as transport:
            self.assertEqual(net.download("https://two.invalid/a.dll", "a.dll", attempts=1).read_bytes(), b"MZsecond")
            self.assertEqual(transport.call_count, 1)
        with patch.object(net.urllib.request, "urlopen", return_value=Response(b"invalid")):
            with self.assertRaises(net.WrongContent):
                net.download("https://three.invalid/a.dll", "a.dll", attempts=1)
        self.assertEqual(first.read_bytes(), b"MZsecond")

    def test_unbound_legacy_cache_is_not_assumed_to_match_new_url(self):
        cache = net.cache_dir()
        (cache / "a.dll").write_bytes(b"MZlegacy")
        with patch.object(net.urllib.request, "urlopen", return_value=Response(b"MZauthenticated-origin")) as transport:
            got = net.download("https://publisher.invalid/a.dll", "a.dll", attempts=1)
        self.assertEqual(got.read_bytes(), b"MZauthenticated-origin")
        transport.assert_called_once()

    def test_unsafe_filename_scheme_credentials_and_redirect_are_rejected(self):
        for name in ("../a.dll", "C:/a.dll", "NUL.dll", "a.dll:stream", "a.dll "):
            with self.subTest(name=name), patch.object(net.urllib.request, "urlopen") as transport:
                with self.assertRaises(ValueError):
                    net.download("https://publisher.invalid/a.dll", name, attempts=1)
                transport.assert_not_called()
        for url in ("http://publisher.invalid/a.dll", "https://token@publisher.invalid/a.dll"):
            with self.subTest(url=url), patch.object(net.urllib.request, "urlopen") as transport:
                with self.assertRaises(ValueError):
                    net.download(url, "a.dll", attempts=1)
                transport.assert_not_called()
        with patch.object(net.urllib.request, "urlopen", return_value=Response(b"MZpayload", final="http://publisher.invalid/a.dll")):
            with self.assertRaises(ValueError):
                net.download("https://publisher.invalid/a.dll", "a.dll", attempts=1)
        self.assertFalse((net.CACHE / "a.dll").exists())

    def test_declared_and_streamed_download_limits_remove_partial_bytes(self):
        for declared in (True, False):
            with self.subTest(declared=declared), patch.object(net.urllib.request, "urlopen", return_value=Response(b"MZ" + b"x" * 100, declared=declared)):
                with self.assertRaises(net.WrongContent):
                    net.download("https://publisher.invalid/a.dll", "a.dll", attempts=1, max_bytes=20)
            self.assertFalse((net.CACHE / "a.dll.part").exists())
            self.assertFalse((net.CACHE / "a.dll").exists())
        with self.assertRaises(net.WrongContent):
            net.read_bounded(io.BytesIO(b"12345"), 4)

    def test_stream_limit_is_checked_before_write_and_preserves_completed_cache(self):
        with patch.object(net.urllib.request, "urlopen", return_value=Response(b"MZprior")):
            prior = net.download("https://one.invalid/a.dll", "a.dll", attempts=1)
        class Chunks(Response):
            def __init__(self):
                super().__init__(b"", declared=False)
                self.chunks = iter((b"MZaccepted", b"x" * 20, b""))
            def read(self, size=-1):
                return next(self.chunks)
        real_open, writes = open, []
        class Traced:
            def __init__(self, stream):
                self.stream = stream
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return self.stream.__exit__(*args)
            def write(self, data):
                writes.append(len(data))
                self_test.assertLessEqual(sum(writes), 10, "partial file exceeded its byte cap")
                return self.stream.write(data)
        self_test = self
        def monitored(path, mode="r", *args, **kwargs):
            stream = real_open(path, mode, *args, **kwargs)
            return Traced(stream) if str(path).endswith("a.dll.part") and mode in ("wb", "ab") else stream
        with patch.object(net, "open", monitored, create=True), patch.object(net.urllib.request, "urlopen", return_value=Chunks()):
            with self.assertRaises(net.WrongContent):
                net.download("https://two.invalid/a.dll", "a.dll", attempts=1, max_bytes=10)
        self.assertEqual(writes, [10])
        self.assertFalse((net.CACHE / "a.dll.part").exists())
        self.assertEqual(prior.read_bytes(), b"MZprior")
        with patch.object(net.urllib.request, "urlopen", side_effect=AssertionError("original cache binding lost")):
            self.assertEqual(net.download("https://one.invalid/a.dll", "a.dll").read_bytes(), b"MZprior")

    def test_same_component_threads_share_one_complete_transfer(self):
        def transport(*args, **kwargs):
            time.sleep(0.03)
            return Response(b"MZcomplete")
        with patch.object(net.urllib.request, "urlopen", side_effect=transport) as request, ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(net.download, "https://publisher.invalid/a.dll", "a.dll", attempts=1) for _ in range(2)]
            self.assertEqual([job.result(timeout=5).read_bytes() for job in futures], [b"MZcomplete"] * 2)
        self.assertEqual(request.call_count, 1)

    def test_extract_rejects_unsafe_ambiguous_and_wrong_suffix_members_before_overwrite(self):
        destination = self.root / "keep.dll"
        destination.write_bytes(b"personal")
        symlink = zipfile.ZipInfo("nvngx_dlss.dll")
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        for members in ([('../nvngx_dlss.dll', b'bad')], [('NUL.dll', b'bad')],
                        [(symlink, b'target')], [('evilnvngx_dlss.dll', b'bad')],
                        [('one/nvngx_dlss.dll', b'one'), ('two/nvngx_dlss.dll', b'two')]):
            with self.subTest(members=str(members)):
                archive = self.zipped(members)
                with self.assertRaises((RuntimeError, ValueError)):
                    net.extract_one(archive, "nvngx_dlss.dll", destination)
                self.assertEqual(destination.read_bytes(), b"personal")

    def test_extraction_failure_preserves_destination_and_tree_uses_writer(self):
        archive = self.zipped([("root/Shaders/a.fx", b"shader")])
        destination = self.root / "a.fx"
        destination.write_bytes(b"personal")
        def broken(arc, member, target):
            target.write_bytes(b"partial")
            raise OSError("fixture disk failure")
        with patch.object(net, "_copy_member", side_effect=broken):
            with self.assertRaises(OSError):
                net.extract_one(archive, "a.fx", destination)
        self.assertEqual(destination.read_bytes(), b"personal")
        seen = []
        def writer(source, target):
            self.assertEqual(source.read_bytes(), b"shader")
            self.assertEqual(target.read_bytes(), b"personal")
            seen.append(target)
        result = net.extract_tree(archive, "Shaders", "", self.root, writer=writer)
        self.assertEqual(result, [destination])
        self.assertEqual(seen, [destination])
        self.assertEqual(destination.read_bytes(), b"personal")

    def test_unpacked_cache_tracks_archive_and_detects_modified_files(self):
        archive = self.zipped([("OptiScaler.dll", b"first")])
        first = optiscaler._unpacked(archive)
        (first / "OptiScaler.dll").write_bytes(b"personal cache change")
        again = optiscaler._unpacked(archive)
        self.assertEqual((again / "OptiScaler.dll").read_bytes(), b"first")
        archive = self.zipped([("OptiScaler.dll", b"second")])
        second = optiscaler._unpacked(archive)
        self.assertNotEqual(first, second)
        self.assertEqual((second / "OptiScaler.dll").read_bytes(), b"second")

    def test_7z_listing_rejects_escape_links_duplicates_and_bounds_before_extracting(self):
        valid = "Path = OptiScaler.dll\nSize = 6\nEncrypted = -\nAttributes = A\n"
        listings = [valid.replace("OptiScaler.dll", "../outside.dll"),
                    valid.replace("OptiScaler.dll", "C:/outside.dll"),
                    valid + "Symbolic Link = outside\n", valid + "Hard Link = outside\n",
                    valid.replace("Attributes = A", "Attributes = A_ lrwxrwxrwx"),
                    valid.replace("Encrypted = -", "Encrypted = +"),
                    valid.replace("Size = 6", f"Size = {net.MAX_DOWNLOAD + 1}"),
                    valid + "\n" + valid, valid + "unparsed filename line\n"]
        for listing in listings:
            with self.subTest(listing=listing), patch.object(optiscaler, "_unpacker_output", return_value=subprocess.CompletedProcess([], 0, listing, "")):
                with self.assertRaises(net.WrongContent):
                    optiscaler._preflight_7z(Path("7z.exe"), self.root / "fixture.7z", self.root / "dest", 0)
        self.assertFalse((self.root / "dest").exists())

    def test_unpacker_output_limit_and_timeout_stop_and_reap_only_owned_children(self):
        real_popen, real_timer = subprocess.Popen, threading.Timer
        children = []
        def launch(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            children.append(process)
            return process
        for code, expected in (("import sys,time;sys.stdout.write('x'*4096);sys.stdout.flush();time.sleep(30)", net.WrongContent),
                               ("import time;time.sleep(30)", subprocess.TimeoutExpired)):
            with self.subTest(expected=expected), patch.object(optiscaler.subprocess, "Popen", side_effect=launch), patch.object(net, "MAX_TEXT", 64), patch.object(optiscaler.threading, "Timer", side_effect=lambda seconds, callback: real_timer(0.1, callback)):
                with self.assertRaises(expected):
                    optiscaler._unpacker_output([sys.executable, "-c", code], 0)
            self.assertIsNotNone(children[-1].poll())
            self.assertTrue(children[-1].stdout.closed)

    def test_native_7z_listing_and_extraction_of_owned_archive(self):
        exe = optiscaler._seven_zip()
        if exe is None:
            self.skipTest("No installed 7-Zip; parser/unsafe-listing fixture still runs")
        package = self.root / "package"
        package.mkdir()
        source = package / "OptiScaler.dll"
        source.write_bytes(b"native extractor fixture")
        (package / "nested").mkdir()
        (package / "nested" / "libxess.dll").write_bytes(b"nested extractor fixture")
        archive = self.root / "fixture.7z"
        result = subprocess.run([str(exe), "a", str(archive), package.name], cwd=self.root,
                                capture_output=True, timeout=10,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertEqual(result.returncode, 0, result.stderr)
        dest = self.root / "native-extracted"
        optiscaler.extract_7z(archive, dest)
        self.assertEqual((dest / "package" / source.name).read_bytes(), source.read_bytes())
        self.assertEqual((dest / "package/nested/libxess.dll").read_bytes(), b"nested extractor fixture")

    def update_fixture(self, dll=b"valid internal"):
        pe = bytearray(1024)
        pe[:2] = b"MZ"
        struct.pack_into("<I", pe, 0x3C, 0x80)
        pe[0x80:0x86] = b"PE\0\0\x64\x86"
        archive = self.zipped([("DLSS5-AIO.exe", pe), ("_internal/python312.dll", dll)])
        name = "DLSS5-AIO-v99.0.0-win-x64.zip"
        release = {"tag_name": "v99.0.0", "assets": [
            {"name": name, "browser_download_url": "https://publisher.invalid/archive"},
            {"name": "SHA256SUMS.txt", "browser_download_url": "https://publisher.invalid/sums"}]}
        sums = net.sha256(archive) + "  " + name + "\n" + hashlib.sha256(pe).hexdigest() + "  DLSS5-AIO.exe\n"
        return archive, release, sums

    def test_self_update_verifies_all_internal_payload_before_extracting(self):
        archive, release, sums = self.update_fixture()
        target = self.root / "stage"
        target.mkdir()
        with patch.object(net, "json_get", return_value=release), patch.object(net, "download", return_value=archive), patch.object(net, "fetch_text", return_value=sums.encode()), patch.object(selfupdate, "MIN_BYTES", 1024):
            got = selfupdate._fetch(target)
        self.assertTrue(got.is_file())
        with zipfile.ZipFile(archive, "a") as arc:
            arc.writestr("_internal/unverified.dll", b"added code")
        another = self.root / "rejected"
        another.mkdir()
        with patch.object(net, "json_get", return_value=release), patch.object(net, "download", return_value=archive), patch.object(net, "fetch_text", return_value=sums.encode()), patch.object(selfupdate, "MIN_BYTES", 1024):
            with self.assertRaisesRegex(selfupdate.UpdateError, "archive does not match"):
                selfupdate._fetch(another)
        self.assertEqual(list(another.iterdir()), [])
        self.assertIsNone(selfupdate._expected_hash("a" * 64 + "  evilDLSS5-AIO.exe", "DLSS5-AIO.exe"))
        with self.assertRaisesRegex(selfupdate.UpdateError, "more than once"):
            selfupdate._expected_hash(("a" * 64 + "  DLSS5-AIO.exe\n") * 2, "DLSS5-AIO.exe")

    @unittest.skipUnless(os.name == "nt", "Windows batch helper")
    def test_native_update_handles_unicode_percent_and_copy_failure(self):
        for fail in (False, True):
            with self.subTest(fail=fail):
                folder = self.root / ("portable %AIO_AUDIT% ! & 漢字" + str(fail))
                folder.mkdir()
                target, source = folder / "DLSS5-AIO.exe", folder / "next.exe"
                target.write_bytes(b"last good build")
                source.write_bytes(b"verified new build")
                script = selfupdate.swap_script(target, source).replace('start "" "%TARGET%"', 'exit /b 0')
                if fail:
                    source.unlink()
                bat = folder / "swap.bat"
                bat.write_text(script, encoding="utf8")
                env = dict(os.environ, AIO_AUDIT="must not expand")
                result = subprocess.run([str(Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/cmd.exe"), "/d", "/c", bat.name], cwd=folder, env=env, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(target.read_bytes(), b"last good build" if fail else b"verified new build")

    @unittest.skipUnless(os.name == "nt", "Windows batch helper")
    def test_native_folder_update_restores_matching_runtime_when_exe_copy_fails(self):
        folder = self.root / "portable %AIO_AUDIT% ! & 漢字 folder"
        stage = self.root / "stage"
        folder.mkdir()
        stage.mkdir()
        target, source = folder / "DLSS5-AIO.exe", stage / "DLSS5-AIO.exe"
        target.write_bytes(b"last good build")
        (folder / selfupdate.INTERNAL).mkdir()
        (folder / selfupdate.INTERNAL / "python.dll").write_bytes(b"last good runtime")
        (stage / selfupdate.INTERNAL).mkdir()
        (stage / selfupdate.INTERNAL / "python.dll").write_bytes(b"verified new runtime")
        # The runtime copy succeeds, then the missing EXE forces paired rollback.
        script = selfupdate.swap_script(target, source).replace('start "" "%TARGET%"', 'exit /b 0')
        bat = folder / "swap.bat"
        bat.write_text(script, encoding="utf8")
        env = dict(os.environ, AIO_AUDIT="must not expand")
        result = subprocess.run([str(Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/cmd.exe"), "/d", "/c", bat.name], cwd=folder, env=env, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(target.read_bytes(), b"last good build")
        self.assertEqual((folder / selfupdate.INTERNAL / "python.dll").read_bytes(), b"last good runtime")

    def remix_record(self, game, content=b"installed", original=None):
        target = game / "d3d9.dll"
        target.write_bytes(content)
        record = {"format": 2, "files": [target.name], "backups": [],
                  "hashes": {target.name: remixdl._identity(target)}, "backup_hashes": {}}
        if original is not None:
            backup = game / (target.name + remixdl.BACKUP_SUFFIX)
            backup.write_bytes(original)
            record["backups"].append(backup.name)
            record["backup_hashes"][backup.name] = remixdl._identity(backup)
        (game / remixdl.RECORD).write_text(json.dumps(record))
        return record

    def test_remix_rejects_all_escaping_records_before_mutating_any_file(self):
        game = self.game()
        victim = self.root / "unrelated.txt"
        victim.write_bytes(b"preserve")
        record = self.remix_record(game)
        record["files"].append("../unrelated.txt")
        (game / remixdl.RECORD).write_text(json.dumps(record))
        with self.assertRaises(remixdl.NotAModError):
            remixdl.remove(game)
        self.assertEqual(victim.read_bytes(), b"preserve")
        self.assertEqual((game / "d3d9.dll").read_bytes(), b"installed")

    def test_remix_restores_verified_backup_and_preserves_personal_changes_and_failed_journal(self):
        game = self.game()
        self.remix_record(game, original=b"original")
        (game / "d3d9.dll").write_bytes(b"personal edit")
        with self.assertRaisesRegex(remixdl.NotAModError, "Recovery incomplete"):
            remixdl.remove(game)
        self.assertEqual((game / "d3d9.dll").read_bytes(), b"personal edit")
        self.assertTrue((game / remixdl.RECORD).is_file())
        (game / "d3d9.dll").write_bytes(b"installed")
        with patch.object(remixdl, "_copy", side_effect=OSError("locked")):
            with self.assertRaisesRegex(remixdl.NotAModError, "Recovery incomplete"):
                remixdl.remove(game)
        self.assertTrue((game / remixdl.RECORD).is_file())
        remixdl.remove(game)
        self.assertEqual((game / "d3d9.dll").read_bytes(), b"original")
        self.assertFalse((game / remixdl.RECORD).exists())

    def test_remix_install_is_journaled_and_rolls_back_on_copy_failure(self):
        game = self.game()
        original = game / "d3d9.dll"
        original.write_bytes(b"original")
        archive = self.zipped([("d3d9.dll", b"proxy"), (".trex/d3d9.dll", b"runtime"), ("rtx.conf", b"config")])
        fetch = remixdl.Fetch("v1", archive.name, "https://publisher.invalid/mod.zip", archive.stat().st_size)
        real = remixdl._copy
        def failing(source, target, expected_current=None, source_identity=None):
            if target.name == "rtx.conf":
                raise OSError("fixture full disk")
            return real(source, target, expected_current, source_identity)
        with patch.object(remixdl, "resolve", return_value=fetch), patch.object(net, "download", return_value=archive), patch.object(remixdl, "_copy", side_effect=failing):
            with self.assertRaisesRegex(OSError, "full disk"):
                remixdl.install("https://github.com/publisher/mod", game)
        self.assertEqual(original.read_bytes(), b"original")
        self.assertFalse((game / ".trex/d3d9.dll").exists())
        self.assertFalse((game / remixdl.RECORD).exists())
        self.assertEqual(remixdl.repo_of("https://github.com.evil.invalid/publisher/mod"), "")

    def test_remix_recovery_metadata_names_are_case_insensitive(self):
        game = self.game()
        archive = self.zipped([(".trex/d3d9.dll", b"runtime"), (remixdl.RECORD.upper(), b"replace journal")])
        fetch = remixdl.Fetch("v1", archive.name, "https://publisher.invalid/mod.zip", archive.stat().st_size)
        with patch.object(remixdl, "resolve", return_value=fetch), patch.object(net, "download", return_value=archive):
            with self.assertRaisesRegex(remixdl.NotAModError, "recovery metadata"):
                remixdl.install("https://github.com/publisher/mod", game)
        self.assertFalse((game / remixdl.RECORD).exists())
        self.assertFalse((game / ".trex").exists())

    def test_report_text_removes_private_identity_paths_credentials_and_addresses(self):
        raw = (r"Cannot load 'C:\Users\PrivatePerson\Games\Game Name\proxy.dll': Access denied. "
               r"UNC '\\server\PrivatePerson\saved.log' "
               "Unix '/home/PrivatePerson/Game Name/log.txt' "
               "PrivatePerson private@example.invalid 192.0.2.42 2001:db8::dead:beef "
               "https://account:credential@publisher.invalid/build?token=secretvalue#private "
               "Authorization: Bearer bearer-secret api_key=key-secret token=token-secret "
               "https://[malformed/file "
               "ReShade version 6.7.0. DLSS-NR FeatureInitResult=Success")
        with patch.dict(os.environ, {"USERNAME": "PrivatePerson"}):
            text = public_text(raw)
        for private in ("PrivatePerson", "C:\\Users", "server", "/home/", "private@example", "192.0.2.42",
                        "2001:db8", "account", "credential", "secretvalue", "bearer-secret", "key-secret", "token-secret"):
            self.assertNotIn(private, text)
        self.assertIn("Access denied", text)
        self.assertIn("DLSS-NR FeatureInitResult=Success", text)
        self.assertIn("https://publisher.invalid/build", text)

    def test_bug_report_redacts_each_serialized_section_and_keeps_diagnosis(self):
        from core.diagnose import body
        game = SimpleNamespace(name="fixture", exe=Path("fixture.exe"), folder=self.root / "private-game",
                               bit_label="64-bit", api="DX11", api_why="")
        profile = r"C:\Users\PrivatePerson\AppData\Local\dlss5-aio\aio.log"
        with patch.object(body, "_loaded_block", return_value=""), patch.object(body, "_start_lines", return_value=""), patch.object(body, "_tool_log_lines", return_value=[r"Failed C:\Users\PrivatePerson\secret.log"]), patch.dict(os.environ, {"USERNAME": "PrivatePerson"}):
            report = body.issue_body("2.0.1", "RTX fixture", 89, "fixture", game, "feeder", None,
                                     "fixture tail", profile, None,
                                     last_error=r"Access denied: 'C:\Users\PrivatePerson\private.dll'",
                                     answers={"started": "yes", "happened": "PrivatePerson saw the game close"})
        self.assertNotIn("PrivatePerson", report)
        self.assertNotIn("C:\\Users", report)
        self.assertNotIn(profile, report)
        self.assertIn("Access denied", report)
        self.assertIn("aio.log", report)

    def test_shared_result_redacts_prefilled_title_body_and_record_before_url(self):
        rec = {"v": 1, "result": "failed", "game": r"C:\Users\PrivatePerson\Game",
               "exe": "fixture.exe", "route": "feeder", "gpu": "RTX fixture", "tool": "2.0.1"}
        with patch.dict(os.environ, {"USERNAME": "PrivatePerson"}):
            url = community.issue_url(rec, "PrivatePerson error https://account:credential@publisher.invalid/build?token=private")
        query = parse_qs(urlsplit(url).query)
        for text in (query["title"][0], query["body"][0]):
            self.assertNotIn("PrivatePerson", text)
            self.assertNotIn("C:\\Users", text)
            self.assertNotIn("credential", text)
        self.assertEqual(community.parse(query["body"][0])["route"], "feeder")


if __name__ == "__main__":
    unittest.main()
