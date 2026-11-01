"""Anti-cheat detection regressions for the fork's own suite.

Black Desert Online ships XIGNCODE3 as `bin64\\XignCode` (the KR client's own
log names `bin64\\XignCode\\KR\\1\\xmag_x64.xem`). `bin64` holds well over
eighty files, so the scan used to stop before the end of the alphabet and
report the game as having no anti-cheat when it was handed the install root.
The reference suite's #187 cases (a marker must be a whole word) still hold.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("DLSS5_AIO_OFFLINE", "1")   # tests never reach the publishers

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
from core import anticheat


class AnticheatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="aio_anticheat_")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _bdo(self) -> Path:
        """An install shaped like Black Desert's: a busy bin64 with XignCode."""
        bin64 = self.root / "bin64"
        bin64.mkdir()
        for i in range(100):
            (bin64 / f"a_dll_{i:03d}.dll").write_bytes(b"x")
        (bin64 / "BlackDesert64.exe").write_bytes(b"MZ")
        xc = bin64 / "XignCode" / "KR" / "1"
        xc.mkdir(parents=True)
        (xc / "xmag_x64.xem").write_bytes(b"x")
        return bin64

    def test_the_install_root_finds_xigncode_past_eighty_entries(self):
        bin64 = self._bdo()
        self.assertGreater(len(list(bin64.iterdir())), 80)
        found = anticheat.detect(self.root, self.root)
        self.assertTrue(found.present, found.evidence)
        self.assertIn("XIGNCODE3", found.products)
        self.assertTrue(any("XignCode" in e for e in found.evidence), found.evidence)

    def test_the_executable_folder_finds_it_too(self):
        bin64 = self._bdo()
        found = anticheat.detect(self.root, bin64)
        self.assertIn("XIGNCODE3", found.products)

    def test_a_marker_inside_a_longer_word_is_still_not_evidence(self):
        bin64 = self.root / "bin64"
        bin64.mkdir()
        for i in range(100):
            (bin64 / f"a_asset_{i:03d}.pak").write_bytes(b"x")
        (bin64 / "vanguard_outfit.pak").write_bytes(b"x")
        (bin64 / "gameguardians.txt").write_bytes(b"x")
        found = anticheat.detect(self.root, self.root)
        self.assertFalse(found.present, found.products)


if __name__ == "__main__":
    unittest.main()
