"""Map saves (*.sts): why Unlocked Trucks could not open the trucks on the map, and the laws of
the save edit that does. Works ONLY on copies in a temp folder.

MUDRUNNER_SAVES_COPY=<folder with COPIES of UserSaves/*.sts> adds the same laws on real saves
(each file is copied into the temp folder first; the given files are only read)."""

import glob
import io
import json
import math
import os
import shutil
import struct
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

import common
import build_mods
import engine_limits
import save_sts
import unlock_profile

V = save_sts.VERSION


def s(text):
    b = text.encode("ascii") + b"\0"
    return struct.pack("<H", len(b)) + b


def mat(x=0.0, z=0.0, y=10.0):
    return struct.pack("<16f", 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, x, y, z, 1)


# the physics state after a truck header: bytes that look like strings, never like a truck
PHYS = b"\x07\x00Bone_ab\x00" + b"\x11" * 97 + s("BoneChassis_cdt") + b"\x00" * 40


def truck(typ, x, z, unlocked, addons=()):
    out = s(typ) + struct.pack("<I", len(addons))
    for a in addons:
        out += s(a) + s("BoneChassis_cdt") + mat() + struct.pack("<I", 1) + s("BoneTail") + struct.pack("<II", 0, 0)
    out += struct.pack("<3I", 0x43480000, 0, 0) + mat(x, z) + struct.pack("<ff", 0.0, 0.0)
    out += bytes([unlocked]) + struct.pack("<I", 0x817BF8AC) + PHYS
    return out


GARAGES = [(-249.2, 187.762), (313.333, -189.107)]
TRUCKS = [("zil131", -242.0, 188.4, 1, ()), ("kraz255", -245.5, 183.6, 1, ()),
          ("maz535", -120.4, 49.4, 0, ("maz_tractor",)), ("kirovets700", -208.2, -253.3, 0, ("kirovets_loader",)),
          ("trailer_utility", 10.0, 20.0, 0, ())]


def save(trucks=TRUCKS, garages=((GARAGES[0], 4), (GARAGES[1], 0)), count=None, version=V):
    out = struct.pack("<II", version, 0) + b"\x01" + struct.pack("<f", 8.07) + b"\x00\x00"
    out += struct.pack("<ffffI", 0.07, 8.7, 0.0, 0.08, 0) + b"\x01\x00" + b"\xff\xff\x7f\x7f" * 4 + b"\x00" * 20
    out += struct.pack("<I", len(trucks) if count is None else count)
    out += b"".join(truck(*t) for t in trucks)
    out += struct.pack("<II", 4, 4) + b"\x80" * 16
    out += struct.pack("<I", len(garages)) + b"".join(struct.pack("<ffI", x, z, p) for (x, z), p in garages)
    out += struct.pack("<I", 2) + b"\x00" * 64
    return out


class FormatTest(unittest.TestCase):
    def check_truck_law(self, data):
        """After the edit: every truck open, only their isUnlocked bytes changed (0 -> 1),
        the same trucks found again in the same places."""
        before = save_sts.trucks(data)
        new, locked = save_sts.unlock_trucks(data)
        self.assertEqual(len(new), len(data))
        self.assertEqual(save_sts.changed_offsets(data, new), [t["unlocked_at"] for t in locked])
        for t in locked:
            self.assertEqual((data[t["unlocked_at"]], new[t["unlocked_at"]]), (0, 1))
        after = save_sts.trucks(new)
        self.assertEqual([(t["type"], t["start"], t["x"], t["z"]) for t in after],
                         [(t["type"], t["start"], t["x"], t["z"]) for t in before])
        self.assertTrue(all(t["unlocked"] == 1 for t in after))
        return before, locked

    def test_truck_law_synthetic(self):
        before, locked = self.check_truck_law(save())
        self.assertEqual([t["type"] for t in before], [t[0] for t in TRUCKS])
        self.assertEqual([t["type"] for t in locked], ["maz535", "kirovets700", "trailer_utility"])
        self.assertEqual(before[2]["addons"], ["maz_tractor"])

    def test_open_save_is_left_as_it_is(self):
        data = save(trucks=[t[:3] + (1, t[4]) for t in TRUCKS])
        new, locked = save_sts.unlock_trucks(data)
        self.assertEqual((new, locked), (data, []))

    def test_wrong_count_or_version_is_refused(self):
        with self.assertRaises(save_sts.StsError):
            save_sts.trucks(save(count=len(TRUCKS) + 1))
        with self.assertRaises(save_sts.StsError):
            save_sts.trucks(save(count=len(TRUCKS) - 1))
        with self.assertRaises(save_sts.StsError):
            save_sts.trucks(save(version=V - 1))
        with self.assertRaises(save_sts.StsError):
            save_sts.trucks(save()[:40])

    def test_broken_truck_header_is_refused(self):
        data = bytearray(save())
        first = save_sts.trucks(bytes(data))[1]
        data[first["unlocked_at"]] = 7          # not 0 or 1: that header is not a truck any more
        with self.assertRaises(save_sts.StsError):
            save_sts.trucks(bytes(data))

    def test_garage_law_synthetic(self):
        data = save()
        need = engine_limits.GARAGE_NEED[0]
        gs = save_sts.garages(data, GARAGES)
        self.assertEqual([g["points"] for g in gs], [4, 0])
        new, low = save_sts.open_garages(data, GARAGES, need)
        self.assertEqual(len(low), 1)
        at = low[0]["points_at"]
        self.assertEqual(save_sts.changed_offsets(data, new), [at])      # 0 -> 4: one byte of the u32
        self.assertEqual([g["points"] for g in save_sts.garages(new, GARAGES)], [4, need])
        self.assertEqual(save_sts.trucks(new), save_sts.trucks(data))

    def test_garages_must_match_the_level_exactly(self):
        with self.assertRaises(save_sts.StsError):
            save_sts.garages(save(), [(1.0, 2.0), GARAGES[1]])
        with self.assertRaises(save_sts.StsError):
            save_sts.garages(save(), GARAGES[:1])
        twice = save() + struct.pack("<I", 2) + b"".join(struct.pack("<ffI", x, z, 0) for x, z in GARAGES)
        with self.assertRaises(save_sts.StsError):
            save_sts.garages(twice, GARAGES)
        self.assertEqual(save_sts.garages(save(), []), [])

    @unittest.skipUnless(os.environ.get("MUDRUNNER_SAVES_COPY"), "no copy of real saves given")
    def test_laws_on_real_save_copies(self):
        src = os.environ["MUDRUNNER_SAVES_COPY"]
        files = sorted(glob.glob(os.path.join(glob.escape(src), "*.sts")))
        self.assertTrue(files)
        with tempfile.TemporaryDirectory() as tmp:
            for f in files:
                dst = os.path.join(tmp, os.path.basename(f))
                shutil.copyfile(f, dst)
                with open(dst, "rb") as fh:
                    data = fh.read()
                with self.subTest(save=os.path.basename(f)):
                    self.check_truck_law(data)
                    level = unlock_profile.level_of_save(dst)
                    if level and common.HAVE_GAME:
                        gxz = unlock_profile.level_garages(common.GAME, level)
                        new, low = save_sts.open_garages(data, gxz, engine_limits.GARAGE_NEED[0])
                        self.assertTrue(set(save_sts.changed_offsets(data, new))
                                        <= {g["points_at"] + k for g in low for k in range(4)})


@unittest.skipUnless(common.HAVE_GAME, "game not installed")
class RandomTruckCauseTest(unittest.TestCase):
    """The cause (16.10): the locked trucks on the map are put there by the exe, not by the level."""

    def test_rules_match_the_exe(self):
        got = engine_limits.read_exe_random_trucks(os.path.join(common.GAME, "MudRunner.exe"))
        self.assertEqual(got, dict(locator=engine_limits.RANDOM_TRUCK_LOCATOR, max=engine_limits.RANDOM_TRUCKS_MAX,
                                   pool=engine_limits.RANDOM_TRUCK_POOL, radius=engine_limits.TRUCK_UNLOCK_RADIUS))

    def test_no_level_record_at_a_random_truck_spot(self):
        """So no change of levels/*.stg (all Unlocked Trucks can do) reaches the trucks the
        game puts on these spots; every sandbox map but Old-timers has such spots."""
        fs = common.fs()
        with_spots = []
        for path in fs.list("levels/level_", ".stg"):
            with fs.open(path) as fh:
                head = fh.read(build_mods.STG_HEAD)
            recs, end = build_mods.read_stg_trucks(head)
            spots = [(l["x"], l["z"]) for l in build_mods.read_stg_locators(head, end)["locators"]
                     if l["type"] == engine_limits.RANDOM_TRUCK_LOCATOR]
            if spots:
                with_spots.append(path)
            for x, z in spots:
                near = [r["type"] for r in recs if math.hypot(r["x"] - x, r["z"] - z) < engine_limits.TRUCK_UNLOCK_RADIUS]
                self.assertEqual(near, [], (path, x, z))
        self.assertEqual(len(with_spots), 10, with_spots)
        self.assertNotIn("levels/level_dlc4_01.stg", with_spots)

    def test_unlock_mod_tells_where_its_power_ends(self):
        with open(os.path.join(common.ROOT, "mods", "unlocked_trucks", "mod.json"), encoding="utf-8") as f:
            spec = json.load(f)
        ru = " ".join(spec["about"]["ru"])
        en = " ".join(spec["about"]["en"])
        self.assertIn("Открыть карты MudRunner.bat", ru)
        self.assertIn("случайн", ru)
        self.assertIn("random", en)


class ToolTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.saves = os.path.join(self.tmp, "UserSaves")
        os.makedirs(self.saves)
        self.path = os.path.join(self.saves, "level_volcano.sts")
        with open(self.path, "wb") as f:
            f.write(save())
        self.bk = os.path.join(self.tmp, "backup")
        os.environ["OPENTRAIL_NO_GAME_CHECK"] = "1"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_tool(self, *args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = unlock_profile.main(["--profile", os.path.join(self.tmp, "UserProfile.stu"), "--exe", "-",
                                      "--game", common.GAME, "--backup-dir", self.bk,
                                      "--save", "level_volcano"] + list(args))
        return rc, buf.getvalue()

    def read(self):
        with open(self.path, "rb") as f:
            return f.read()

    def test_dry_run_writes_nothing(self):
        rc, out = self.run_tool("--trucks")
        self.assertEqual(rc, 0)
        self.assertEqual(self.read(), save())
        self.assertIn("заперто: 3", out)
        self.assertIn("Пробный режим", out)
        self.assertFalse(os.path.exists(self.bk))

    def test_trucks_open_with_backup_outside_the_saves_and_restore(self):
        rc, out = self.run_tool("--trucks", "--write", "--yes")
        self.assertEqual(rc, 0, out)
        self.assertTrue(all(t["unlocked"] for t in save_sts.trucks(self.read())))
        bks = unlock_profile.save_backups(self.path, self.bk)
        self.assertEqual(len(bks), 1)
        self.assertEqual(os.listdir(self.saves), ["level_volcano.sts"])   # nothing extra for the game/cloud
        with open(bks[0], "rb") as f:
            self.assertEqual(f.read(), save())
        rc, _ = self.run_tool("--restore-save", "--write", "--yes")
        self.assertEqual(rc, 0)
        self.assertEqual(self.read(), save())

    @unittest.skipUnless(common.HAVE_GAME, "game not installed")
    def test_garages_open_by_the_level_file(self):
        real = unlock_profile.level_garages(common.GAME, "level_volcano")
        with open(self.path, "wb") as f:
            f.write(save(garages=[(real[0], 4), (real[1], 0)]))
        rc, out = self.run_tool("--garages", "--write", "--yes")
        self.assertEqual(rc, 0, out)
        self.assertEqual([g["points"] for g in save_sts.garages(self.read(), real)], [4, 4])

    def test_garages_of_a_map_not_from_the_game_are_left_alone(self):
        other = os.path.join(self.saves, "26nhvc9q.sts")
        shutil.copyfile(self.path, other)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = unlock_profile.main(["--profile", os.path.join(self.tmp, "UserProfile.stu"), "--exe", "-",
                                      "--game", common.GAME, "--backup-dir", self.bk, "--save", other,
                                      "--garages", "--write", "--yes"])
        self.assertEqual(rc, 1)
        self.assertIn("не карты из игры", buf.getvalue())
        with open(other, "rb") as f:
            self.assertEqual(f.read(), save())

    def test_no_without_confirmation(self):
        with mock.patch("builtins.input", return_value="нет"):
            rc, _ = self.run_tool("--trucks", "--write")
        self.assertEqual(rc, 1)
        self.assertEqual(self.read(), save())
        self.assertFalse(os.path.exists(self.bk))

    def test_refuses_while_game_runs(self):
        with mock.patch.object(unlock_profile.install_local, "game_running", return_value=True):
            rc, out = self.run_tool("--trucks", "--write", "--yes")
        self.assertEqual(rc, 1)
        self.assertIn("Закройте", out)
        self.assertEqual(self.read(), save())

    def test_broken_save_is_left_alone(self):
        with open(self.path, "wb") as f:
            f.write(save(count=9))
        rc, out = self.run_tool("--trucks", "--write", "--yes")
        self.assertEqual(rc, 1)
        self.assertIn("Ничего не меняю", out)
        self.assertEqual(self.read(), save(count=9))

    def test_menu_item_3_opens_the_trucks(self):
        answers = iter(["3", "", "да"])
        buf = io.StringIO()
        with mock.patch("builtins.input", lambda _q="": next(answers)), redirect_stdout(buf):
            rc = unlock_profile.menu(os.path.join(self.tmp, "UserProfile.stu"), "-", common.GAME, self.saves, self.bk)
        self.assertEqual(rc, 0, buf.getvalue())
        self.assertTrue(all(t["unlocked"] for t in save_sts.trucks(self.read())))


if __name__ == "__main__":
    unittest.main()
