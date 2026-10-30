"""Tools, runtimes and VR utilities a store lists beside the games are not games."""
import sys
import os
os.environ.setdefault("DLSS5_AIO_OFFLINE", "1")   # tests never reach the publishers
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import games  # noqa: E402


def fake(name, folder=None):
    return SimpleNamespace(name=name, folder=Path("Z:/nonexistent") / (folder or name))


class NonGames(unittest.TestCase):
    def test_tools_and_runtimes_are_dropped(self):
        for name in ("SlimeVR", "OVR Toolkit", "SteamVR", "Wallpaper Engine",
                     "Steamworks Common Redistributables", "Proton 9.0", "Proton Experimental",
                     "Source SDK Base 2013", "Valheim Dedicated Server", "Skyrim Creation Kit",
                     "Steam Linux Runtime 3.0 (sniper)"):
            with self.subTest(name=name):
                self.assertTrue(games.is_non_game(fake(name)))

    def test_games_with_similar_names_stay(self):
        for name in ("Terraria", "VRChat", "HELLDIVERS 2", "Proton Pulse", "Sdkfoo Wars",
                     "Slime Rancher", "Blender Quest", "Steam Hunters", "tModLoader"):
            with self.subTest(name=name):
                self.assertFalse(games.is_non_game(fake(name)))

    def test_folder_name_counts_when_the_store_name_is_a_title(self):
        self.assertTrue(games.is_non_game(fake("Some Title", folder="SteamVR")))

    def test_an_install_this_tool_made_is_kept(self):
        g = fake("SteamVR")
        original = games._marked
        games._marked = lambda folder: True
        try:
            self.assertFalse(games.is_non_game(g))
        finally:
            games._marked = original


if __name__ == "__main__":
    unittest.main()
