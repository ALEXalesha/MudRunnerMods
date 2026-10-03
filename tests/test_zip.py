"""The zip law: MudRunner's PhysFS 2.0 must be able to read every package.

1.0.0 failed in game because the level package had Zip64 local headers (version
45, sizes 0xFFFFFFFF) that PhysFS 2.0 rejects as "Corrupted archive". These
checks hold the law on the stock archives and the Workshop items on this PC
(so the law matches what the game reads), on a deliberately bad zip, and on
every package the build writes.
"""

import glob
import io
import os
import tempfile
import unittest
import zipfile

import common
from common import HAVE_GAME, GAME
import build_mods
import zipcheck

WORKSHOP_ZIPS = glob.glob(os.path.join(os.path.dirname(os.path.dirname(GAME)),
                                       "workshop", "content", "675010", "*", "*.zip"))


class ZipLawTest(unittest.TestCase):
    def test_forced_zip64_is_caught(self):
        path = os.path.join(tempfile.mkdtemp(prefix="mrzip_"), "bad.zip")
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            with z.open(zipfile.ZipInfo("levels/x.stg"), "w", force_zip64=True) as dst:
                dst.write(b"x" * 1000)
        pr = zipcheck.problems(path)
        self.assertTrue(any("version needed" in p for p in pr), pr)
        self.assertTrue(any("Zip64" in p or "0xffffffff" in p for p in pr), pr)

    def test_plain_zip_passes(self):
        path = os.path.join(tempfile.mkdtemp(prefix="mrzip_"), "ok.zip")
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("classes/trucks/a.xml", "<Truck />")
            zi = zipfile.ZipInfo("levels/x.stg")
            zi.file_size = 5000
            with z.open(zi, "w") as dst:
                dst.write(os.urandom(5000))
        self.assertEqual(zipcheck.problems(path), [])

    @unittest.skipUnless(HAVE_GAME, "game not installed")
    def test_stock_archives_pass(self):
        for name in ["Media.zip", "MeshCache.zip"] + common.DLC:
            self.assertEqual(zipcheck.problems(os.path.join(GAME, name)), [], name)

    @unittest.skipUnless(WORKSHOP_ZIPS, "no Workshop items on this PC")
    def test_working_workshop_items_pass(self):
        for p in WORKSHOP_ZIPS:
            self.assertEqual(zipcheck.problems(p), [], p)

    @unittest.skipUnless(HAVE_GAME, "game not installed")
    def test_every_class_package_passes(self):
        out = tempfile.mkdtemp(prefix="mrpkg_")
        for name, b in common.built().items():
            if b.levels:
                continue        # level packages: StgPackageTest (fake level) and the slow test below
            path = os.path.join(out, build_mods.zip_name(b.spec))
            build_mods.write_package(b, common.fs(), path)
            self.assertEqual(zipcheck.problems(path), [], name)
            with zipfile.ZipFile(path) as z:
                self.assertFalse([n for n in z.namelist() if n.endswith("/")])
                self.assertEqual(sorted(z.namelist()), sorted(b.files))

    @unittest.skipUnless(HAVE_GAME and os.environ.get("MR_SLOW") == "1", "set MR_SLOW=1 (writes 300 MB)")
    def test_level_package_passes(self):
        b = common.built()["unlocked_trucks"]
        path = os.path.join(tempfile.mkdtemp(prefix="mrpkg_"), "levels.zip")
        build_mods.write_package(b, common.fs(), path)
        self.assertEqual(zipcheck.problems(path), [])


    @unittest.skipUnless(HAVE_GAME, "game not installed")
    def test_probe_is_byte_identical(self):
        import build_probe
        out = build_probe.build(tempfile.mkdtemp(prefix="mrprobe_"), GAME)
        with zipfile.ZipFile(out) as z:
            for p in build_probe.PROBE_FILES:
                self.assertEqual(z.read(p), common.fs().read(p), p)
        self.assertEqual(zipcheck.problems(out), [])


if __name__ == "__main__":
    unittest.main()
