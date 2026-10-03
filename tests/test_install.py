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
    PKGS = ["C:/Mods/OpenTrail_Hyper_Power.zip", "C:/Mods/OpenTrail_No_Damage.zip"]

    def test_lines_go_above_media_zip_in_order(self):
        out = install_local.edit_config(CONFIG, self.PKGS)
        lines = out.splitlines()
        i = [k for k, l in enumerate(lines) if 'Path="Media.zip"' in l][0]
        self.assertIn("OpenTrail_Hyper_Power.zip", lines[i - 2])
        self.assertIn("OpenTrail_No_Damage.zip", lines[i - 1])
        self.assertTrue(lines[i - 1].startswith("    <MediaPath"))

    def test_idempotent_and_removable(self):
        once = install_local.edit_config(CONFIG, self.PKGS)
        self.assertEqual(install_local.edit_config(once, self.PKGS), once)
        self.assertEqual(install_local.edit_config(once, []), CONFIG)
        other = install_local.edit_config(once, self.PKGS[1:])
        self.assertNotIn("Hyper", other)

    def test_crlf_kept(self):
        crlf = CONFIG.replace("\n", "\r\n")
        out = install_local.edit_config(crlf, self.PKGS)
        self.assertNotRegex(out, r"(?<!\r)\n")

    def test_backslashes_become_slashes(self):
        out = install_local.edit_config(CONFIG, [r"D:\x\OpenTrail_No_Damage.zip"])
        self.assertIn('Path="D:/x/OpenTrail_No_Damage.zip"', out)

    def test_no_media_line(self):
        with self.assertRaises(ValueError):
            install_local.edit_config("<Config />\n", self.PKGS)

    def test_apply_on_a_copy_writes_backup(self):
        tmp = tempfile.mkdtemp(prefix="mrinst_")
        cfg = os.path.join(tmp, "Config.xml")
        local = os.path.join(tmp, "local")
        os.makedirs(local)
        with open(cfg, "w", encoding="utf-8", newline="") as fh:
            fh.write(CONFIG)
        open(os.path.join(local, "OpenTrail_No_Damage.zip"), "wb").close()
        r = subprocess.run([sys.executable, os.path.join(common.ROOT, "tools", "install_local.py"),
                            "--config", cfg, "--local", local, "--apply"],
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = open(cfg, encoding="utf-8").read()
        self.assertIn("OpenTrail_No_Damage.zip", text)
        backups = [f for f in os.listdir(tmp) if f.startswith("Config.xml.opentrail-")]
        self.assertEqual(len(backups), 1)
        self.assertEqual(open(os.path.join(tmp, backups[0]), encoding="utf-8").read(), CONFIG)
        shutil.rmtree(tmp, ignore_errors=True)       # a temp folder made by this test only


if __name__ == "__main__":
    unittest.main()
