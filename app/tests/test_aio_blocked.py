"""A build that needs AMD's loader beside it cannot update a game that has none, and
so must not keep that game's update button lit."""
import os
os.environ.setdefault("DLSS5_AIO_OFFLINE", "1")   # tests never reach the publishers
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import dlssupdate as du  # noqa: E402

GAME = Path("Z:/nonexistent/game")
LOADER = "amd_fidelityfx_loader_dx12.dll"


def entry(name, family, version="4.0.3.604", state=du.ORIGINAL, folder=GAME):
    return du.Entry(path=folder / name, rel=name, family=family, version=version, state=state,
                    original="", label="", backup=None)


class Blocked(unittest.TestCase):
    NEW = {"version": "4.1.2.4555", "requires": {LOADER: "2.3.0.4555"}}

    def test_no_loader_in_the_folder_blocks_the_line(self):
        up = entry("amd_fidelityfx_upscaler_dx12.dll", "fsr4")
        self.assertEqual(du.missing_dependency(up, [up, entry("nvngx_dlss.dll", "dlss")], self.NEW), [LOADER])

    def test_a_loader_beside_it_unblocks_it_even_when_older(self):
        up = entry("amd_fidelityfx_upscaler_dx12.dll", "fsr4")
        old_loader = entry(LOADER, "fsr_loader", "2.1.0.604")
        self.assertEqual(du.missing_dependency(up, [up, old_loader], self.NEW), [])

    def test_a_loader_in_another_folder_does_not_count(self):
        up = entry("amd_fidelityfx_upscaler_dx12.dll", "fsr4")
        other = entry(LOADER, "fsr_loader", folder=GAME / "other")
        self.assertEqual(du.missing_dependency(up, [up, other], self.NEW), [LOADER])

    def test_a_build_with_no_requirements_is_never_blocked(self):
        sr = entry("nvngx_dlss.dll", "dlss", "310.2.0")
        self.assertEqual(du.missing_dependency(sr, [sr], {"version": "310.9.16"}), [])


if __name__ == "__main__":
    unittest.main()
