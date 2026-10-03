"""No personal data in anything that can be published: tracked files, built
packages, Workshop folders and release notes."""

import os
import subprocess
import unittest

import common
from common import HAVE_GAME, ROOT, built, workshop_dir, private_strings

FORBIDDEN = private_strings()


def tracked_files():
    out = subprocess.run(["git", "-C", ROOT, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                         capture_output=True, timeout=60).stdout.decode("utf-8")
    return [f for f in out.split("\0") if f]


class PrivacyTest(unittest.TestCase):
    def assertClean(self, data, where):
        low = data.lower()
        for s in FORBIDDEN:
            self.assertNotIn(s, low, "%s contains a private string" % where)

    def test_forbidden_list_has_the_real_items(self):
        # without the git config the check would pass trivially
        self.assertTrue(any(b"@" in s for s in FORBIDDEN) or os.environ.get("CI"), FORBIDDEN)

    def test_repository_files(self):
        n = 0
        for rel in tracked_files():
            path = os.path.join(ROOT, rel)
            if not os.path.isfile(path):
                continue
            with open(path, "rb") as fh:
                self.assertClean(fh.read(), rel)
            n += 1
        self.assertGreater(n, 10)

    @unittest.skipUnless(HAVE_GAME, "game not installed")
    def test_packages(self):
        for name, b in built().items():
            for path, data in b.files.items():
                self.assertClean(data, "%s:%s" % (name, path))

    @unittest.skipUnless(HAVE_GAME, "game not installed")
    def test_workshop_folders(self):
        for dp, _dn, fn in os.walk(workshop_dir()):
            for f in fn:
                with open(os.path.join(dp, f), "rb") as fh:
                    self.assertClean(fh.read(), f)

    def test_detects_a_planted_email(self):
        email = subprocess.run(["git", "-C", ROOT, "config", "user.email"], capture_output=True,
                               text=True, timeout=30).stdout.strip()
        if not email:
            self.skipTest("no git user.email here")
        with self.assertRaises(AssertionError):
            self.assertClean(("text " + email.upper()).encode(), "planted")


if __name__ == "__main__":
    unittest.main()
