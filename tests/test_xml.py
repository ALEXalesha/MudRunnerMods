"""The class XML parser, resolver and text edits. No game files needed.

Examples (fixed cases) first, then laws over generated inputs (hypothesis;
HYPOTHESIS_PROFILE=thorough for a long run).
"""

import os
import re
import unittest

from hypothesis import given, settings, strategies as st

import common  # noqa: F401  (sets sys.path)
import mrxml

settings.register_profile("default", max_examples=400, deadline=None)
settings.register_profile("thorough", max_examples=4000, deadline=None)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))


class FakeView(object):
    def __init__(self, files):
        self.files = {k.lower(): (v.encode("utf-8") if isinstance(v, str) else v) for k, v in files.items()}

    def exists(self, path):
        return path.lower() in self.files

    def read(self, path):
        return self.files[path.lower()]


TRUCKS_TPL = """<_templates>
\t<WheelFriction>
\t\t<Offroad BodyFriction="1.0" SubstanceFriction="1.2" />
\t</WheelFriction>
</_templates>
"""


class ParserExamples(unittest.TestCase):
    def test_several_top_level_elements_and_comments(self):
        tops = mrxml.parse('<_templates Include="trucks" />\n<_parent File="a" />\n'
                           '<Truck>\n\t<!--<Intake Size="1" />-->\n\t<TruckData FuelCapacity="260" />\n</Truck>\n')
        self.assertEqual([t.tag for t in tops], ["_templates", "_parent", "Truck"])
        self.assertEqual(mrxml.parent_name(tops), "a")
        self.assertEqual(mrxml.root_of(tops).children[0].get("FuelCapacity"), "260")

    def test_duplicate_attribute_last_wins(self):
        # zil_cistern.xml has ImpactType twice; the parser must not fail on it
        n = mrxml.parse('<Body ImpactType="A" Mass="5" ImpactType="B" />')[0]
        self.assertEqual(n.get("ImpactType"), "B")
        self.assertEqual(len(n.attrs), 3)

    def test_value_offsets(self):
        text = '<Motor Torque="140000" />'
        a = mrxml.parse(text)[0].attr("Torque")
        self.assertEqual(text[a.vstart:a.vend], "140000")

    def test_errors(self):
        for bad in ["<A><B></A>", "<A>", "<A x=1 />", "<A></B>", "<!-- open"]:
            with self.assertRaises(mrxml.XmlError, msg=bad):
                mrxml.parse(bad)

    def test_bom_is_dropped(self):
        self.assertEqual(mrxml.parse(b'\xef\xbb\xbf<A b="1" />')[0].get("b"), "1")


class ResolverExamples(unittest.TestCase):
    def view(self, **trucks):
        files = {"_templates/trucks.xml": TRUCKS_TPL}
        for k, v in trucks.items():
            files["classes/trucks/%s.xml" % k] = v
        return FakeView(files)

    def test_positional_merge_and_remove(self):
        v = self.view(
            a='<Truck><Wheels><Wheel T="1" X="a"/><Wheel T="2"/><Wheel T="3"/></Wheels></Truck>',
            b='<_parent File="a" /><Truck><Wheels><Wheel/><Wheel T="9"/><Wheel _inheritRemove="true"/></Wheels></Truck>')
        root, chain = mrxml.Resolver(v).resolve("trucks", "b")
        self.assertEqual([w.get("T") for w in root.find("Wheels/Wheel")], ["1", "9"])
        self.assertEqual(root.find("Wheels/Wheel")[0].get("X"), "a")
        self.assertEqual(chain, ["classes/trucks/b.xml", "classes/trucks/a.xml"])

    def test_noinherit(self):
        v = self.view(a='<Truck><Wheels Y="1"><Wheel/><Wheel/></Wheels></Truck>',
                      b='<_parent File="a" /><Truck><Wheels _noinherit="true"><Wheel Z="2"/></Wheels></Truck>')
        root, _ = mrxml.Resolver(v).resolve("trucks", "b")
        w = root.find("Wheels")[0]
        self.assertIsNone(w.get("Y"))
        self.assertEqual(len(w.children), 1)

    def test_templates_local_chain_and_include(self):
        v = self.view(a='<_templates Include="trucks"><Wheel><Base S="1" T="x"/><Front _template="Base" T="y"/>'
                        '</Wheel></_templates><Truck><Wheels><Wheel _template="Front" H="5"/></Wheels>'
                        '<WheelFriction _template="Offroad" BodyFriction="2.0"/></Truck>')
        root, _ = mrxml.Resolver(v).resolve("trucks", "a")
        w = root.find("Wheels/Wheel")[0]
        self.assertEqual((w.get("S"), w.get("T"), w.get("H")), ("1", "y", "5"))
        f = root.find("WheelFriction")[0]
        self.assertEqual((f.get("BodyFriction"), f.get("SubstanceFriction")), ("2.0", "1.2"))
        self.assertEqual(f.src["SubstanceFriction"][0], "_templates/trucks.xml")
        self.assertEqual(f.src["BodyFriction"][0], "classes/trucks/a.xml")

    def test_child_override_of_template_value(self):
        # kamaz65115: <Wheel Torque="none"/> over the parent's <Wheel _template="FrontWheel"/>
        v = self.view(a='<_templates><Wheel><F Torque="full" Type="k"/></Wheel></_templates>'
                        '<Truck><Wheels><Wheel _template="F"/></Wheels></Truck>',
                      b='<_parent File="a" /><Truck><Wheels><Wheel Torque="none"/></Wheels></Truck>')
        root, _ = mrxml.Resolver(v).resolve("trucks", "b")
        w = root.find("Wheels/Wheel")[0]
        self.assertEqual((w.get("Torque"), w.get("Type")), ("none", "k"))
        self.assertEqual(w.own[0], "classes/trucks/b.xml")

    def test_loop_detected(self):
        v = self.view(a='<_parent File="b" /><Truck/>', b='<_parent File="a" /><Truck/>')
        with self.assertRaises(mrxml.XmlError):
            mrxml.Resolver(v).resolve("trucks", "a")


class EditExamples(unittest.TestCase):
    def test_insert_inline(self):
        text = '<Wheel _template="F" X="1" />'
        n = mrxml.parse(text)[0]
        out = mrxml.apply_edits(text, [mrxml.insert_attr_edit(text, n, "Torque", "full")])
        self.assertEqual(out, '<Wheel _template="F" X="1" Torque="full" />')

    def test_insert_multiline_keeps_style(self):
        text = '<Damage\n\t\t\tCapacity="600"\n\t\t\tParentFrame="B"\n\t\t/>'
        n = mrxml.parse(text)[0]
        out = mrxml.apply_edits(text, [mrxml.insert_attr_edit(text, n, "X", "1")])
        self.assertEqual(out, '<Damage\n\t\t\tCapacity="600"\n\t\t\tParentFrame="B"\n\t\t\tX="1"\n\t\t/>')

    def test_overlapping_edits_rejected(self):
        with self.assertRaises(mrxml.XmlError):
            mrxml.apply_edits("abcdef", [(0, 3, "x"), (2, 4, "y")])

    def test_fmt_num(self):
        self.assertEqual(mrxml.fmt_num(350000.0, "140000"), "350000")
        self.assertEqual(mrxml.fmt_num(3.0, "1.2"), "3.0")
        self.assertEqual(mrxml.fmt_num(1.875, "0.75"), "1.875")
        self.assertEqual(mrxml.fmt_vec([0.16, 3.17, -0.95]), "(0.16; 3.17; -0.95)")


# ----------------------------------------------------------------------------- laws

NAMES = st.from_regex(r"[A-Z][A-Za-z]{0,8}", fullmatch=True)
VALUES = st.text(alphabet=st.characters(blacklist_characters='"<>&\r\n', blacklist_categories=("Cs", "Cc")),
                 max_size=12)


@st.composite
def elements(draw, depth=0):
    tag = draw(NAMES)
    attrs = draw(st.dictionaries(NAMES, VALUES, max_size=4))
    kids = draw(st.lists(elements(depth + 1), max_size=3)) if depth < 3 else []
    return (tag, attrs, kids)


def render(el, ind=0, style="inline"):
    tag, attrs, kids = el
    if style == "multi" and attrs:
        a = "".join('\n%s\t%s="%s"' % ("\t" * ind, k, v) for k, v in attrs.items()) + "\n" + "\t" * ind
    else:
        a = "".join(' %s="%s"' % (k, v) for k, v in attrs.items())
    if not kids:
        return "%s<%s%s/>" % ("\t" * ind, tag, a)
    inner = "\n".join(render(k, ind + 1, style) for k in kids)
    return "%s<%s%s>\n%s\n%s</%s>" % ("\t" * ind, tag, a, inner, "\t" * ind, tag)


def shape(node):
    return (node.tag, node.adict(), [shape(c) for c in node.children])


def as_tuple(el):
    tag, attrs, kids = el
    return (tag, attrs, [as_tuple(k) for k in kids])


class ParserLaws(unittest.TestCase):
    @given(st.lists(elements(), min_size=1, max_size=3), st.sampled_from(["inline", "multi"]))
    def test_parse_reads_back_what_was_written(self, els, style):
        text = "\n".join(render(e, 0, style) for e in els)
        self.assertEqual([shape(n) for n in mrxml.parse(text)], [as_tuple(e) for e in els])

    @given(elements(), NAMES, VALUES)
    def test_insert_attr_adds_exactly_one_attribute(self, el, name, value):
        tag, attrs, kids = el
        attrs.pop(name, None)
        text = render((tag, attrs, kids))
        node = mrxml.parse(text)[0]
        out = mrxml.apply_edits(text, [mrxml.insert_attr_edit(text, node, name, value)])
        node2 = mrxml.parse(out)[0]
        want = dict(attrs)
        want[name] = value
        self.assertEqual(node2.adict(), want)
        self.assertEqual([shape(c) for c in node2.children], [shape(c) for c in node.children])

    @given(elements(), st.data())
    def test_replacing_a_value_touches_nothing_else(self, el, data):
        text = render(el)
        node = mrxml.parse(text)[0]
        allattrs = []

        def walk(n):
            allattrs.extend(n.attrs)
            for c in n.children:
                walk(c)
        walk(node)
        if not allattrs:
            return
        a = data.draw(st.sampled_from(allattrs))
        new = data.draw(VALUES)
        out = mrxml.apply_edits(text, [(a.vstart, a.vend, new)])
        self.assertEqual(out[:a.vstart], text[:a.vstart])
        self.assertEqual(out[a.vstart + len(new):], text[a.vend:])
        mrxml.parse(out)

    @given(st.floats(min_value=1e-3, max_value=1e7, allow_nan=False), st.sampled_from(["1", "1.0", "0.75"]))
    def test_fmt_num_round_trip(self, x, like):
        s = mrxml.fmt_num(x, like)
        self.assertAlmostEqual(float(s), x, delta=max(6e-5, 6e-5 * abs(x)) if "." in s else 0.5)
        self.assertTrue(re.fullmatch(r"-?\d+(\.\d+)?", s), s)

    @given(st.integers(min_value=1, max_value=10 ** 7), st.sampled_from([2.5, 10, 2]))
    def test_integer_values_stay_integer(self, x, k):
        s = mrxml.fmt_num(x * k, str(x)) if float(x * k).is_integer() else None
        if s is not None:
            self.assertEqual(s, str(int(x * k)))


if __name__ == "__main__":
    unittest.main()
