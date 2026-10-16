"""Turn the local OpenTrail packages on or off in MudRunner's Config.xml.

  python tools/install_local.py                      # dry run: show what would change
  python tools/install_local.py --apply              # the safe set (backup first)
  python tools/install_local.py --all --apply        # also the opt-in mods
  python tools/install_local.py --mods no_damage,infinite_fuel --apply
  python tools/install_local.py --remove --apply     # take all OpenTrail lines out
  python tools/install_local.py --custom --apply     # only your own set (tools/combine.py, build/custom)
  python tools/install_local.py --probe names --apply     # only new strings files (names of new trucks)
  python tools/install_local.py --probe wheel --apply     # one stock wheel file, byte-identical
  python tools/install_local.py --probe truck --apply     # REPLACES A STOCK TRUCK FILE: diagnosis only
  (--probe identical and --probe changed also hold a stock truck file)

Package names are at most 16 characters before .zip (engine_limits.ARCHIVE_NAME_MAX):
the game copies the name of the archive a truck or level comes from into a 17 byte
buffer, and a longer name ends the game (every crash of the tests 03.10 to 10.10).

The safe set is every mod except those listed under "opt_in" in mods/order.json
(Unlocked Trucks: it replaces whole level files). The script prints exactly
which mods it installs and which it leaves out.

How the game finds the packages: Config.xml lists <MediaPath> entries; the game
mounts each one (zip or folder, absolute paths work) and uses the FIRST copy of a
file it finds. So the OpenTrail lines go above <MediaPath Path="Media.zip" />, in
the order of mods/order.json (top = highest priority).

Which Config.xml: the game saves its settings to
%APPDATA%\\SpinTires MudRunner\\Config.xml on exit ("Combine config saved to ..."
in Log.txt) and reads it at start. Run this only with the game closed, or the
game overwrites the change on exit. A backup Config.xml.opentrail-<time> is
written next to it before any change. (The current game build no longer writes
Log.txt, so the check is in game: the main menu must appear as usual.)
"""

import argparse
import datetime
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_mods  # noqa: E402

DEFAULT_CONFIG = os.path.join(os.environ.get("APPDATA", ""), "SpinTires MudRunner", "Config.xml")
MARKS = ("opentrail_", "otprobe_")      # also matches the old OpenTrail_<Title>.zip lines
CUSTOM_DIR = os.path.join(build_mods.ROOT, "build", "custom")
LINE_RE = re.compile(r'^[ \t]*<MediaPath\b[^>]*Path="([^"]*)"[^>]*/>[ \t]*\r?\n?', re.M)


def opt_in():
    return build_mods.load_order_file().get("opt_in", [])


def chosen_mods(mods=None, include_opt_in=False):
    """Mod names to install, top priority first."""
    order = build_mods.load_order()
    if mods:
        unknown = [m for m in mods if m not in order]
        if unknown:
            raise SystemExit("unknown mods: %s (known: %s)" % (", ".join(unknown), ", ".join(order)))
        return [n for n in order if n in mods]
    skip = [] if include_opt_in else opt_in()
    return [n for n in order if n not in skip]


def packages_in_order(local_dir, mods=None):
    """Absolute paths of the built packages, top priority first."""
    order = build_mods.load_order()
    out = []
    for name in order:
        if mods is not None and name not in mods:
            continue
        p = os.path.join(local_dir, build_mods.zip_name(build_mods.load_spec(name)))
        if os.path.isfile(p):
            out.append(os.path.abspath(p))
        else:
            raise SystemExit("package not built: %s (run tools/build_mods.py first)" % p)
    return out


def edit_config(text, packages):
    """Remove old OpenTrail lines, insert `packages` above the Media.zip line."""
    nl = "\r\n" if "\r\n" in text else "\n"
    text = "".join(part for part in _split_keep(text) if not _is_ours(part))
    if not packages:
        return text
    m = None
    for x in LINE_RE.finditer(text):
        if x.group(1).replace("\\", "/").lower().endswith("media.zip"):
            m = x
            break
    if m is None:
        raise ValueError("no <MediaPath Path=\"Media.zip\" /> line in Config.xml")
    indent = re.match(r"[ \t]*", text[m.start():]).group(0)
    block = "".join('%s<MediaPath Path="%s" />%s' % (indent, p.replace("\\", "/"), nl) for p in packages)
    return text[:m.start()] + block + text[m.start():]


def _split_keep(text):
    return re.findall(r"[^\n]*\n|[^\n]+$", text)


def _is_ours(line):
    m = LINE_RE.match(line)
    return bool(m) and os.path.basename(m.group(1).replace("\\", "/")).lower().startswith(MARKS)


def game_running():
    # the tests set this: the CI runner is the same PC, the game may be open there
    if os.environ.get("OPENTRAIL_NO_GAME_CHECK") == "1":
        return False
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq MudRunner.exe", "/NH"],
                             capture_output=True, timeout=30).stdout.decode("ascii", "replace")
    except (OSError, subprocess.TimeoutExpired):
        return False
    return "MudRunner.exe" in out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--local", default=os.path.join(build_mods.ROOT, "build", "local"))
    ap.add_argument("--mods", help="comma separated mod names (default: the safe set)")
    ap.add_argument("--all", action="store_true", help="include the opt-in mods (Hyper Power, Unlocked Trucks)")
    ap.add_argument("--probe", nargs="?", const="identical",
                    choices=["identical", "changed", "manifest", "names", "plant", "wheel", "truck"],
                    help="install only a probe (tools/build_probe.py): identical = 3 stock files byte for "
                         "byte; changed = uaz469.xml with FuelCapacity 80 -> 81; manifest = only a ModStrings "
                         "file, overrides nothing; names = only new strings files (how the truck mods name "
                         "their new trucks), overrides nothing; plant / wheel = one stock file byte for byte; "
                         "truck = uaz469.xml byte for byte. truck, identical and changed replace a stock truck "
                         "file: diagnosis only, the game may crash (with the old long names they always did)")
    ap.add_argument("--custom", action="store_true",
                    help="install only your own set build/custom/%s (made by tools/combine.py)" % build_mods.CUSTOM_ZIP)
    ap.add_argument("--custom-dir", default=CUSTOM_DIR, help=argparse.SUPPRESS)
    ap.add_argument("--remove", action="store_true")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if not os.path.isfile(a.config):
        raise SystemExit("Config.xml not found: %s (start the game once)" % a.config)
    mods = None
    if a.custom:
        custom = os.path.abspath(os.path.join(a.custom_dir, build_mods.CUSTOM_ZIP))
        if not os.path.isfile(custom):
            raise SystemExit("your own set is not built: run tools/combine.py first (%s)" % custom)
        print("Installing your own set only: %s" % custom)
        packages = [custom]
        mods = []
    elif a.probe:
        import build_probe
        zname = build_probe.PROBE_ZIP if a.probe == "identical" else (
            build_probe.CHANGED_ZIP if a.probe == "changed" else build_probe.sub_zip_name(a.probe))
        probe = os.path.abspath(os.path.join(a.local, zname))
        if not os.path.isfile(probe):
            raise SystemExit("probe not built: run tools/build_probe.py first")
        what = {"identical": "3 stock files, byte-identical", "changed": "uaz469.xml, FuelCapacity 80 -> 81",
                "manifest": "only a ModStrings file, overrides nothing", "plant": "stump_b.xml, byte-identical",
                "names": "only strings/<lang>/opentrail_probe.txt, overrides nothing",
                "wheel": "kamaz_offroad.xml, byte-identical", "truck": "uaz469.xml, byte-identical"}[a.probe]
        print("Installing the probe only (%s): %s" % (what, probe))
        if a.probe in ("truck", "identical", "changed"):
            print("WARNING: this probe REPLACES A STOCK TRUCK FILE: diagnosis only, the game may crash. "
                  "Undo: install_local.py --remove --apply")
        packages = [probe]
        mods = []
    elif not a.remove:
        mods = chosen_mods([x.strip() for x in a.mods.split(",")] if a.mods else None, a.all)
        left = [n for n in build_mods.load_order() if n not in mods]
        print("Installing %d mods (top = highest priority): %s" % (len(mods), ", ".join(mods)))
        print("Not installed: %s" % (", ".join(left) or "-"))
    if not a.probe and not a.custom:
        packages = [] if a.remove else packages_in_order(a.local, mods)
    if not a.remove and not a.probe and not a.custom and len(packages) != len(mods):
        raise SystemExit("not every package is built in %s: run tools/build_mods.py first" % a.local)
    with open(a.config, encoding="utf-8", newline="") as fh:
        old = fh.read()
    new = edit_config(old, packages)
    print("Config.xml:", a.config)
    for p in packages:
        print('  <MediaPath Path="%s" />' % p.replace("\\", "/"))
    if new == old:
        print("no change")
        return 0
    if not a.apply:
        print("dry run: add --apply to write (the game must be closed)")
        return 0
    if game_running():
        raise SystemExit("MudRunner is running: close it first, it rewrites Config.xml on exit")
    backup = a.config + ".opentrail-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copyfile(a.config, backup)
    with open(a.config, "w", encoding="utf-8", newline="") as fh:
        fh.write(new)
    print("written; backup:", backup)
    return 0


if __name__ == "__main__":
    sys.exit(main())
