"""Build the OpenTrail mods for Spintires: MudRunner from the game's own files.

The repository holds no game files. This script reads the class XML files from
the installed game (Media.zip plus the DLC archives), applies the changes listed
in mods/<name>/mod.json and writes one override package per mod: a zip with the
changed files at the same paths as in Media.zip. The game mounts it through a
<MediaPath> line in Config.xml (see README, "Install").

How a change is described
-------------------------
A mod says what the EFFECTIVE value of an attribute must be for every class it
targets, for example "Motor Torque of every drivable truck = stock x2.5". The
effective value is the one the game sees after inheritance (<_parent>) and
templates (_template, <_templates Include="trucks">). The build then edits the
fewest attributes needed to get there:
  1. if the value comes from the same file, it is replaced in place;
  2. otherwise the attribute is written on the file's own node at that position
     (it overrides the parent or template value);
  3. after the edits the class is resolved again and every target value is
     checked. Any mismatch stops the build.
Parents are processed before children, so a child that does not override a
value simply inherits the patched parent.

Ops in mod.json ("ops": [...]):
  {"kind": "trucks", "only": "drivable", "path": "TruckData/Motor", "attr": "Torque",
   "scale": 2.5}                         multiply (keeps integers integer)
  ... "set": "100000"                    set a value
  ... "map": {"none": "full", "": "full"} replace listed values ("" = attribute missing)
  ... "scale": 2.5, "min": 2.5           scale, then raise to at least min
  ... "scale": 10, "max": 1000000        scale, then cap (engine limits: tools/engine_limits.py)
  {"kind": "trucks", "only": "drivable", "path": "TruckData/Damage", "fording": {...}}
  {"kind": "plants", "names": [...], "winch_socket": {...}}
  {"levels": ["level_*"], "unlock_trucks": true}   level files (binary .stg)
"only": "drivable" = <Truck> classes with gears; "trailers" = <Truck> without
gears; "all" = every class of the kind.

Truck mods are new trucks (since the third in-game test)
-------------------------------------------------------
Replacing a stock classes/trucks/*.xml crashed the game on "Single player" even
when only FuelCapacity changed (wheel and plant replacements worked). The truck
mods ("as_heirs": true in mod.json) therefore never replace a stock truck file:
their package holds NEW classes: full copies of the stock truck files under new
names (otf_kamaz4310.xml) with only the changed values, plus a copy of the
selection icon billboards/trucks/<name>.dds. (Thin heirs with <_parent> and one
value crashed at truck selection in the fourth test.) The stock trucks on the maps stay stock; the new
trucks are picked in the truck slots at map start or spawned in the Proving
Ground. `--only` with several truck mods builds combined heirs (otc_*).

Load order and shared files
---------------------------
mods/order.json lists the mods from the top of the Config.xml MediaPath list
(highest priority) to the bottom. The game uses the first copy of a file it
finds. When several of our mods change the same file (the truck files are
shared by six mods), the copy in a mod also carries the changes of every mod
BELOW it in that list. "replaces" names alternatives (Hyper Power replaces
Powerful Engines): their changes are not inherited.

Usage:
  python tools/build_mods.py [--game DIR] [--out DIR] [--only a,b,c] [--skip-levels]
"""

import argparse
import fnmatch
import json
import os
import re
import struct
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine_limits  # noqa: E402
import mrxml  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GAME = r"C:\Program Files (x86)\Steam\steamapps\common\MudRunner"
FAMILY = "OpenTrail"


class BuildError(Exception):
    pass


# --------------------------------------------------------------------------- specs

def mods_dir():
    return os.path.join(ROOT, "mods")


def load_spec(name):
    with open(os.path.join(mods_dir(), name, "mod.json"), encoding="utf-8") as fh:
        return json.load(fh)


def load_order_file():
    with open(os.path.join(mods_dir(), "order.json"), encoding="utf-8") as fh:
        return json.load(fh)


def load_order():
    order = load_order_file()["top_to_bottom"]
    present = sorted(n for n in os.listdir(mods_dir())
                     if os.path.isfile(os.path.join(mods_dir(), n, "mod.json")))
    if sorted(order) != present:
        raise BuildError("mods/order.json %s does not match mod folders %s" % (order, present))
    return order


def load_replaces():
    return load_order_file().get("replaces", {})


def zip_name(spec):
    return "%s_%s.zip" % (FAMILY, spec["title"].replace(" & ", "_and_").replace(" ", "_"))


# --------------------------------------------------------------------------- targets

def is_drivable(root):
    return root.tag == "Truck" and bool(root.find("TruckData/Motor/Gear"))


def is_trailer(root):
    return root.tag == "Truck" and not root.find("TruckData/Motor/Gear")


def target_classes(fs, resolver, op):
    kind = op["kind"]
    names = fs.class_names(kind)
    if "names" in op:
        wanted = []
        for pat in op["names"]:
            hit = [n for n in names if fnmatch.fnmatchcase(n, pat)]
            if not hit:
                raise BuildError("no %s class matches %s" % (kind, pat))
            wanted.extend(hit)
        names = sorted(set(wanted))
    only = op.get("only", "all")
    out = []
    for n in names:
        root, _chain = resolver.resolve(kind, n)
        if only == "drivable" and not is_drivable(root):
            continue
        if only == "trailers" and not is_trailer(root):
            continue
        out.append(n)
    if not out:
        raise BuildError("op %r selects no class" % op)
    return out


def iter_path(root, path):
    """Yield (pos, node): pos = ((tag, index among same-tag siblings), ...)."""
    steps = path.split("/")

    def walk(node, i, pos):
        if i == len(steps):
            yield tuple(pos), node
            return
        counts = {}
        for c in node.children:
            k = counts.get(c.tag, 0)
            counts[c.tag] = k + 1
            if c.tag == steps[i]:
                for x in walk(c, i + 1, pos + [(c.tag, k)]):
                    yield x
    for x in walk(root, 0, []):
        yield x


def node_at(root, pos):
    node = root
    for tag, idx in pos:
        kids = [c for c in node.children if c.tag == tag]
        if idx >= len(kids):
            return None
        node = kids[idx]
    return node


def _num(text, what):
    try:
        return float(text)
    except (TypeError, ValueError):
        raise BuildError("%s: %r is not a number" % (what, text))


def desired_values(op, node, where):
    """{attr: new value} for one element, from its stock effective attributes."""
    if "fording" in op:
        cfg = op["fording"]
        lo = mrxml.parse_vec(node.get("SensationMin"))
        hi = mrxml.parse_vec(node.get("SensationMax"))
        top = max(lo[1], hi[1])
        new_lo = [lo[0], top + cfg["lift"], lo[2]]
        new_hi = [hi[0], top + cfg["lift"] + cfg["height"], hi[2]]
        return {"SensationMin": mrxml.fmt_vec(new_lo), "SensationMax": mrxml.fmt_vec(new_hi)}
    attr = op["attr"]
    old = node.get(attr)
    if "set" in op:
        return {attr: op["set"]}
    if "map" in op:
        key = "" if old is None else old
        if key in op["map"]:
            return {attr: op["map"][key]}
        return {}
    if "scale" in op:
        if old is None:
            raise BuildError("%s: %s has no %s to scale" % (where, node.tag, attr))
        v = _num(old, where) * op["scale"]
        if "min" in op:
            v = max(v, op["min"])
        if "max" in op:
            v = min(v, op["max"])
        return {attr: mrxml.fmt_num(v, old)}
    raise BuildError("unknown op %r" % op)


def plan_mod(spec, fs, resolver):
    """Desired effective values of one mod: {(kind, name): [(pos, attr, value)]}.

    Also returns the extra plans for plants (winch sockets) and levels.
    """
    desires = {}
    sockets = []
    levels = []
    for op in spec["ops"]:
        if "levels" in op:
            for pat in op["levels"]:
                hit = [p for p in fs.list("levels/", ".stg") if fnmatch.fnmatchcase(p[7:-4], pat)]
                if not hit:
                    raise BuildError("no level matches %s" % pat)
                levels.extend(hit)
            continue
        if "winch_socket" in op:
            for n in target_classes(fs, resolver, op):
                sockets.append((n, op["winch_socket"]))
            continue
        for n in target_classes(fs, resolver, op):
            root, _chain = resolver.resolve(op["kind"], n)
            hits = list(iter_path(root, op["path"]))
            if not hits:
                raise BuildError("%s %s: no %s" % (op["kind"], n, op["path"]))
            for pos, node in hits:
                for attr, value in desired_values(op, node, "%s/%s" % (n, op["path"])).items():
                    desires.setdefault((op["kind"], n), []).append((pos, attr, value))
    return desires, sockets, sorted(set(levels))


# --------------------------------------------------------------------------- patching

class Patcher(object):
    """Applies desired values to a growing overlay of patched files."""

    def __init__(self, fs, overlay=None):
        self.fs = fs
        self.overlay = dict(overlay or {})
        self.log = []          # (path, attr, old, new, mod id)

    def view(self):
        return mrxml.Layer(self.fs, self.overlay)

    def text(self, path):
        return mrxml.decode(self.view().read(path))

    def put(self, path, text):
        self.overlay[path.lower()] = text.encode("utf-8")

    def _check(self, kind, name, wants):
        root, _chain = mrxml.Resolver(self.view()).resolve(kind, name)
        bad = []
        for pos, attr, value in wants:
            node = node_at(root, pos)
            if node is None:
                raise BuildError("%s %s: element %s vanished" % (kind, name, pos))
            if node.get(attr) != value:
                bad.append((pos, attr, value, node))
        return bad

    def apply(self, desires, mod_id):
        """desires: {(kind, name): [(pos, attr, value)]}. Returns the set of touched paths."""
        touched = set()
        resolver = mrxml.Resolver(self.view())
        depth = {}
        for (kind, name) in desires:
            depth[(kind, name)] = len(resolver.raw(kind, name)[2])
        for key in sorted(desires, key=lambda k: (depth[k], k)):
            kind, name = key
            path = mrxml.KIND_DIRS[kind] + name.lower() + ".xml"
            for stage in ("in_place", "own_node"):
                bad = self._check(kind, name, desires[key])
                if not bad:
                    break
                text = self.text(path)
                edits = {}
                for pos, attr, value, node in bad:
                    src = node.src.get(attr)
                    if stage == "in_place" and src and src[0] == path:
                        a = src[1].attr(attr)
                        span = (a.vstart, a.vend)
                    elif stage == "own_node" and node.own and node.own[0] == path:
                        own = node.own[1]
                        a = own.attr(attr)
                        if a is not None:
                            span = (a.vstart, a.vend)
                        else:
                            e = mrxml.insert_attr_edit(text, own, attr, value)
                            span = ("ins", e[0], attr)
                            if span in edits and edits[span][2] != e[2]:
                                raise BuildError("%s: conflicting inserts" % path)
                            edits[span] = e
                            self.log.append((path, attr, None, value, mod_id))
                            continue
                    else:
                        continue
                    if span in edits and edits[span][2] != value:
                        if stage == "in_place":
                            continue      # a shared template wanted two values: write on own nodes
                        raise BuildError("%s %s: two values for one source" % (path, attr))
                    edits[span] = (span[0], span[1], value)
                    self.log.append((path, attr, text[span[0]:span[1]], value, mod_id))
                if edits:
                    self.put(path, mrxml.apply_edits(text, list(edits.values())))
                    touched.add(path)
            bad = self._check(kind, name, desires[key])
            if bad:
                pos, attr, value, node = bad[0]
                raise BuildError("%s %s: cannot set %s=%s at %s (value comes from %s)"
                                 % (kind, name, attr, value, pos, node.src.get(attr, ("missing",))[0]))
        return touched

    def add_winch_sockets(self, sockets, mod_id):
        touched = set()
        for name, cfg in sockets:
            path = mrxml.KIND_DIRS["plants"] + name.lower() + ".xml"
            root, chain = mrxml.Resolver(self.view()).resolve("plants", name)
            if root.find("GameData/WinchSocket"):
                continue
            text = self.text(path)
            tops = mrxml.parse(text)
            own_root = mrxml.root_of(tops)
            frame = cfg.get("parent_frame")
            line = '<WinchSocket Pos="%s"%s />' % (cfg["pos"], ' ParentFrame="%s"' % frame if frame else "")
            nl = "\r\n" if "\r\n" in text else "\n"
            gd = own_root.find_all("GameData")
            if gd and not gd[-1].self_closing:
                g = gd[-1]
                indent = _indent_of(text, g.start)
                ls = _line_start(text, g.close_start)
                if text[ls:g.close_start].strip():
                    ins = (g.close_start, g.close_start, nl + indent + "\t" + line + nl + indent)
                else:
                    ins = (ls, ls, indent + "\t" + line + nl)
                text = mrxml.apply_edits(text, [ins])
            elif own_root.self_closing:
                raise BuildError("%s: self-closing root" % path)
            else:
                base = _indent_of(text, own_root.start)
                block = "%s\t<GameData>%s%s\t\t%s%s%s\t</GameData>%s" % (base, nl, base, line, nl, base, nl)
                cs = own_root.close_start
                ls = _line_start(text, cs)
                if text[ls:cs].strip():
                    block = nl + block
                    ls = cs
                text = mrxml.apply_edits(text, [(ls, ls, block)])
            self.put(path, text)
            touched.add(path)
            self.log.append((path, "WinchSocket", None, line, mod_id))
            if not mrxml.Resolver(self.view()).resolve("plants", name)[0].find("GameData/WinchSocket"):
                raise BuildError("%s: winch socket not effective" % path)
        return touched


def _line_start(text, pos):
    return text.rfind("\n", 0, pos) + 1


def _indent_of(text, pos):
    ls = _line_start(text, pos)
    return re.match(r"[ \t]*", text[ls:]).group(0)


# --------------------------------------------------------------------------- levels

def read_stg_trucks(head):
    """Parse the truck list at the start of a level .stg.

    Layout (TerrainSTGLoad.cpp in the exe, read order): u32 file version, u32 GUID,
    u32 numTrucks, then per truck: u16 len + type name (zero terminated), 4x4 float
    matrix, u32 numAddons + names, u16 len + trailer name, f32 damage, f32 fuel
    (percent), u8 isLocked. Returns (records, end offset); a record is
    dict(type, trailer, addons, damage, fuel, locked, locked_at).
    """
    def rd_str(o):
        n = struct.unpack_from("<H", head, o)[0]
        if n == 0 or n > 128:
            raise BuildError("unexpected string length %d at %d" % (n, o))
        s = head[o + 2:o + 2 + n]
        if s[-1:] != b"\0":
            raise BuildError("string at %d is not zero terminated" % o)
        return s[:-1].decode("ascii"), o + 2 + n

    version = struct.unpack_from("<I", head, 0)[0]
    if version != 0x0133ED03:
        raise BuildError("unknown .stg version 0x%08x" % version)
    o = 8
    count = struct.unpack_from("<I", head, o)[0]
    o += 4
    if count > 64:
        raise BuildError("implausible truck count %d" % count)
    recs = []
    for _ in range(count):
        typ, o = rd_str(o)
        o += 64
        na = struct.unpack_from("<I", head, o)[0]
        o += 4
        if na > 32:
            raise BuildError("implausible addon count %d" % na)
        adds = []
        for _ in range(na):
            a, o = rd_str(o)
            adds.append(a)
        trailer, o = rd_str(o)
        dmg, fuel = struct.unpack_from("<ff", head, o)
        o += 8
        locked = head[o]
        if locked not in (0, 1):
            raise BuildError("isLocked byte is %d at %d" % (locked, o))
        recs.append(dict(type=typ, trailer=trailer, addons=adds, damage=dmg, fuel=fuel,
                         locked=locked, locked_at=o))
        o += 1
    return recs, o


STG_HEAD = 65536


def unlock_stg_head(head):
    """Return (patched head bytes, records before, number of unlocked trucks)."""
    recs, _end = read_stg_trucks(head)
    buf = bytearray(head)
    n = 0
    for r in recs:
        if r["locked"]:
            buf[r["locked_at"]] = 0
            n += 1
    return bytes(buf), recs, n


# --------------------------------------------------------------------------- building

class Built(object):
    """Result of one mod build."""

    def __init__(self, name, spec):
        self.name = name
        self.spec = spec
        self.files = {}         # archive path -> bytes (class files)
        self.file_mods = {}     # archive path -> [mod names in this file, top first]
        self.heir_parents = {}  # archive path of a new truck class -> stock class it inherits
        self.levels = {}        # archive path -> (patched head, records, unlocked)
        self.log = []
        self.zip_path = None


def build_all(game_dir, out_dir=None, only=None, skip_levels=False, verbose=True, fs=None):
    """Build every mod. Returns {name: Built}.

    only: list of mod names for a custom package; then ONE package is built with
    exactly those mods' changes (no chain), named OpenTrail_Custom.zip.
    """
    fs = fs or mrxml.GameFs(game_dir)
    stock = mrxml.Resolver(fs)
    order = load_order()
    replaces = load_replaces()
    plans = {}
    for name in order:
        plans[name] = plan_mod(load_spec(name), fs, stock)

    heirs = {n for n in order if is_heir_mod(n)}

    def run(chain_names):
        """Apply mods bottom-first. Returns Patcher and the touched set per mod."""
        p = Patcher(fs)
        touched = {}
        for n in chain_names:
            if n in heirs:
                touched[n] = set()
                continue
            desires, sockets, _levels = plans[n]
            t = p.apply(desires, n)
            t |= p.add_winch_sockets(sockets, n)
            touched[n] = t
        return p, touched

    result = {}
    if only:
        for n in only:
            if n not in order:
                raise BuildError("unknown mod %s" % n)
        names = [n for n in reversed(order) if n in only]
        if "hyper_power" in names and "powerful_engines" in names:
            raise BuildError("hyper_power and powerful_engines are alternatives: pick one")
        p, touched = run(names)
        b = Built("custom", {"id": "custom", "title": "Custom", "version": load_spec(names[0])["version"]})
        files = set().union(*touched.values())
        for path in sorted(files):
            b.files[path] = p.overlay[path]
            b.file_mods[path] = [n for n in reversed(names) if path in touched[n]]
        b.log = p.log
        chosen_heirs = [n for n in names if n in heirs]
        if chosen_heirs:
            combo = {"id": "custom", "workshop_prefix": "otc", "ops": []}
            for n in chosen_heirs:
                combo["ops"].extend(load_spec(n)["ops"])
            hf, hp = heir_package(combo, fs, stock)
            b.files.update(hf)
            b.heir_parents.update(hp)
        bad = limit_violations(fs, b.files)
        if bad:
            raise BuildError("custom: value outside the game's limits: %s" % (bad[0],))
        levels = sorted(set(l for n in names for l in plans[n][2]))
        _levels(b, fs, levels, skip_levels)
        if out_dir:
            b.zip_path = os.path.join(out_dir, "%s_Custom.zip" % FAMILY)
            write_package(b, fs, b.zip_path)
        return {"custom": b}

    for i, name in enumerate(order):
        spec = load_spec(name)
        lower = [n for n in reversed(order[i + 1:]) if n not in replaces.get(name, []) and n not in heirs]
        b = Built(name, spec)
        if name in heirs:
            b.files, b.heir_parents = heir_package(spec, fs, stock)
        else:
            p, touched = run(lower + [name])
            for path in sorted(touched[name]):
                b.files[path] = p.overlay[path]
                b.file_mods[path] = [n for n in reversed(lower + [name]) if path in touched[n]]
            b.log = [x for x in p.log if x[0] in touched[name]]
        if stock_truck_replacements(fs, b.files):
            raise BuildError("%s replaces stock truck files (crashes the game): %s"
                             % (name, stock_truck_replacements(fs, b.files)[:3]))
        _levels(b, fs, plans[name][2], skip_levels)
        if not b.files and not plans[name][2]:
            raise BuildError("%s changes nothing" % name)
        bad = limit_violations(fs, b.files)
        if bad:
            raise BuildError("%s: value outside the game's limits: %s" % (name, bad[0]))
        result[name] = b
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
            b.zip_path = os.path.join(out_dir, zip_name(spec))
            write_package(b, fs, b.zip_path, skip_levels)
        if verbose:
            print("== %s: %d class files%s, %d levels%s" % (spec["title"],
                                                            sum(1 for p in b.files if p.endswith(".xml")),
                                                            " (new heir trucks)" if b.heir_parents else "", len(b.levels),
                                                          (" -> " + b.zip_path) if b.zip_path else ""))
            summarize(b)
    return result


def is_heir_mod(name):
    return bool(load_spec(name).get("as_heirs"))


def heir_package(spec, fs, stock):
    """{path: bytes} of new trucks for one heir mod (base game and DLC, local use): full
    copies of the stock truck files under new names plus their selection icons."""
    import build_workshop
    variants = build_workshop.plan_variants(spec["id"], spec, fs, stock, include_dlc=True)
    build_workshop.verify_variants(spec["id"], spec, variants, fs, stock)
    files, parents = {}, {}
    for (kind, new), (xml, parent) in sorted(variants.items()):
        path = mrxml.KIND_DIRS[kind] + new + ".xml"
        files[path] = xml.encode("utf-8")
        parents[path] = parent
    files.update(build_workshop.billboard_copies(variants, fs))
    return files, parents


def stock_truck_replacements(fs, files):
    """Paths in a package that replace a stock truck class file (the crash cause)."""
    return sorted(p for p in files if p.startswith(mrxml.KIND_DIRS["trucks"]) and fs.exists(p))


def limit_violations(fs, files):
    """Effective values outside the exe's limits, for every truck and wheel class
    over the package `files` (stock classes and new ones): [(kind, class, tag, attr, value, (lo, hi))]."""
    r = mrxml.Resolver(mrxml.Layer(fs, files))
    out = []
    for kind in ("trucks", "wheels"):
        names = set(fs.class_names(kind))
        d = mrxml.KIND_DIRS[kind]
        names |= {p[len(d):-4] for p in files if p.startswith(d) and p.endswith(".xml")}
        for n in sorted(names):
            root, _chain = r.resolve(kind, n)
            stack = [root]
            while stack:
                node = stack.pop()
                for attr, val, rng in engine_limits.violations(node.tag, node.attrs):
                    out.append((kind, n, node.tag, attr, val, rng))
                stack.extend(node.children)
    return out


def _levels(b, fs, levels, skip_levels):
    for path in levels:
        with fs.open(path) as fh:
            head = fh.read(STG_HEAD)
        patched, recs, n = unlock_stg_head(head)
        if n:                      # levels without locked trucks are not shipped
            b.levels[path] = (patched, recs, n)


def write_package(b, fs, out_path, skip_levels=False):
    """Zip with the changed files at their Media paths, deflated, no directory entries.

    The game reads zips with PhysFS 2.0: no Zip64, and every local header must match
    the central directory (tools/zipcheck.py). Level files are streamed, so the entry
    size is given up front: then Python writes a plain 2.0 header and patches the real
    sizes into it after the data. (1.0.0 used force_zip64=True here, which wrote
    Zip64 local headers and made the six level files unreadable in game.)"""
    tmp = out_path + ".part"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(b.files):
            zi = zipfile.ZipInfo(path, date_time=(2026, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, b.files[path])
        if not skip_levels:
            for path in sorted(b.levels):
                patched_head = b.levels[path][0]
                zi = zipfile.ZipInfo(path, date_time=(2026, 1, 1, 0, 0, 0))
                zi.compress_type = zipfile.ZIP_DEFLATED
                zi.file_size = fs.size(path)
                if zi.file_size >= zipfile.ZIP64_LIMIT:
                    raise BuildError("%s is too big for a zip without Zip64" % path)
                with fs.open(path) as src, z.open(zi, "w") as dst:
                    src.read(len(patched_head))
                    dst.write(patched_head)
                    while True:
                        chunk = src.read(1 << 22)
                        if not chunk:
                            break
                        dst.write(chunk)
    import zipcheck
    bad = zipcheck.problems(tmp)
    if bad:
        raise BuildError("%s cannot be read by the game: %s" % (out_path, "; ".join(bad[:5])))
    os.replace(tmp, out_path)


def summarize(b):
    rows = {}
    for path, attr, old, new, owner in b.log:
        folder = path.rsplit("/", 1)[0]
        rows.setdefault((folder, attr, owner), []).append((old, new))
    for (folder, attr, owner), vals in sorted(rows.items()):
        olds = sorted({str(o) for o, _ in vals})
        news = sorted({str(n) for _, n in vals})
        o = olds[0] if len(olds) == 1 else "%d values" % len(olds)
        n = news[0] if len(news) == 1 else "%d values" % len(news)
        print("   %-16s %-16s %-14s -> %-16s x%-4d %s" % (folder, attr, o[:14], n[:16], len(vals), owner))
    for path, (_h, recs, n) in sorted(b.levels.items()):
        print("   %-34s trucks %2d, unlocked %d" % (path, len(recs), n))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default=DEFAULT_GAME)
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "local"))
    ap.add_argument("--only", help="comma separated mod names: one custom package with exactly these")
    ap.add_argument("--skip-levels", action="store_true", help="do not write the big level files")
    a = ap.parse_args()
    if os.path.isdir(a.out) and os.listdir(a.out):
        to_recycle_bin(a.out)
    os.makedirs(a.out, exist_ok=True)
    only = [x.strip() for x in a.only.split(",")] if a.only else None
    build_all(a.game, a.out, only=only, skip_levels=a.skip_levels)
    return 0


def to_recycle_bin(path):
    """Move a file or folder to the Windows Recycle Bin (never a permanent delete)."""
    import subprocess
    full = os.path.abspath(path).replace("'", "''")
    method = "DeleteDirectory" if os.path.isdir(path) else "DeleteFile"
    ps = ("Add-Type -AssemblyName Microsoft.VisualBasic; "
          "[Microsoft.VisualBasic.FileIO.FileSystem]::%s('%s', 'OnlyErrorDialogs', 'SendToRecycleBin')"
          % (method, full))
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], check=True, timeout=120)
    if os.path.exists(path):
        raise RuntimeError("could not move %s to the Recycle Bin" % path)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (BuildError, mrxml.XmlError) as e:
        print("BUILD FAILED:", e)
        sys.exit(2)
