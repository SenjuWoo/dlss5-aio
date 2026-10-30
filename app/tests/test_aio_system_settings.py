"""Prove GPU preference changes cannot precede their recovery record."""
import sys
import os
os.environ.setdefault("DLSS5_AIO_OFFLINE", "1")   # tests never reach the publishers
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import gpupref


class GpuPreferenceRecovery(unittest.TestCase):
    def test_refused_checkpoint_leaves_registry_untouched(self):
        memory = gpupref.Memory()
        with patch.object(gpupref, "backend", memory):
            with self.assertRaises(OSError):
                gpupref.apply(["Game.exe"], checkpoint=lambda rows: self.refuse())
        self.assertEqual(memory.values, {})

    @staticmethod
    def refuse():
        raise OSError("injected journal failure")

    def test_record_precedes_each_write_and_restores_only_our_token(self):
        saved = []
        class Registry(gpupref.Memory):
            def set(self, name, value):
                assert saved and saved[-1]["exe"] == name
                super().set(name, value)
        memory = Registry()
        memory.values["Game.exe"] = "AutoHDREnable=1;"
        with patch.object(gpupref, "backend", memory):
            records, theirs = gpupref.apply(["Game.exe"], checkpoint=lambda rows: saved.extend(rows))
            self.assertFalse(theirs)
            self.assertEqual(records, saved)
            self.assertIn("GpuPreference=2;", memory.values["Game.exe"])
            gpupref.restore(records)
        self.assertEqual(memory.values["Game.exe"], "AutoHDREnable=1;")

    def test_external_change_during_checkpoint_is_preserved(self):
        memory = gpupref.Memory()
        with patch.object(gpupref, "backend", memory):
            records, theirs = gpupref.apply(["Game.exe"], checkpoint=lambda rows: memory.values.update({"Game.exe": "GpuPreference=1;"}))
        self.assertFalse(records)
        self.assertEqual(theirs, ["Game.exe"])
        self.assertEqual(memory.values["Game.exe"], "GpuPreference=1;")

    def test_choice_arriving_between_reads_is_preserved(self):
        class Registry(gpupref.Memory):
            def get(self, name):
                value = super().get(name)
                self.values[name] = "GpuPreference=1;AutoHDREnable=1;"
                return value
        memory = Registry()
        with patch.object(gpupref, "backend", memory):
            records, theirs = gpupref.apply(["Game.exe"])
        self.assertFalse(records)
        self.assertEqual(theirs, ["Game.exe"])
        self.assertEqual(memory.values["Game.exe"], "GpuPreference=1;AutoHDREnable=1;")


if __name__ == "__main__":
    unittest.main()
