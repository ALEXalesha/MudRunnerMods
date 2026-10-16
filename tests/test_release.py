"""OpenTrail_Tools.zip (tools/build_workshop.tools_zip) unpacked into an empty folder:
the tools start without the repository and its .venv, install_local.py finds the
packages that came with it and edits a COPY of a Config.xml, the .bat files keep CRLF,
and there is no personal data inside."""

import os
import subprocess
import sys
import tempfile
import unittest
import zipfile

import common
import build_workshop
from common import ROOT
from test_install import CONFIG

LOCAL = os.path.join(ROOT, "build", "local")
FORBIDDEN = common.private_strings()


def have_packages():
    return os.path.isdir(LOCAL) and any(f.startswith("opentrail_") for f in os.listdir(LOCAL))


@unittest.skipUnless(have_packages(), "build/local has no packages (tools/build_mods.py)")
class ToolsZipTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = tempfile.mkdtemp(prefix="ot_rel_")
        cls.path = build_workshop.tools_zip(LOCAL, cls.out)
        cls.dest = tempfile.mkdtemp(prefix="ot_kit_")
        with zipfile.ZipFile(cls.path) as z:
            cls.names = z.namelist()
            cls.blobs = {n: z.read(n) for n in cls.names}
            z.extractall(cls.dest)

    def run_tool(self, *args):
        env = dict(os.environ, PYTHONIOENCODING="utf-8", OPENTRAIL_NO_GAME_CHECK="1")
        return subprocess.run([sys.executable, "-I"] + list(args), cwd=self.dest, capture_output=True,
                              text=True, encoding="utf-8", env=env, timeout=300)

    def test_contents(self):
        for bat in build_workshop.TOOLS_BATS:
            self.assertIn(bat, self.names)
            self.assertNotIn(b"\n", self.blobs[bat].replace(b"\r\n", b""), bat)
        for f in ("tools/install_local.py", "tools/unlock_profile.py", "tools/combine.py",
                  "tools/profile_stu.py", "tools/save_sts.py", "mods/order.json", "README - ПРОЧТИ.txt"):
            self.assertIn(f, self.names)
        self.assertNotIn("tools/mutation_check.py", self.names)
        pk = [n for n in self.names if n.startswith("build/local/")]
        self.assertTrue(pk)
        self.assertNotIn("build/local/opentrail_unlock.zip", pk)       # 295 MB, separate asset
        for n in pk:
            with open(os.path.join(LOCAL, os.path.basename(n)), "rb") as fh:
                self.assertEqual(self.blobs[n], fh.read(), n)

    def test_no_personal_data(self):
        for n, data in self.blobs.items():
            blob = n.lower().encode("utf-8") + b"\n" + data.lower()
            for bad in FORBIDDEN:
                if bad.startswith(b"steam"):        # the code names the generic Steam folder
                    continue
                self.assertNotIn(bad, blob, n)

    def test_tools_start_from_the_unpacked_copy(self):
        for script in ("tools/install_local.py", "tools/unlock_profile.py", "tools/combine.py"):
            r = self.run_tool(script, "--help")
            self.assertEqual(r.returncode, 0, script + "\n" + r.stderr)

    def test_install_local_uses_the_bundled_packages(self):
        cfg = os.path.join(tempfile.mkdtemp(prefix="ot_cfg_"), "Config.xml")
        with open(cfg, "w", encoding="utf-8", newline="\r\n") as fh:
            fh.write(CONFIG)
        r = self.run_tool("tools/install_local.py", "--config", cfg, "--apply")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(cfg, encoding="utf-8") as fh:
            text = fh.read()
        kit = os.path.join(self.dest, "build", "local").replace("\\", "/").lower()
        lines = [l for l in text.splitlines() if "opentrail_" in l]
        self.assertTrue(lines, r.stdout)
        for l in lines:
            self.assertIn(kit, l.replace("\\", "/").lower())
        self.assertLess(text.index("opentrail_"), text.index('Path="Media.zip"'))


if __name__ == "__main__":
    unittest.main()
