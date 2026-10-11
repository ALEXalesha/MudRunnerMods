"""Probe package: stock files, byte-identical, through the same install path.

  .venv\\Scripts\\python tools\\build_probe.py
  .venv\\Scripts\\python tools\\install_local.py --probe --apply           (identical)
  .venv\\Scripts\\python tools\\install_local.py --probe changed --apply   (one value changed)

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
# Names at most 16 characters before .zip (engine_limits.ARCHIVE_NAME_MAX). Until 10.10
# they were OpenTrail_Probe_<Name>.zip (21 to 25): every probe with a truck crashed
# the game for that reason alone, not for its content.
PROBE_ZIP = "otprobe_ident.zip"
CHANGED_ZIP = "otprobe_changed.zip"     # uaz469.xml with FuelCapacity 80 -> 81, nothing else


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


# Sub-probes, each a separate zip and `install_local.py --probe <name>`:
#   manifest  only a ModStrings file at the zip root, overrides nothing: is ANY extra mount a problem?
#   names     only new strings files strings/<lang>/opentrail_probe.txt (one new key), overrides
#             nothing: does the game accept an extra strings file? (the truck mods name their
#             new trucks this way since 1.0.0 test 6)
#   plant     classes/plants/stump_b.xml, byte-identical
#   wheel     classes/wheels/kamaz_offroad.xml, byte-identical
#   truck     classes/trucks/uaz469.xml, byte-identical. With the long name it crashed the game
#             (04.10, as OpenTrail_Probe_Identical); with the short name it tells whether a
#             stock truck file can be shadowed at all (7th test).
SUB_PROBES = {
    "manifest": None,
    "names": "strings",
    "plant": "classes/plants/stump_b.xml",
    "wheel": "classes/wheels/kamaz_offroad.xml",
    "truck": "classes/trucks/uaz469.xml",
}

MANIFEST = b'<ModStrings>\n\t<String Id="opentrail_probe" Value="OpenTrail probe" />\n</ModStrings>\n'


def sub_zip_name(name):
    return "otprobe_%s.zip" % name


def build_sub(name, out_dir, game=build_mods.DEFAULT_GAME):
    fs = mrxml.GameFs(game)
    os.makedirs(out_dir, exist_ok=True)
    b = build_mods.Built("probe_" + name, {"title": "Probe " + name})
    path = SUB_PROBES[name]
    if path is None:
        b.files["opentrail_probe.xml"] = MANIFEST
    elif path == "strings":
        import build_workshop
        for lang in build_workshop.languages(fs):
            b.files["strings/%s/opentrail_probe.txt" % lang] = build_workshop.strings_txt(
                {"opentrail_probe": "OpenTrail probe"})
    else:
        b.files[path] = fs.read(path)
    out = os.path.join(out_dir, sub_zip_name(name))
    build_mods.write_package(b, fs, out)
    return out


def build_changed(out_dir, game=build_mods.DEFAULT_GAME):
    """One stock truck file with one value changed in place (80 -> 81 litres)."""
    fs = mrxml.GameFs(game)
    os.makedirs(out_dir, exist_ok=True)
    path = "classes/trucks/uaz469.xml"
    old = fs.read(path)
    if old.count(b'FuelCapacity="80"') != 1:
        raise build_mods.BuildError("uaz469.xml changed in the game: no single FuelCapacity=\"80\"")
    b = build_mods.Built("probe_changed", {"title": "Probe Changed"})
    b.files[path] = old.replace(b'FuelCapacity="80"', b'FuelCapacity="81"')
    out = os.path.join(out_dir, CHANGED_ZIP)
    build_mods.write_package(b, fs, out)
    return out


if __name__ == "__main__":
    local = os.path.join(build_mods.ROOT, "build", "local")
    print(build(local))
    print(build_changed(local))
    for n in SUB_PROBES:
        print(build_sub(n, local))
