"""The truck-file law: no mod writes to classes/trucks/<stock name>.xml.

In game (tests 3 to 5, 04.10 to 10.10) a stock truck class shadowed by an extra
MediaPath package crashed the game ("Single player", Esc, the truck menu), even
byte for byte (`install_local.py --probe truck`). New trucks under their own
names worked (Infinite Fuel, 10.10). So every truck change ships as a full copy
`<prefix>_<stock truck>` with its own selection icon and display names, and no
output of any mod may hold a stock truck path.

These checks do not use the build's own guard (build_mods.forbidden_files): they
list the stock truck names straight from the game archives and look at every
output: the packages in memory, the zips as written, custom packages, the
Workshop folders and, when present, the packages in build/local that the
install script mounts.
"""

import os
import re
import tempfile
import unittest
import zipfile

import common
from common import HAVE_GAME, built, fs, drivable_trucks, workshop_dir
import build_mods
import build_workshop

TRUCK_MODS = ["hyper_power", "powerful_engines", "awd_difflock", "deep_fording", "no_damage", "infinite_fuel"]
PREFIXES = ("otf", "otd", "otp", "oth", "ota", "otw", "otc", "otg")
TRUCK_DIR = "classes/trucks/"


def stock_truck_paths():
    """Every classes/trucks/*.xml in Media.zip and the DLC archives, read with zipfile."""
    out = set()
    for name in ["Media.zip"] + common.DLC:
        full = os.path.join(common.GAME, name)
        if os.path.isfile(full):
            with zipfile.ZipFile(full) as z:
                out |= {n.lower() for n in z.namelist() if n.lower().startswith(TRUCK_DIR)
                        and n.lower().endswith(".xml")}
    return out


def truck_entries(paths):
    return [p.replace("\\", "/").lower() for p in paths if p.replace("\\", "/").lower().startswith(TRUCK_DIR)]


@unittest.skipUnless(HAVE_GAME, "game not installed")
class NoStockTruckFileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stock = stock_truck_paths()
        cls.drivable = set(drivable_trucks())

    def assert_clean(self, paths, where):
        bad = [p for p in truck_entries(paths) if p in self.stock]
        self.assertEqual(bad, [], "%s writes stock truck files" % where)
        for p in truck_entries(paths):
            m = re.match(r"^classes/trucks/(%s)_([a-z0-9_]+)\.xml$" % "|".join(PREFIXES), p)
            self.assertTrue(m, "%s: %s is not <prefix>_<truck>.xml" % (where, p))
            self.assertIn(m.group(2), self.drivable, "%s: %s copies no drivable stock truck" % (where, p))

    def test_stock_list_is_complete(self):
        self.assertEqual(len(self.stock), 144)
        self.assertIn("classes/trucks/uaz469.xml", self.stock)

    def test_no_mod_writes_a_stock_truck_file(self):
        """Every package in memory, every zip as written, custom packages."""
        n = 0
        for name, b in built().items():
            self.assert_clean(b.files, name)
            n += len(truck_entries(b.files))
        self.assertEqual(n, 36 * 5 + 10)             # five mods x 36 trucks, AWD on 10
        out = tempfile.mkdtemp(prefix="mrlaw_")
        for name, b in built().items():
            if b.levels:
                continue                              # level files: no class files (test_zip)
            path = os.path.join(out, build_mods.zip_name(b.spec))
            build_mods.write_package(b, fs(), path)
            with zipfile.ZipFile(path) as z:
                self.assert_clean(z.namelist(), path)
        for only in (["infinite_fuel"], ["infinite_fuel", "no_damage", "grippy_wheels", "strong_winch"],
                     ["hyper_power", "awd_difflock", "deep_fording"]):
            custom = build_mods.build_all(common.GAME, None, only=only, skip_levels=True, verbose=False,
                                          fs=fs())["custom"]
            self.assert_clean(custom.files, "custom %s" % only)
            self.assertTrue(truck_entries(custom.files), only)

    def test_workshop_folders(self):
        base = workshop_dir()
        for d in sorted(os.listdir(base)):
            mod = os.path.join(base, d, "mod")
            rel = []
            for dp, _dn, fn in os.walk(mod):
                rel += [os.path.relpath(os.path.join(dp, x), mod) for x in fn]
            self.assert_clean(rel, d)
            self.assertTrue(truck_entries(rel), d)

    @unittest.skipUnless(os.path.isdir(os.path.join(common.ROOT, "build", "local")), "no build/local")
    def test_installable_packages_on_disk(self):
        """What install_local.py mounts. The probes are left out: --probe truck, identical
        and changed hold uaz469.xml on purpose (diagnosis only)."""
        local = os.path.join(common.ROOT, "build", "local")
        for f in sorted(os.listdir(local)):
            if f.startswith("opentrail_") and f.endswith(".zip"):          # not the otprobe_ zips
                with zipfile.ZipFile(os.path.join(local, f)) as z:
                    self.assert_clean(z.namelist(), f)

    def test_truck_mods_ship_no_stock_path_at_all(self):
        """A truck mod only adds: trucks, icons and strings files under new names."""
        for m in TRUCK_MODS:
            b = built()[m]
            self.assertEqual([p for p in b.files if fs().exists(p)], [], m)
            for p in b.files:
                self.assertRegex(p, r"^(classes/trucks/ot[a-z]_|billboards/trucks/ot[a-z]_|"
                                    r"strings/[a-z-]+/opentrail_%s\.txt$)" % m, m)


@unittest.skipUnless(HAVE_GAME, "game not installed")
class NamesTest(unittest.TestCase):
    def test_new_trucks_have_names_in_every_language(self):
        langs = build_workshop.languages(fs())
        self.assertIn("en", langs)
        self.assertIn("ru", langs)
        self.assertEqual(len(langs), 12)
        for m in TRUCK_MODS:
            b = built()[m]
            spec = build_mods.load_spec(m)
            new = {p[len(TRUCK_DIR):-4] for p in truck_entries(b.files)}
            for lang in langs:
                path = "strings/%s/opentrail_%s.txt" % (lang, m)
                data = b.files.get(path)
                self.assertIsNotNone(data, path)
                self.assertFalse(fs().exists(path), "%s replaces a stock strings file" % path)
                self.assertEqual(data[:2], b"\xff\xfe", path)            # UTF-16 LE with BOM
                self.assertEqual(len(data) % 2, 0, path)
                text = data[2:].decode("utf-16-le")
                self.assertNotRegex(text, "(?<!\r)\n", "bare LF in %s" % path)
                entries = dict(re.findall(r"^/([a-z0-9_]+)\r\n([^\r\n]+)\r\n", text, re.M))
                self.assertEqual(set(entries), new, path)
                suffix = spec["suffix_ru"] if lang == "ru" else spec["workshop_suffix"]
                for k, v in entries.items():
                    self.assertTrue(v.endswith(" (%s)" % suffix), "%s %s=%s" % (path, k, v))
                    self.assertNotIn("_", v.split(" (")[0], "%s: id instead of a name: %s" % (path, v))
            self.assertEqual(b.files["strings/en/opentrail_%s.txt" % m][2:].decode("utf-16-le").count("\r\n/"),
                             len(new) - 1, m)

    def test_names_can_be_left_out(self):
        st = common.stock()
        files, _p = build_mods.heir_package(build_mods.load_spec("no_damage"), fs(), st, names=False)
        self.assertFalse([p for p in files if p.startswith("strings/")])
        self.assertTrue(truck_entries(files))

    def test_custom_names_say_own_set(self):
        """16.10: one copy per truck for your own set, "<truck> (Свой набор)" ("(Custom)"
        in the other languages), whatever mods are in it (was "A + B" until 1.0.0)."""
        b = build_mods.build_all(common.GAME, None, only=["infinite_fuel", "no_damage"], skip_levels=True,
                                 verbose=False, fs=fs())["custom"]
        text = b.files["strings/en/opentrail_custom.txt"][2:].decode("utf-16-le")
        self.assertIn("/otc_kamaz4310\r\nC-4310 (Custom)\r\n", text)
        ru = b.files["strings/ru/opentrail_custom.txt"][2:].decode("utf-16-le")
        self.assertIn("(Свой набор)", ru)


if __name__ == "__main__":
    unittest.main()
