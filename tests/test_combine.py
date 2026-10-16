"""Your own set (tools/combine.py, "Собрать свой мод.bat"), 16.10.

The player asked whether mods can be combined in one truck. The laws:
  1. the combined copy otc_<truck> = the sum of the parts: at every value a chosen mod
     changes it holds exactly what that mod gives on its own, every other value is stock;
  2. two mods that change the same value (Powerful Engines and Hyper Power) are a
     visible choice, never a silent overwrite;
  3. one package with a name the game can take (<= 16 characters), names
     "<truck> (Свой набор)" in Russian and "(Custom)" elsewhere.
"""

import os
import shutil
import tempfile
import unittest

import common
from common import HAVE_GAME, fs, stock, resolver_with, drivable_trucks
import build_mods
import combine
import test_mods

SET_A = ["infinite_fuel", "powerful_engines", "awd_difflock", "deep_fording", "no_damage", "grippy_wheels",
         "strong_winch"]
SET_B = ["hyper_power", "no_damage", "infinite_fuel"]


def custom(names):
    return build_mods.build_all(common.GAME, None, only=names, skip_levels=True, verbose=False, fs=fs())["custom"]


class ConflictTest(unittest.TestCase):
    def test_power_mods_conflict_and_nothing_else_does(self):
        order = build_mods.load_order()
        clash = build_mods.conflicts(order)
        self.assertEqual([(a, b) for a, b, _w in clash], [("hyper_power", "powerful_engines")])
        self.assertIn("TruckData/Motor Torque", clash[0][2])
        self.assertIn("AngVel", clash[0][2])
        self.assertEqual(build_mods.conflicts([n for n in order if n != "hyper_power"]), [])

    def test_conflict_is_a_choice_not_an_overwrite(self):
        picked = []

        def choose(a, b, what):
            picked.append((a, b))
            return b
        got = combine.resolve(["no_damage", "hyper_power", "powerful_engines"], choose)
        self.assertEqual(picked, [("hyper_power", "powerful_engines")])
        self.assertEqual(got, ["no_damage", "powerful_engines"])
        with self.assertRaises(combine.CombineError) as cm:
            combine.resolve(["hyper_power", "powerful_engines"], combine.refuse)
        self.assertIn("Гипермощь", str(cm.exception))
        self.assertIn("Мощный мотор", str(cm.exception))

    @unittest.skipUnless(HAVE_GAME, "game not installed")
    def test_build_refuses_a_conflict(self):
        with self.assertRaises(build_mods.BuildError):
            custom(["hyper_power", "powerful_engines"])

    def test_numbers(self):
        items = combine.menu()
        self.assertEqual(len(items), len(build_mods.load_order()))
        self.assertTrue(all(t for _i, _n, t, _a in items))           # every mod has a Russian title
        first, second = items[0][1], items[1][1]
        self.assertEqual(combine.parse_numbers("2, 1 2", items), [second, first])
        with self.assertRaises(combine.CombineError):
            combine.parse_numbers("99", items)


@unittest.skipUnless(HAVE_GAME, "game not installed")
class SumOfPartsTest(unittest.TestCase):
    def check_sum(self, names):
        b = custom(names)
        r = resolver_with(b.files)
        st = stock()
        trucks = drivable_trucks()
        heirs = [n for n in names if build_mods.is_heir_mod(n)]
        for n in trucks:
            path = "classes/trucks/otc_%s.xml" % n
            self.assertIn(path, b.files, n)
            got = r.resolve("trucks", "otc_" + n)[0]
            s = st.resolve("trucks", n)[0]
            for mod in heirs:
                test_mods.check_truck(self, mod, n, s, got)
        # every value a mod plans is exactly there; verify_variants (inside the build)
        # already refused any other difference from the stock truck
        for mod in heirs:
            desires, _s, _l = build_mods.plan_mod(build_mods.load_spec(mod), fs(), st)
            for (kind, cls), wants in desires.items():
                got = r.resolve(kind, "otc_" + cls)[0]
                for pos, attr, value in wants:
                    self.assertEqual(build_mods.node_at(got, pos).get(attr), value, "%s %s %s" % (mod, cls, pos))
        for mod in names:
            if not build_mods.is_heir_mod(mod):
                test_mods.check_mod_effect(self, mod, b.files)
        return b

    def test_everything_compatible_in_one_truck(self):
        self.check_sum(SET_A)

    def test_hyper_power_with_others(self):
        self.check_sum(SET_B)

    def test_names_and_package(self):
        b = custom(["infinite_fuel", "no_damage"])
        ru = b.files["strings/ru/opentrail_custom.txt"].decode("utf-16")
        en = b.files["strings/en/opentrail_custom.txt"].decode("utf-16")
        self.assertIn("(Свой набор)", ru)
        self.assertIn("(Custom)", en)
        self.assertNotIn("+", ru)
        self.assertIsNone(build_mods.archive_name_problem(build_mods.CUSTOM_ZIP))

    def test_combine_writes_one_package(self):
        out = tempfile.mkdtemp(prefix="mrcomb_")
        try:
            path = combine.build(["infinite_fuel", "powerful_engines"], out, common.GAME, verbose=False)
            self.assertEqual(os.listdir(out), [build_mods.CUSTOM_ZIP])
            self.assertEqual(os.path.basename(path), build_mods.CUSTOM_ZIP)
        finally:
            shutil.rmtree(out, ignore_errors=True)        # a temp folder made by this test only


if __name__ == "__main__":
    unittest.main()
