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


class FuelFillLawTest(unittest.TestCase):
    """Infinite Fuel 1.0.0 (64000 l) made trucks jerk and not move: the exe coughs the
    engine when fuel litres / FuelCapacity < 0.06, and a truck from the profile or a
    save brings its fuel in litres (at most 800 l = 1.25 % of 64000). The law: a full
    STOCK tank must stay above the red warning (0.2) and the cough (0.06) in the new tank."""

    def test_thresholds_order(self):
        self.assertLess(engine_limits.FUEL_COUGH_FILL, engine_limits.FUEL_WARN_FILL)
        self.assertGreater(1.0 / engine_limits.FUEL_TANK_MAX_SCALE, engine_limits.FUEL_WARN_FILL)

    @unittest.skipUnless(os.path.isfile(EXE), "game not installed")
    def test_thresholds_match_the_exe(self):
        self.assertEqual(engine_limits.read_exe_fuel_fills(EXE),
                         [engine_limits.FUEL_COUGH_FILL, engine_limits.FUEL_WARN_FILL])

    @unittest.skipUnless(HAVE_GAME, "game not installed")
    def test_full_stock_tank_is_not_near_empty(self):
        """Every truck file any package ships: stock FuelCapacity / new >= 1/FUEL_TANK_MAX_SCALE."""
        from common import resolver_with, stock, drivable_trucks
        st = stock()
        stock_cap = {n: float(st.resolve("trucks", n)[0].find("TruckData")[0].get("FuelCapacity"))
                     for n in drivable_trucks()}
        seen = 0
        for name, b in built().items():
            r = resolver_with(b.files)
            for path in b.files:
                if not (path.startswith("classes/trucks/") and path.endswith(".xml")):
                    continue
                cls = path[len("classes/trucks/"):-4]
                base = cls.split("_", 1)[1] if cls.split("_", 1)[0] in ("otf", "otc", "otd", "otp", "oth", "ota",
                                                                         "otw") else cls
                if base not in stock_cap:
                    continue
                new = float(r.resolve("trucks", cls)[0].find("TruckData")[0].get("FuelCapacity"))
                fill = stock_cap[base] / new
                self.assertGreaterEqual(fill, 1.0 / engine_limits.FUEL_TANK_MAX_SCALE - 1e-9,
                                        "%s %s: full stock tank is %.1f %% of the new one" % (name, cls, fill * 100))
                seen += 1
        self.assertGreater(seen, 30)


class GarageRulesTest(unittest.TestCase):
    """The garage lock is code + game state, not a file (see engine_limits, 11.10):
    a garage needs GARAGE_NEED points, a new game gives them only to garages within
    GARAGE_START_RADIUS of the drive truck."""

    @unittest.skipUnless(os.path.isfile(EXE), "game not installed")
    def test_garage_rules_match_the_exe(self):
        self.assertEqual(engine_limits.read_exe_garage_rules(EXE),
                         (engine_limits.GARAGE_NEED, engine_limits.GARAGE_START_RADIUS))


class GearRulesTest(unittest.TestCase):
    """How the exe splits Motor Torque over the gears (engine_limits, 16.10): the power
    law test_power_mods_are_felt_in_every_gear computes with these numbers, so they are
    read back from the drivetrain code of the installed exe."""

    @unittest.skipUnless(os.path.isfile(EXE), "game not installed")
    def test_gear_rules_match_the_exe(self):
        el = engine_limits
        self.assertEqual(el.read_exe_gear_rules(EXE),
                         (el.GEAR_HALF, el.GEAR_FLOOR, el.GEAR_POWER, el.HIGH_GEAR_TORQUE, el.BAND_SCALE,
                          el.BAND_ADD,
                          el.HIGH_BAND_ADD))

    def test_low_gears_get_more_torque(self):
        el = engine_limits
        self.assertEqual(el.gear_torque(40000, 2.0), 40000)
        self.assertAlmostEqual(el.gear_torque(40000, 20.0), 40000 / 10 ** 0.5)
        self.assertEqual(el.gear_torque(40000, 12.0, high=True), 50000)
        self.assertEqual(el.band_end(20.0), 45.0)
        self.assertEqual(el.band_end(12.0, high=True), 14.0)


class BigTankMassTest(unittest.TestCase):
    """16.10, in-game test: the Big Fuel Tank A-469 "goes slowly and feels very heavy". The exe
    adds fuel mass only through a <FuelMass><Body Mass=.../></FuelMass> block of the truck
    XML (reader 0x1408c93b9, 'fuel mass body', the body mass follows the fill at
    0x1408caf4f); only cisterns have one. The law: no truck a fuel package ships has a
    FuelMass block, and apart from FuelCapacity the copy is the stock truck (also checked
    for every copy by build_workshop.verify_variants), so a bigger tank weighs nothing."""

    @unittest.skipUnless(os.path.isfile(EXE), "game not installed")
    def test_exe_reads_fuel_mass_only_from_the_block(self):
        with open(EXE, "rb") as fh:
            data = fh.read()
        self.assertIn(b"\0FuelMass\0", data)
        self.assertIn(b"fuel mass body", data)

    @unittest.skipUnless(HAVE_GAME, "game not installed")
    def test_big_tank_copies_have_no_fuel_mass_and_stock_mass(self):
        from common import resolver_with, stock
        b = built()["infinite_fuel"]
        r = resolver_with(b.files)
        seen = 0
        for path in b.files:
            if not (path.startswith("classes/trucks/otf_") and path.endswith(".xml")):
                continue
            cls = path[len("classes/trucks/"):-4]
            got = r.resolve("trucks", cls)[0]
            want = stock().resolve("trucks", cls[4:])[0]
            self.assertFalse(got.find("FuelMass"), cls)
            self.assertEqual([x.get("Mass") for x in got.find("PhysicsModel/Body")],
                             [x.get("Mass") for x in want.find("PhysicsModel/Body")], cls)
            self.assertEqual([x.get("CenterOfMassOffset") for x in got.find("PhysicsModel/Body")],
                             [x.get("CenterOfMassOffset") for x in want.find("PhysicsModel/Body")], cls)
            seen += 1
        self.assertGreater(seen, 30)
