"""MudRunner class XML: a tolerant parser, the inheritance resolver and text patching.

Why not xml.etree: stock class files are not strict XML. A file has several
top-level elements (<_templates>, <_parent>, <Truck>), and a few repeat an
attribute (zil_cistern.xml: ImpactType twice, ford_f150.xml: IsLight twice).
The game reads them anyway, so this module does too.

The parser keeps the byte offsets of every attribute value and of the end of
every start tag. Patches are applied as text edits at those offsets, so a
patched file differs from the stock one only in the changed values.

Resolution follows the official modding guide (Appendix C, "General information
on XML inheritance"):
  - <_parent File="x"/>: the file inherits x.xml of the same class folder; nodes
    and attributes of the child are merged on top. Child nodes match parent
    nodes by position among siblings with the same tag.
  - _inheritRemove="true" on a child node removes the matching parent node.
  - _noinherit="true" on a child node: nothing is copied from the parent node.
  - _template="Name" on a node copies attributes and child nodes from
    <_templates><Tag><Name .../></Tag></_templates> (the node's own attributes
    win). <_templates Include="trucks"/> adds Media/_templates/trucks.xml.
Inheritance is merged first, templates are expanded after that.
"""

import io
import os
import re
import zipfile

ROOT_TAGS = ("Truck", "TruckAddon", "TruckWheel", "PlantBrand")
KIND_DIRS = {"trucks": "classes/trucks/", "wheels": "classes/wheels/", "plants": "classes/plants/"}


class XmlError(Exception):
    pass


# --------------------------------------------------------------------------- parser

class Attr(object):
    __slots__ = ("name", "value", "vstart", "vend")

    def __init__(self, name, value, vstart, vend):
        self.name, self.value, self.vstart, self.vend = name, value, vstart, vend


class Node(object):
    """A parsed element with source offsets."""

    def __init__(self, tag, start):
        self.tag = tag
        self.start = start          # offset of '<'
        self.head_end = None        # offset of '>' or '/>' that closes the start tag
        self.self_closing = False
        self.end = None             # offset just past the element
        self.close_start = None     # offset of '</tag>' (None if self-closing)
        self.attrs = []             # [Attr], duplicates kept in source order
        self.children = []
        self.parent = None

    def get(self, name, default=None):
        val = default
        for a in self.attrs:            # the last duplicate wins
            if a.name == name:
                val = a.value
        return val

    def attr(self, name):
        found = None
        for a in self.attrs:
            if a.name == name:
                found = a
        return found

    def adict(self):
        d = {}
        for a in self.attrs:
            d[a.name] = a.value
        return d

    def find_all(self, tag):
        return [c for c in self.children if c.tag == tag]

    def __repr__(self):
        return "<Node %s %r>" % (self.tag, self.adict())


TAG_NAME = re.compile(r"[A-Za-z_][\w.:-]*")
ATTR_RE = re.compile(r"\s*([A-Za-z_:][\w.:-]*)\s*=\s*(\"([^\"]*)\"|'([^']*)')")


def parse(text):
    """Parse class XML text. Returns the list of top-level Nodes.

    Raises XmlError on unbalanced tags or broken attribute syntax: the checks the
    tests run on every patched file.
    """
    if isinstance(text, bytes):
        text = decode(text)
    tops, stack = [], []
    i, n = 0, len(text)
    while True:
        j = text.find("<", i)
        if j < 0:
            break
        if text.startswith("<!--", j):
            k = text.find("-->", j + 4)
            if k < 0:
                raise XmlError("unclosed comment at %d" % j)
            i = k + 3
            continue
        if text.startswith("<?", j):
            k = text.find("?>", j + 2)
            if k < 0:
                raise XmlError("unclosed declaration at %d" % j)
            i = k + 2
            continue
        if text.startswith("<![CDATA[", j):
            k = text.find("]]>", j)
            if k < 0:
                raise XmlError("unclosed CDATA at %d" % j)
            i = k + 3
            continue
        if text.startswith("</", j):
            m = TAG_NAME.match(text, j + 2)
            if not m:
                raise XmlError("bad end tag at %d" % j)
            k = text.find(">", m.end())
            if k < 0 or text[m.end():k].strip():
                raise XmlError("bad end tag at %d" % j)
            if not stack or stack[-1].tag != m.group(0):
                raise XmlError("end tag </%s> at %d does not match <%s>"
                               % (m.group(0), j, stack[-1].tag if stack else "-"))
            node = stack.pop()
            node.close_start = j
            node.end = k + 1
            i = k + 1
            continue
        m = TAG_NAME.match(text, j + 1)
        if not m:
            raise XmlError("bad '<' at %d" % j)
        node = Node(m.group(0), j)
        p = m.end()
        while True:
            am = ATTR_RE.match(text, p)
            if am:
                quoted = 3 if am.group(3) is not None else 4
                node.attrs.append(Attr(am.group(1), am.group(quoted), am.start(quoted), am.end(quoted)))
                p = am.end()
                continue
            ws = re.compile(r"\s*").match(text, p).end()
            if text.startswith("/>", ws):
                node.head_end = ws
                node.self_closing = True
                node.end = ws + 2
                break
            if text.startswith(">", ws):
                node.head_end = ws
                break
            raise XmlError("bad attribute syntax in <%s> at %d: %r" % (node.tag, ws, text[ws:ws + 30]))
        if stack:
            node.parent = stack[-1]
            stack[-1].children.append(node)
        else:
            tops.append(node)
        if node.self_closing:
            i = node.end
        else:
            stack.append(node)
            i = node.head_end + 1
    if stack:
        raise XmlError("unclosed <%s> at %d" % (stack[-1].tag, stack[-1].start))
    return tops


def decode(data):
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    return data.decode("utf-8")


def root_of(tops):
    roots = [t for t in tops if t.tag in ROOT_TAGS]
    if len(roots) != 1:
        raise XmlError("expected one root element, got %s" % [t.tag for t in tops])
    return roots[0]


def parent_name(tops):
    for t in tops:
        if t.tag == "_parent":
            return t.get("File")
    return None


# --------------------------------------------------------------------------- game files

class GameFs(object):
    """Media.zip plus the DLC archives, read only. Paths are lower case.

    `overlay` maps a path to replacement bytes (patched files) without touching
    the archives.
    """

    ARCHIVES = ["Media.zip", "_dlc_valley.zip", "_dlc_ridge.zip", "_dlc_usa.zip", "_dlc_oldtimers.zip"]

    def __init__(self, game_dir, archives=None):
        self.game_dir = game_dir
        self.files = {}          # path -> (archive name, ZipInfo)
        self.zips = {}
        for name in archives or self.ARCHIVES:
            full = os.path.join(game_dir, name)
            if not os.path.isfile(full):
                continue
            z = zipfile.ZipFile(full)
            self.zips[name] = z
            for info in z.infolist():
                if info.is_dir():
                    continue
                key = info.filename.lower()
                if key in self.files:
                    raise XmlError("%s is in %s and %s" % (key, self.files[key][0], name))
                self.files[key] = (name, info)
        self._cache = {}

    def exists(self, path):
        return path.lower() in self.files

    def source(self, path):
        return self.files[path.lower()][0]

    def info(self, path):
        return self.files[path.lower()][1]

    def read(self, path):
        key = path.lower()
        if key not in self._cache:
            arch, info = self.files[key]
            self._cache[key] = self.zips[arch].read(info)
        return self._cache[key]

    def size(self, path):
        return self.files[path.lower()][1].file_size

    def open(self, path):
        arch, info = self.files[path.lower()]
        return self.zips[arch].open(info)

    def list(self, prefix, suffix=""):
        prefix = prefix.lower()
        return sorted(p for p in self.files if p.startswith(prefix) and p.endswith(suffix)
                      and "/" not in p[len(prefix):])

    def class_names(self, kind):
        d = KIND_DIRS[kind]
        return [p[len(d):-4] for p in self.list(d, ".xml")]


class Layer(object):
    """A read view: the game files with some paths replaced."""

    def __init__(self, base, overlay=None):
        self.base = base
        self.overlay = dict(overlay or {})

    def exists(self, path):
        return path.lower() in self.overlay or self.base.exists(path)

    def read(self, path):
        key = path.lower()
        if key in self.overlay:
            return self.overlay[key]
        return self.base.read(key)


# --------------------------------------------------------------------------- resolution

class RNode(object):
    """A resolved element. `src` names the source of each attribute value:
    {attr: (file_path, Node)}. `own` is (file_path, Node) of the last class file in
    the inheritance chain that has a node at this position (None if the position
    comes only from a template).
    `raw_index` is the position among same-tag siblings in the merged tree before
    template expansion (None for nodes that come only from a template)."""

    __slots__ = ("tag", "attrs", "src", "children", "own", "raw_index", "origin")

    def __init__(self, tag):
        self.tag = tag
        self.attrs = {}
        self.src = {}
        self.children = []
        self.own = None
        self.raw_index = None
        self.origin = None          # (file_path, Node) of the deepest raw source

    def get(self, name, default=None):
        return self.attrs.get(name, default)

    def find_all(self, tag):
        return [c for c in self.children if c.tag == tag]

    def find(self, path):
        """All descendants along a path like 'TruckData/Motor' (each step: every match)."""
        cur = [self]
        for step in path.split("/"):
            nxt = []
            for c in cur:
                nxt.extend(x for x in c.children if step == "*" or x.tag == step)
            cur = nxt
        return cur

    def __repr__(self):
        return "<RNode %s %r>" % (self.tag, self.attrs)


def _from_node(node, path, own):
    r = RNode(node.tag)
    for a in node.attrs:
        r.attrs[a.name] = a.value
        r.src[a.name] = (path, node)
    r.own = (path, node) if own else None
    r.origin = (path, node)
    r.children = [_from_node(c, path, own) for c in node.children]
    return r


def _copy(r):
    c = RNode(r.tag)
    c.attrs = dict(r.attrs)
    c.src = dict(r.src)
    c.own = r.own
    c.raw_index = r.raw_index
    c.origin = r.origin
    c.children = [_copy(x) for x in r.children]
    return c


CONTROL = ("_inheritRemove", "_noinherit")


def merge(parent, child):
    """Merge resolved `child` on top of resolved `parent` (both RNode, same tag)."""
    if child.attrs.get("_noinherit") == "true":
        out = _copy(child)
        return out
    out = RNode(parent.tag)
    out.attrs = dict(parent.attrs)
    out.src = dict(parent.src)
    out.attrs.update(child.attrs)
    out.src.update(child.src)
    out.own = child.own
    out.origin = child.origin
    out.raw_index = child.raw_index if child.raw_index is not None else parent.raw_index
    pkids = {}
    for p in parent.children:
        pkids.setdefault(p.tag, []).append(p)
    ckids = {}
    for c in child.children:
        ckids.setdefault(c.tag, []).append(c)
    used = {}
    result = []
    removed = set()
    merged_at = {}
    for tag, clist in ckids.items():
        plist = pkids.get(tag, [])
        for i, c in enumerate(clist):
            if i < len(plist):
                if c.attrs.get("_inheritRemove") == "true":
                    removed.add(id(plist[i]))
                else:
                    merged_at[id(plist[i])] = merge(plist[i], c)
            else:
                if c.attrs.get("_inheritRemove") != "true":
                    used.setdefault(tag, []).append(_copy(c))
    for p in parent.children:
        if id(p) in removed:
            continue
        result.append(merged_at.get(id(p)) or _copy(p))
    for c in child.children:
        extra = used.get(c.tag)
        if extra:
            result.append(extra.pop(0))
    out.children = result
    return out


def _index_raw(node):
    counts = {}
    for c in node.children:
        c.raw_index = counts.get(c.tag, 0)
        counts[c.tag] = c.raw_index + 1
        _index_raw(c)


class Resolver(object):
    """Resolves class files of one view (stock or patched)."""

    def __init__(self, view):
        self.view = view
        self._raw = {}
        self._tpl_files = {}

    # raw merge of the inheritance chain -------------------------------------
    def raw(self, kind, name, _stack=()):
        key = (kind, name.lower())
        if key in self._raw:
            return self._raw[key]
        if key in _stack:
            raise XmlError("inheritance loop: %s" % (list(_stack) + [key]))
        path = KIND_DIRS[kind] + name.lower() + ".xml"
        if not self.view.exists(path):
            raise XmlError("missing class file %s" % path)
        tops = parse(self.view.read(path))
        root = root_of(tops)
        tpls = [t for t in tops if t.tag == "_templates"]
        r_root = _from_node(root, path, True)
        r_tpl = RNode("_templates")
        for t in tpls:
            r_tpl = merge(r_tpl, _from_node(t, path, True))
        pname = parent_name(tops)
        if pname:
            p_root, p_tpl, _chain = self.raw(kind, pname, _stack + (key,))
            r_root = merge(p_root, r_root)
            r_tpl = merge(p_tpl, r_tpl)
            chain = [path] + _chain
        else:
            chain = [path]
        out = (r_root, r_tpl, chain)
        self._raw[key] = out
        return out

    # templates ----------------------------------------------------------------
    def _global_templates(self, include):
        if include not in self._tpl_files:
            path = "_templates/%s.xml" % include
            tops = parse(self.view.read(path))
            t = [x for x in tops if x.tag == "_templates"]
            if len(t) != 1:
                raise XmlError("%s: expected one <_templates>" % path)
            self._tpl_files[include] = _from_node(t[0], path, False)
        return self._tpl_files[include]

    def _lookup(self, tpl_sets, tag, name):
        for s in tpl_sets:
            for group in s.children:
                if group.tag != tag:
                    continue
                for t in group.children:
                    if t.tag == name:
                        return t
        return None

    def _expand(self, node, tpl_sets, depth=0):
        if depth > 32:
            raise XmlError("template nesting too deep at <%s>" % node.tag)
        name = node.attrs.get("_template")
        if name:
            t = self._lookup(tpl_sets, node.tag, name)
            if t is None:
                raise XmlError("template %s/%s not found" % (node.tag, name))
            base = RNode(node.tag)
            base.attrs = dict(t.attrs)
            base.src = dict(t.src)
            base.children = [_copy(c) for c in t.children]
            base = self._expand(base, tpl_sets, depth + 1)
            for c in base.children:
                _mark_template(c)
            own_attrs = {k: v for k, v in node.attrs.items() if k != "_template"}
            own_src = {k: v for k, v in node.src.items() if k != "_template"}
            merged = RNode(node.tag)
            merged.attrs = dict(base.attrs)
            merged.attrs.pop("_template", None)
            merged.src = {k: v for k, v in base.src.items() if k != "_template"}
            merged.attrs.update(own_attrs)
            merged.src.update(own_src)
            merged.own, merged.raw_index, merged.origin = node.own, node.raw_index, node.origin
            child_view = RNode(node.tag)
            child_view.children = node.children
            merged.children = merge(_with_children(base), child_view).children
            node = merged
        node.children = [self._expand(c, tpl_sets, depth) for c in node.children]
        return node

    def resolve(self, kind, name):
        """Effective tree of a class: returns (root RNode, chain of file paths)."""
        r_root, r_tpl, chain = self.raw(kind, name)
        root = _copy(r_root)
        _index_raw(root)
        sets = [r_tpl]
        inc = r_tpl.attrs.get("Include")
        if inc:
            for part in inc.split(","):
                sets.append(self._global_templates(part.strip()))
        return self._expand(root, sets), chain


def _mark_template(node):
    node.raw_index = None
    node.own = None
    for c in node.children:
        _mark_template(c)


def _with_children(base):
    b = RNode(base.tag)
    b.children = base.children
    return b


def raw_path(node_chain):
    """[(tag, raw_index), ...] from the root's child down to the node."""
    return [(n.tag, n.raw_index) for n in node_chain]


# --------------------------------------------------------------------------- flat files

CONTROL_ATTRS = ("_template", "_noinherit", "_inheritRemove")


def _esc(v):
    return v.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def serialize(node, depth=0):
    """A resolved tree as one standalone element: no <_parent>, no templates, the way
    the MudRunner Editor publishes Workshop items (every value written out)."""
    ind = "\t" * depth
    attrs = "".join(' %s="%s"' % (k, _esc(v)) for k, v in node.attrs.items() if k not in CONTROL_ATTRS)
    if not node.children:
        return "%s<%s%s />\n" % (ind, node.tag, attrs)
    out = ["%s<%s%s>\n" % (ind, node.tag, attrs)]
    for c in node.children:
        out.append(serialize(c, depth + 1))
    out.append("%s</%s>\n" % (ind, node.tag))
    return "".join(out)


def copy_tree(r):
    return _copy(r)


# --------------------------------------------------------------------------- values

def fmt_num(value, like=None):
    """Format a number the way the stock files do: integers stay integers."""
    if like is not None and re.fullmatch(r"-?\d+", like.strip()) and abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    s = ("%.4f" % value).rstrip("0").rstrip(".")
    if s in ("-0", ""):
        s = "0"
    if "." not in s and like is not None and "." in like:
        s += ".0"
    return s


VEC_RE = re.compile(r"^\s*\(\s*([^;()]+);\s*([^;()]+);\s*([^;()]+)\)\s*$")


def parse_vec(text):
    m = VEC_RE.match(text)
    if not m:
        raise XmlError("not a vector: %r" % text)
    return [float(x) for x in m.groups()]


def fmt_vec(v):
    return "(%s; %s; %s)" % tuple(fmt_num(x, "0.0") for x in v)


# --------------------------------------------------------------------------- text edits

def apply_edits(text, edits):
    """edits: [(start, end, replacement)], non-overlapping. Returns new text."""
    out, pos = [], 0
    for s, e, rep in sorted(edits, key=lambda x: (x[0], x[1])):
        if s < pos:
            raise XmlError("overlapping edits at %d" % s)
        out.append(text[pos:s])
        out.append(rep)
        pos = e
    out.append(text[pos:])
    return "".join(out)


def insert_attr_edit(text, node, name, value):
    """An edit that adds name="value" to node's start tag, in the file's style."""
    head = text[node.start:node.head_end]
    pos = node.head_end
    # strip whitespace before '>' or '/>' so the new attribute sits after the last one
    k = pos
    while k > node.start and text[k - 1] in " \t\r\n":
        k -= 1
    if "\n" in head and node.attrs:
        last = node.attrs[-1]
        line_start = text.rfind("\n", 0, last.vstart) + 1
        indent = re.match(r"[ \t]*", text[line_start:]).group(0)
        nl = "\r\n" if "\r\n" in head else "\n"
        return (k, k, "%s%s%s=\"%s\"" % (nl, indent, name, value))
    return (k, k, " %s=\"%s\"" % (name, value))


def read_zip_bytes(data):
    """Open in-memory zip bytes (used by tests)."""
    return zipfile.ZipFile(io.BytesIO(data))
