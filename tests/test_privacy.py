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

    def test_public_remote_host_is_not_private(self):
        # law: GitHub (CI checkout) is public, any other remote host is private
        for url in ("https://github.com/ALEXalesha/MudRunnerMods", "https://x-access-token:t@github.com/a/b.git",
                    "https://GitHub.com/a/b"):
            self.assertIsNone(common.private_host(url), url)
        for host in ("192.168.7.9", "gitea.home.lan", "10.0.0.5"):
            self.assertEqual(common.private_host("http://%s:3000/u/r.git" % host), host.encode(), host)
        self.assertIsNone(common.private_host(""))

    def test_authorship_first_name_is_public(self):
        # the README authorship line names Alexey; the check must not turn it red
        self.assertNotIn(b"alexey", FORBIDDEN)

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
