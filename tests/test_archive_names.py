"""The archive-name law: a package name (without .zip) has at most 16 characters.

The real cause of every in-game crash from 03.10 to 10.10 (18 WER reports, 10
dumps, all MSVCR110.dll+0x6d5ff, c0000409, fast fail 5 = invalid parameter):
MudRunner.exe asks PhysFS which archive a truck file (classes/trucks/<name>.xml)
or a level (levels/<name>.stg) came from (PHYSFS_getRealDir), and when it is a
.zip it copies the archive name between the last '/' and the '.' into a 17 byte
buffer: strncpy_s(buf, 17, name, len). Then it compares that name with the
"%llx" id of every loaded Workshop item, to know which mod the truck belongs to.
Workshop zips are named after the item id (47f38fe1.zip, 8 characters), Media
and _dlc_oldtimers fit too; "OpenTrail_Infinite_Fuel" (23) does not, and
strncpy_s ends the process. Wheel, plant and strings files never go through
this function, so those packages worked with equally long names.

A name made only of hex digits could match a Workshop item id, so names must
contain a non-hex letter (all ours start with "opentrail_" or "otprobe_").
"""

import os
import re
import unittest
import zipfile

import common
from common import HAVE_GAME, GAME
import build_mods
import build_probe
import engine_limits
import install_local

EXE = os.path.join(GAME, "MudRunner.exe")


def check_name(test, zname):
    test.assertTrue(zname.endswith(".zip"), zname)
    stem = zname[:-4]
    test.assertLessEqual(len(stem), 16, "%s: %d characters, the exe copies at most 16" % (zname, len(stem)))
    test.assertRegex(stem, r"^[a-z0-9_]+$", zname)
    test.assertFalse(re.fullmatch(r"[0-9a-f]+", stem), "%s looks like a Workshop item id" % zname)


class ArchiveNameTest(unittest.TestCase):
    def test_limit_is_16(self):
        self.assertEqual(engine_limits.ARCHIVE_NAME_MAX, 16)

    def test_every_package_name_fits(self):
        names = [build_mods.zip_name(build_mods.load_spec(n)) for n in build_mods.load_order()]
        names.append(build_mods.CUSTOM_ZIP)
        names += [build_probe.PROBE_ZIP, build_probe.CHANGED_ZIP]
        names += [build_probe.sub_zip_name(n) for n in build_probe.SUB_PROBES]
        self.assertEqual(len(set(names)), len(names))
        for z in names:
            check_name(self, z)
            self.assertTrue(install_local._is_ours('<MediaPath Path="D:/x/%s" />\n' % z), z)

    def test_old_long_names_are_still_removed(self):
        self.assertTrue(install_local._is_ours('<MediaPath Path="C:/a/OpenTrail_Infinite_Fuel.zip" />\n'))
        self.assertFalse(install_local._is_ours('<MediaPath Path="Media.zip" />\n'))
        self.assertFalse(install_local._is_ours('<MediaPath Path="_dlc_valley.zip" />\n'))

    def test_the_build_refuses_a_long_name(self):
        b = build_mods.Built("x", {"title": "x"})
        b.files["classes/plants/x.xml"] = b"<Plant />"
        out = os.path.join(common.tempfile.mkdtemp(prefix="mrname_"), "opentrail_much_too_long.zip")
        with self.assertRaises(build_mods.BuildError):
            build_mods.write_package(b, None, out)
        self.assertFalse(os.path.exists(out))

    @unittest.skipUnless(os.path.isdir(os.path.join(common.ROOT, "build", "local")), "no build/local")
    def test_packages_on_disk(self):
        """What install_local.py mounts (and the release copies)."""
        local = os.path.join(common.ROOT, "build", "local")
        for f in sorted(os.listdir(local)):
            if f.endswith(".zip"):
                check_name(self, f)

    @unittest.skipUnless(os.path.isfile(EXE), "game not installed")
    def test_limit_matches_the_exe(self):
        """strncpy_s(buf, 17, ...) right after the '.zip' compare, read back from the
        installed exe: a game update that changes the buffer fails here first."""
        self.assertEqual(engine_limits.read_exe_archive_name_max(EXE), engine_limits.ARCHIVE_NAME_MAX)


@unittest.skipUnless(HAVE_GAME, "game not installed")
class WrittenPackageNamesTest(unittest.TestCase):
    def test_written_class_packages(self):
        out = common.tempfile.mkdtemp(prefix="mrnames_")
        for name, b in common.built().items():
            if b.levels:
                continue
            path = os.path.join(out, build_mods.zip_name(b.spec))
            build_mods.write_package(b, common.fs(), path)
            check_name(self, os.path.basename(path))
            with zipfile.ZipFile(path) as z:
                self.assertTrue(z.namelist())


if __name__ == "__main__":
    unittest.main()
