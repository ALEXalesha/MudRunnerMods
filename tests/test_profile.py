"""Profile unlock tool: the format laws and the safety rules. Works ONLY on copies in a temp folder.

MUDRUNNER_PROFILE_COPY=<path to a COPY of UserProfile.stu> adds the same laws on a real profile
(the file is copied into the temp folder first; the given file is only read)."""

import io
import os
import shutil
import struct
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

import common  # noqa: F401  (tools on sys.path)
import engine_limits
import profile_stu
import unlock_profile

V = 0x133ee19


def s(text):
    b = text.encode("latin-1") + b"\0"
    return struct.pack("<H", len(b)) + b


def map_entry(name, trucks=2, balance=0, cloak=b"\x78\x01abc"):
    out = s(name) + s("01/10/26 21:51") + struct.pack("<fB", 12.5, 0)
    out += struct.pack("<I", trucks) + b"".join(struct.pack("<3f", i, 2.0, 3.0) for i in range(trucks))
    out += struct.pack("<I", 1) + struct.pack("<H", 0) + s("zil131")
    out += s("zil131,zil131")
    if cloak:
        out += struct.pack("<II", 4, 4) + struct.pack("<I", len(cloak)) + cloak
    else:
        out += struct.pack("<II", 0, 0)
    out += struct.pack("<IBBB", balance, 0, 0, 1)
    return out


def profile(points=0, maps=None):
    maps = maps if maps is not None else [map_entry("abc12345"), map_entry("level_plains", cloak=b"")]
    out = struct.pack("<I", V) + s("abc12345") + s("abc12345") + s("")
    out += bytes([0, 0, 0, 1, 1]) + struct.pack("<I", points)
    out += struct.pack("<I", 2) + s("chlg_crash") + b"\x01" * 8 + s("chlg_hill") + b"\x02" * 8
    out += struct.pack("<I", len(maps)) + b"".join(maps)
    out += s("") + s("") + b"\x00\x00" + struct.pack("<I", 0) + struct.pack("<I", 0)
    out += struct.pack("<I", 3) + b"set" + struct.pack("<I", 5) + b"ctrls"
    return out


class FormatTest(unittest.TestCase):
    def test_synthetic_profile_parses_to_the_end(self):
        p = profile_stu.parse(profile(points=1))
        self.assertEqual(p["numLogPoints"], 1)
        self.assertEqual([m["strId"] for m in p["maps"]], ["abc12345", "level_plains"])
        self.assertEqual(p["controls"], b"ctrls")

    def test_extra_or_missing_bytes_are_refused(self):
        with self.assertRaises(profile_stu.StuError):
            profile_stu.parse(profile() + b"\0")
        with self.assertRaises(profile_stu.StuError):
            profile_stu.parse(profile()[:-1])
        with self.assertRaises(profile_stu.StuError):
            profile_stu.parse(b"\x00\x00\x00\x00" + profile()[4:])

    def check_edit_law(self, data):
        """After --maps: parses again, only numLogPoints changed, every other byte identical."""
        need = engine_limits.MAP_LOG_POINTS
        new, _ = unlock_profile.plan_maps(data, need)
        a, b = profile_stu.parse(data), profile_stu.parse(new)
        self.assertEqual(len(new), len(data))
        o = a["numLogPoints_at"]
        self.assertEqual(new[:o], data[:o])
        self.assertEqual(new[o + 4:], data[o + 4:])
        self.assertEqual(b["numLogPoints"], max(a["numLogPoints"], max(need.values())))
        for k in a:
            if k != "numLogPoints":
                self.assertEqual(a[k], b[k], k)
        self.assertEqual(profile_stu.locked_maps(b, need), [])
        return a, b

    def test_edit_law_synthetic(self):
        a, _ = self.check_edit_law(profile(points=0))
        self.assertEqual(profile_stu.locked_maps(a, engine_limits.MAP_LOG_POINTS),
                         ["level_coast", "level_dlc3_02", "level_flood", "level_hill", "level_river"])

    def test_points_never_go_down(self):
        new, lines = unlock_profile.plan_maps(profile(points=7), engine_limits.MAP_LOG_POINTS)
        self.assertEqual(new, profile(points=7))
        self.assertIn("уже открыты", lines[-1])

    def test_completed_map_is_open_without_points(self):
        p = profile_stu.parse(profile(points=0, maps=[map_entry("level_flood", balance=500)]))
        self.assertNotIn("level_flood", profile_stu.locked_maps(p, engine_limits.MAP_LOG_POINTS))

    @unittest.skipUnless(os.environ.get("MUDRUNNER_PROFILE_COPY"), "no real profile copy given")
    def test_edit_law_real_profile_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            dst = os.path.join(tmp, "UserProfile.stu")
            shutil.copyfile(os.environ["MUDRUNNER_PROFILE_COPY"], dst)
            with open(dst, "rb") as f:
                self.check_edit_law(f.read())

    @unittest.skipUnless(common.HAVE_GAME, "game not installed")
    def test_table_matches_the_exe(self):
        exe = os.path.join(common.GAME, "MudRunner.exe")
        self.assertEqual(engine_limits.read_exe_map_requirements(exe), engine_limits.MAP_LOG_POINTS)


class ToolTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "UserProfile.stu")
        with open(self.path, "wb") as f:
            f.write(profile(points=0))
        os.environ["OPENTRAIL_NO_GAME_CHECK"] = "1"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_tool(self, *args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = unlock_profile.main(["--profile", self.path, "--exe", "-"] + list(args))
        return rc, buf.getvalue()

    def read(self):
        with open(self.path, "rb") as f:
            return f.read()

    def test_dry_run_writes_nothing(self):
        rc, out = self.run_tool("--maps")
        self.assertEqual(rc, 0)
        self.assertEqual(self.read(), profile(points=0))
        self.assertIn("Наводнение", out)
        self.assertIn("Пробный режим", out)
        self.assertEqual(unlock_profile.backups(self.path), [])

    def test_write_makes_backup_and_restore_brings_it_back(self):
        rc, _ = self.run_tool("--maps", "--write", "--yes")
        self.assertEqual(rc, 0)
        self.assertEqual(profile_stu.parse(self.read())["numLogPoints"], 3)
        bks = unlock_profile.backups(self.path)
        self.assertEqual(len(bks), 1)
        with open(bks[0], "rb") as f:
            self.assertEqual(f.read(), profile(points=0))
        rc, _ = self.run_tool("--restore", "--write", "--yes")
        self.assertEqual(rc, 0)
        self.assertEqual(self.read(), profile(points=0))

    def test_no_without_confirmation(self):
        with mock.patch("builtins.input", return_value="нет"):
            rc, out = self.run_tool("--maps", "--write")
        self.assertEqual(rc, 1)
        self.assertEqual(self.read(), profile(points=0))
        self.assertEqual(unlock_profile.backups(self.path), [])

    def test_refuses_while_game_runs(self):
        with mock.patch.object(unlock_profile.install_local, "game_running", return_value=True):
            rc, out = self.run_tool("--maps", "--write", "--yes")
        self.assertEqual(rc, 1)
        self.assertIn("Закройте", out)
        self.assertEqual(self.read(), profile(points=0))

    def test_broken_profile_is_left_alone(self):
        with open(self.path, "wb") as f:
            f.write(profile()[:-3])
        rc, out = self.run_tool("--maps", "--write", "--yes")
        self.assertEqual(rc, 1)
        self.assertEqual(self.read(), profile()[:-3])


if __name__ == "__main__":
    unittest.main()
