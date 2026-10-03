"""Probe package: stock files, byte-identical, through the same install path.

  .venv\\Scripts\\python tools\\build_probe.py
  .venv\\Scripts\\python tools\\install_local.py --probe --apply

It ships three files copied unchanged from the game archives (one truck, one
wheel, one plant) in a zip written exactly like the mod packages. If the game
works with it, the mount mechanism (Config.xml line, zip format, shadowing a
stock path) is fine and a crash comes from the content of a mod. If it crashes,
the mechanism itself is the cause.
"""

import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_mods  # noqa: E402
import mrxml  # noqa: E402
import zipcheck  # noqa: E402

PROBE_FILES = ["classes/trucks/uaz469.xml", "classes/wheels/kamaz_offroad.xml", "classes/plants/stump_b.xml"]
PROBE_ZIP = "OpenTrail_Probe_Identical.zip"


def build(out_dir, game=build_mods.DEFAULT_GAME):
    fs = mrxml.GameFs(game)
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, PROBE_ZIP)
    b = build_mods.Built("probe", {"title": "Probe Identical"})
    for p in PROBE_FILES:
        b.files[p] = fs.read(p)
    build_mods.write_package(b, fs, out)
    with zipfile.ZipFile(out) as z:
        for p in PROBE_FILES:
            if z.read(p) != fs.read(p):
                raise build_mods.BuildError("%s is not byte-identical" % p)
    if zipcheck.problems(out):
        raise build_mods.BuildError("probe zip fails zipcheck")
    return out


if __name__ == "__main__":
    print(build(os.path.join(build_mods.ROOT, "build", "local")))
