"""The engine-limits law: no mod may write a value that MudRunner.exe clamps.

Second in-game test (safe set): the game crashed on "Single player", the screen
that loads the map trucks. Three mods wrote values above the exe's range-checked
getters (FuelCapacity 100000 and Damage Capacity 1000000 over the 64000 limit,
Hyper Power torque up to 2400000 over 1000000). The exe clamps such a value and
reports it through its XML error logger. See tools/engine_limits.py.
"""

import os
import unittest

import common
from common import HAVE_GAME, GAME, built, fs, workshop_dir
import build_mods
import engine_limits
import mrxml

EXE = os.path.join(GAME, "MudRunner.exe")


class LimitsTableTest(unittest.TestCase):
    def test_violations(self):
        self.assertEqual(engine_limits.violations("Damage", {"Capacity": "64000"}), [])
        self.assertEqual(len(engine_limits.violations("Damage", {"Capacity": "64001"})), 1)
        self.assertEqual(len(engine_limits.violations("TruckData", {"FuelCapacity": "100000"})), 1)
        self.assertEqual(len(engine_limits.violations("Motor", {"Torque": "2400000"})), 1)
        self.assertEqual(len(engine_limits.violations("WheelFriction", {"SubstanceFriction": "0.05"})), 1)
        self.assertEqual(engine_limits.violations("Motor", {"Torque": "600000"}), [])


@unittest.skipUnless(os.path.isfile(EXE), "game not installed")
class ExeLimitsTest(unittest.TestCase):
    def test_limits_match_the_exe(self):
        """The table is read again from the installed exe, so a game update that
        changes a limit fails here first."""
        self.assertEqual(engine_limits.read_exe_limits(EXE), engine_limits.LIMITS)


@unittest.skipUnless(HAVE_GAME, "game not installed")
class PackageLimitsTest(unittest.TestCase):
    def test_stock_files_are_within_limits(self):
        self.assertEqual(build_mods.limit_violations(fs(), {}), [])

    def test_every_mod_value_within_limits(self):
        for name, b in built().items():
            self.assertEqual(build_mods.limit_violations(fs(), b.files), [], name)

    def test_every_package_within_limits(self):
        """Also every package in the load order together."""
        order = build_mods.load_order()
        overlay = {}
        for n in order:
            for p, data in built()[n].files.items():
                overlay.setdefault(p, data)
        self.assertEqual(build_mods.limit_violations(fs(), overlay), [])

    def test_workshop_variants_within_limits(self):
        files = {}
        base = workshop_dir()
        for folder in os.listdir(base):
            mod = os.path.join(base, folder, "mod")
            for kind in ("trucks", "wheels"):
                d = os.path.join(mod, "classes", kind)
                if not os.path.isdir(d):
                    continue
                for x in os.listdir(d):
                    with open(os.path.join(d, x), "rb") as fh:
                        files[mrxml.KIND_DIRS[kind] + x] = fh.read()
        r = mrxml.Resolver(mrxml.Layer(fs(), files))
        n = 0
        for path in files:
            kind = "trucks" if "/trucks/" in path else "wheels"
            root, _c = r.resolve(kind, path.rsplit("/", 1)[1][:-4])
            stack = [root]
            while stack:
                node = stack.pop()
                self.assertEqual(engine_limits.violations(node.tag, node.attrs), [], path)
                stack.extend(node.children)
            n += 1
        self.assertGreater(n, 100)


if __name__ == "__main__":
    unittest.main()
