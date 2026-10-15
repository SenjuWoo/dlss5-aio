"""Verify component writers preserve originals and use the shared recovery journal."""
import io
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import dxvk, installer, mfg, net, optiscaler, refw


class ComponentRecovery(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.game = self.root / "game"
        self.game.mkdir()
        self.cache = patch.object(net, "CACHE", self.root / "cache")
        self.cache.start()

    def tearDown(self):
        self.cache.stop()
        self.temp.cleanup()

    def zip(self, **members):
        archive = self.root / "component.zip"
        with zipfile.ZipFile(archive, "w") as zipped:
            for name, value in members.items():
                zipped.writestr(name, value)
        return archive

    def refuse_backups(self, source, target):
        if target.name.endswith(installer.BACKUP_SUFFIX):
            raise PermissionError("injected backup refusal")
        return self.real_copy(source, target)

    def test_reframework_backup_failure_leaves_original_whole(self):
        target = self.game / refw.DINPUT8
        target.write_bytes(b"personal wrapper")
        archive = self.zip(**{refw.DINPUT8: b"new component"})
        self.real_copy = installer._atomic_copy
        with patch.object(refw, "resolve", return_value=("fixture", "https://example.invalid/file")), \
                patch.object(net, "download", return_value=archive), \
                patch.object(installer, "_atomic_copy", side_effect=self.refuse_backups):
            with self.assertRaises(OSError):
                refw.install(self.game)
        self.assertEqual(target.read_bytes(), b"personal wrapper")

    def test_dxvk_backup_failure_leaves_original_whole(self):
        target = self.game / "dxgi.dll"
        target.write_bytes(b"personal graphics wrapper")
        archive = self.root / "dxvk.tar.gz"
        with tarfile.open(archive, "w:gz") as packed:
            for name in ("dxgi.dll", "d3d11.dll"):
                member = tarfile.TarInfo("dxvk-fixture/x64/" + name)
                member.size = len(b"new component")
                packed.addfile(member, io.BytesIO(b"new component"))
        self.real_copy = installer._atomic_copy
        with patch.object(dxvk, "resolve", return_value=("fixture", "https://example.invalid/file")), \
                patch.object(net, "download", return_value=archive), \
                patch.object(installer, "_atomic_copy", side_effect=self.refuse_backups):
            with self.assertRaises(OSError):
                dxvk.install(self.game, True)
        self.assertEqual(target.read_bytes(), b"personal graphics wrapper")

    def test_zip_component_calls_journal_writer_with_complete_staged_bytes(self):
        archive = self.zip(**{refw.DINPUT8: b"whole component"})
        calls = []
        def writer(source, target):
            calls.append((source.read_bytes(), target))
        with patch.object(refw, "resolve", return_value=("fixture", "https://example.invalid/file")), \
                patch.object(net, "download", return_value=archive):
            refw.install(self.game, writer=writer)
        self.assertEqual(calls, [(b"whole component", self.game / refw.DINPUT8)])
        self.assertFalse((self.game / refw.DINPUT8).exists())

    def test_loader_configuration_merge_is_journalled_and_preserves_user_settings(self):
        target = self.game / "dinput8.ini"
        original = "[Personal]\nKeep=1\n"
        target.write_text(original, encoding="utf8")
        report = installer.Report()
        mfg._merge_ini(target, writer=lambda source, dst: installer._copy(source, dst, report, self.game))
        self.assertIn("Keep=1", target.read_text(encoding="utf8"))
        self.assertIn("[GlobalSets]", target.read_text(encoding="utf8"))
        self.assertEqual((self.game / (target.name + installer.BACKUP_SUFFIX)).read_text(), original)
        self.assertIn(target.name, report.hashes)

    def test_disabling_mfg_keeps_later_personal_bytes(self):
        target = self.game / mfg.FILES[0]
        target.write_bytes(b"changed after installation")
        removed = mfg.remove_leftovers(self.game, [target.name])
        self.assertIn(target.name, removed)
        self.assertFalse(target.exists())
        preserved = list(self.game.glob(target.name + ".dlss5-aio-displaced*"))
        self.assertEqual([path.read_bytes() for path in preserved], [b"changed after installation"])

    def test_disabling_mfg_refuses_an_unverified_original_loader_backup(self):
        unlock = self.game / mfg.FILES[0]
        unlock.write_bytes(b"installed unlock")
        loader = self.game / mfg.LOADER_NAMES[0]
        loader.write_bytes(b"installed loader")
        backup = loader.with_name(loader.name + mfg.BACKUP_SUFFIX)
        backup.write_bytes(b"unverified or changed original")
        with self.assertRaises(OSError):
            mfg.remove_leftovers(self.game, [unlock.name, loader.name, backup.name])
        self.assertEqual(loader.read_bytes(), b"installed loader")
        self.assertEqual(backup.read_bytes(), b"unverified or changed original")

    def test_failed_optional_ini_writer_never_commits_partial_configuration(self):
        target = self.game / optiscaler.INI
        original_write = Path.write_text
        def partial(path, text, *args, **kwargs):
            original_write(path, "PARTIAL", *args, **kwargs)
            raise OSError("injected configuration write failure")
        writers = ((optiscaler.enable_nr, ()), (optiscaler.set_overlay_key, (65,)),
                   (optiscaler.set_dx11_bridged_upscaler, ()), (optiscaler.enable_inputs, ("xess", "DX12")))
        for function, args in writers:
            with self.subTest(writer=function.__name__):
                target.write_text("[Personal]\nKeep=1\n", encoding="utf8")
                report = installer.Report()
                with patch.object(Path, "write_text", partial), self.assertRaises(OSError):
                    installer._configure(self.game, report, function, *args, names=(optiscaler.INI,))
                self.assertEqual(target.read_text(encoding="utf8"), "[Personal]\nKeep=1\n")

    def test_optiscaler_backup_failure_never_overwrites_tuned_proxy(self):
        target = self.game / optiscaler.DEFAULT_PROXY
        target.write_bytes(b"personal proxy")
        archive = self.zip(**{optiscaler.MAIN_DLL: b"replacement"})
        self.real_copy = installer._atomic_copy
        with patch.object(installer, "_atomic_copy", side_effect=self.refuse_backups):
            with self.assertRaises(OSError):
                optiscaler.install(self.game, dl=lambda *args: archive,
                                   release=("fixture", "https://example.invalid/file.zip"))
        self.assertEqual(target.read_bytes(), b"personal proxy")


if __name__ == "__main__":
    unittest.main()
