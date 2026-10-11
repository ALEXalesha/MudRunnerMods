"""Prepare Steam Workshop folders for the MudRunner Editor (nothing is uploaded).

  .venv\\Scripts\\python tools\\build_workshop.py [--out workshop] [--release release]

Why the Workshop versions differ from the local packages
--------------------------------------------------------
MudRunner mods reach the Workshop only through the MudRunner Editor. On
"Publish" the Editor converts, RENAMES and zips the mod files (official modding
guide, step 7: "those files would be automatically converted to game-friendly
formats, renamed and packed"). A published file therefore never has the name of
a stock file and cannot replace it. Downloaded Workshop items confirm this: every
file is named after the item id (classes/trucks/1v37v3em.xml) and stock files are
only referenced (<_parent File="load_logs_short" />).

So a Workshop version adds NEW trucks: full standalone copies of the stock
trucks (the stock class resolved and written out, no <_parent>, the format of
every Workshop truck on this PC) under new names (otf_kamaz4310) with only the
changed values, each with the stock selection icon billboards/trucks/<new>.dds
and a friendly name in strings.xml (<ModStrings>). Players pick them in the
truck slots at map start or spawn them in the Proving Ground. Grippy Wheels also
adds wheel copies. Only base-game trucks get variants: a variant of a DLC truck has
a different file name, and the game checks DLC ownership by asset name (the exe
holds a list "usa level_dlc3_01,...,ford_f150,..."), so a variant could hand out
paid DLC trucks to players without the DLC. The local packages (build_mods.py) use
the same copies, DLC trucks included (the player owns the DLC there), and name the
trucks through strings/<language>/opentrail_<mod>.txt (name_files below).

Winch Anchors (plant classes) and Unlocked Trucks (level files) change stock
files only, so they have no Workshop version.

Layout per mod:
  workshop/NN_OpenTrail_<Name>/
      mod/                    copy the CONTENTS into <Editor>/Media/_mods/<mod id>/
          strings.xml         friendly names (<ModStrings>, English: mod
                              localization is not supported, guide step 7)
          classes/trucks/...  full truck copies
          classes/wheels/...  wheel copies (Grippy Wheels)
          billboards/trucks/  selection icons of the new trucks (.dds)
          preview.png         512x512, under 1 MB
      steam_page.txt          what to type into the Publish dialog (CRLF)
      steam_description.txt   only the description, to copy whole (CRLF)
"""

import argparse
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_mods  # noqa: E402
import mrxml  # noqa: E402

ROOT = build_mods.ROOT
FAMILY = build_mods.FAMILY
NAME_RE = re.compile(r"^[a-z0-9_]{1,48}$")


class WorkshopError(Exception):
    pass


# --------------------------------------------------------------------------- names

def stock_names(fs, lang="en"):
    """Display names from strings/<lang>/assets.txt (UTF-16, '/key' then value)."""
    raw = fs.read("strings/%s/assets.txt" % lang)
    text = raw.decode("utf-16")
    names = {}
    key = None
    for line in text.replace("\r", "").split("\n"):
        if line.startswith("/"):
            key = line[1:].strip().lower()
        elif key and line.strip():
            names.setdefault(key, line.strip())
            key = None
    return names


def languages(fs):
    """The language folders of the game: strings/<lang>/assets.txt (en, ru, fr, ...)."""
    return sorted(p.split("/")[1] for p in fs.files if p.startswith("strings/") and p.endswith("/assets.txt")
                  and p.count("/") == 2)


# --------------------------------------------------------------------------- child files

def raw_steps(root, pos):
    """Expanded position -> [(tag, raw index)] for writing an inheriting child."""
    node = root
    out = []
    for tag, idx in pos:
        kids = [c for c in node.children if c.tag == tag]
        node = kids[idx]
        if node.raw_index is None:
            raise WorkshopError("element %s comes from a template; cannot override by position" % (pos,))
        out.append((tag, node.raw_index))
    return out


def child_xml(parent, root_tag, changes):
    """changes: [([(tag, raw index)], attr, value)]. Returns child class XML text.

    Child nodes match parent nodes by position among same-tag siblings, so a
    change at index 3 needs three empty placeholders of that tag before it.
    """
    tree = {}
    for steps, attr, value in changes:
        cur = tree
        for st in steps:
            cur = cur.setdefault(st, {"@": {}, "kids": {}})
            last = cur
            cur = cur["kids"]
        last["@"][attr] = value

    def emit(kids, depth):
        lines = []
        by_tag = {}
        order = []
        for (tag, idx) in kids:
            if tag not in by_tag:
                order.append(tag)
            by_tag.setdefault(tag, {})[idx] = kids[(tag, idx)]
        for tag in order:
            top = max(by_tag[tag])
            for i in range(top + 1):
                ind = "\t" * depth
                node = by_tag[tag].get(i)
                if node is None:
                    lines.append("%s<%s />" % (ind, tag))
                    continue
                attrs = "".join(' %s="%s"' % (k, v) for k, v in sorted(node["@"].items()))
                if node["kids"]:
                    lines.append("%s<%s%s>" % (ind, tag, attrs))
                    lines.extend(emit(node["kids"], depth + 1))
                    lines.append("%s</%s>" % (ind, tag))
                else:
                    lines.append("%s<%s%s />" % (ind, tag, attrs))
        return lines

    body = emit(tree, 1)
    return '<_parent File="%s" />\n<%s>\n%s\n</%s>\n' % (parent, root_tag, "\n".join(body), root_tag)


def base_game(fs, kind, name):
    return fs.source(mrxml.KIND_DIRS[kind] + name + ".xml") == "Media.zip"


def make_copies(desires, prefix, fs):
    """Standalone copies of stock classes under new names, with the wanted values.

    desires: {(kind, cls): [(pos, attr, value)]}. Each copy is the stock class
    RESOLVED (inheritance and templates applied) and written out in full, with no
    <_parent> and no _template: the format of every Workshop truck on this PC (the
    Editor flattens on publish; only load addons keep a <_parent>). Thin heirs
    (<_parent File="kamaz4310"/> + one value) are not used for trucks.
    Returns {(kind, new): (xml text, cls)}."""
    stock = mrxml.Resolver(fs)
    out = {}
    for (kind, cls), wants in sorted(desires.items()):
        new = "%s_%s" % (prefix, cls)
        if not NAME_RE.match(new):
            raise WorkshopError("bad file name %s" % new)
        root = mrxml.copy_tree(stock.resolve(kind, cls)[0])
        for pos, attr, value in wants:
            node = build_mods.node_at(root, pos)
            if node is None:
                raise WorkshopError("%s %s: no element at %s" % (kind, cls, pos))
            node.attrs[attr] = value
        out[(kind, new)] = (mrxml.serialize(root), cls)
    return out


def plan_variants(name, spec, fs, stock, include_dlc=False):
    """{(kind, new name): (xml text, stock class)} for one mod: full copies."""
    prefix = spec["workshop_prefix"]
    desires, sockets, levels = build_mods.plan_mod(spec, fs, stock)
    if sockets or levels:
        raise WorkshopError("%s has no Workshop version" % name)
    picked = {k: v for k, v in desires.items() if include_dlc or base_game(fs, k[0], k[1])}
    out = make_copies(picked, prefix, fs)
    wheel_map = {cls: new for (kind, new), (_x, cls) in out.items() if kind == "wheels"}
    if wheel_map:
        # trucks that use the new wheels: every wheel of every drivable truck
        truck_desires = {}
        for cls in fs.class_names("trucks"):
            if not include_dlc and not base_game(fs, "trucks", cls):
                continue
            root, _chain = stock.resolve("trucks", cls)
            if not build_mods.is_drivable(root):
                continue
            wants = []
            for pos, node in build_mods.iter_path(root, "Wheels/Wheel"):
                t = node.get("Type")
                if t not in wheel_map:
                    raise WorkshopError("%s wheel type %s has no grippy variant" % (cls, t))
                wants.append((pos, "Type", wheel_map[t]))
            truck_desires[("trucks", cls)] = wants
        out.update(make_copies(truck_desires, prefix, fs))
    return out


def billboard_copies(variants, fs):
    """{path: bytes}: the truck-selection icon billboards/trucks/<truck>.dds for every
    new truck, copied from its stock truck (every drivable stock truck has one; the
    truck selection screen loads it by the truck's file name)."""
    out = {}
    for (kind, new), (_xml, cls) in variants.items():
        if kind != "trucks":
            continue
        src = "billboards/trucks/%s.dds" % cls
        if not fs.exists(src):
            raise WorkshopError("no %s for the new truck %s" % (src, new))
        out["billboards/trucks/%s.dds" % new] = fs.read(src)
    return out


def verify_variants(name, spec, variants, fs, stock):
    """Resolve every variant over the stock files: the planned values must hold and
    nothing else may differ from the stock class. Returns the number checked."""
    overlay = {mrxml.KIND_DIRS[k] + n + ".xml": x.encode("utf-8") for (k, n), (x, _p) in variants.items()}
    res = mrxml.Resolver(mrxml.Layer(fs, overlay))
    desires, _s, _l = build_mods.plan_mod(spec, fs, stock)
    prefix = spec["workshop_prefix"]
    n = 0
    for (kind, new), (_xml, parent) in variants.items():
        got, _chain = res.resolve(kind, new)
        want, _c2 = stock.resolve(kind, parent)
        expected = {}
        for pos, attr, value in desires.get((kind, parent), []):
            expected[(pos, attr)] = value
        if kind == "trucks" and spec["id"] == "grippy_wheels":
            for pos, node in build_mods.iter_path(want, "Wheels/Wheel"):
                expected[(pos, "Type")] = "%s_%s" % (prefix, node.get("Type"))
        _compare(got, want, (), expected, "%s %s" % (name, new))
        n += 1
    return n


def _compare(got, want, pos, expected, where):
    keys = (set(got.attrs) | set(want.attrs)) - set(mrxml.CONTROL_ATTRS)   # merge directives only
    for k in keys:
        if (pos, k) in expected:
            if got.attrs.get(k) != expected[(pos, k)]:
                raise WorkshopError("%s: %s %s=%r, expected %r" % (where, pos, k, got.attrs.get(k), expected[(pos, k)]))
        elif got.attrs.get(k) != want.attrs.get(k):
            raise WorkshopError("%s: %s %s changed %r -> %r" % (where, pos, k, want.attrs.get(k), got.attrs.get(k)))
    if [c.tag for c in got.children] != [c.tag for c in want.children]:
        raise WorkshopError("%s: children differ at %s" % (where, pos))
    counts = {}
    for g, w in zip(got.children, want.children):
        i = counts.get(g.tag, 0)
        counts[g.tag] = i + 1
        _compare(g, w, pos + ((g.tag, i),), expected, where)


# --------------------------------------------------------------------------- texts

def order_lines(order, lang):
    replaces = build_mods.load_replaces()
    out = []
    for i, n in enumerate(order):
        spec = build_mods.load_spec(n)
        line = "%d. %s" % (i + 1, spec["title"])
        if any(n in v for v in replaces.values()):
            line += " (off when Hyper Power is on)" if lang == "en" else " (выключить, если включён Hyper Power)"
        out.append(line)
    return out


def description(spec, n_trucks, n_wheels):
    w = spec["workshop"]
    en = ["[b]%s %s[/b]" % (FAMILY, spec["title"]), ""] + w["en"] + [
        "",
        "This Workshop version adds %d new trucks%s: copies of the base-game trucks with the change, named "
        "\"<truck> (%s)\". Pick them in the truck slots when you start a map, or spawn them in the Proving Ground. "
        "The trucks placed on the maps stay stock." % (
            n_trucks, (" and %d wheel types" % n_wheels) if n_wheels else "", spec["workshop_suffix"]),
        "DLC trucks are not included (they need the DLC). The local version on the project page adds the same "
        "copies of the DLC trucks too (manual install, for players who own the DLC).",
        "",
        "Single player. Not affiliated with Saber Interactive or Focus Entertainment.",
    ]
    ru = ["", "-----", "[b]%s %s[/b]" % (FAMILY, spec["title"]), ""] + w["ru"] + [
        "",
        "Эта версия для Мастерской добавляет %d новых грузовиков%s: копии грузовиков базовой игры с изменением, "
        "с именем \"<грузовик> (%s)\". Их выбирают в слотах грузовиков при старте карты или вызывают на полигоне "
        "(Proving Ground). Грузовики, стоящие на картах, остаются обычными." % (
            n_trucks, (" и %d типов колёс" % n_wheels) if n_wheels else "", spec["workshop_suffix"]),
        "Грузовиков из DLC здесь нет (для них нужно DLC). Локальная версия на странице проекта добавляет такие же "
        "копии и грузовиков из DLC (установка вручную, для тех, у кого DLC есть).",
        "",
        "Одиночная игра. Не связано с Saber Interactive и Focus Entertainment.",
    ]
    return "\n".join(en + ru) + "\n"


def steam_page(spec, desc):
    return (
        "MudRunner Editor -> File View -> right click _mods -> Create new mod, then copy the CONTENTS of the\n"
        "folder 'mod' into the new folder Media\\_mods\\<mod id>\\ and right click the mod -> Publish.\n\n"
        "TITLE:\n%s %s\n\n"
        "VISIBILITY: Private for the first test, then Public\n"
        "PREVIEW: keep mod\\preview.png (or press Autogenerate)\n"
        "CHANGE NOTE: Version %s\n\n"
        "DESCRIPTION (paste):\n%s"
    ) % (FAMILY, spec["title"], spec["version"], desc)


def display_name(parent, names, stock, kind):
    """The game's English name; a class without its own string borrows the name of
    the class it inherits (zaz968m_blue -> "A-968m blue")."""
    if parent in names:
        return names[parent]
    for path in stock.raw(kind, parent)[2][1:]:
        anc = path.rsplit("/", 1)[1][:-4]
        if anc in names:
            rest = parent[len(anc):].strip("_").replace("_", " ") if parent.startswith(anc) else ""
            return (names[anc] + " " + rest).strip()
    return parent.replace("_", " ")


def variant_names(variants, names, suffix, stock, fallback=None):
    """{new class: "<stock display name> (<suffix>)"} for every variant; a name the
    language lacks comes from `fallback` (English)."""
    out = {}
    for (kind, new), (_xml, parent) in sorted(variants.items()):
        base = display_name(parent, names, stock, kind)
        if fallback is not None and base == parent.replace("_", " "):
            base = display_name(parent, fallback, stock, kind)
        out[new] = "%s (%s)" % (base, suffix)
    return out


def strings_xml(variants, names, suffix, stock):
    lines = ["<ModStrings>"]
    for new, value in sorted(variant_names(variants, names, suffix, stock).items()):
        lines.append('\t<String Id="%s" Value="%s" />' % (new, _xml_escape(value)))
    lines.append("</ModStrings>")
    return "\n".join(lines) + "\n"


def strings_txt(entries):
    """A game strings file: UTF-16 LE with BOM, CRLF, '/key' line, value line, blank line
    (the format of strings/en/assets.txt)."""
    blocks = ["/%s\r\n%s\r\n" % (k, v.replace("\r", " ").replace("\n", " ")) for k, v in sorted(entries.items())]
    return b"\xff\xfe" + "\r\n".join(blocks).encode("utf-16-le")


def name_files(variants, fs, stock, suffix_en, suffix_ru, file_id):
    """{path: bytes}: names of the new classes for the local packages.

    The game reads <ModStrings> only from a Steam Workshop item (the exe opens
    "%llx.xml", the item id). For a package mounted through Config.xml the names go
    into a NEW strings file per language, strings/<lang>/opentrail_<file_id>.txt:
    the game enumerates strings/<lang>/*.txt (china.txt exists only in two
    languages and its name is not in the exe), so the file is read and no stock
    strings file is replaced. Every language folder gets one, Russian with a
    Russian suffix, the others with the English one."""
    en = stock_names(fs, "en")
    out = {}
    for lang in languages(fs):
        names = stock_names(fs, lang)
        suffix = suffix_ru if lang == "ru" and suffix_ru else suffix_en
        entries = variant_names(variants, names, suffix, stock, fallback=en)
        out["strings/%s/opentrail_%s.txt" % (lang, file_id)] = strings_txt(entries)
    return out


def _xml_escape(s):
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


# --------------------------------------------------------------------------- images

def draw_preview(spec, out_path, size=(512, 512)):
    from PIL import Image, ImageDraw, ImageFont
    bold = r"C:\Windows\Fonts\segoeuib.ttf"
    reg = r"C:\Windows\Fonts\segoeui.ttf"
    w = spec["workshop"]
    bg = tuple(w["bg"])
    accent = tuple(w["accent"])
    W, H = size
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    for y in range(H):
        k = 1.0 - 0.5 * y / H
        d.line([(0, y), (W, y)], fill=tuple(int(c * k) for c in bg))
    # muddy track: two wheel ruts in perspective
    top = int(H * 0.62)
    d.polygon([(W * 0.40, top), (W * 0.60, top), (W * 0.98, H), (W * 0.02, H)], fill=(58, 44, 30))
    for side in (-1, 1):
        d.polygon([(W / 2 + side * W * 0.04, top), (W / 2 + side * W * 0.06, top),
                   (W / 2 + side * W * 0.30, H), (W / 2 + side * W * 0.20, H)], fill=(36, 27, 18))

    def fit(text, path, max_w, start):
        s = start
        while s > 10:
            f = ImageFont.truetype(path, s)
            if d.textlength(text, font=f) <= max_w:
                return f
            s -= 1
        return ImageFont.truetype(path, 10)

    d.rectangle([0, 0, W - 1, H - 1], outline=accent, width=8)
    d.text((28, 22), FAMILY.upper(), font=ImageFont.truetype(bold, 34), fill=(255, 255, 255))
    y = 90
    for word in w["short"].split("\n"):
        f = fit(word, bold, W - 60, 96)
        d.text(((W - d.textlength(word, font=f)) / 2, y), word, font=f, fill=accent)
        y += f.size + 6
    for line in (w["tag_en"], w["tag_ru"]):
        f = fit(line, reg, W - 70, 30)
        d.text(((W - d.textlength(line, font=f)) / 2, y + 10), line, font=f, fill=(255, 255, 255))
        y += f.size + 10
    img.save(out_path, "PNG", optimize=True)


# --------------------------------------------------------------------------- build

def workshop_mods(order):
    return [n for n in order if "workshop_prefix" in build_mods.load_spec(n)]


def folder_name(i, spec):
    return "%02d_%s_%s" % (i + 1, FAMILY, spec["title"].replace(" ", "_"))


def build(out_dir, game=build_mods.DEFAULT_GAME, verbose=True):
    fs = mrxml.GameFs(game)
    stock = mrxml.Resolver(fs)
    names = stock_names(fs)
    order = build_mods.load_order()
    if os.path.isdir(out_dir) and os.listdir(out_dir):
        build_mods.to_recycle_bin(out_dir)          # never a permanent delete
    os.makedirs(out_dir, exist_ok=True)
    folders = []
    for i, name in enumerate(workshop_mods(order)):
        spec = build_mods.load_spec(name)
        variants = plan_variants(name, spec, fs, stock)
        verify_variants(name, spec, variants, fs, stock)
        base = os.path.join(out_dir, folder_name(i, spec))
        mod = os.path.join(base, "mod")
        for (kind, new), (xml, _parent) in variants.items():
            dst = os.path.join(mod, "classes", kind, new + ".xml")
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(xml)
        for path, data in billboard_copies(variants, fs).items():
            dst = os.path.join(mod, *path.split("/"))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as fh:
                fh.write(data)
        with open(os.path.join(mod, "strings.xml"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(strings_xml(variants, names, spec["workshop_suffix"], stock))
        draw_preview(spec, os.path.join(mod, "preview.png"))
        n_trucks = sum(1 for (k, _n) in variants if k == "trucks")
        n_wheels = sum(1 for (k, _n) in variants if k == "wheels")
        desc = description(spec, n_trucks, n_wheels)
        # Copy-paste files use CRLF: the Publish dialog is a Windows edit box and glues
        # lines joined by a bare LF into one paragraph (the lesson from the SCS uploader).
        with open(os.path.join(base, "steam_page.txt"), "w", encoding="utf-8", newline="\r\n") as fh:
            fh.write(steam_page(spec, desc))
        with open(os.path.join(base, "steam_description.txt"), "w", encoding="utf-8", newline="\r\n") as fh:
            fh.write(desc)
        folders.append(base)
        if verbose:
            print("%s: %d trucks, %d wheels" % (base, n_trucks, n_wheels))
    return folders


def release_assets(folders, local_dir, out_dir):
    """Copies of the local packages plus one zip of all Workshop folders."""
    import shutil
    os.makedirs(out_dir, exist_ok=True)
    assets = []
    for f in sorted(os.listdir(local_dir)):
        if f.startswith("opentrail_") and f.endswith(".zip"):          # not the otprobe_ zips
            dst = os.path.join(out_dir, f)
            shutil.copyfile(os.path.join(local_dir, f), dst)
            assets.append(dst)
    allzip = os.path.join(out_dir, "%s_Workshop_Folders.zip" % FAMILY)
    with zipfile.ZipFile(allzip, "w", zipfile.ZIP_DEFLATED) as z:
        for base in folders:
            for dp, _dn, fn in os.walk(base):
                for f in sorted(fn):
                    full = os.path.join(dp, f)
                    z.write(full, os.path.relpath(full, os.path.dirname(base)).replace("\\", "/"))
    assets.append(allzip)
    return assets


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default=build_mods.DEFAULT_GAME)
    ap.add_argument("--out", default=os.path.join(ROOT, "workshop"))
    ap.add_argument("--local", default=os.path.join(ROOT, "build", "local"),
                    help="folder with the local packages (tools/build_mods.py)")
    ap.add_argument("--release", default=os.path.join(ROOT, "release"))
    a = ap.parse_args()
    folders = build(a.out, a.game)
    if os.path.isdir(a.local):
        if os.path.isdir(a.release) and os.listdir(a.release):
            build_mods.to_recycle_bin(a.release)
        for f in release_assets(folders, a.local, a.release):
            print("asset:", f)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (WorkshopError, build_mods.BuildError, mrxml.XmlError) as e:
        print("WORKSHOP BUILD FAILED:", e)
        sys.exit(2)
