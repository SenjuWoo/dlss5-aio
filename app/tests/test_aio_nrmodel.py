"""The NR model choice: one value, written where each route reads it.

renodx-dlss5 takes it from [RenoDX.DLSS5] NRPreset in ReShade.ini and
OptiScaler from [DlssNr] Preset in OptiScaler.ini - the fork's own menu
calls both "NR model" (DlssNr_MenuControls.cpp): 0 Automatic, 1 Original
(the September model), 2 Optimized (the FP8 model that first ships in
nvngx_dlssnr 310.9.16). There is no preset 3. Offline only.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("DLSS5_AIO_OFFLINE", "1")   # tests never reach the publishers

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
from core import dlss, installer, optiscaler, reshade_ini


class NrModelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="aio_nrmodel_")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_the_values_are_the_fork_s_own(self):
        # A 3 is "Unavailable preset" in the fork's menu; offering it would
        # write a value the add-on ignores.
        self.assertEqual(set(optiscaler.NR_PRESETS), {0, 1, 2})
        self.assertIn("Model A", optiscaler.NR_PRESETS[1])
        self.assertIn("Model B", optiscaler.NR_PRESETS[2])

    def test_reshade_ini_carries_the_model_and_keeps_the_user_s_keys(self):
        ini_path = self.root / "ReShade.ini"
        ini_path.write_text("[RenoDX.DLSS5]\nNeuralUplift=1\nIntensity=0.8\n",
                            encoding="utf8")
        reshade_ini.write_reshade_ini(self.root, 3, 2)
        ini = reshade_ini.Ini.load(ini_path)
        self.assertEqual(ini.get("RenoDX.DLSS5", "NRPreset"), "2")
        self.assertEqual(ini.get("RenoDX.DLSS5", "Intensity"), "0.8")

    def test_addon_only_ini_carries_the_model(self):
        reshade_ini.write_addon_only_ini(self.root, 1)
        ini = reshade_ini.Ini.load(self.root / "ReShade.ini")
        self.assertEqual(ini.get("RenoDX.DLSS5", "NRPreset"), "1")

    def test_automatic_writes_nothing(self):
        reshade_ini.write_addon_only_ini(self.root, 0)
        ini = reshade_ini.Ini.load(self.root / "ReShade.ini")
        self.assertIsNone(ini.get("RenoDX.DLSS5", "NRPreset"))

    def test_a_stale_three_is_not_offered(self):
        # 2.2.1 wrote Preset 3 as "Preset 3"; it was never a model. Reading it
        # back must not resurrect it as a choice.
        self.assertNotIn(3, optiscaler.NR_PRESETS)

    def test_the_install_says_when_the_build_cannot_give_model_b(self):
        rep = installer.Report()
        installer._nr_model_note(rep, "310.8.0", 2)
        self.assertTrue(rep.notes)
        self.assertIn("310.9.16", rep.notes[0])

    def test_the_install_is_quiet_when_the_build_can(self):
        rep = installer.Report()
        installer._nr_model_note(rep, "310.9.16", 2)
        self.assertEqual(rep.notes, [])

    def test_driver_621_01_names_the_startup_crash(self):
        text = dlss.driver_warning(dlss.NATIVE, "621.01",
                                   offered=[dlss.STANDALONE])
        self.assertIn("621.01", text)
        self.assertIn("startup", text)
        # The same route one driver before the change: the evaluate fault,
        # not the crash.
        mid = dlss.driver_warning(dlss.NATIVE, "617.14",
                                  offered=[dlss.STANDALONE])
        self.assertIn("NGX", mid)
        self.assertNotIn("startup", mid)


if __name__ == "__main__":
    unittest.main()
