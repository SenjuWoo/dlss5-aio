"""Nothing a game ships or a drive holds is left out because a list was too short."""
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
from core import dlss, dlssupdate as du, emulators, games, prefs  # noqa: E402


class EveryRuntimeIsListed(unittest.TestCase):
    """An Unreal game keeps each vendor's runtime in its own plugin folder."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.game = games.Game("Fixture game", self.root, self.root / "Game.exe", 64, "DX12")
        self.game.exe.write_bytes(dll("1.0.0", size=8192))
        self.pref = patch.object(prefs, "FILE", self.root / "settings.json")
        self.pref.start()
        dlss.forget_walk()

    def tearDown(self):
        self.pref.stop()
        self.temp.cleanup()
        dlss.forget_walk()

    def test_more_than_six_runtimes_in_separate_folders(self):
        layout = {"DLSS": ("dlss", "dlssd"), "Streamline": ("dlssg",), "XeSS": ("xess", "xess_dx11"),
                  "XeFG": ("xess_fg", "xell"), "FSR": ("fsr_loader", "fsr4", "fsr4_fg")}
        for plugin, families in layout.items():
            folder = self.root / "Engine" / "Plugins" / plugin / "Binaries" / "Win64"
            folder.mkdir(parents=True)
            for family in families:
                (folder / du.FILE_OF[family]).write_bytes(dll("1.0.0", size=8192))
        want = {family for families in layout.values() for family in families}
        self.assertEqual({entry.family for entry in du.scan(self.game, fresh=True)}, want)

    def test_detection_still_stops_early(self):
        """The route detector only needs proof that DLSS is there, not every copy."""
        for n in range(8):
            folder = self.root / f"copy{n}"
            folder.mkdir()
            (folder / "nvngx_dlss.dll").write_bytes(dll("1.0.0", size=8192))
        self.assertEqual(len(dlss.find_dlss_files(self.root)), 6)


class EveryLocalDriveIsSearched(unittest.TestCase):
    FIXED, REMOTE, CDROM = 3, 4, 5

    def test_letters_past_h_are_included(self):
        with patch.object(emulators, "_logical_drives",
                          return_value={"C": self.FIXED, "S": self.FIXED, "Z": self.FIXED}):
            letters = emulators.drive_letters("CDEFGH")
        self.assertIn("S", letters)
        self.assertIn("Z", letters)
        self.assertEqual(letters[:6], "CDEFGH")      # what was searched before still is

    def test_network_and_optical_drives_are_not_added(self):
        with patch.object(emulators, "_logical_drives",
                          return_value={"C": self.FIXED, "Y": self.REMOTE, "X": self.CDROM}):
            letters = emulators.drive_letters("CDEFGH")
        self.assertNotIn("Y", letters)
        self.assertNotIn("X", letters)

    def test_store_scans_ask_every_drive(self):
        asked = []

        def isdir(path):
            asked.append(str(path).replace("\\", "/"))
            return False

        with patch.object(emulators, "_logical_drives", return_value={"C": self.FIXED, "S": self.FIXED}), \
                patch.object(games, "_isdir", side_effect=isdir), \
                patch.object(games, "is_removable", return_value=False):
            games.scan_xbox()
            games.scan_amazon()
            games.scan_folders()
        for wanted in ("S:/XboxGames", "S:/Amazon Games/Library", "S:/"):
            self.assertIn(wanted, asked)


if __name__ == "__main__":
    unittest.main()
