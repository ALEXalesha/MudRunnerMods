"""Checks for the Workshop folders (tools/build_workshop.py).

Rules from the official modding guide and the MudRunner Editor: a mod is a
folder in Media/_mods/<mod id>; trucks in classes/trucks, wheels in
classes/wheels; friendly names in strings.xml (English only); preview.png in the
mod root; files with unknown extensions are left out with a warning, so only
.xml and .png go into the folder; file names lowercase letters, digits and "_";
names must be unique across mods (the game ignores folders).
"""

import os
import re
import struct
import unittest

import common
from common import HAVE_GAME, fs, stock, workshop_dir
import build_mods
import build_workshop
import mrxml

WS_MODS = ["hyper_power", "powerful_engines", "awd_difflock", "deep_fording", "no_damage", "infinite_fuel",
           "grippy_wheels"]


def png_size(path):
    with open(path, "rb") as fh:
        head = fh.read(24)
    assert head[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", head[16:24])


def folders():
    base = workshop_dir()
    return sorted(os.path.join(base, d) for d in os.listdir(base))


@unittest.skipUnless(HAVE_GAME, "game not installed")
class WorkshopTest(unittest.TestCase):
    def test_folders(self):
        names = [os.path.basename(f) for f in folders()]
        self.assertEqual(len(names), len(WS_MODS))
        for i, f in enumerate(names):
            self.assertTrue(f.startswith("%02d_OpenTrail_" % (i + 1)), f)
        self.assertFalse([n for n in names if "Winch" in n or "Unlocked" in n])

    def test_mod_folder_holds_only_xml_and_png(self):
        seen = set()
        for f in folders():
            mod = os.path.join(f, "mod")
            for dp, _dn, fn in os.walk(mod):
                for x in fn:
                    self.assertTrue(x.endswith((".xml", ".png")), x)
                    rel = os.path.relpath(os.path.join(dp, x), mod).replace("\\", "/")
                    if rel.startswith("classes/"):
                        stem = x[:-4]
                        self.assertRegex(stem, r"^[a-z0-9_]+$")
                        self.assertNotIn(stem, seen, "name used twice across mods")
                        seen.add(stem)
                        self.assertFalse(fs().exists(rel), "%s would shadow a stock file" % rel)
            self.assertTrue(os.path.isfile(os.path.join(mod, "strings.xml")))
            self.assertEqual(png_size(os.path.join(mod, "preview.png")), (512, 512))
            self.assertLess(os.path.getsize(os.path.join(mod, "preview.png")), 1024 * 1024)

    def test_strings_name_every_class(self):
        for f in folders():
            mod = os.path.join(f, "mod")
            tops = mrxml.parse(open(os.path.join(mod, "strings.xml"), "rb").read())
            self.assertEqual([t.tag for t in tops], ["ModStrings"])
            ids = {s.get("Id"): s.get("Value") for s in tops[0].children}
            files = set()
            for kind in ("trucks", "wheels"):
                d = os.path.join(mod, "classes", kind)
                if os.path.isdir(d):
                    files |= {x[:-4] for x in os.listdir(d)}
            self.assertEqual(set(ids), files, f)
            for v in ids.values():
                self.assertTrue(v and "_" not in v.split(" (")[0], v)
                self.assertTrue(all(ord(c) < 128 for c in v), "English only: %s" % v)

    def test_variants_resolve_to_the_mod_values(self):
        """Every inherited truck/wheel over the stock files gives exactly the planned
        values and nothing else changes (verify_variants raises otherwise)."""
        st = stock()
        for name in WS_MODS:
            spec = build_mods.load_spec(name)
            variants = build_workshop.plan_variants(name, spec, fs(), st)
            n = build_workshop.verify_variants(name, spec, variants, fs(), st)
            self.assertGreater(n, 0)

    def test_base_game_trucks_only(self):
        base_trucks = [n for n in common.drivable_trucks() if common.source("trucks", n) == "Media.zip"]
        self.assertEqual(len(base_trucks), 20)
        for f in folders():
            d = os.path.join(f, "mod", "classes", "trucks")
            for x in os.listdir(d):
                parent = mrxml.parent_name(mrxml.parse(open(os.path.join(d, x), "rb").read()))
                self.assertEqual(common.source("trucks", parent), "Media.zip", x)
            if "AWD" not in f:
                self.assertEqual(len(os.listdir(d)), 20, f)

    def test_copy_paste_files_use_crlf(self):
        for f in folders():
            for name in ("steam_page.txt", "steam_description.txt"):
                data = open(os.path.join(f, name), "rb").read()
                self.assertIn(b"\r\n", data)
                self.assertNotRegex(data, re.compile(b"(?<!\r)\n"), "bare LF in %s" % name)
                text = data.decode("utf-8")
                self.assertIn("Saber Interactive", text)
                self.assertGreater(len(text), 300)
            desc = open(os.path.join(f, "steam_description.txt"), encoding="utf-8").read()
            self.assertRegex(desc, "[А-Яа-я]")        # Russian part
            self.assertIn("-----", desc)

    def test_page_title(self):
        for f in folders():
            page = open(os.path.join(f, "steam_page.txt"), encoding="utf-8").read()
            title = page.split("TITLE:")[1].strip().splitlines()[0]
            self.assertTrue(title.startswith("OpenTrail "), title)

    def test_child_xml_placeholders(self):
        x = build_workshop.child_xml("p", "Truck", [([("Wheels", 0), ("Wheel", 2)], "Torque", "full")])
        root = mrxml.root_of(mrxml.parse(x))
        wheels = root.find_all("Wheels")[0].find_all("Wheel")
        self.assertEqual([w.get("Torque") for w in wheels], [None, None, "full"])


if __name__ == "__main__":
    unittest.main()
