"""Checks of the built mods against the installed game files.

Run:  .venv\\Scripts\\python -m unittest discover -s tests -v

Every check resolves the classes the way the game does (inheritance and
templates) and looks at the EFFECTIVE values, so a value that a child truck
inherits from a patched parent counts, and a value hidden by a child override
does not.
"""

import unittest
import xml.etree.ElementTree as ET

import common
from common import HAVE_GAME, built, fs, stock, resolver_with, drivable_trucks, source, DLC
import build_mods
import mrxml

TRUCK_MODS = ["hyper_power", "powerful_engines", "awd_difflock", "deep_fording", "no_damage", "infinite_fuel"]


def vec(text):
    return mrxml.parse_vec(text)


def check_truck(test, mod, name, s, p):
    """Assert the effective result of `mod` on drivable truck `name` (s = stock root, p = patched)."""
    where = "%s %s" % (mod, name)
    if mod == "infinite_fuel":
        test.assertEqual(p.find("TruckData")[0].get("FuelCapacity"), "64000", where)
    elif mod == "no_damage":
        dm = p.find("TruckData/Damage")
        test.assertTrue(dm, where)
        for d in dm:
            test.assertEqual(d.get("Capacity"), "64000", where)
    elif mod in ("powerful_engines", "hyper_power"):
        k = 2.5 if mod == "powerful_engines" else 10
        so = float(s.find("TruckData/Motor")[0].get("Torque"))
        pa = float(p.find("TruckData/Motor")[0].get("Torque"))
        want = so * k if mod == "powerful_engines" else min(so * k, 1000000.0)
        test.assertAlmostEqual(pa, want, delta=1.0, msg=where)
    elif mod == "awd_difflock":
        wheels = p.find("Wheels/Wheel")
        test.assertTrue(wheels, where)
        for w in wheels:
            test.assertIn(w.get("Torque"), ("default", "full"), where)
        test.assertNotEqual(p.find("TruckData")[0].get("DiffLockType"), "None", where)
        test.assertIn(p.find("TruckData")[0].get("DiffLockType"), (None, "Default", "Always"), where)
    elif mod == "deep_fording":
        for sd, pd in zip(s.find("TruckData/Damage"), p.find("TruckData/Damage")):
            lo, hi = vec(sd.get("SensationMin")), vec(sd.get("SensationMax"))
            plo, phi = vec(pd.get("SensationMin")), vec(pd.get("SensationMax"))
            top = max(lo[1], hi[1])
            test.assertAlmostEqual(plo[1], top + 1.0, delta=1e-3, msg=where)
            test.assertAlmostEqual(phi[1], top + 1.2, delta=1e-3, msg=where)
            test.assertEqual((plo[0], plo[2], phi[0], phi[2]), (lo[0], lo[2], hi[0], hi[2]), where)
    else:
        raise AssertionError("no truck check for " + mod)


def check_wheel(test, name, s, p):
    sf = s.find("WheelFriction")[0]
    pf = p.find("WheelFriction")[0]
    want_sub = max(float(sf.get("SubstanceFriction")) * 2.5, 2.5)
    want_body = max(float(sf.get("BodyFriction")) * 1.5, 2.0)
    test.assertAlmostEqual(float(pf.get("SubstanceFriction")), want_sub, delta=1e-3, msg=name)
    test.assertAlmostEqual(float(pf.get("BodyFriction")), want_body, delta=1e-3, msg=name)


WINCH_PLANTS = ["stump_b", "fir_small_b", "pine_small_b", "small_tree_a", "small_tree_b", "small_tree_c",
                "small_tree_d"]


def check_mod_effect(test, mod, files):
    """`files` = the package overlay. Checks every target class of `mod`."""
    r = resolver_with(files)
    st = stock()
    if mod in TRUCK_MODS:
        trucks = drivable_trucks()
        for n in trucks:
            check_truck(test, mod, n, st.resolve("trucks", n)[0], r.resolve("trucks", n)[0])
        return len(trucks)
    if mod == "grippy_wheels":
        wheels = fs().class_names("wheels")
        for n in wheels:
            check_wheel(test, n, st.resolve("wheels", n)[0], r.resolve("wheels", n)[0])
        return len(wheels)
    if mod == "strong_winch":
        for n in WINCH_PLANTS:
            test.assertTrue(r.resolve("plants", n)[0].find("GameData/WinchSocket"), n)
            test.assertFalse(st.resolve("plants", n)[0].find("GameData/WinchSocket"), n)
        return len(WINCH_PLANTS)
    if mod == "unlocked_trucks":
        return 0
    raise AssertionError("no check for " + mod)


@unittest.skipUnless(HAVE_GAME, "game not installed")
class GameFilesTest(unittest.TestCase):
    def test_counts_base_and_dlc(self):
        """The task numbers: 73 truck files in Media.zip, the DLC archives add more; wheels too."""
        f = fs()
        trucks = f.class_names("trucks")
        wheels = f.class_names("wheels")
        by = {}
        for n in trucks:
            by.setdefault(source("trucks", n), []).append(n)
        self.assertEqual(len(by["Media.zip"]), 73)
        for d in DLC:
            self.assertTrue(by.get(d), d)
        self.assertEqual(len(trucks), 144)
        self.assertEqual(len(wheels), 50)
        self.assertEqual(len(drivable_trucks()), 36)

    def test_every_stock_class_parses_and_resolves(self):
        f = fs()
        r = stock()
        n = 0
        for kind in ("trucks", "wheels", "plants"):
            for name in f.class_names(kind):
                root, _chain = r.resolve(kind, name)
                self.assertIn(root.tag, mrxml.ROOT_TAGS)
                n += 1
        self.assertEqual(n, 255)

    def test_missing_wheel_torque_means_not_driven(self):
        """ZIL-130, ZAZ and UMZ front wheels have no Torque: they are the 4x2 trucks, so
        'missing' must count as 'none' and AWD must add it."""
        r = stock()
        for n in ("zil130", "zaz968m", "umz6a"):
            front = r.resolve("trucks", n)[0].find("Wheels/Wheel")[:2]
            self.assertTrue(all(w.get("Torque") is None for w in front), n)


@unittest.skipUnless(HAVE_GAME, "game not installed")
class BuiltModsTest(unittest.TestCase):
    def test_order_matches_folders(self):
        order = build_mods.load_order()
        self.assertEqual(len(order), 9)
        self.assertEqual(order[0], "hyper_power")
        self.assertIn("powerful_engines", build_mods.load_replaces()["hyper_power"])

    def test_each_mod_alone_patches_every_target(self):
        """Base game and every DLC: each package used alone gives the full effect."""
        counts = {}
        for name, b in built().items():
            counts[name] = check_mod_effect(self, name, b.files)
        for m in TRUCK_MODS:
            self.assertEqual(counts[m], 36, m)
        self.assertEqual(counts["grippy_wheels"], 50)

    def test_dlc_files_are_in_the_packages(self):
        dlc_trucks = {n for n in drivable_trucks() if source("trucks", n) != "Media.zip"}
        self.assertEqual(len(dlc_trucks), 16)
        for m in TRUCK_MODS:
            sources = {fs().source(p) for p in built()[m].files}
            # AWD: the Valley DLC trucks already have AWD and a diff lock, nothing to change
            for d in DLC if m != "awd_difflock" else ["_dlc_usa.zip", "_dlc_ridge.zip", "_dlc_oldtimers.zip"]:
                self.assertIn(d, sources, m)
        wsrc = {fs().source(p) for p in built()["grippy_wheels"].files}
        for d in ("_dlc_valley.zip", "_dlc_ridge.zip", "_dlc_usa.zip"):
            self.assertIn(d, wsrc)

    def test_all_mods_in_order(self):
        """All packages mounted in the recommended order (first copy wins): every mod
        keeps its effect, Hyper Power replaces Powerful Engines."""
        order = build_mods.load_order()
        overlay = {}
        for n in order:
            for p, data in built()[n].files.items():
                overlay.setdefault(p, data)
        for n in order:
            if n == "powerful_engines":
                continue
            check_mod_effect(self, n, overlay)

    def test_chain_upper_carries_lower(self):
        """A shared file in an upper mod carries the changes of every lower mod in that
        file (except mods it replaces), so the upper package alone keeps them."""
        order = build_mods.load_order()
        replaces = build_mods.load_replaces()
        res = built()
        st = stock()
        pairs = 0
        for i, upper in enumerate(order):
            for lower in order[i + 1:]:
                if lower in replaces.get(upper, []) or lower not in TRUCK_MODS:
                    continue
                shared = set(res[upper].files) & set(res[lower].files)
                if not shared:
                    continue
                r = resolver_with(res[upper].files)
                for n in drivable_trucks():
                    chain = st.raw("trucks", n)[2]
                    touched = [c for c in chain if c in res[lower].files]
                    if touched and all(c in res[upper].files for c in touched):
                        check_truck(self, lower, n, st.resolve("trucks", n)[0], r.resolve("trucks", n)[0])
                        pairs += 1
                for p in shared:
                    self.assertIn(lower, res[upper].file_mods[p], p)
        self.assertGreater(pairs, 100)

    def test_hyper_power_is_not_stacked(self):
        hp = built()["hyper_power"]
        self.assertFalse(any("powerful_engines" in m for m in hp.file_mods.values()))
        r = resolver_with(hp.files)
        for n in drivable_trucks():
            so = float(stock().resolve("trucks", n)[0].find("TruckData/Motor")[0].get("Torque"))
            self.assertAlmostEqual(float(r.resolve("trucks", n)[0].find("TruckData/Motor")[0].get("Torque")),
                                   min(so * 10, 1000000.0), delta=1.0, msg=n)

    def test_custom_package_has_exactly_the_chosen_mods(self):
        b = build_mods.build_all(common.GAME, None, only=["infinite_fuel", "no_damage"], skip_levels=True,
                                 verbose=False, fs=fs())["custom"]
        check_mod_effect(self, "infinite_fuel", b.files)
        check_mod_effect(self, "no_damage", b.files)
        r = resolver_with(b.files)
        for n in drivable_trucks():
            s = stock().resolve("trucks", n)[0]
            p = r.resolve("trucks", n)[0]
            self.assertEqual(s.find("TruckData/Motor")[0].get("Torque"), p.find("TruckData/Motor")[0].get("Torque"))
            self.assertEqual(s.find("TruckData/Damage")[0].get("SensationMin"),
                             p.find("TruckData/Damage")[0].get("SensationMin"))

    def test_outputs_stay_valid_xml(self):
        """Every patched file parses; where the stock file is well-formed XML (one
        wrapper root added), the patched one is too; the element structure is the
        stock one (plants may gain GameData/WinchSocket)."""
        n = 0
        for name, b in built().items():
            for path, data in b.files.items():
                old = mrxml.decode(fs().read(path))
                new = mrxml.decode(data)
                tops = mrxml.parse(new)
                try:
                    ET.fromstring("<R>" + old + "</R>")
                    stock_ok = True
                except ET.ParseError:
                    stock_ok = False             # duplicate attributes in 6 stock files
                if stock_ok:
                    ET.fromstring("<R>" + new + "</R>")
                otags = _tags(mrxml.parse(old))
                ntags = _tags(tops)
                if path.startswith("classes/plants/"):
                    ntags = [t for t in ntags if t not in ("GameData", "WinchSocket")]
                    otags = [t for t in otags if t not in ("GameData", "WinchSocket")]
                self.assertEqual(otags, ntags, "%s %s" % (name, path))
                n += 1
        self.assertGreater(n, 200)

    def test_only_targeted_attributes_change(self):
        allowed = {"Torque", "FuelCapacity", "Capacity", "DiffLockType", "SensationMin", "SensationMax",
                   "SubstanceFriction", "BodyFriction", "Pos", "ParentFrame"}
        for name, b in built().items():
            for path, data in b.files.items():
                o = _attrs(mrxml.parse(fs().read(path)))
                p = _attrs(mrxml.parse(data))
                for k in set(o) | set(p):
                    if o.get(k) != p.get(k):
                        self.assertIn(k[-1], allowed, "%s %s %s" % (name, path, k))

    def test_no_zero_divisors(self):
        """Values the game divides by, or that scale forces, must never be 0 or negative
        (the ETS2 lesson: fuel consumption 0 broke the dashboard with 0/0)."""
        keys = {"FuelCapacity", "Capacity", "Torque", "AngVel", "SubstanceFriction", "BodyFriction",
                "RepairsCapacity", "Mass"}
        seen = 0
        for name, b in built().items():
            r = resolver_with(b.files)
            for kind in ("trucks", "wheels"):
                for cls in fs().class_names(kind):
                    root = r.resolve(kind, cls)[0]
                    for node in _walk(root):
                        for k, v in node.attrs.items():
                            if k in keys and v not in ("default", "full", "none") and not (
                                    k == "Torque" and node.tag == "Wheel"):
                                if k == "RepairsCapacity" and v == "0":
                                    continue        # stock addons without repair points
                                seen += 1
                                self.assertGreater(float(v), 0.0, "%s %s %s %s=%s" % (name, cls, node.tag, k, v))
        self.assertGreater(seen, 10000)

    def test_no_value_is_set_to_zero_by_a_mod(self):
        for name, b in built().items():
            for path, attr, old, new, owner in b.log:
                if attr in ("WinchSocket",):
                    continue
                if str(new).startswith("("):
                    continue           # vectors may hold 0 components
                for num in _numbers(new):
                    self.assertNotEqual(num, 0.0, "%s %s %s" % (name, path, attr))

    def test_every_patch_is_logged_and_lands(self):
        for name, b in built().items():
            own = [x for x in b.log if x[4] == name]
            self.assertTrue(own or b.levels or name == "unlocked_trucks", name)
            for path, attr, old, new, owner in own:
                if attr == "WinchSocket":
                    self.assertIn(new, mrxml.decode(b.files[path]))
                    continue
                vals = [a.value for a in _all_attrs(mrxml.parse(b.files[path])) if a.name == attr]
                self.assertIn(new, vals, "%s %s %s" % (name, path, attr))


@unittest.skipUnless(HAVE_GAME, "game not installed")
class LevelsTest(unittest.TestCase):
    def test_truck_records_of_every_level_parse(self):
        n = 0
        for path in fs().list("levels/", ".stg"):
            with fs().open(path) as fh:
                head = fh.read(build_mods.STG_HEAD)
            recs, end = build_mods.read_stg_trucks(head)
            self.assertLess(end, build_mods.STG_HEAD)
            for r in recs:
                self.assertIn(r["locked"], (0, 1))
                self.assertTrue(0.0 <= r["fuel"] <= 100.0, path)
                if r["type"]:
                    self.assertTrue(fs().exists("classes/trucks/%s.xml" % r["type"]), r["type"])
            n += 1
        self.assertEqual(n, 25)        # 17 in Media.zip, 5 American Wilds, 1 per other DLC

    def test_unlock_changes_only_lock_bytes(self):
        b = built()["unlocked_trucks"]
        self.assertEqual(sorted(p[7:-4] for p in b.levels),
                         ["level_coast", "level_dlc4_01", "level_flood", "level_ridge", "level_river",
                          "level_valley"])
        total = 0
        for path, (patched, recs, n) in b.levels.items():
            with fs().open(path) as fh:
                head = fh.read(build_mods.STG_HEAD)
            diff = [i for i in range(len(head)) if head[i] != patched[i]]
            self.assertEqual(diff, [r["locked_at"] for r in recs if r["locked"]], path)
            after, _end = build_mods.read_stg_trucks(patched)
            self.assertTrue(all(r["locked"] == 0 for r in after), path)
            self.assertEqual([(r["type"], r["fuel"]) for r in after], [(r["type"], r["fuel"]) for r in recs])
            total += n
        self.assertEqual(total, 24)

    def test_challenges_and_proving_ground_are_not_touched(self):
        b = built()["unlocked_trucks"]
        self.assertFalse([p for p in b.levels if "/chlg_" in p or "/game_" in p])


class StgPackageTest(unittest.TestCase):
    """write_package streams a level file and replaces only its head (no game needed)."""

    def test_stream_copy(self):
        import io
        import os
        import struct
        import tempfile
        import zipfile

        name = b"zil131\0"
        head = struct.pack("<III", 0x0133ED03, 7, 1) + struct.pack("<H", len(name)) + name + b"\0" * 64 \
            + struct.pack("<I", 0) + struct.pack("<H", 1) + b"\0" + struct.pack("<ff", 0.0, 100.0) + b"\x01"
        body = head + os.urandom(300000)

        class Fs(object):
            def open(self, path):
                return io.BytesIO(body)

            def size(self, path):
                return len(body)

        patched, recs, n = build_mods.unlock_stg_head(body[:build_mods.STG_HEAD])
        self.assertEqual(n, 1)
        b = build_mods.Built("unlocked_trucks", {"title": "Unlocked Trucks"})
        b.levels["levels/level_x.stg"] = (patched, recs, n)
        out = os.path.join(tempfile.mkdtemp(prefix="mrstg_"), "t.zip")
        build_mods.write_package(b, Fs(), out)
        with zipfile.ZipFile(out) as z:
            data = z.read("levels/level_x.stg")
            self.assertEqual(z.namelist(), ["levels/level_x.stg"])
        self.assertEqual(len(data), len(body))
        diff = [i for i in range(len(body)) if body[i] != data[i]]
        self.assertEqual(diff, [recs[0]["locked_at"]])
        # the cause of the 1.0.0 in-game failure: Zip64 local headers that PhysFS 2.0 rejects
        import zipcheck
        self.assertEqual(zipcheck.problems(out), [])


def _tags(tops):
    out = []

    def walk(n):
        out.append(n.tag)
        for c in n.children:
            walk(c)
    for t in tops:
        walk(t)
    return out


def _walk(r):
    yield r
    for c in r.children:
        for x in _walk(c):
            yield x


def _all_attrs(tops):
    out = []

    def walk(n):
        out.extend(n.attrs)
        for c in n.children:
            walk(c)
    for t in tops:
        walk(t)
    return out


def _attrs(tops):
    """{(path..., attr): value} keyed by element position."""
    out = {}

    def walk(n, pos):
        for a in n.attrs:
            out[pos + (a.name,)] = a.value
        counts = {}
        for c in n.children:
            i = counts.get(c.tag, 0)
            counts[c.tag] = i + 1
            walk(c, pos + ((c.tag, i),))
    counts = {}
    for t in tops:
        i = counts.get(t.tag, 0)
        counts[t.tag] = i + 1
        walk(t, ((t.tag, i),))
    return out


def _numbers(text):
    import re
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", str(text))]


if __name__ == "__main__":
    unittest.main()
