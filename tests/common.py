"""Shared fixtures: the game files and one cached build of every mod (no level files written)."""

import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import build_mods  # noqa: E402
import mrxml  # noqa: E402

GAME = os.environ.get("MUDRUNNER_DIR", build_mods.DEFAULT_GAME)
HAVE_GAME = os.path.isfile(os.path.join(GAME, "Media.zip"))
DLC = ["_dlc_valley.zip", "_dlc_ridge.zip", "_dlc_usa.zip", "_dlc_oldtimers.zip"]

_FS = []
_BUILT = {}
_WS = []


def fs():
    if not _FS:
        _FS.append(mrxml.GameFs(GAME))
    return _FS[0]


def stock():
    return mrxml.Resolver(fs())


def built():
    """{name: Built} for every mod in mods/order.json, chain applied, levels planned only."""
    if not _BUILT:
        _BUILT.update(build_mods.build_all(GAME, None, skip_levels=True, verbose=False, fs=fs()))
    return _BUILT


def workshop_dir():
    if not _WS:
        import build_workshop
        out = os.path.join(tempfile.mkdtemp(prefix="mrws_test_"), "workshop")
        build_workshop.build(out, GAME, verbose=False)
        _WS.append(out)
    return _WS[0]


def resolver_with(files):
    return mrxml.Resolver(mrxml.Layer(fs(), files))


def drivable_trucks():
    r = stock()
    out = []
    for n in fs().class_names("trucks"):
        root, _c = r.resolve("trucks", n)
        if build_mods.is_drivable(root):
            out.append(n)
    return out


def source(kind, name):
    return fs().source(mrxml.KIND_DIRS[kind] + name + ".xml")


def private_strings():
    """Personal strings that must never reach a public file.

    None of them is written here (this file is public too): they come from the
    local git config (user.email, publish.privateName, publish.privateExtra), the
    HOST of the Gitea remote (the repo name is public), the folder this repository
    lives in and the Steam user folders on this PC.
    """
    import glob
    import subprocess

    def git(*args):
        try:
            return subprocess.run(["git", "-C", ROOT] + list(args), capture_output=True,
                                  text=True, encoding="utf-8", timeout=30).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            return ""

    # generic markers, glued from parts so that this file does not contain them itself
    out = {b"gmail" + b".com", b"steam\\" + b"userdata", b"steam/" + b"userdata"}
    email = git("config", "user.email")
    if email:
        out.add(email.lower().encode())
    for word in (git("config", "publish.privateName") + " " +
                 git("config", "publish.privateExtra").replace("|", " ")).split():
        if len(word) >= 4:
            out.add(word.lower().encode("utf-8"))
    m = re.match(r"^[a-z]+://([^/:]+)", git("remote", "get-url", "origin"))
    if m:
        out.add(m.group(1).lower().encode())
    parent = os.path.dirname(ROOT)
    for variant in (parent, parent.replace("\\", "/"), parent.replace("\\", "\\\\")):
        out.add(variant.lower().encode())
    for d in glob.glob(os.path.join(r"C:\Program Files (x86)", "Steam", "user" + "data", "*")):
        out.add(os.path.basename(d).lower().encode())
    return sorted(x for x in out if len(x) >= 4)
