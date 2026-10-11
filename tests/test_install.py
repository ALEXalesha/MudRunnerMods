"""tools/install_local.py on a copy of a Config.xml (never the real one)."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import common
import install_local

CONFIG = """<Config Version="20151004">
    <System Height="1080" Maximized="false" Width="1920" Windowed="false" />
    <MediaPath Path="Media.zip" />
    <MediaPath Path="_dlc_valley.zip" />
    <MediaPath DoPrepend="true" MountPoint="_t/" Path="TextureCache.zip" />
</Config>
"""


class ConfigEditTest(unittest.TestCase):
    PKGS = ["C:/Mods/opentrail_hyper.zip", "C:/Mods/opentrail_damage.zip"]

    def test_lines_go_above_media_zip_in_order(self):
        out = install_local.edit_config(CONFIG, self.PKGS)
        lines = out.splitlines()
        i = [k for k, l in enumerate(lines) if 'Path="Media.zip"' in l][0]
        self.assertIn("opentrail_hyper.zip", lines[i - 2])
        self.assertIn("opentrail_damage.zip", lines[i - 1])
        self.assertTrue(lines[i - 1].startswith("    <MediaPath"))

    def test_idempotent_and_removable(self):
        once = install_local.edit_config(CONFIG, self.PKGS)
        self.assertEqual(install_local.edit_config(once, self.PKGS), once)
        self.assertEqual(install_local.edit_config(once, []), CONFIG)
        other = install_local.edit_config(once, self.PKGS[1:])
        self.assertNotIn("hyper", other)

    def test_crlf_kept(self):
        crlf = CONFIG.replace("\n", "\r\n")
        out = install_local.edit_config(crlf, self.PKGS)
        self.assertNotRegex(out, r"(?<!\r)\n")

    def test_backslashes_become_slashes(self):
        out = install_local.edit_config(CONFIG, [r"D:\x\opentrail_damage.zip"])
        self.assertIn('Path="D:/x/opentrail_damage.zip"', out)

    def test_no_media_line(self):
        with self.assertRaises(ValueError):
            install_local.edit_config("<Config />\n", self.PKGS)

    def run_tool(self, *args):
        tmp = tempfile.mkdtemp(prefix="mrinst_")
        cfg = os.path.join(tmp, "Config.xml")
        local = os.path.join(tmp, "local")
        os.makedirs(local)
        with open(cfg, "w", encoding="utf-8", newline="") as fh:
            fh.write(CONFIG)
        for name in install_local.build_mods.load_order():
            spec = install_local.build_mods.load_spec(name)
            open(os.path.join(local, install_local.build_mods.zip_name(spec)), "wb").close()
        open(os.path.join(local, "otprobe_ident.zip"), "wb").close()
        for n in ("changed", "manifest", "names", "plant", "wheel", "truck"):
            open(os.path.join(local, "otprobe_%s.zip" % n), "wb").close()
        env = dict(os.environ, OPENTRAIL_NO_GAME_CHECK="1")    # the game may be open on this PC
        r = subprocess.run([sys.executable, os.path.join(common.ROOT, "tools", "install_local.py"),
                            "--config", cfg, "--local", local] + list(args),
                           capture_output=True, text=True, timeout=120, env=env)
        text = open(cfg, encoding="utf-8").read()
        backups = [f for f in os.listdir(tmp) if f.startswith("Config.xml.opentrail-")]
        backup = open(os.path.join(tmp, backups[0]), encoding="utf-8").read() if backups else None
        shutil.rmtree(tmp, ignore_errors=True)       # a temp folder made by this test only
        return r, text, backup

    def test_default_is_the_safe_set_and_says_so(self):
        r, text, backup = self.run_tool("--apply")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(backup, CONFIG)
        self.assertNotIn("opentrail_unlock", text)
        self.assertNotIn("opentrail_hyper", text)          # alternative to Powerful Engines, opt-in
        self.assertEqual(text.count("opentrail_"), 7)
        self.assertIn("Installing 7 mods", r.stdout)
        self.assertIn("Not installed: hyper_power, unlocked_trucks", r.stdout)

    def test_all_and_explicit(self):
        r, text, _b = self.run_tool("--all", "--apply")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("opentrail_unlock.zip", text)
        r, text, _b = self.run_tool("--mods", "unlocked_trucks,no_damage", "--apply")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(text.count("opentrail_"), 2)
        self.assertLess(text.index("opentrail_damage"), text.index("opentrail_unlock"))     # load order kept

    def test_probe_only(self):
        r, text, _b = self.run_tool("--probe", "--apply")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(text.count("otprobe_"), 1)
        self.assertIn("otprobe_ident.zip", text)
        r3, text3, _b = self.run_tool("--probe", "changed", "--apply")
        self.assertEqual(r3.returncode, 0, r3.stdout + r3.stderr)
        self.assertIn("otprobe_changed.zip", text3)
        self.assertEqual(text3.count("otprobe_"), 1)
        for n in ("manifest", "names", "plant", "wheel", "truck"):
            r4, text4, _b = self.run_tool("--probe", n, "--apply")
            self.assertEqual(r4.returncode, 0, r4.stdout + r4.stderr)
            self.assertIn("otprobe_%s.zip" % n, text4)
            self.assertEqual(text4.count("otprobe_"), 1)
            # the truck probe replaces a stock truck file: it must say so
            self.assertEqual("REPLACES A STOCK TRUCK FILE" in r4.stdout, n == "truck", n)
        r2, text2, _b = self.run_tool("--remove", "--apply")
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)

    def test_help_marks_the_crashing_probes(self):
        r = subprocess.run([sys.executable, os.path.join(common.ROOT, "tools", "install_local.py"), "--help"],
                           capture_output=True, text=True, timeout=60)
        text = " ".join(r.stdout.split())
        self.assertIn("names = only new strings files", text)
        self.assertIn("replace a stock truck file", text)
        self.assertIn("diagnosis only", text)

    def test_dry_run_writes_nothing(self):
        r, text, backup = self.run_tool()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(text, CONFIG)
        self.assertIsNone(backup)

    def test_opt_in_lists_unlocked_trucks(self):
        self.assertEqual(install_local.opt_in(), ["hyper_power", "unlocked_trucks"])

if __name__ == "__main__":
    unittest.main()
