# Tests for WikiText parsing
#
# Copyright (c) 2020-2022 Tatu Ylonen.  See file LICENSE and https://ylonen.org

import unittest

from wikitextprocessor import Wtp
from wikitextprocessor.parser import (
    HTMLNode,
    LevelNode,
    NodeKind,
    TemplateNode,
    WikiNode,
    print_tree,
)


class ParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Wtp()
        self.ctx.analyze_templates()

    def tearDown(self) -> None:
        self.ctx.close_db_conn()

    def parse(self, title: str, text: str, **kwargs) -> WikiNode:
        self.ctx.start_page(title)
        return self.ctx.parse(text, **kwargs)

    def test_empty(self):
        tree = self.parse("test", "")
        self.assertEqual(tree.kind, NodeKind.ROOT)
        self.assertEqual(tree.children, [])
        self.assertEqual(tree.largs, [["test"]])

    def test_text(self):
        tree = self.parse("test", "some text")
        self.assertEqual(tree.children, ["some text"])

    def test_text2(self):
        tree = self.parse("test", "some:text")
        self.assertEqual(tree.children, ["some:text"])

    def test_text3(self):
        tree = self.parse("test", "some|text")
        self.assertEqual(tree.children, ["some|text"])

    def test_text4(self):
        tree = self.parse("test", "some}}text")
        self.assertEqual(tree.children, ["some}}text"])

    def test_text5(self):
        tree = self.parse("test", "some* text")
        self.assertEqual(tree.children, ["some* text"])

    def test_hdr2a(self):
        tree = self.parse("test", "==Foo==")
        self.assertEqual(len(tree.children), 1)
        child = tree.children[0]
        self.assertEqual(child.kind, NodeKind.LEVEL2)
        self.assertEqual(child.largs, [["Foo"]])
        self.assertEqual(child.children, [])

    def test_hdr2b(self):
        tree = self.parse("test", "== Foo:Bar ==\nZappa\n")
        self.assertEqual(len(tree.children), 1)
        child = tree.children[0]
        self.assertEqual(child.kind, NodeKind.LEVEL2)
        self.assertEqual(child.largs, [["Foo:Bar"]])
        self.assertEqual(child.children, ["\nZappa\n"])

    def test_hdr2c(self):
        tree = self.parse("test", "=== Foo:Bar ===\nZappa\n")
        self.assertEqual(len(tree.children), 1)
        child = tree.children[0]
        self.assertEqual(child.kind, NodeKind.LEVEL3)
        self.assertEqual(child.largs, [["Foo:Bar"]])
        self.assertEqual(child.children, ["\nZappa\n"])

    def test_hdr23a(self):
        tree = self.parse("test", "==Foo==\na\n===Bar===\nb\n===Zappa===\nc\n")
        self.assertEqual(len(tree.children), 1)
        h2 = tree.children[0]
        self.assertEqual(h2.kind, NodeKind.LEVEL2)
        self.assertEqual(len(h2.children), 3)
        self.assertEqual(h2.children[0], "\na\n")
        h3a = h2.children[1]
        h3b = h2.children[2]
        self.assertEqual(h3a.kind, NodeKind.LEVEL3)
        self.assertEqual(h3b.kind, NodeKind.LEVEL3)
        self.assertEqual(h3a.largs, [["Bar"]])
        self.assertEqual(h3a.children, ["\nb\n"])
        self.assertEqual(h3b.largs, [["Zappa"]])
        self.assertEqual(h3b.children, ["\nc\n"])

    def test_hdr23b(self):
        tree = self.parse("test", "==Foo==\na\n===Bar===\nb\n==Zappa==\nc\n")
        self.assertEqual(len(tree.children), 2)
        h2a = tree.children[0]
        h2b = tree.children[1]
        self.assertEqual(h2a.kind, NodeKind.LEVEL2)
        self.assertEqual(h2b.kind, NodeKind.LEVEL2)
        self.assertEqual(len(h2a.children), 2)
        self.assertEqual(h2a.children[0], "\na\n")
        h3a = h2a.children[1]
        self.assertEqual(h3a.kind, NodeKind.LEVEL3)
        self.assertEqual(h3a.largs, [["Bar"]])
        self.assertEqual(h3a.children, ["\nb\n"])
        self.assertEqual(h2b.largs, [["Zappa"]])
        self.assertEqual(h2b.children, ["\nc\n"])

    def test_hdr23456(self):
        tree = self.parse(
            "test",
            """
==Foo2==
dasfdasfas
===Foo3===
adsfdasfas
====Foo4====
dasfdasfdas
=====Foo5=====
dsfasasdd
======Foo6======
dasfasddasfdas
""",
        )
        self.assertEqual(len(tree.children), 2)
        h2 = tree.children[1]
        h3 = h2.children[1]
        h4 = h3.children[1]
        h5 = h4.children[1]
        h6 = h5.children[1]
        self.assertEqual(h6.kind, NodeKind.LEVEL6)
        self.assertEqual(h6.children, ["\ndasfasddasfdas\n"])

    def test_hdr_anchor(self):
        tree = self.parse(
            "test", """==<Span id="anchor">hdr text</span>==\ndata"""
        )
        self.assertEqual(len(tree.children), 1)
        h = tree.children[0]
        self.assertEqual(h.kind, NodeKind.LEVEL2)
        self.assertEqual(len(h.largs), 1)
        self.assertEqual(len(h.largs[0]), 1)
        a = h.largs[0][0]
        self.assertEqual(a.kind, NodeKind.HTML)
        self.assertEqual(a.sarg, "span")
        self.assertEqual(a.attrs.get("id"), "anchor")
        self.assertEqual(a.children, ["hdr text"])
        self.assertEqual(h.children, ["\ndata"])

    def test_nowiki1(self):
        tree = self.parse(
            "test", "==Foo==\na<nowiki>\n===Bar===\nb</nowiki>\n==Zappa==\nc\n"
        )
        self.assertEqual(len(tree.children), 2)
        h2a = tree.children[0]
        h2b = tree.children[1]
        self.assertEqual(h2a.kind, NodeKind.LEVEL2)
        self.assertEqual(h2b.kind, NodeKind.LEVEL2)
        self.assertEqual(
            h2a.children,
            [
                "\na\n&equals;&equals;&equals;Bar"
                "&equals;&equals;&equals;\nb\n"
            ],
        )
        self.assertEqual(h2b.largs, [["Zappa"]])
        self.assertEqual(h2b.children, ["\nc\n"])

    def test_nowiki2(self):
        tree = self.parse("test", "<<nowiki/>foo>")
        self.assertEqual(tree.children, ["<<nowiki />foo>"])

    def test_nowiki3(self):
        tree = self.parse("test", "&<nowiki/>amp;")
        self.assertEqual(tree.children, ["&<nowiki />amp;"])

    def test_nowiki4(self):
        tree = self.parse("test", "a</nowiki>b")
        self.assertEqual(tree.children, ["a</nowiki>b"])
        self.assertEqual(len(self.ctx.debugs), 1)

    def test_nowiki5(self):
        tree = self.parse("test", "<nowiki />#b")
        self.assertEqual(tree.children, ["<nowiki />#b"])

    def test_nowiki6(self):
        tree = self.parse("test", "a<nowiki>\n</nowiki>b")
        self.assertEqual(tree.children, ["a\nb"])

    def test_nowiki7(self):
        tree = self.parse("test", "a<nowiki>\nb</nowiki>c")
        self.assertEqual(tree.children, ["a\nbc"])

    def test_nowiki8(self):
        tree = self.parse("test", "'<nowiki />'Italics' markup'<nowiki/>'")
        self.assertEqual(
            tree.children, ["'<nowiki />'Italics' markup'<nowiki />'"]
        )

    def test_nowiki9(self):
        tree = self.parse("test", "<nowiki>[[Example]]</nowiki>")
        self.assertEqual(tree.children, ["&lsqb;&lsqb;Example&rsqb;&rsqb;"])

    def test_nowiki10(self):
        tree = self.parse("test", "<nowiki><!-- revealed --></nowiki>")
        self.assertEqual(tree.children, ["&lt;&excl;-- revealed --&gt;"])

    def test_nowiki11(self):
        tree = self.parse("test", "__HIDDENCAT<nowiki />__")
        self.assertEqual(tree.children, ["__HIDDENCAT<nowiki />__"])

    def test_nowiki12(self):
        tree = self.parse("test", "[<nowiki />[x]]")
        self.assertEqual(tree.children, ["&lsqb;&lsqb;x&rsqb;&rsqb;"])

    def test_nowiki13(self):
        tree = self.parse("test", "[[x]<nowiki />]")
        self.assertEqual(tree.children, ["&lsqb;&lsqb;x&rsqb;&rsqb;"])

    def test_nowiki14(self):
        tree = self.parse("test", "[[<nowiki />x]]")
        self.assertEqual(tree.children, ["&lsqb;&lsqb;<nowiki />x&rsqb;&rsqb;"])

    def test_nowiki15(self):
        tree = self.parse("test", "{<nowiki />{x}}")
        self.assertEqual(tree.children, ["&lbrace;&lbrace;x&rbrace;&rbrace;"])

    def test_nowiki16(self):
        tree = self.parse("test", "{{x}<nowiki />}")
        self.assertEqual(tree.children, ["&lbrace;&lbrace;x&rbrace;&rbrace;"])

    def test_nowiki17(self):
        tree = self.parse("test", "{{x<nowiki />}}")
        self.assertEqual(
            tree.children, ["&lbrace;&lbrace;x<nowiki />&rbrace;&rbrace;"]
        )

    def test_nowiki18(self):
        tree = self.parse("test", "{{<nowiki />{x}}}")
        self.assertEqual(
            tree.children, ["&lbrace;&lbrace;&lbrace;x&rbrace;&rbrace;&rbrace;"]
        )

    def test_nowiki19(self):
        tree = self.parse("test", "{<nowiki />{{x}}}")
        self.assertEqual(
            tree.children, ["&lbrace;&lbrace;&lbrace;x&rbrace;&rbrace;&rbrace;"]
        )

    def test_nowiki20(self):
        tree = self.parse("test", "{{{x|1}<nowiki />}}")
        self.assertEqual(
            tree.children,
            ["&lbrace;&lbrace;&lbrace;x&vert;1" "&rbrace;&rbrace;&rbrace;"],
        )

    def test_nowiki21(self):
        tree = self.parse("test", "{{{x}}<nowiki />}")
        self.assertEqual(
            tree.children, ["&lbrace;&lbrace;&lbrace;x&rbrace;&rbrace;&rbrace;"]
        )

    def test_nowiki22(self):
        tree = self.parse("test", "{{{x<nowiki />|}}}")
        self.assertEqual(
            tree.children,
            [
                "&lbrace;&lbrace;&lbrace;x<nowiki />&vert;"
                "&rbrace;&rbrace;&rbrace;"
            ],
        )

    def test_no_template_name1(self):
        tree = self.parse("test", "{{|es|something}}")
        self.assertEqual(
            tree.children,
            ["&lbrace;&lbrace;&vert;es&vert;something&rbrace;&rbrace;"],
        )

    def test_no_template_name2(self):
        tree = self.parse("test", "{{}}")
        self.assertEqual(
            tree.children,
            ["&lbrace;&lbrace;&rbrace;&rbrace;"],
        )

    def test_entity_expand(self):
        tree = self.parse("test", "R&amp;D")
        self.assertEqual(tree.children, ["R&amp;D"])

    def test_processonce1(self):
        tree = self.parse("test", "&amp;amp;")
        self.assertEqual(tree.children, ["&amp;amp;"])

    def test_html1(self):
        tree = self.parse("test", "<b>foo</b>")
        self.assertEqual(len(tree.children), 1)
        a = tree.children[0]
        self.assertEqual(a.kind, NodeKind.HTML)
        self.assertEqual(a.sarg, "b")
        self.assertEqual(a.children, ["foo"])

    def test_html2(self):
        tree = self.parse(
            "test",
            """<div style='color: red' width="40" """
            """max-width=100 bogus>red text</DIV>""",
        )
        self.assertEqual(len(tree.children), 1)
        a = tree.children[0]
        self.assertEqual(a.kind, NodeKind.HTML)
        self.assertEqual(a.sarg, "div")
        self.assertEqual(a.attrs.get("style", False), "color: red")
        self.assertEqual(a.attrs.get("width", False), "40")
        self.assertEqual(a.attrs.get("max-width", False), "100")
        self.assertEqual(a.attrs.get("bogus", False), "")
        self.assertEqual(a.children, ["red text"])

    def test_html3(self):
        tree = self.parse("test", """<br class="big" />""")
        self.assertEqual(len(tree.children), 1)
        h = tree.children[0]
        self.assertEqual(h.kind, NodeKind.HTML)
        self.assertEqual(h.sarg, "br")
        self.assertEqual(h.attrs.get("class", False), "big")
        self.assertEqual(h.children, [])

    def test_html4(self):
        tree = self.parse("test", """<div><span>foo</span></div>""")
        self.assertEqual(len(tree.children), 1)
        a = tree.children[0]
        self.assertEqual(a.kind, NodeKind.HTML)
        self.assertEqual(a.sarg, "div")
        self.assertEqual(len(a.children), 1)
        b = a.children[0]
        self.assertEqual(b.kind, NodeKind.HTML)
        self.assertEqual(b.sarg, "span")
        self.assertEqual(b.children, ["foo"])
        self.assertEqual(self.ctx.errors, [])

    def test_html5(self):
        tree = self.parse("test", """<div><span>foo</div></span>""")
        self.assertEqual(len(tree.children), 2)
        a, rest = tree.children
        self.assertEqual(rest, "</span>")
        self.assertEqual(a.kind, NodeKind.HTML)
        self.assertEqual(a.sarg, "div")
        self.assertEqual(len(a.children), 1)
        b = a.children[0]
        self.assertEqual(b.kind, NodeKind.HTML)
        self.assertEqual(b.sarg, "span")
        self.assertEqual(b.children, ["foo"])
        self.assertEqual(len(self.ctx.debugs), 2)

    def test_html6(self):
        tree = self.parse("test", """<div><span>foo</div>""")
        self.assertEqual(len(tree.children), 1)
        a = tree.children[0]
        self.assertEqual(a.kind, NodeKind.HTML)
        self.assertEqual(a.sarg, "div")
        self.assertEqual(len(a.children), 1)
        b = a.children[0]
        self.assertEqual(b.kind, NodeKind.HTML)
        self.assertEqual(b.sarg, "span")
        self.assertEqual(b.children, ["foo"])
        self.assertEqual(len(self.ctx.debugs), 1)

    def test_html7(self):
        tree = self.parse("test", """<ul><li>foo<li>bar</ul>""")
        self.assertEqual(len(tree.children), 1)
        a = tree.children[0]
        self.assertEqual(a.kind, NodeKind.HTML)
        self.assertEqual(a.sarg, "ul")
        self.assertEqual(len(a.children), 2)
        b, c = a.children
        self.assertEqual(b.kind, NodeKind.HTML)
        self.assertEqual(b.sarg, "li")
        self.assertEqual(b.children, ["foo"])
        self.assertEqual(c.kind, NodeKind.HTML)
        self.assertEqual(c.sarg, "li")
        self.assertEqual(c.children, ["bar"])
        self.assertEqual(self.ctx.errors, [])

    def test_html8(self):
        tree = self.parse("test", "==Title==\n<ul><li>foo<li>bar</ul>" "</div>")
        self.assertEqual(len(tree.children), 1)
        h = tree.children[0]
        self.assertEqual(h.kind, NodeKind.LEVEL2)
        self.assertEqual(h.largs, [["Title"]])
        self.assertEqual(len(h.children), 3)
        x, a, rest = h.children
        self.assertEqual(rest, "</div>")
        self.assertEqual(x, "\n")
        self.assertEqual(a.kind, NodeKind.HTML)
        self.assertEqual(a.sarg, "ul")
        self.assertEqual(len(a.children), 2)
        b, c = a.children
        self.assertEqual(b.kind, NodeKind.HTML)
        self.assertEqual(b.sarg, "li")
        self.assertEqual(b.children, ["foo"])
        self.assertEqual(c.kind, NodeKind.HTML)
        self.assertEqual(c.sarg, "li")
        self.assertEqual(c.children, ["bar"])
        self.assertEqual(len(self.ctx.debugs), 1)

    def test_html9(self):
        tree = self.parse("test", "<b <!-- bar -->>foo</b>")
        self.assertEqual(len(tree.children), 1)
        a = tree.children[0]
        self.assertTrue(isinstance(a, WikiNode))
        self.assertEqual(a.kind, NodeKind.HTML)
        self.assertEqual(a.sarg, "b")
        self.assertEqual(a.children, ["foo"])
        self.assertEqual(self.ctx.errors, [])

    def test_html10(self):
        tree = self.parse("test", "<br />")
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(len(tree.children), 1)
        a = tree.children[0]
        self.assertTrue(isinstance(a, WikiNode))
        self.assertEqual(a.kind, NodeKind.HTML)
        self.assertEqual(a.sarg, "br")
        self.assertEqual(a.children, [])

    def test_html11(self):
        tree = self.parse("test", "<wbr>")  # Omits closing tag
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(len(tree.children), 1)
        a = tree.children[0]
        self.assertTrue(isinstance(a, WikiNode))
        self.assertEqual(a.kind, NodeKind.HTML)
        self.assertEqual(a.sarg, "wbr")
        self.assertEqual(a.children, [])

    def test_html12(self):
        tree = self.parse("test", "<tt><nowiki>{{f|oo}}</nowiki></tt>")
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(len(tree.children), 1)
        a = tree.children[0]
        self.assertTrue(isinstance(a, WikiNode))
        self.assertEqual(a.kind, NodeKind.HTML)
        self.assertEqual(a.sarg, "tt")
        self.assertEqual(
            a.children, ["&lbrace;&lbrace;f&vert;oo&rbrace;&rbrace;"]
        )

    def test_html13(self):
        tree = self.parse("test", "<span>[</span>")
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(len(tree.children), 1)
        a = tree.children[0]
        self.assertTrue(isinstance(a, WikiNode))
        self.assertEqual(a.kind, NodeKind.HTML)
        self.assertEqual(a.sarg, "span")
        self.assertEqual(a.children, ["["])

    def test_html14(self):
        tree = self.parse("test", "a<3>b")
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        self.assertEqual(self.ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        self.assertEqual(tree.children, ["a<3>b"])

    def test_html15(self):
        tree = self.parse("test", "<DIV>foo</DIV>")
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        self.assertEqual(self.ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        a = tree.children[0]
        self.assertTrue(isinstance(a, WikiNode))
        self.assertEqual(a.kind, NodeKind.HTML)
        self.assertEqual(a.sarg, "div")
        self.assertEqual(a.children, ["foo"])

    def test_html16(self):
        tree = self.parse(
            "test",
            """<TABLE ALIGN=RIGHT border="1" cellpadding="5" cellspacing="0">
            <TR ALIGN=RIGHT><TD>'''Depth'''</TD></TR></TABLE>""",
        )
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        self.assertEqual(self.ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        a = tree.children[0]
        self.assertTrue(isinstance(a, WikiNode))
        self.assertEqual(a.kind, NodeKind.HTML)

    def test_html17(self):
        tree = self.parse(
            "test",
            """<table>
            <tr><th>Depth
            <tr><td>4
            <tr><td>5
            </table>""",
        )
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        self.assertEqual(self.ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        a = tree.children[0]
        self.assertTrue(isinstance(a, WikiNode))
        self.assertEqual(a.kind, NodeKind.HTML)

    def test_html18(self):
        tree = self.parse(
            "test",
            """<DIV


                                            >foo</DIV>""",
        )
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        self.assertEqual(self.ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        a = tree.children[0]
        self.assertTrue(isinstance(a, WikiNode))
        self.assertEqual(a.kind, NodeKind.HTML)
        self.assertEqual(a.sarg, "div")
        self.assertEqual(a.children, ["foo"])

    def test_html_unknown(self):
        tree = self.parse("test", "<unknown>foo</unknown>")
        self.assertNotEqual(self.ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        self.assertEqual(tree.children, ["<unknown>foo</unknown>"])

    def test_html_section1(self):
        tree = self.parse("test", "a<section begin=foo />b")
        self.assertEqual(tree.children, ["ab"])
        self.assertEqual(len(self.ctx.warnings), 0)
        self.assertEqual(len(self.ctx.debugs), 0)

    def test_html_section2(self):
        tree = self.parse("test", "a</section>b")
        self.assertEqual(tree.children, ["ab"])
        self.assertEqual(len(self.ctx.debugs), 1)

    def test_italic1(self):
        tree = self.parse("test", "a ''italic test'' b")
        self.assertEqual(len(tree.children), 3)
        a, b, c = tree.children
        self.assertEqual(a, "a ")
        self.assertEqual(b.kind, NodeKind.ITALIC)
        self.assertEqual(b.children, ["italic test"])
        self.assertEqual(c, " b")

    def test_italic2(self):
        # Italic is frequently used in enPR in Wiktionary to italicize
        # certain parts of the pronunciation, followed by a single quote.
        tree = self.parse("test", "a''test'''b")
        self.assertEqual(len(tree.children), 3)
        a, b, c = tree.children
        self.assertEqual(a, "a")
        self.assertEqual(b.kind, NodeKind.ITALIC)
        self.assertEqual(b.children, ["test"])
        self.assertEqual(c, "'b")

    def test_italic3(self):
        tree = self.parse("test", "a''t{{test}}t''b")
        self.assertEqual(len(tree.children), 3)
        a, b, c = tree.children
        self.assertEqual(a, "a")
        self.assertEqual(b.kind, NodeKind.ITALIC)
        self.assertEqual(len(b.children), 3)
        ba, bb, bc = b.children
        self.assertEqual(ba, "t")
        self.assertEqual(bb.kind, NodeKind.TEMPLATE)
        self.assertEqual(bb.largs, [["test"]])
        self.assertEqual(bc, "t")
        self.assertEqual(c, "b")

    def test_italic4(self):
        tree = self.parse("test", "a''t<span>test</span>t''b")
        self.assertEqual(len(tree.children), 3)
        a, b, c = tree.children
        self.assertEqual(a, "a")
        self.assertEqual(b.kind, NodeKind.ITALIC)
        self.assertEqual(len(b.children), 3)
        ba, bb, bc = b.children
        self.assertEqual(ba, "t")
        self.assertEqual(bb.kind, NodeKind.HTML)
        self.assertEqual(bb.sarg, "span")
        self.assertEqual(bc, "t")
        self.assertEqual(c, "b")

    def test_italic5(self):
        tree = self.parse("test", "a''t[[test]]t''b")
        self.assertEqual(len(tree.children), 3)
        a, b, c = tree.children
        self.assertEqual(a, "a")
        self.assertEqual(b.kind, NodeKind.ITALIC)
        self.assertEqual(len(b.children), 2)
        ba, bb = b.children
        self.assertEqual(ba, "t")
        self.assertEqual(bb.kind, NodeKind.LINK)
        self.assertEqual(bb.largs, [["test"]])
        self.assertEqual(bb.children, ["t"])
        self.assertEqual(c, "b")

    def test_italic6(self):
        self.parse("test", "''[[M|''M'']]''")
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        self.assertEqual(self.ctx.debugs, [])
        # XXX

    def test_bold1(self):
        tree = self.parse("test", "a '''bold test''' b")
        self.assertEqual(len(tree.children), 3)
        a, b, c = tree.children
        self.assertEqual(a, "a ")
        self.assertEqual(b.kind, NodeKind.BOLD)
        self.assertEqual(b.children, ["bold test"])
        self.assertEqual(c, " b")

    def test_bold2(self):
        tree = self.parse("test", "'''C''''est")
        self.assertEqual(len(tree.children), 2)
        a, b = tree.children
        self.assertEqual(a.kind, NodeKind.BOLD)
        self.assertEqual(a.children, ["C"])
        self.assertEqual(b, "'est")
        t = self.ctx.node_to_wikitext(tree)
        self.assertEqual(t, "'''C''''est")

        def node_handler(node):
            if node.kind == NodeKind.BOLD:
                return node.children
            return None

        t = self.ctx.node_to_html(tree, node_handler_fn=node_handler)
        self.assertEqual(t, "C'est")

    def test_bolditalic1(self):
        tree = self.parse("test", "a '''''bold italic test''''' b")
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        self.assertEqual(self.ctx.debugs, [])
        self.assertEqual(len(tree.children), 3)
        a, b, c = tree.children
        self.assertEqual(a, "a ")
        self.assertEqual(b.kind, NodeKind.ITALIC)
        self.assertEqual(len(b.children), 1)
        ba = b.children[0]
        self.assertEqual(ba.kind, NodeKind.BOLD)
        self.assertEqual(ba.children, ["bold italic test"])

    def test_bolditalic2(self):
        # Mismatch in bold/italic close ordering is permitted
        tree = self.parse("test", "''' ''bold italic test'''<nowiki/>''")
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        self.assertEqual(self.ctx.debugs, [])
        self.assertEqual(len(tree.children), 2)
        a, b = tree.children
        self.assertEqual(a.kind, NodeKind.BOLD)
        aa, ab = a.children
        self.assertEqual(aa, " ")
        self.assertEqual(ab.kind, NodeKind.ITALIC)
        self.assertEqual(ab.children, ["bold italic test"])
        self.assertEqual(b.kind, NodeKind.ITALIC)
        self.assertEqual(b.children, ["<nowiki />"])

    def test_bolditalic3(self):
        # Mismatch in bold/italic close ordering is permitted
        tree = self.parse("test", "'' '''bold italic test''<nowiki/>'''")
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        self.assertEqual(self.ctx.debugs, [])
        self.assertEqual(len(tree.children), 2)
        a, b = tree.children
        self.assertEqual(a.kind, NodeKind.ITALIC)
        aa, ab = a.children
        self.assertEqual(aa, " ")
        self.assertEqual(ab.kind, NodeKind.BOLD)
        self.assertEqual(ab.children, ["bold italic test"])
        self.assertEqual(b.kind, NodeKind.BOLD)
        self.assertEqual(b.children, ["<nowiki />"])

    def test_bolditalic4(self):
        tree = self.parse("test", "'' '''bold italic test'''''")
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        self.assertEqual(self.ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        self.assertEqual(tree.children[0].kind, NodeKind.ITALIC)
        a, b = tree.children[0].children
        self.assertEqual(a, " ")
        self.assertEqual(b.kind, NodeKind.BOLD)
        self.assertEqual(b.children, ["bold italic test"])

    def test_bolditalic5(self):
        tree = self.parse("test", "''' ''bold italic test'''''")
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        self.assertEqual(self.ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        self.assertEqual(tree.children[0].kind, NodeKind.BOLD)
        a, b = tree.children[0].children
        self.assertEqual(a, " ")
        self.assertEqual(b.kind, NodeKind.ITALIC)
        self.assertEqual(b.children, ["bold italic test"])

    def test_bolditalic6(self):
        tree = self.parse("test", """''X'''B'''Y''""")
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        self.assertEqual(self.ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        self.assertEqual(tree.children[0].kind, NodeKind.ITALIC)

    def test_bolditalic7(self):
        tree = self.parse("test", """''S '''''n''''' .''""")
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        self.assertEqual(self.ctx.debugs, [])
        self.assertEqual(len(tree.children), 3)
        self.assertEqual(tree.children[0].kind, NodeKind.ITALIC)
        self.assertEqual(tree.children[1].kind, NodeKind.BOLD)
        self.assertEqual(tree.children[2].kind, NodeKind.ITALIC)

    def test_hline(self):
        tree = self.parse("test", "foo\n*item\n----\nmore")
        self.assertEqual(len(tree.children), 4)
        a, b, c, d = tree.children
        self.assertEqual(a, "foo\n")
        self.assertEqual(b.kind, NodeKind.LIST)
        self.assertEqual(c.kind, NodeKind.HLINE)
        self.assertEqual(d, "\nmore")

    def test_list_html1(self):
        tree = self.parse("test", "foo\n*item\n\n<strong>bar</strong>")
        self.assertEqual(len(tree.children), 4)
        a, b, c, d = tree.children
        self.assertEqual(a, "foo\n")
        self.assertEqual(b.kind, NodeKind.LIST)
        self.assertEqual(c, "\n")
        self.assertEqual(d.kind, NodeKind.HTML)

    def test_list_html2(self):
        tree = self.parse("test", "foo\n*item <strong>bar\n</strong>\n*item2\n")
        self.assertEqual(len(tree.children), 2)
        a, b = tree.children
        self.assertEqual(a, "foo\n")
        self.assertEqual(b.kind, NodeKind.LIST)
        self.assertEqual(len(b.children), 2)
        c, d = b.children
        self.assertEqual(c.kind, NodeKind.LIST_ITEM)
        self.assertEqual(d.kind, NodeKind.LIST_ITEM)
        self.assertEqual(c.children[1].kind, NodeKind.HTML)
        self.assertEqual(c.children[2], "\n")

    def test_ul(self):
        tree = self.parse(
            "test", "foo\n\n* item1\n** item1.1\n** item1.2\n" "* item2\n"
        )
        self.assertEqual(len(tree.children), 2)
        a, b = tree.children
        self.assertEqual(a, "foo\n\n")
        self.assertEqual(b.kind, NodeKind.LIST)
        self.assertEqual(b.sarg, "*")
        self.assertEqual(len(b.children), 2)
        ba, bb = b.children
        self.assertEqual(ba.kind, NodeKind.LIST_ITEM)
        self.assertEqual(ba.sarg, "*")
        self.assertEqual(len(ba.children), 2)
        baa, bab = ba.children
        self.assertEqual(baa, " item1\n")
        self.assertEqual(bab.kind, NodeKind.LIST)
        self.assertEqual(bab.sarg, "**")
        self.assertEqual(len(bab.children), 2)
        baba, babb = bab.children
        self.assertEqual(baba.kind, NodeKind.LIST_ITEM)
        self.assertEqual(baba.sarg, "**")
        self.assertEqual(baba.children, [" item1.1\n"])
        self.assertEqual(babb.kind, NodeKind.LIST_ITEM)
        self.assertEqual(babb.sarg, "**")
        self.assertEqual(babb.children, [" item1.2\n"])
        self.assertEqual(bb.kind, NodeKind.LIST_ITEM)
        self.assertEqual(bb.sarg, "*")
        self.assertEqual(bb.children, [" item2\n"])

    def test_ol(self):
        tree = self.parse(
            "test", "foo\n\n# item1\n##item1.1\n## item1.2\n" "# item2\n"
        )
        self.assertEqual(len(tree.children), 2)
        a, b = tree.children
        self.assertEqual(a, "foo\n\n")
        self.assertEqual(b.kind, NodeKind.LIST)
        self.assertEqual(b.sarg, "#")
        self.assertEqual(len(b.children), 2)
        ba, bb = b.children
        self.assertEqual(ba.kind, NodeKind.LIST_ITEM)
        self.assertEqual(ba.sarg, "#")
        self.assertEqual(len(ba.children), 2)
        baa, bab = ba.children
        self.assertEqual(baa, " item1\n")
        self.assertEqual(bab.kind, NodeKind.LIST)
        self.assertEqual(bab.sarg, "##")
        self.assertEqual(len(bab.children), 2)
        baba, babb = bab.children
        self.assertEqual(baba.kind, NodeKind.LIST_ITEM)
        self.assertEqual(baba.sarg, "##")
        self.assertEqual(baba.children, ["item1.1\n"])
        self.assertEqual(babb.kind, NodeKind.LIST_ITEM)
        self.assertEqual(babb.sarg, "##")
        self.assertEqual(babb.children, [" item1.2\n"])
        self.assertEqual(bb.kind, NodeKind.LIST_ITEM)
        self.assertEqual(bb.sarg, "#")
        self.assertEqual(bb.children, [" item2\n"])

    def test_dl(self):
        tree = self.parse(
            "test",
            """; Mixed definition lists
; item 1 : definition
:; sub-item 1 plus term
:: two colons plus definition
:; sub-item 2 : colon plus definition
; item 2
: back to the main list
""",
        )
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.LIST)
        self.assertEqual(t.sarg, ";")
        self.assertIsNone(t.temp_head)
        self.assertIsNone(t.definition)
        self.assertEqual(len(t.children), 3)
        a, b, c = t.children
        self.assertEqual(a.kind, NodeKind.LIST_ITEM)
        self.assertEqual(a.sarg, ";")
        self.assertEqual(a.children, [" Mixed definition lists\n"])
        self.assertEqual(a.attrs, {})
        self.assertEqual(b.kind, NodeKind.LIST_ITEM)
        self.assertEqual(b.sarg, ";")
        self.assertEqual(b.children, [" item 1 "])
        self.assertIsNone(b.temp_head)
        self.assertIsNotNone(len(b.definition))
        bdef = b.definition
        self.assertEqual(len(bdef), 2)
        self.assertEqual(bdef[0], " definition\n")
        bdef1 = bdef[1]
        self.assertEqual(bdef1.kind, NodeKind.LIST)
        self.assertEqual(bdef1.sarg, ":;")
        self.assertIsNone(bdef1.temp_head)
        self.assertIsNone(bdef1.definition)
        self.assertEqual(len(bdef1.children), 2)
        bdef1a, bdef1b = bdef1.children
        self.assertEqual(bdef1a.kind, NodeKind.LIST_ITEM)
        self.assertEqual(bdef1a.sarg, ":;")
        self.assertEqual(bdef1a.children, [" sub-item 1 plus term\n"])
        self.assertIsNone(bdef1a.temp_head)
        self.assertEqual(bdef1a.definition, [" two colons plus definition\n"])
        self.assertEqual(bdef1b.kind, NodeKind.LIST_ITEM)
        self.assertEqual(bdef1b.sarg, ":;")
        self.assertEqual(bdef1b.children, [" sub-item 2 "])
        self.assertIsNone(bdef1b.temp_head)
        self.assertEqual(bdef1b.definition, [" colon plus definition\n"])
        self.assertEqual(c.kind, NodeKind.LIST_ITEM)
        self.assertEqual(c.sarg, ";")
        self.assertIsNone(c.temp_head)
        self.assertEqual(c.definition, [" back to the main list\n"])
        self.assertEqual(c.children, [" item 2\n"])

    # Disabling this test after changing some list behavior.
    # https://github.com/tatuylonen/wikitextprocessor/issues/84
    # Instead of appending "continued items" to parent node as an
    # exception, just let it generate a `...#:` list with list-items;
    # these can be interpreted by the user in Wiktextract later on,
    # and the appending can be done done.
    #     def test_list_cont1(self):
    #         tree = self.parse("test", """#list item A1
    # ##list item B1
    # ##list item B2
    # #:continuing list item A1
    # #list item A2
    # """)
    #         print_tree(tree, 2)
    #         self.assertEqual(len(tree.children), 1)
    #         t = tree.children[0]
    #         self.assertEqual(t.kind, NodeKind.LIST)
    #         self.assertEqual(len(t.children), 2)
    #         a, b = t.children
    #         self.assertEqual(a.kind, NodeKind.LIST_ITEM)
    #         self.assertEqual(a.sarg, "#")
    #         self.assertEqual(len(a.children), 3)
    #         aa, ab, ac = a.children
    #         self.assertEqual(aa, "list item A1\n")
    #         self.assertEqual(ab.kind, NodeKind.LIST)
    #         self.assertEqual(ab.sarg, "##")
    #         self.assertEqual(len(ab.children), 2)
    #         aba, abb = ab.children
    #         self.assertEqual(aba.kind, NodeKind.LIST_ITEM)
    #         self.assertEqual(aba.sarg, "##")
    #         self.assertEqual(aba.children, ["list item B1\n"])
    #         self.assertEqual(abb.kind, NodeKind.LIST_ITEM)
    #         self.assertEqual(abb.sarg, "##")
    #         self.assertEqual(abb.children, ["list item B2\n"])
    #         self.assertEqual(ac, "continuing list item A1\n")
    #         self.assertEqual(b.kind, NodeKind.LIST_ITEM)
    #         self.assertEqual(b.sarg, "#")
    #         self.assertEqual(b.children, ["list item A2\n"])

    def test_list_cont2(self):
        tree = self.parse(
            "test",
            """# list item
   A1
#list item B1
""",
        )
        self.assertEqual(len(tree.children), 3)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.LIST)
        self.assertEqual(len(t.children), 1)
        a = t.children[0]
        t2 = tree.children[2]
        self.assertEqual(t.kind, NodeKind.LIST)
        self.assertEqual(len(t2.children), 1)
        b = t2.children[0]
        self.assertEqual(a.kind, NodeKind.LIST_ITEM)
        self.assertEqual(a.children, [" list item\n"])
        self.assertEqual(b.kind, NodeKind.LIST_ITEM)
        self.assertEqual(b.children, ["list item B1\n"])

    def test_list_cont3(self):
        tree = self.parse("test", """# list item\n#: sub-item\n""")
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.LIST)
        self.assertEqual(len(t.children), 1)
        a = t.children[0]
        self.assertEqual(a.kind, NodeKind.LIST_ITEM)
        self.assertEqual(len(a.children), 2)
        b, c = a.children
        self.assertEqual(b, " list item\n")
        self.assertEqual(c.kind, NodeKind.LIST)

    def test_listend1(self):
        tree = self.parse("test", "# item1\nFoo\n")
        self.assertEqual(len(tree.children), 2)
        a, b = tree.children
        self.assertEqual(a.kind, NodeKind.LIST)
        self.assertEqual(a.sarg, "#")
        self.assertEqual(len(a.children), 1)
        aa = a.children[0]
        self.assertEqual(aa.kind, NodeKind.LIST_ITEM)
        self.assertEqual(aa.sarg, "#")
        self.assertEqual(aa.children, [" item1\n"])
        self.assertEqual(b, "Foo\n")

    # This test is wrong. Disabled.
    # def test_listend2(self):
    #     tree = self.parse("test", "#\nitem1\nFoo\n")
    #     self.assertEqual(len(tree.children), 2)
    #     a, b = tree.children
    #     self.assertEqual(a.kind, NodeKind.LIST)
    #     self.assertEqual(a.sarg, "#")
    #     self.assertEqual(len(a.children), 1)
    #     aa = a.children[0]
    #     self.assertEqual(aa.kind, NodeKind.LIST_ITEM)
    #     self.assertEqual(aa.sarg, "#")
    #     self.assertEqual(aa.children, ["\nitem1\n"])
    #     self.assertEqual(b, "Foo\n")

    def test_liststart1(self):
        tree = self.parse("test", "==Foo==\n#item1")
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.LEVEL2)
        self.assertEqual(t.largs, [["Foo"]])
        self.assertEqual(len(t.children), 2)
        x, a = t.children
        self.assertEqual(x, "\n")
        self.assertEqual(a.kind, NodeKind.LIST)
        self.assertEqual(a.sarg, "#")
        self.assertEqual(len(a.children), 1)
        b = a.children[0]
        self.assertEqual(b.kind, NodeKind.LIST_ITEM)
        self.assertEqual(b.sarg, "#")
        self.assertEqual(b.children, ["item1"])

    def test_liststart2(self):
        # Lists should not be parsed inside template arguments
        tree = self.parse("test", "{{Foo|\n#item1}}")
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TEMPLATE)
        self.assertEqual(t.children, [])
        self.assertEqual(len(t.largs), 2)
        a, b = t.largs
        self.assertEqual(a, ["Foo"])
        self.assertEqual(b, ["\n#item1"])

    def test_link1(self):
        tree = self.parse("test", "a [[Main Page]] b")
        self.assertEqual(len(tree.children), 3)
        a, b, c = tree.children
        self.assertEqual(a, "a ")
        self.assertEqual(b.kind, NodeKind.LINK)
        self.assertEqual(b.largs, [["Main Page"]])
        self.assertEqual(b.children, [])
        self.assertEqual(c, " b")

    def test_link2(self):
        tree = self.parse("test", "[[Help:Contents]]")
        self.assertEqual(len(tree.children), 1)
        p = tree.children[0]
        self.assertEqual(p.kind, NodeKind.LINK)
        self.assertEqual(p.largs, [["Help:Contents"]])
        self.assertEqual(p.children, [])

    def test_link3(self):
        tree = self.parse("test", "[[#See also|different text]]")
        self.assertEqual(len(tree.children), 1)
        p = tree.children[0]
        self.assertEqual(p.kind, NodeKind.LINK)
        self.assertEqual(p.largs, [["#See also"], ["different text"]])
        self.assertEqual(p.children, [])

    def test_link4(self):
        tree = self.parse("test", "[[User:John Doe|]]")
        self.assertEqual(len(tree.children), 1)
        p = tree.children[0]
        self.assertEqual(p.kind, NodeKind.LINK)
        self.assertEqual(p.largs, [["User:John Doe"], []])
        self.assertEqual(p.children, [])

    def test_link5(self):
        tree = self.parse("test", "[[Help]]<nowiki />ful advise")
        self.assertEqual(len(tree.children), 2)
        a, b = tree.children
        self.assertEqual(a.kind, NodeKind.LINK)
        self.assertEqual(a.largs, [["Help"]])
        self.assertEqual(a.children, [])
        self.assertEqual(b, "<nowiki />ful advise")

    def test_link6(self):
        tree = self.parse("test", "[[of [[musk]]]]")
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        self.assertEqual(self.ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        a = tree.children[0]
        self.assertEqual(a.kind, NodeKind.LINK)
        b = a.largs[0][-1]
        self.assertEqual(b.kind, NodeKind.LINK)

    def test_link7(self):
        tree = self.parse("test", "[[foo|bar}}}]]")
        link = tree.children[0]
        self.assertEqual(link.kind, NodeKind.LINK)
        self.assertEqual(link.largs, [["foo"], ["bar}}}"]])

    def test_link8(self):
        tree = self.parse("test", "[[foo| bar] ]]")
        # print_tree(tree)
        link = tree.children[0]
        self.assertEqual(link.kind, NodeKind.LINK)
        self.assertEqual(link.largs, [["foo"], [" bar] "]])

    def test_link9(self):
        tree = self.parse("test", "[[foo| [bar]]")
        # print_tree(tree)
        link = tree.children[0]
        self.assertEqual(link.kind, NodeKind.LINK)
        self.assertEqual(link.largs, [["foo"], [" [bar"]])

    def test_link10(self):
        tree = self.parse("test", "[[foo| [bar] ]]")
        # print_tree(tree)
        link = tree.children[0]
        self.assertEqual(link.kind, NodeKind.LINK)
        self.assertEqual(link.largs, [["foo"], [" [bar] "]])

    # def test_link11(self):
    # I can't get this to work. Our parser is too different from how
    # wikimedia does it.
    #     tree = self.parse("test", "[[foo| [bar]]]")
    #     print_tree(tree)
    #     link = tree.children[0]
    #     self.assertEqual(link.kind, NodeKind.LINK)
    #     self.assertEqual(link.largs, [["foo"], [" [bar]"]])

    def test_link12(self):
        # Apparently, the text portion of a link is allowed newlines, after
        # the | pipe.
        tree = self.parse("test", "[[foo|\n[bar]]")
        # print_tree(tree)
        link = tree.children[0]
        self.assertEqual(link.kind, NodeKind.LINK)
        self.assertEqual(link.largs, [["foo"], ["\n[bar"]])

    def test_link_trailing(self):
        tree = self.parse("test", "[[Help]]ing heal")
        self.assertEqual(len(tree.children), 2)
        a, b = tree.children
        self.assertEqual(a.kind, NodeKind.LINK)
        self.assertEqual(a.largs, [["Help"]])
        self.assertEqual(a.children, ["ing"])
        self.assertEqual(b, " heal")

    def test_url1(self):
        tree = self.parse("test", "this https://wikipedia.com link")
        self.assertEqual(len(tree.children), 3)
        a, b, c = tree.children
        self.assertEqual(a, "this ")
        self.assertEqual(b.kind, NodeKind.URL)
        self.assertEqual(b.largs, [["https://wikipedia.com"]])
        self.assertEqual(b.children, [])
        self.assertEqual(c, " link")

    def test_url2(self):
        tree = self.parse("test", "this [https://wikipedia.com] link")
        self.assertEqual(len(tree.children), 3)
        a, b, c = tree.children
        self.assertEqual(a, "this ")
        self.assertEqual(b.kind, NodeKind.URL)
        self.assertEqual(b.largs, [["https://wikipedia.com"]])
        self.assertEqual(b.children, [])
        self.assertEqual(c, " link")

    def test_url3(self):
        tree = self.parse("test", "this [https://wikipedia.com here] link")
        self.assertEqual(len(tree.children), 3)
        a, b, c = tree.children
        self.assertEqual(a, "this ")
        self.assertEqual(b.kind, NodeKind.URL)
        self.assertEqual(b.largs, [["https://wikipedia.com"], ["here"]])
        self.assertEqual(b.children, [])
        self.assertEqual(c, " link")

    def test_url4(self):
        tree = self.parse(
            "test", "this [https://wikipedia.com here multiword] link"
        )
        self.assertEqual(len(tree.children), 3)
        a, b, c = tree.children
        self.assertEqual(a, "this ")
        self.assertEqual(b.kind, NodeKind.URL)
        self.assertEqual(
            b.largs, [["https://wikipedia.com"], ["here multiword"]]
        )
        self.assertEqual(b.children, [])
        self.assertEqual(c, " link")

    def test_url5(self):
        tree = self.parse("test", "<ref>https://wiktionary.org</ref>")
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        self.assertEqual(self.ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        a = tree.children[0]
        self.assertEqual(a.kind, NodeKind.HTML)
        self.assertEqual(len(a.children), 1)
        b = a.children[0]
        self.assertEqual(b.kind, NodeKind.URL)
        self.assertEqual(b.largs, [["https://wiktionary.org"]])

    def test_url6(self):
        tree = self.parse("test", "Ed[ward] Foo")
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        self.assertEqual(self.ctx.debugs, [])
        self.assertEqual(tree.children, ["Ed[ward] Foo"])

    def test_url7(self):
        """External url entities should start with a valid url prefix"""
        tree = self.parse("test", """[foo]""")
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        self.assertEqual(self.ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        self.assertEqual(tree.children[0], "[foo]")

    def test_url8(self):
        tree = self.parse(
            "test",
            """[foo
]""",
        )
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        self.assertEqual(self.ctx.debugs, [])
        self.assertEqual(tree.children, ["[foo\n]"])

    def test_url9(self):
        """External url entities should not contain newlines.
        but the url itself becomes a url entity sandwiched by
        the strings."""
        tree = self.parse(
            "test",
            """[https://foo
bar]""",
        )
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        self.assertEqual(self.ctx.debugs, [])
        self.assertEqual(len(tree.children), 3)
        self.assertEqual(tree.children[0], "[")
        self.assertEqual(tree.children[2], "\nbar]")
        self.assertEqual(tree.children[1].kind, NodeKind.URL)
        self.assertEqual(tree.children[1].largs, [["https://foo"]])

    def test_url10(self):
        tree = self.parse("test", """[https://foo""")
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        self.assertEqual(self.ctx.debugs, [])
        self.assertEqual(len(tree.children), 2)
        self.assertEqual(tree.children[0], "[")
        self.assertEqual(tree.children[1].kind, NodeKind.URL)
        self.assertEqual(tree.children[1].largs, [["https://foo"]])

    def test_url11(self):
        # TECHNICALLY this should result in the URL entity and
        # the LINK element to be sibling nodes (Wikimedia parser
        # untangles nested <a>-elements in this case, which is sensible),
        # but for purposes of our parser that could be assigned to a
        # post-processing step if needed. Keeping the parse tree intact
        # like this lets you reverse the parsing easier.
        tree = self.parse("test", """[https://foo [[bar]]]""")
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        self.assertEqual(self.ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        url_node = tree.children[0]
        self.assertEqual(url_node.kind, NodeKind.URL)
        url_str = url_node.largs[0][0]
        self.assertEqual(url_str, "https://foo")
        link_node = url_node.largs[1][0]
        self.assertEqual(link_node.kind, NodeKind.LINK)
        self.assertEqual(link_node.largs, [["bar"]])

    def test_preformatted1(self):
        tree = self.parse(
            "test",
            """
 Start each line with a space.
 Text is '''preformatted''' and
 markups can be done.
Next para""",
        )
        self.assertEqual(len(tree.children), 3)
        self.assertEqual(tree.children[0], "\n")
        p = tree.children[1]
        self.assertEqual(p.kind, NodeKind.PREFORMATTED)
        a, b, c = p.children
        self.assertEqual(a, " Start each line with a space.\n Text is ")
        self.assertEqual(b.kind, NodeKind.BOLD)
        self.assertEqual(b.children, ["preformatted"])
        self.assertEqual(c, " and\n markups can be done.\n")
        self.assertEqual(tree.children[2], "Next para")

    def test_preformatted2(self):
        tree = self.parse(
            "test",
            """
 <nowiki>
def foo(x):
  print(x)
</nowiki>""",
        )
        self.assertEqual(len(tree.children), 2)
        self.assertEqual(tree.children[0], "\n")
        p = tree.children[1]
        self.assertEqual(p.kind, NodeKind.PREFORMATTED)
        self.assertEqual(p.children, [" \ndef foo(x)&colon;\n  print(x)\n"])

    def test_pre1(self):
        tree = self.parse(
            "test",
            """\n<PRE>preformatted &amp; '''not bold''' text</pre> after""",
        )
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        self.assertEqual(self.ctx.debugs, [])
        self.assertEqual(len(tree.children), 3)
        a, b, c = tree.children
        self.assertEqual(a, "\n")
        self.assertEqual(b.kind, NodeKind.PRE)
        self.assertEqual(b.children, ["preformatted &amp; '''not bold''' text"])
        self.assertEqual(c, " after")

    def test_pre2(self):
        tree = self.parse(
            "test", """<PRE style="color: red">line1\nline2</pre>"""
        )
        self.assertEqual(len(tree.children), 1)
        h = tree.children[0]
        self.assertEqual(h.kind, NodeKind.PRE)
        self.assertEqual(h.largs, [])
        self.assertEqual(h.sarg, "")
        self.assertEqual(h.attrs.get("_close", False), False)
        self.assertEqual(h.attrs.get("_also_close", False), False)
        self.assertEqual(h.attrs.get("style", False), "color: red")

    def test_pre3(self):
        tree = self.parse(
            "test", """<PRE style="color: red">line1\n  line2</pre>"""
        )
        self.assertEqual(len(tree.children), 1)
        h = tree.children[0]
        self.assertEqual(h.kind, NodeKind.PRE)
        self.assertEqual(h.largs, [])
        self.assertEqual(h.sarg, "")
        self.assertEqual(h.attrs.get("_close", False), False)
        self.assertEqual(h.attrs.get("_also_close", False), False)
        self.assertEqual(h.attrs.get("style", False), "color: red")
        self.assertEqual(h.children, ["line1\n  line2"])

    # XXX reconsider how pre should work.
    # def test_pre3(self):
    #     tree = self.parse("test", """<pre>The <pre> tag ignores [[wiki]] ''markup'' as does the <nowiki>tag</nowiki>.</pre>""")  # noqa: E501
    #     self.assertEqual(len(tree.children), 1)
    #     a = tree.children[0]
    #     self.assertEqual(a.kind, NodeKind.PRE)
    #     self.assertEqual(a.children,
    #                      ["The &lt;pre&gt; tag ignores &lbsqb;&lsqb;wiki"
    #                       "&rsqb;&rsqb; &apos;&apos;markup&apos;&apos; as "
    #                       "does the &lt;nowiki&gt;tag&lt;/nowiki&gt;."])

    def test_comment1(self):
        tree = self.parse("test", "foo<!-- not\nshown-->bar")
        self.assertEqual(tree.children, ["foobar"])

    def test_comment2(self):
        tree = self.parse(
            "test", "foo<!-- not\nshown-->bar <!-- second --> now"
        )
        self.assertEqual(tree.children, ["foobar  now"])

    def test_comment3(self):
        tree = self.parse("test", "fo<nowiki>o<!-- not\nshown-->b</nowiki>ar")
        self.assertEqual(tree.children, ["foo&lt;&excl;-- not\nshown--&gt;bar"])

    def test_magicword1(self):
        tree = self.parse("test", "a __NOTOC__ b")
        self.assertEqual(len(tree.children), 3)
        a, b, c = tree.children
        self.assertEqual(a, "a ")
        self.assertEqual(b.kind, NodeKind.MAGIC_WORD)
        self.assertEqual(b.sarg, "__NOTOC__")
        self.assertEqual(b.children, [])
        self.assertEqual(c, " b")

    def test_template1(self):
        tree = self.parse("test", "a{{foo}}b")
        self.assertEqual(len(tree.children), 3)
        a, b, c = tree.children
        self.assertEqual(a, "a")
        self.assertEqual(b.kind, NodeKind.TEMPLATE)
        self.assertEqual(b.largs, [["foo"]])
        self.assertEqual(b.children, [])
        self.assertEqual(c, "b")

    def test_template2(self):
        tree = self.parse("test", "{{foo|bar||z|1-1/2|}}")
        self.assertEqual(len(tree.children), 1)
        node = tree.children[0]
        self.assertTrue(isinstance(node, TemplateNode))
        self.assertEqual(node.kind, NodeKind.TEMPLATE)
        self.assertEqual(
            node.largs, [["foo"], ["bar"], [], ["z"], ["1-1/2"], []]
        )
        self.assertEqual(node.children, [])
        self.assertEqual(node.template_name, "foo")
        self.assertEqual(
            node.template_parameters,
            {1: "bar", 2: "", 3: "z", 4: "1-1/2", 5: ""},
        )

    def test_template3(self):
        tree = self.parse("test", "{{\nfoo\n|\nname=testi|bar\n|\nbaz}}")
        self.assertEqual(len(tree.children), 1)
        node = tree.children[0]
        self.assertTrue(isinstance(node, TemplateNode))
        self.assertEqual(node.kind, NodeKind.TEMPLATE)
        self.assertEqual(
            node.largs, [["\nfoo\n"], ["\nname=testi"], ["bar\n"], ["\nbaz"]]
        )
        self.assertEqual(node.children, [])
        self.assertEqual(node.template_name, "foo")
        self.assertEqual(
            node.template_parameters, {"name": "testi", 1: "bar\n", 2: "\nbaz"}
        )

    def test_template4(self):
        tree = self.parse("test", "{{foo bar|name=test word|tässä}}")
        self.assertEqual(len(tree.children), 1)
        b = tree.children[0]
        self.assertEqual(b.kind, NodeKind.TEMPLATE)
        self.assertEqual(b.largs, [["foo bar"], ["name=test word"], ["tässä"]])
        self.assertEqual(b.children, [])

    def test_template5(self):
        tree = self.parse("test", "{{foo bar|name=test word|tässä}}")
        self.assertEqual(len(tree.children), 1)
        b = tree.children[0]
        self.assertEqual(b.kind, NodeKind.TEMPLATE)
        self.assertEqual(b.largs, [["foo bar"], ["name=test word"], ["tässä"]])
        self.assertEqual(b.children, [])

    def test_template6(self):
        tree = self.parse("test", "{{foo bar|{{nested|[[link]]}}}}")
        self.assertEqual(len(tree.children), 1)
        b = tree.children[0]
        self.assertEqual(b.kind, NodeKind.TEMPLATE)
        self.assertEqual(len(b.largs), 2)
        self.assertEqual(b.largs[0], ["foo bar"])
        c = b.largs[1]
        self.assertIsInstance(c, list)
        self.assertEqual(len(c), 1)
        d = c[0]
        self.assertEqual(d.kind, NodeKind.TEMPLATE)
        self.assertEqual(len(d.largs), 2)
        self.assertEqual(d.largs[0], ["nested"])
        self.assertEqual(len(d.largs[1]), 1)
        e = d.largs[1][0]
        self.assertEqual(e.kind, NodeKind.LINK)
        self.assertEqual(e.largs, [["link"]])

    def test_template7(self):
        tree = self.parse("test", "{{{{{foo}}}|bar}}")
        self.assertEqual(len(tree.children), 1)
        b = tree.children[0]
        self.assertEqual(b.kind, NodeKind.TEMPLATE)
        self.assertEqual(len(b.largs), 2)
        c = b.largs[0]
        self.assertIsInstance(c, list)
        self.assertEqual(len(c), 1)
        d = c[0]
        self.assertEqual(d.kind, NodeKind.TEMPLATE_ARG)
        self.assertEqual(d.largs, [["foo"]])
        self.assertEqual(d.children, [])
        self.assertEqual(b.largs[1], ["bar"])

    def test_template8(self):
        # Namespace specifiers, e.g., {{int:xyz}} should not generate
        # parser functions
        tree = self.parse("test", "{{int:xyz}}")
        self.assertEqual(len(tree.children), 1)
        b = tree.children[0]
        self.assertEqual(b.kind, NodeKind.TEMPLATE)
        self.assertEqual(b.largs, [["int:xyz"]])

    def test_template9(self):
        # Main namespace references, e.g., {{:xyz}} should not
        # generate parser functions
        tree = self.parse("test", "{{:xyz}}")
        self.assertEqual(len(tree.children), 1)
        b = tree.children[0]
        self.assertEqual(b.kind, NodeKind.TEMPLATE)
        self.assertEqual(b.largs, [[":xyz"]])

    def test_template10(self):
        tree = self.parse("test", "{{{{a}} }}")
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TEMPLATE)
        self.assertEqual(t.children, [])
        self.assertEqual(len(t.largs), 1)
        tt = t.largs[0][0]
        self.assertEqual(tt.kind, NodeKind.TEMPLATE)
        self.assertEqual(tt.largs, [["a"]])
        self.assertEqual(tt.children, [])

    def test_template11(self):
        tree = self.parse("test", "{{{{{a}}}}}")
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TEMPLATE)
        self.assertEqual(t.children, [])
        self.assertEqual(len(t.largs), 1)
        tt = t.largs[0][0]
        self.assertEqual(tt.kind, NodeKind.TEMPLATE_ARG)
        self.assertEqual(tt.largs, [["a"]])
        self.assertEqual(tt.children, [])

    def test_template12(self):
        tree = self.parse("test", "{{{{{a|}}}}}")
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TEMPLATE)
        self.assertEqual(t.children, [])
        self.assertEqual(len(t.largs), 1)
        tt = t.largs[0][0]
        self.assertEqual(tt.kind, NodeKind.TEMPLATE_ARG)
        self.assertEqual(tt.largs, [["a"], []])
        self.assertEqual(tt.children, [])

    def test_template13(self):
        tree = self.parse("test", "{{ {{a|}}}}")
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TEMPLATE)
        self.assertEqual(t.children, [])
        self.assertEqual(len(t.largs), 1)
        self.assertEqual(t.largs[0][0], " ")
        tt = t.largs[0][1]
        self.assertEqual(tt.kind, NodeKind.TEMPLATE)
        self.assertEqual(tt.largs, [["a"], []])
        self.assertEqual(tt.children, [])

    def test_template14(self):
        tree = self.parse("test", "{{x|[}}")
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        self.assertEqual(self.ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TEMPLATE)
        self.assertEqual(t.children, [])
        self.assertEqual(t.largs, [["x"], ["["]])

    def test_template15(self):
        tree = self.parse("test", "{{x|]}}")
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        self.assertEqual(self.ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TEMPLATE)
        self.assertEqual(t.children, [])
        self.assertEqual(t.largs, [["x"], ["]"]])

    def test_template16(self):
        # This example is from Wiktionary: Unsupported titles/Less than three
        tree = self.parse("test", "{{x|<3}}")
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        self.assertEqual(self.ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TEMPLATE)
        self.assertEqual(t.children, [])
        self.assertEqual(t.largs, [["x"], ["<3"]])

    def test_template17(self):
        tree = self.parse("test", "{{x|3>}}")
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        self.assertEqual(self.ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TEMPLATE)
        self.assertEqual(t.children, [])
        self.assertEqual(t.largs, [["x"], ["3>"]])

    def test_template18(self):
        tree = self.parse("test", "{{foo|name={{bar}}|foo}}")
        node = tree.children[0]
        self.assertTrue(isinstance(node, TemplateNode))
        self.assertEqual(node.template_name, "foo")
        parameters = node.template_parameters
        named_parameter = parameters["name"]
        self.assertEqual(named_parameter.template_name, "bar")
        self.assertEqual(parameters[1], "foo")

    def test_templatevar1(self):
        tree = self.parse("test", "{{{foo}}}")
        self.assertEqual(len(tree.children), 1)
        b = tree.children[0]
        self.assertEqual(b.kind, NodeKind.TEMPLATE_ARG)
        self.assertEqual(b.largs, [["foo"]])
        self.assertEqual(b.children, [])

    def test_templatevar2(self):
        tree = self.parse("test", "{{{foo|bar|baz}}}")
        self.assertEqual(len(tree.children), 1)
        b = tree.children[0]
        self.assertEqual(b.kind, NodeKind.TEMPLATE_ARG)
        self.assertEqual(b.largs, [["foo"], ["bar"], ["baz"]])
        self.assertEqual(b.children, [])

    def test_templatevar3(self):
        tree = self.parse("test", "{{{{{{foo}}}|bar|baz}}}")
        self.assertEqual(len(tree.children), 1)
        b = tree.children[0]
        self.assertEqual(b.kind, NodeKind.TEMPLATE_ARG)
        c = b.largs[0][0]
        self.assertEqual(c.kind, NodeKind.TEMPLATE_ARG)
        self.assertEqual(c.largs, [["foo"]])
        self.assertEqual(b.largs[1:], [["bar"], ["baz"]])
        self.assertEqual(b.children, [])

    def test_templatevar4(self):
        tree = self.parse("test", "{{{{{{1}}}}}}")
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TEMPLATE_ARG)
        self.assertEqual(t.children, [])
        self.assertEqual(len(t.largs), 1)
        tt = t.largs[0][0]
        self.assertEqual(tt.kind, NodeKind.TEMPLATE_ARG)
        self.assertEqual(tt.largs, [["1"]])
        self.assertEqual(tt.children, [])

    def test_templatevar5(self):
        tree = self.parse("test", "{{{{{{1|}}}}}}")
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TEMPLATE_ARG)
        self.assertEqual(t.children, [])
        self.assertEqual(len(t.largs), 1)
        tt = t.largs[0][0]
        self.assertEqual(tt.kind, NodeKind.TEMPLATE_ARG)
        self.assertEqual(tt.largs, [["1"], []])
        self.assertEqual(tt.children, [])

    # def test_templatevar6(self):
    # This is difficult to test in sandbox mode on the Wiki side, because
    # there will never be an argument called "foo[" or anything with a
    # a reserved character...
    #     tree = self.parse("test", "{{{foo[}}}")
    #     self.assertEqual(len(tree.children), 1)
    #     b = tree.children[0]
    #     self.assertEqual(b.kind, NodeKind.TEMPLATE_ARG)
    #     self.assertEqual(b.largs, [["foo["]])
    #     self.assertEqual(b.children, [])

    def test_parserfn1(self):
        tree = self.parse("test", "{{CURRENTYEAR}}x")
        self.assertEqual(len(tree.children), 2)
        b = tree.children[0]
        self.assertEqual(b.kind, NodeKind.PARSER_FN)
        self.assertEqual(b.largs, [["CURRENTYEAR"]])
        self.assertEqual(b.children, [])
        self.assertEqual(tree.children[1], "x")

    def test_parserfn2(self):
        tree = self.parse("test", "{{PAGESIZE:TestPage}}")
        self.assertEqual(len(tree.children), 1)
        b = tree.children[0]
        self.assertEqual(b.kind, NodeKind.PARSER_FN)
        self.assertEqual(b.largs, [["PAGESIZE"], ["TestPage"]])
        self.assertEqual(b.children, [])

    def test_parserfn3(self):
        tree = self.parse(
            "test", "{{#invoke:testmod|testfn|testarg1|testarg2}}"
        )
        self.assertEqual(len(tree.children), 1)
        b = tree.children[0]
        self.assertEqual(b.kind, NodeKind.PARSER_FN)
        self.assertEqual(
            b.largs,
            [["#invoke"], ["testmod"], ["testfn"], ["testarg1"], ["testarg2"]],
        )
        self.assertEqual(b.children, [])

    def test_table_empty(self):
        tree = self.parse("test", "{| \n |}")
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TABLE)
        self.assertEqual(t.largs, [])
        self.assertEqual(t.sarg, "")
        self.assertEqual(t.children, [])

    def test_table_simple(self):
        tree = self.parse(
            "test", "{|\n|Orange||Apple||more\n|-\n|Bread||Pie||more\n|}"
        )
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TABLE)
        self.assertEqual(t.largs, [])
        self.assertEqual(t.sarg, "")
        self.assertEqual(len(t.children), 2)
        a, b = t.children
        self.assertEqual(a.kind, NodeKind.TABLE_ROW)
        self.assertEqual(len(a.children), 3)
        aa, ab, ac = a.children
        self.assertEqual(aa.kind, NodeKind.TABLE_CELL)
        self.assertEqual(aa.children, ["Orange"])
        self.assertEqual(ab.kind, NodeKind.TABLE_CELL)
        self.assertEqual(ab.children, ["Apple"])
        self.assertEqual(ac.kind, NodeKind.TABLE_CELL)
        self.assertEqual(ac.children, ["more\n"])
        self.assertEqual(len(b.children), 3)
        ba, bb, bc = b.children
        self.assertEqual(ba.kind, NodeKind.TABLE_CELL)
        self.assertEqual(ba.children, ["Bread"])
        self.assertEqual(bb.kind, NodeKind.TABLE_CELL)
        self.assertEqual(bb.children, ["Pie"])
        self.assertEqual(bc.kind, NodeKind.TABLE_CELL)
        self.assertEqual(bc.children, ["more\n"])

    def test_table_simple2(self):
        tree = self.parse(
            "test", "{|\n|-\n|Orange||Apple||more\n|-\n|Bread||Pie||more\n|}"
        )
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TABLE)
        self.assertEqual(t.largs, [])
        self.assertEqual(t.sarg, "")
        self.assertEqual(len(t.children), 2)
        a, b = t.children
        self.assertEqual(a.kind, NodeKind.TABLE_ROW)
        self.assertEqual(len(a.children), 3)
        aa, ab, ac = a.children
        self.assertEqual(aa.kind, NodeKind.TABLE_CELL)
        self.assertEqual(aa.children, ["Orange"])
        self.assertEqual(ab.kind, NodeKind.TABLE_CELL)
        self.assertEqual(ab.children, ["Apple"])
        self.assertEqual(ac.kind, NodeKind.TABLE_CELL)
        self.assertEqual(ac.children, ["more\n"])
        self.assertEqual(len(b.children), 3)
        ba, bb, bc = b.children
        self.assertEqual(ba.kind, NodeKind.TABLE_CELL)
        self.assertEqual(ba.children, ["Bread"])
        self.assertEqual(bb.kind, NodeKind.TABLE_CELL)
        self.assertEqual(bb.children, ["Pie"])
        self.assertEqual(bc.kind, NodeKind.TABLE_CELL)
        self.assertEqual(bc.children, ["more\n"])

    def test_table_simple3(self):
        tree = self.parse("test", "{|\n\t|Cell\n|}")
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TABLE)
        self.assertEqual(len(t.children), 1)
        a = t.children[0]
        self.assertEqual(a.kind, NodeKind.TABLE_ROW)
        self.assertEqual(len(a.children), 1)
        b = a.children[0]
        self.assertEqual(b.kind, NodeKind.TABLE_CELL)
        self.assertEqual(b.children, ["Cell\n"])

    def test_table_simple4(self):
        tree = self.parse("test", "{|\n\t!Cell\n|}")
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TABLE)
        self.assertEqual(len(t.children), 1)
        a = t.children[0]
        self.assertEqual(a.kind, NodeKind.TABLE_ROW)
        self.assertEqual(len(a.children), 1)
        b = a.children[0]
        self.assertEqual(b.kind, NodeKind.TABLE_HEADER_CELL)
        self.assertEqual(b.children, ["Cell\n"])

    def test_html_in_link1(self):
        """Tests for a bug where HTML tags inside LINKs broke things."""
        tree = self.parse("test", """[[foo|<b>bar</b>]]""", expand_all=True)
        self.assertEqual(tree.kind, NodeKind.ROOT)
        lnk = tree.children[0]
        self.assertEqual(lnk.kind, NodeKind.LINK)
        lnkargs = lnk.largs
        self.assertEqual(lnkargs[0][0], "foo")
        self.assertEqual(lnkargs[1][0].kind, NodeKind.HTML)
        self.assertEqual(lnkargs[1][0].children[0], "bar")

    def test_html_in_link2(self):
        # expand_all=True here causes the #if-template to be parsed away,
        # and parses the HTML inside the LINK. Without it, the parse-tree
        # would still have an outer node for the #if and the HTML would
        # be just the string '<b>ppp</b>'.
        tree = self.parse(
            "test", """{{#if:x|[[foo|<b>ppp</b>]] bar}}""", expand_all=True
        )
        # print_tree(tree, 2)
        self.assertEqual(tree.kind, NodeKind.ROOT)
        lnk = tree.children[0]
        lnkargs = lnk.largs
        self.assertEqual(lnkargs[0][0], "foo")
        self.assertEqual(lnkargs[1][0].kind, NodeKind.HTML)
        self.assertEqual(lnkargs[1][0].children[0], "ppp")
        self.assertEqual(tree.children[1], " bar")

    def test_table_hdr1(self):
        tree = self.parse("test", "{|\n!Header\n|}")
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TABLE)
        self.assertEqual(len(t.children), 1)
        a = t.children[0]
        self.assertEqual(a.kind, NodeKind.TABLE_ROW)
        self.assertEqual(len(a.children), 1)
        b = a.children[0]
        self.assertEqual(b.kind, NodeKind.TABLE_HEADER_CELL)
        self.assertEqual(b.children, ["Header\n"])

    def test_table_hdr2(self):
        tree = self.parse("test", "{|\n{{#if:a|!!b|!!c}}\n|}", pre_expand=True)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TABLE)
        self.assertEqual(len(t.children), 1)
        a = t.children[0]
        self.assertEqual(a.kind, NodeKind.TABLE_ROW)
        self.assertEqual(len(a.children), 1)
        b = a.children[0]
        self.assertEqual(b.kind, NodeKind.TABLE_HEADER_CELL)
        self.assertEqual(b.children, ["b\n"])

    def test_table_hdr3(self):
        tree = self.parse("test", "{|\n|-\n\t!Header\n|}")
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TABLE)
        self.assertEqual(len(t.children), 1)
        a = t.children[0]
        self.assertEqual(a.kind, NodeKind.TABLE_ROW)
        self.assertEqual(len(a.children), 1)
        b = a.children[0]
        self.assertEqual(b.kind, NodeKind.TABLE_HEADER_CELL)
        self.assertEqual(b.children, ["Header\n"])

    def test_table_complex1(self):
        tree = self.parse(
            "test",
            "{|\n|+ cap!!tion!||text\n!H1!!H2!!H3\n|"
            "-\n|Orange||Apple||more!!\n|-\n|Bread||Pie||more\n|}",
        )
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TABLE)
        self.assertEqual(t.largs, [])
        self.assertEqual(t.sarg, "")
        self.assertEqual(len(t.children), 4)
        c, h, a, b = t.children
        self.assertEqual(c.kind, NodeKind.TABLE_CAPTION)
        self.assertEqual(c.children, [" cap!!tion!||text\n"])
        self.assertEqual(h.kind, NodeKind.TABLE_ROW)
        self.assertEqual(len(h.children), 3)
        ha, hb, hc = h.children
        self.assertEqual(ha.kind, NodeKind.TABLE_HEADER_CELL)
        self.assertEqual(ha.children, ["H1"])
        self.assertEqual(hb.kind, NodeKind.TABLE_HEADER_CELL)
        self.assertEqual(hb.children, ["H2"])
        self.assertEqual(hc.kind, NodeKind.TABLE_HEADER_CELL)
        self.assertEqual(hc.children, ["H3\n"])

        self.assertEqual(a.kind, NodeKind.TABLE_ROW)
        self.assertEqual(len(a.children), 3)
        aa, ab, ac = a.children
        self.assertEqual(aa.kind, NodeKind.TABLE_CELL)
        self.assertEqual(aa.children, ["Orange"])
        self.assertEqual(ab.kind, NodeKind.TABLE_CELL)
        self.assertEqual(ab.children, ["Apple"])
        self.assertEqual(ac.kind, NodeKind.TABLE_CELL)
        self.assertEqual(ac.children, ["more!!\n"])
        self.assertEqual(len(b.children), 3)
        ba, bb, bc = b.children
        self.assertEqual(ba.kind, NodeKind.TABLE_CELL)
        self.assertEqual(ba.children, ["Bread"])
        self.assertEqual(bb.kind, NodeKind.TABLE_CELL)
        self.assertEqual(bb.children, ["Pie"])
        self.assertEqual(bc.kind, NodeKind.TABLE_CELL)
        self.assertEqual(bc.children, ["more\n"])

    def test_table_attrs1(self):
        tree = self.parse(
            "test",
            """{| class="table"
|+ class="caption" |cap!!tion!||text
! class="h1" |H1!!class="h2"|H2!!class="h3"|H3|x
|- class="row1"
|class="cell1"|Orange||class="cell2"|Apple||class="cell3"|more!!
|- class="row2"
|Bread||Pie||more!
|}""",
        )
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        self.assertEqual(self.ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TABLE)
        self.assertEqual(t.attrs.get("class"), "table")
        self.assertEqual(t.largs, [])
        self.assertEqual(t.sarg, "")
        self.assertEqual(len(t.children), 4)
        c, h, a, b = t.children
        self.assertEqual(c.kind, NodeKind.TABLE_CAPTION)
        self.assertEqual(c.attrs.get("class"), "caption")
        # XXX "||text\n" should be discarded, if we follow wikitext
        # Left this here as an XXX because... This is an ok fail state for us.
        self.assertEqual(c.children, ["cap!!tion!||text\n"])
        self.assertEqual(h.kind, NodeKind.TABLE_ROW)
        self.assertEqual(len(h.children), 3)
        ha, hb, hc = h.children
        self.assertEqual(ha.kind, NodeKind.TABLE_HEADER_CELL)
        self.assertEqual(ha.attrs.get("class"), "h1")
        self.assertEqual(ha.children, ["H1"])
        self.assertEqual(hb.kind, NodeKind.TABLE_HEADER_CELL)
        self.assertEqual(hb.attrs.get("class"), "h2")
        self.assertEqual(hb.children, ["H2"])
        self.assertEqual(hc.kind, NodeKind.TABLE_HEADER_CELL)
        self.assertEqual(hc.attrs.get("class"), "h3")
        self.assertEqual(hc.children, ["H3|x\n"])
        self.assertEqual(a.kind, NodeKind.TABLE_ROW)
        self.assertEqual(a.attrs.get("class"), "row1")
        self.assertEqual(len(a.children), 3)
        aa, ab, ac = a.children
        self.assertEqual(aa.kind, NodeKind.TABLE_CELL)
        self.assertEqual(aa.attrs.get("class"), "cell1")
        self.assertEqual(aa.children, ["Orange"])
        self.assertEqual(ab.kind, NodeKind.TABLE_CELL)
        self.assertEqual(ab.attrs.get("class"), "cell2")
        self.assertEqual(ab.children, ["Apple"])
        self.assertEqual(ac.kind, NodeKind.TABLE_CELL)
        self.assertEqual(ac.attrs.get("class"), "cell3")
        self.assertEqual(ac.children, ["more!!\n"])
        self.assertEqual(b.kind, NodeKind.TABLE_ROW)
        self.assertEqual(b.attrs.get("class"), "row2")
        self.assertEqual(len(b.children), 3)
        ba, bb, bc = b.children
        self.assertEqual(ba.kind, NodeKind.TABLE_CELL)
        self.assertEqual(ba.children, ["Bread"])
        self.assertEqual(bb.kind, NodeKind.TABLE_CELL)
        self.assertEqual(bb.children, ["Pie"])
        self.assertEqual(bc.kind, NodeKind.TABLE_CELL)
        self.assertEqual(bc.children, ["more!\n"])

    def test_table_attrs2(self):
        # Also tests empty cell after | after attrs (there was once a bug
        # in handling it)
        tree = self.parse(
            "test",
            """{|
|-
| style="width=20%" |
! colspan=2 | Singular
|}""",
        )
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        self.assertEqual(self.ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TABLE)
        self.assertEqual(t.attrs, {})
        self.assertEqual(t.largs, [])
        self.assertEqual(t.sarg, "")
        self.assertEqual(len(t.children), 1)
        r = t.children[0]
        self.assertEqual(r.kind, NodeKind.TABLE_ROW)
        self.assertEqual(r.attrs, {})
        self.assertEqual(r.largs, [])
        self.assertEqual(r.sarg, "")
        self.assertEqual(len(r.children), 2)
        aa, ab = r.children
        self.assertEqual(aa.kind, NodeKind.TABLE_CELL)
        self.assertEqual(aa.attrs.get("style"), "width=20%")
        self.assertEqual(aa.children, ["\n"])
        self.assertEqual(ab.kind, NodeKind.TABLE_HEADER_CELL)
        self.assertEqual(ab.attrs.get("colspan"), "2")
        self.assertEqual(ab.children, [" Singular\n"])

    def test_table_rowhdrs(self):
        tree = self.parse(
            "test",
            """{| class="wikitable"
|-
! scope="col"| Item
! scope="col"| Quantity
! scope="col"| Price
|-
! scope="row"| Bread
| 0.3 kg
| $0.65
|-
! scope="row"| Butter
| 0.125 kg
| $1.25
|-
! scope="row" colspan="2"| Total
| $1.90
|}""",
        )
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TABLE)
        self.assertEqual(t.attrs.get("class"), "wikitable")
        self.assertEqual(t.largs, [])
        self.assertEqual(t.sarg, "")
        self.assertEqual(len(t.children), 4)
        h, a, b, c = t.children
        self.assertEqual(h.kind, NodeKind.TABLE_ROW)
        self.assertEqual(len(h.children), 3)
        ha, hb, hc = h.children
        self.assertEqual(ha.kind, NodeKind.TABLE_HEADER_CELL)
        self.assertEqual(ha.attrs.get("scope"), "col")
        self.assertEqual(ha.children, [" Item\n"])
        self.assertEqual(hb.kind, NodeKind.TABLE_HEADER_CELL)
        self.assertEqual(hb.attrs.get("scope"), "col")
        self.assertEqual(hb.children, [" Quantity\n"])
        self.assertEqual(hc.kind, NodeKind.TABLE_HEADER_CELL)
        self.assertEqual(hc.attrs.get("scope"), "col")
        self.assertEqual(hc.children, [" Price\n"])
        self.assertEqual(a.kind, NodeKind.TABLE_ROW)
        self.assertEqual(len(a.children), 3)
        aa, ab, ac = a.children
        self.assertEqual(aa.kind, NodeKind.TABLE_HEADER_CELL)
        self.assertEqual(aa.attrs.get("scope"), "row")
        self.assertEqual(aa.children, [" Bread\n"])
        self.assertEqual(ab.kind, NodeKind.TABLE_CELL)
        self.assertEqual(ab.children, [" 0.3 kg\n"])
        self.assertEqual(ac.kind, NodeKind.TABLE_CELL)
        self.assertEqual(ac.children, [" $0.65\n"])
        self.assertEqual(b.kind, NodeKind.TABLE_ROW)
        self.assertEqual(len(b.children), 3)
        ba, bb, bc = b.children
        self.assertEqual(ba.kind, NodeKind.TABLE_HEADER_CELL)
        self.assertEqual(ba.attrs.get("scope"), "row")
        self.assertEqual(ba.children, [" Butter\n"])
        self.assertEqual(bb.kind, NodeKind.TABLE_CELL)
        self.assertEqual(bc.kind, NodeKind.TABLE_CELL)
        self.assertEqual(len(c.children), 2)
        ca, cb = c.children
        self.assertEqual(ca.kind, NodeKind.TABLE_HEADER_CELL)
        self.assertEqual(ca.attrs.get("scope"), "row")
        self.assertEqual(ca.attrs.get("colspan"), "2")
        self.assertEqual(ca.children, [" Total\n"])
        self.assertEqual(cb.kind, NodeKind.TABLE_CELL)
        self.assertEqual(cb.children, [" $1.90\n"])

    def test_table_hdr_vbar_vbar(self):
        tree = self.parse(
            "test",
            """{|
|-
! foo || bar
|}""",
        )
        print(tree)
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TABLE)
        self.assertEqual(len(t.children), 1)
        row = t.children[0]
        self.assertEqual(row.kind, NodeKind.TABLE_ROW)
        self.assertEqual(len(row.children), 2)
        a, b = row.children
        self.assertEqual(a.kind, NodeKind.TABLE_HEADER_CELL)
        self.assertEqual(b.kind, NodeKind.TABLE_HEADER_CELL)

    def test_table_hdr4(self):
        tree = self.parse("test", "{|\n! Hdr\n||bar\n| |baz\n| zap\n|}")
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        self.assertEqual(self.ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TABLE)
        self.assertEqual(len(t.children), 1)
        row = t.children[0]
        self.assertEqual(row.kind, NodeKind.TABLE_ROW)
        self.assertEqual(len(row.children), 5)
        for c, kind in zip(
            row.children,
            [
                NodeKind.TABLE_HEADER_CELL,
                NodeKind.TABLE_CELL,
                NodeKind.TABLE_CELL,
                NodeKind.TABLE_CELL,
                NodeKind.TABLE_CELL,
            ],
        ):
            self.assertEqual(c.kind, kind)

    def test_table_bang1(self):
        # Testing that the single exclamation mark in the middle of a table
        # cell is handled correctly as text.
        text = """
{| class="translations" role="presentation" style="width:100%;" data-gloss="country in Southern Africa"
|-
* Nama: {{t|naq|!Aǂkhib|m}}
|}"""  # noqa: E501
        self.parse("test", text)
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        self.assertEqual(self.ctx.debugs, [])

    def test_error1(self):
        self.parse("test", "'''")
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])  # Warning now disabled
        self.assertEqual(self.ctx.debugs, [])  # Warning now disabled

    def test_error2(self):
        self.parse("test", "=== ''' ===")
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])  # Warning now disabled
        self.assertEqual(self.ctx.debugs, [])

    def test_error3(self):
        self.parse("test", "=== Test ======")
        self.assertNotEqual(self.ctx.debugs, [])

    # There are links within italics that have italics inside them, for example
    # Wiktionary 鶴 has "''[[w:Man'yōshū|''Man'yōshū'']]''"
    # XXX I'm worried I may have added these tests because of opposite example
    # def test_error4(self):
    #     tree, ctx = parse_with_ctx("test", "[['''x]]")
    #     self.assertEqual(len(ctx.warnings), 1)
    #     self.assertEqual(tree.children[0].kind, NodeKind.LINK)

    # def test_error5(self):
    #     tree, ctx = parse_with_ctx("test", "['''x]")
    #     self.assertEqual(len(ctx.warnings), 1)
    #     self.assertEqual(tree.children[0].kind, NodeKind.URL)

    def test_error6(self):
        # This is not actually an error; italic is not processed inside
        # template args
        tree = self.parse("test", "{{foo|''x}}")
        self.assertEqual(len(self.ctx.warnings), 0)
        self.assertEqual(len(self.ctx.debugs), 0)
        self.assertEqual(tree.children[0].kind, NodeKind.TEMPLATE)

    def test_error7(self):
        # This is not actually an error; bold is not processed inside
        # template args
        tree = self.parse("test", "{{{foo|'''x}}}")
        self.assertEqual(len(self.ctx.warnings), 0)
        self.assertEqual(len(self.ctx.debugs), 0)
        self.assertEqual(tree.children[0].kind, NodeKind.TEMPLATE_ARG)

    def test_error8(self):
        self.parse("test", "</pre>")
        self.assertEqual(len(self.ctx.debugs), 1)

    def test_error9(self):
        self.parse("test", "</nowiki>")
        self.assertEqual(len(self.ctx.debugs), 1)

    def test_error10(self):
        self.parse("test", "{| ''\n|-\n'' \n|}")
        self.assertEqual(self.ctx.warnings, [])  # Warning now disabled
        self.assertEqual(self.ctx.debugs, [])  # Warning now disabled

    def test_error11(self):
        self.parse("test", "{| ''\n|+\n'' \n|}")
        self.assertEqual(self.ctx.warnings, [])  # Warning now disabled
        self.assertEqual(self.ctx.debugs, [])  # Warning now disabled

    def test_error12(self):
        self.parse("test", "'''''")
        self.assertEqual(self.ctx.warnings, [])  # Warning now disabled
        self.assertEqual(self.ctx.debugs, [])  # Warning now disabled

    def test_plain1(self):
        tree = self.parse("test", "]]")
        self.assertEqual(tree.children, ["]]"])

    def test_plain2(self):
        tree = self.parse("test", "]")
        self.assertEqual(tree.children, ["]"])

    def test_plain3(self):
        tree = self.parse("test", "}}")
        self.assertEqual(tree.children, ["}}"])

    def test_plain4(self):
        tree = self.parse("test", "}}}")
        self.assertEqual(tree.children, ["}}}"])

    def test_plain5(self):
        tree = self.parse("test", "|+")
        self.assertEqual(tree.children, ["|+"])

    def test_plain6(self):
        tree = self.parse("test", "|}")
        self.assertEqual(tree.children, ["|}"])

    def test_plain7(self):
        tree = self.parse("test", "|+")
        self.assertEqual(tree.children, ["|+"])

    def test_plain8(self):
        tree = self.parse("test", "|")
        self.assertEqual(tree.children, ["|"])

    def test_plain9(self):
        tree = self.parse("test", "||")
        self.assertEqual(tree.children, ["||"])

    def test_plain10(self):
        tree = self.parse("test", "!")
        self.assertEqual(tree.children, ["!"])

    def test_plain11(self):
        tree = self.parse("test", "!!")
        self.assertEqual(tree.children, ["!!"])

    def test_plain12(self):
        tree = self.parse("test", "|-")
        self.assertEqual(tree.children, ["|-"])

    def test_plain13(self):
        tree = self.parse("test", "&lt;nowiki />")
        self.assertEqual(tree.children, ["&lt;nowiki />"])

    def test_plain14(self):
        tree = self.parse("test", "a < b < c")
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        self.assertEqual(self.ctx.debugs, [])
        self.assertEqual(tree.children, ["a < b < c"])

    def test_nonsense1(self):
        tree = self.parse("test", "<pre />")
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.PRE)

    def test_nonsense2(self):
        tree = self.parse("test", "{{{{{{{{")
        self.assertEqual(tree.children, ["{{{{{{{{"])
        self.assertEqual(self.ctx.errors, [])

    def test_nonsense3(self):
        tree = self.parse("test", "}}}}}}}}")
        self.assertEqual(tree.children, ["}}}}}}}}"])
        self.assertEqual(self.ctx.errors, [])

    def test_nonsense4(self):
        tree = self.parse("test", "|}}}}}}}}")
        self.assertEqual(tree.children, ["|}}}}}}}}"])
        self.assertEqual(self.ctx.errors, [])

    def test_nonsense5(self):
        self.parse("test", "{|''foo''\n|-\n|}")
        self.assertEqual(self.ctx.errors, [])

    def test_nonsense6(self):
        self.parse("test", "{|\n|-''foo''\n|col\n|}")
        self.assertEqual(self.ctx.errors, [])

    def test_print_tree(self):
        tree = self.parse(
            "test",
            """{| class="wikitable"
|-
! scope="col"| Item
! scope="col"| Quantity
! scope="col"| Price
|-
! scope="row"| Bread
| 0.3 kg
| $0.65
|-
! scope="row"| Butter
| 0.125 kg
| $1.25
|-
! scope="row" colspan="2"| Total
| $1.90
|}""",
        )
        print_tree(tree)

    def test_str(self):
        tree = self.parse(
            "test",
            """{| class="wikitable"
|-
! scope="col"| Item
! scope="col"| Quantity
! scope="col"| Price
|-
! scope="row"| Bread
| 0.3 kg
| $0.65
|-
! scope="row"| Butter
| 0.125 kg
| $1.25
|-
! scope="row" colspan="2"| Total
| $1.90
|}""",
        )
        x = str(tree)  # This print is part of the text, do not remove
        self.assertTrue(isinstance(x, str))

    def test_repr(self):
        tree = self.parse(
            "test",
            """{| class="wikitable"
|-
! scope="col"| Item
! scope="col"| Quantity
! scope="col"| Price
|-
! scope="row"| Bread
| 0.3 kg
| $0.65
|-
! scope="row"| Butter
| 0.125 kg
| $1.25
|-
! scope="row" colspan="2"| Total
| $1.90
|}""",
        )
        x = repr(tree)
        self.assertTrue(isinstance(x, str))

    def test_file_animal(self):
        with open("tests/animal.txt", "r") as f:
            self.parse("animal", f.read())
            self.assertEqual(self.ctx.errors, [])

    def test_file_Babel(self):
        self.ctx.add_page("Template:isValidPageName", 10, "")
        with open("tests/Babel.txt", "r") as f:
            self.parse("Babel", f.read(), pre_expand=True)
            self.assertEqual(self.ctx.errors, [])

    def test_file_fi_gradation(self):
        self.ctx.add_page("Template:fi-gradation-row", 10, "")
        with open("tests/fi-gradation.txt", "r") as f:
            self.parse("fi-gradation", f.read(), pre_expand=True)
            self.assertEqual(self.ctx.errors, [])

    def test_newline_template_argument_in_list(self):
        # new line characters in template arguments shouldn't pop the parser
        # stack to break the template node.
        wikitext = """#*{{  foo
|bar
|baz
}}"""
        tree = self.parse("test_page", wikitext)
        list_node = tree.children[0]
        list_item_node = list_node.children[0]
        template_node = list_item_node.children[0]
        self.assertEqual(template_node.children, [])
        self.assertEqual(
            template_node.largs, [["  foo\n"], ["bar\n"], ["baz\n"]]
        )

    def test_empty_language_converter_template_argument(self):
        """
        Test `Wtp._encode()` when template argument uses "-{}-" as empty
        string placeholder.
        -{}- syntax doc: https://www.mediawiki.org/wiki/Writing_systems/Syntax
        example template: https://zh.wiktionary.org/wiki/Template:Ja-romanization_of
        GitHub issue #59
        """
        tree = self.parse(
            "test_page",
            "{{#invoke:form of/templates|form_of_t|-{}-|withcap=1|lang=ja|noprimaryentrycat=}}",  # noqa: E501
        )
        parser_fn_node = tree.children[0]
        self.assertTrue(isinstance(parser_fn_node, WikiNode))
        self.assertEqual(parser_fn_node.kind, NodeKind.PARSER_FN)
        self.assertEqual(
            parser_fn_node.largs,
            [
                ["#invoke"],
                ["form of/templates"],
                ["form_of_t"],
                ["-{}-"],
                ["withcap=1"],
                ["lang=ja"],
                ["noprimaryentrycat="],
            ],
        )

    def test_unused_pinyin_template_argument(self):
        # GitHub issue #72
        tree = self.parse(
            "test_page",
            "{{zh-x|約 有 6 '''%'''{pā} 的 臺灣人 血型 是 A{ēi}B{bī}型。|}}",
        )
        template_node = tree.children[0]
        self.assertTrue(isinstance(template_node, WikiNode))
        self.assertEqual(template_node.kind, NodeKind.TEMPLATE)
        self.assertEqual(
            template_node.largs,
            [
                ["zh-x"],
                ["約 有 6 '''%'''{pā} 的 臺灣人 血型 是 A{ēi}B{bī}型。"],
                [],
            ],
        )

    def test_template_regex_backtracking(self):
        # backtrack regex halts at this wikitext
        # part of page https://zh.wiktionary.org/wiki/路用
        tree = self.parse(
            "test_page",
            r"""#* {{zh-x|人 準若 bat ^孔子字 到 真深，nā koh 加{ke} bat 白話字，也是 加{ke} 一項 ê 路用。|人若是對漢字了解很深，如果再加會白話字，也是多一項'''用處'''。|TW|ref='''1886'''，[http://pojbh.lib.ntnu.edu.tw/artical-12751.htm {{lang|zh|白話字ê利益}} (Pe̍h-oē-jī ê Lī-ek)]}}
#* {{zh-x|卵白{pe̍h}質，伊 ê 成分 是 炭{Thàn}素，^水素，^酸素，窒{Chek}素，伊 ê 路用 是 會{ōe} hō͘ 人 ê 身軀 得{tit}著[着] 勢{sè}力{le̍k}，也 是 hō͘ 細胞 加{ke}添 新 %ê。|蛋白質，其成分是碳、氫、氧、氮，其'''用途'''是給人體提供能量並再生細胞。 |TW|ref='''1926'''，{{lang|zh|張基全}} (Tiuⁿ Ki-chôan)，[http://210.240.194.97/nmtl/dadwt/thak.asp?id=513&kw=%B2%BF%AF%C0 {{lang|zh|酒佮健康}} (Chiú kap Kiān-khong)]}}
#* {{zh-x|腦海 中{tiong} 的 走馬燈，留{liû}戀 啥\什{siáⁿ} 路用？|腦海中的跑馬燈，留戀有什麼'''用'''？|TW|ref={{w2|zh|陳一郎}}，{{lang|zh|留戀什路用}}}}
            """,  # noqa: E501
        )
        first_zh_x_node = tree.children[0].children[0].children[1]
        self.assertTrue(isinstance(first_zh_x_node, WikiNode))
        self.assertEqual(first_zh_x_node.kind, NodeKind.TEMPLATE)
        self.assertEqual(first_zh_x_node.largs[0], ["zh-x"])

    def test_find_node(self):
        tree = self.parse(
            "t",
            """== English ==
=== Noun ===
=== Verb ===""",
        )
        node = tree.children[0]
        level_nodes = list(node.find_child(NodeKind.LEVEL3))
        self.assertEqual(len(level_nodes), 2)

    def test_find_node_recursively(self):
        tree = self.parse(
            "t",
            """== English ==
=== Noun ===
# gloss 1
# gloss 2""",
        )
        node = tree.children[0]
        list_items = list(node.find_child_recursively(NodeKind.LIST_ITEM))
        self.assertEqual(len(list_items), 2)

    def test_contain_node(self):
        tree = self.parse(
            "t",
            """== English ==
=== Noun ===
# gloss 1
# gloss 2""",
        )
        node = tree.children[0]
        self.assertTrue(node.contain_node(NodeKind.LIST_ITEM))

        tree = self.parse("t", "{{foo|{{bar}}}}")
        node = tree.children[0]
        self.assertTrue(node.contain_node(NodeKind.TEMPLATE))

    def test_find_html(self):
        tree = self.parse("t", "<div><p class='class_name'></p></div>")
        node = tree.children[0]
        self.assertTrue(isinstance(node, HTMLNode))
        found_node = False
        for index, p_tag in node.find_html("p", True, "class", "class_name"):
            self.assertTrue(isinstance(p_tag, HTMLNode))
            self.assertEqual(p_tag.tag, "p")
            self.assertEqual(index, 0)
            self.assertEqual(p_tag.attrs.get("class"), "class_name")
            found_node = True
        self.assertTrue(found_node)

    def test_find_html_recursively(self):
        tree = self.parse("t", "<div><p><a class='class_name'></a></p></div>")
        node = tree.children[0]
        self.assertTrue(isinstance(node, HTMLNode))
        found_node = False
        for a_tag in node.find_html_recursively("a", "class", "class_name"):
            self.assertTrue(isinstance(a_tag, HTMLNode))
            self.assertEqual(a_tag.tag, "a")
            self.assertEqual(a_tag.attrs.get("class"), "class_name")
            found_node = True
        self.assertTrue(found_node)

    def test_filter_empty_str_child(self):
        tree = self.parse("t", "==English==\n===Noun===")
        node = tree.children[0]
        filered_children = list(node.filter_empty_str_child())
        self.assertEqual(len(filered_children), 1)
        pos_node = filered_children[0]
        self.assertTrue(isinstance(pos_node, WikiNode))
        self.assertEqual(pos_node.kind, NodeKind.LEVEL3)

    def test_invert_find_child(self):
        tree = self.parse("", "# gloss text {{foo}}\n#: example")
        gloss_node = tree.children[0].children[0]
        not_list_nodes = list(gloss_node.invert_find_child(NodeKind.LIST))
        self.assertEqual(len(not_list_nodes), 2)
        self.assertEqual(not_list_nodes[0], " gloss text ")
        self.assertEqual(not_list_nodes[1].template_name, "foo")

    def test_empty_template_parameter(self):
        tree = self.parse("", "{{foo||bar}}")
        node = tree.children[0]
        self.assertEqual(node.template_parameters.get(1), "")
        self.assertEqual(node.template_parameters.get(2), "bar")

    def test_template_in_template_parameters(self):
        # https://fr.wiktionary.org/wiki/animal
        tree = self.parse(
            "",
            "{{exemple|lang=fr|{{smcp|Moricet}}. — Mais pas du tout, il est à moi !<br\n/>{{smcp|Duchotel}}, ''bas à Moricet''. — Oh ! '''animal''' !|source={{w|Georges Feydeau}}, ''{{w|Monsieur chasse !}}'', 1892}}",  # noqa: E501
        )
        node = tree.children[0]
        self.assertEqual(node.template_parameters.get("lang"), "fr")
        unnamed_parameter = node.template_parameters.get(1)
        self.assertEqual(unnamed_parameter[0].template_name, "smcp")
        self.assertEqual(
            unnamed_parameter[0].template_parameters, {1: "Moricet"}
        )
        self.assertEqual(
            unnamed_parameter[1], ". — Mais pas du tout, il est à moi !<br/>"
        )
        self.assertEqual(unnamed_parameter[2].template_name, "smcp")
        self.assertEqual(
            unnamed_parameter[2].template_parameters, {1: "Duchotel"}
        )
        self.assertEqual(
            unnamed_parameter[3], ", ''bas à Moricet''. — Oh ! '''animal''' !"
        )
        source_parameter = node.template_parameters.get("source")
        self.assertEqual(source_parameter[0].template_name, "w")
        self.assertEqual(
            source_parameter[0].template_parameters, {1: "Georges Feydeau"}
        )
        self.assertEqual(source_parameter[1], ", ''")
        self.assertEqual(source_parameter[2].template_name, "w")
        self.assertEqual(
            source_parameter[2].template_parameters, {1: "Monsieur chasse !"}
        )
        self.assertEqual(source_parameter[3], "'', 1892")

    def test_level_node_find_content(self):
        tree = self.parse("", "== {{foo}} ==")
        node = tree.children[0]
        self.assertTrue(isinstance(node, LevelNode))
        for template_node in node.find_content(NodeKind.TEMPLATE):
            self.assertTrue(isinstance(template_node, TemplateNode))
            self.assertEqual(template_node.template_name, "foo")

    def test_template_parameter_contains_equals_sign(self):
        # https://fr.wiktionary.org/wiki/L2#Dérivés
        tree = self.parse("", "{{lien|1=L1 = L2 hypothesis|lang=en}}")
        node = tree.children[0]
        self.assertTrue(isinstance(node, TemplateNode))
        self.assertEqual(
            node.template_parameters, {1: "L1 = L2 hypothesis", "lang": "en"}
        )

    def test_template_name_end_space(self):
        # https://fr.wiktionary.org/wiki/lenn
        tree = self.parse(
            "", "{{exemple |Hag ar roue a gas anezañ e-tal eul '''lenn'''. }}"
        )
        node = tree.children[0]
        self.assertTrue(isinstance(node, TemplateNode))
        self.assertEqual(node.template_name, "exemple")

    def test_latex_math_tag_template_parameter(self):
        # https://en.wiktionary.org/wiki/antisymmetric
        tree = self.parse("", "{{quote-book|en|<math>\\frac{1}{2}</math>}}")
        template_node = tree.children[0]
        self.assertTrue(isinstance(template_node, TemplateNode))
        self.assertEqual(template_node.template_name, "quote-book")
        self.assertEqual(
            template_node.template_parameters,
            {1: "en", 2: "<math>\\frac{1}{2}</math>"},
        )

    def test_match_template_contains_unpaired_curly_brackets(self):
        # https://en.wiktionary.org/wiki/Template:str_index-lite/logic
        tree = self.parse("", "{{#switch:foo|*foo{*={|*bar}*=}|-}}")
        parser_function_node = tree.children[0]
        self.assertEqual(parser_function_node.kind, NodeKind.PARSER_FN)

    def test_find_two_kinds_of_nodes(self):
        tree = self.parse("", "[[link]]\n{{foo}}\n<a>tag</a>")
        found_nodes = list(tree.find_child(NodeKind.TEMPLATE | NodeKind.HTML))
        self.assertEqual(len(found_nodes), 2)
        self.assertTrue(isinstance(found_nodes[0], TemplateNode))
        self.assertTrue(isinstance(found_nodes[1], HTMLNode))

    def test_parse_html_with_xml_attribute(self):
        # https://fr.wiktionary.org/wiki/autrice
        # expanded from template "équiv-pour"
        # https://fr.wiktionary.org/wiki/Modèle:équiv-pour
        tree = self.parse(
            "",
            '<bdi lang="fr" xml:lang="fr" class="lang-fr">[[auteur#fr|auteur]]</bdi>',  # noqa: E501
        )
        self.assertTrue(isinstance(tree.children[0], HTMLNode))
        self.assertEqual(tree.children[0].tag, "bdi")
        self.assertEqual(tree.children[0].children[0].kind, NodeKind.LINK)

    def test_space_around_attr_equal_sign(self):
        # https://fr.wiktionary.org/wiki/русский
        # template "ru-décl-adjd"
        tree = self.parse("", '<th colspan = "2">Cas</th>')
        html_node = tree.children[0]
        self.assertTrue(isinstance(html_node, HTMLNode))
        self.assertEqual(html_node.tag, "th")
        self.assertEqual(html_node.attrs, {"colspan": "2"})

    def test_inverse_order_template_numbered_parameter(self):
        # https://en.wiktionary.org/wiki/落葉歸根
        wikitext = "{{zh-x|3=CL|葉落歸根，來 時 無 口。||ref=宋·釋道原《景德傳燈錄》|collapsed=y}}"  # noqa: E501
        self.ctx.start_page("落葉歸根")
        tree = self.ctx.parse(wikitext)
        template_node = tree.children[0]
        self.assertTrue(isinstance(template_node, TemplateNode))
        self.assertEqual(template_node.template_name, "zh-x")
        self.assertEqual(
            template_node.template_parameters,
            {
                1: "葉落歸根，來 時 無 口。",
                2: "",
                3: "CL",
                "ref": "宋·釋道原《景德傳燈錄》",
                "collapsed": "y",
            },
        )
        self.ctx.add_page("Template:zh-x", 10, "{{{1}}}")
        self.assertEqual(self.ctx.expand(wikitext), "葉落歸根，來 時 無 口。")

    def test_level_1_header(self):
        tree = self.parse("test", "=Foo=")
        self.assertEqual(len(tree.children), 1)
        level_node = tree.children[0]
        self.assertTrue(isinstance(level_node, LevelNode))
        self.assertEqual(level_node.largs, [["Foo"]])
        self.assertEqual(len(level_node.children), 0)

    def test_equal_sign_in_template_argument(self):
        # remove a strange code replaces `=` in argument with `&#61;`
        # https://en.wiktionary.org/wiki/quadratic
        self.ctx.add_page(
            "Template:trans-top", 10, "{{#invoke:translations|top}}"
        )
        self.ctx.add_page(
            "Module:translations",
            828,
            """
        local export = {}
        function export.top(frame)
          local args = frame:getParent().args
          return args[1]
        end

        return export
        """,
        )
        self.ctx.start_page("")
        wikitext = "{{trans-top|1=of a class of polynomial of the form y = ax² + bx + c}}"  # noqa: E501
        expanded = self.ctx.expand(wikitext)
        self.assertEqual(
            expanded, "of a class of polynomial of the form y = ax² + bx + c"
        )

        # https://en.wiktionary.org/wiki/can
        self.ctx.add_page("Template:qualifier", 10, "({{{1|}}})")
        self.ctx.add_page(
            "Template:tt+", 10, "⦃⦃t+¦{{{1|}}}¦{{{2|}}}¦tr={{{tr|}}}⦄⦄"
        )
        wikitext = "{{qualifier|the ability/inability to achieve a result is expressed with various verb complements, e.g. {{tt+|cmn|得了|tr=-deliǎo}}}}"  # noqa: E501
        expanded = self.ctx.expand(wikitext)
        self.assertEqual(
            expanded,
            "(the ability/inability to achieve a result is expressed with various verb complements, e.g. ⦃⦃t+¦cmn¦得了¦tr=-deliǎo⦄⦄)",  # noqa: E501
        )

    def test_hdr_italics(self):
        tree = self.parse("test", "=== ''nachklassisch'' ===")
        self.assertEqual(len(tree.children), 1)
        self.assertEqual(tree.children[0].kind, NodeKind.LEVEL3)
        self.assertEqual(len(tree.children[0].largs), 1)
        self.assertEqual(tree.children[0].largs[0][0].kind, NodeKind.ITALIC)

    def test_language_parser_function(self):
        self.ctx.start_page("")
        self.assertEqual(self.ctx.expand("{{PAGELANGUAGE}}"), "en")
        self.assertEqual(
            self.ctx.expand("{{#language:{{PAGELANGUAGE}}}}"), "English"
        )

    def test_apostrophe_in_template_arg_name(self):
        # https://fr.wiktionary.org/wiki/Modèle:fr-conj
        self.ctx.start_page("")
        self.ctx.add_page(
            "Template:fr-conj/Tableau-composé", 10, "{{{'aux.1s|}}}"
        )
        self.assertEqual(
            self.ctx.expand("{{fr-conj/Tableau-composé|'aux.1s=oui}}"), "oui"
        )

    def test_wikinode_as_template_name(self):
        # https://fr.wiktionary.org/wiki/trempage
        # a link is mistakenly used as template name
        self.ctx.start_page("")
        root = self.ctx.parse("{{{{foo}}|bar}}")
        t_node = root.children[0]
        self.assertEqual(t_node.template_name, "<WikiNode>")

    def test_html_end_tag_in_parserfn(self):
        # https://fr.wiktionary.org/wiki/Modèle:fr-conj/Tableau-composé
        # the parser should be able to parse the second argument
        self.ctx.start_page("")
        self.ctx.add_page(
            "Template:t",
            10,
            "{{#if:|<nowiki /> t{{#if:|’|e <nowiki />}}|<nowiki> </nowiki>}}",
        )
        self.assertEqual(self.ctx.expand("{{t}}"), " ")

    def test_hypen_in_table_cell(self):
        # https://fr.wiktionary.org/wiki/Conjugaison:français/s’abattre
        # "|-toi" is table cell not table row
        self.ctx.start_page("")
        root = self.ctx.parse(
            """{|
|-
|width="25%"|-toi
|}"""
        )
        table_node = root.children[0]
        self.assertEqual(table_node.kind, NodeKind.TABLE)
        table_row = table_node.children[0]
        self.assertEqual(table_row.kind, NodeKind.TABLE_ROW)
        table_cell = table_row.children[0]
        self.assertEqual(table_cell.kind, NodeKind.TABLE_CELL)
        self.assertEqual(table_cell.children, ["-toi\n"])

    def test_plus_in_table_cell(self):
        # Based on above test
        self.ctx.start_page("")
        root = self.ctx.parse(
            """{|
|-
|width="25%"|+toi
|}"""
        )
        table_node = root.children[0]
        self.assertEqual(table_node.kind, NodeKind.TABLE)
        table_row = table_node.children[0]
        self.assertEqual(table_row.kind, NodeKind.TABLE_ROW)
        table_cell = table_row.children[0]
        self.assertEqual(table_cell.kind, NodeKind.TABLE_CELL)
        self.assertEqual(table_cell.children, ["+toi\n"])

    def test_curly_in_table_cell(self):
        self.ctx.start_page("")
        root = self.ctx.parse(
            """{|
|Test{||}Test2
|}"""
        )
        table_node = root.children[0]
        self.assertEqual(table_node.kind, NodeKind.TABLE)
        table_row = table_node.children[0]
        self.assertEqual(table_row.kind, NodeKind.TABLE_ROW)
        table_cell = table_row.children[0]
        self.assertEqual(table_cell.kind, NodeKind.TABLE_CELL)
        self.assertEqual(table_cell.children, ["Test{"])
        table_cell = table_row.children[1]
        self.assertEqual(table_cell.kind, NodeKind.TABLE_CELL)
        self.assertEqual(table_cell.children, ["}Test2\n"])

    def test_italics_in_table_header(self):
        # GH issue tatuylonen/wiktextract#597
        # https://en.wiktionary.org/wiki/sledovat
        # https://en.wiktionary.org/wiki/Template:cs-conj-forms
        self.ctx.start_page("sledovat")
        root = self.ctx.parse(
            """{|
!''Italics'' !!colspan="2"|bar
|}"""
        )
        table_node = root.children[0]
        self.assertEqual(table_node.kind, NodeKind.TABLE)
        table_row = table_node.children[0]
        self.assertEqual(table_row.kind, NodeKind.TABLE_ROW)
        table_header_cell = table_row.children[0]
        self.assertEqual(table_header_cell.kind, NodeKind.TABLE_HEADER_CELL)
        self.assertEqual(table_header_cell.children[0].kind, NodeKind.ITALIC)
        self.assertEqual(table_header_cell.children[1], " ")
        table_header_cell = table_row.children[1]
        self.assertEqual(table_header_cell.kind, NodeKind.TABLE_HEADER_CELL)
        self.assertEqual(table_header_cell.children[0], "bar\n")
        self.assertEqual(table_header_cell.attrs, {"colspan": "2"})

    def test_nowiki_in_link(self):
        # https://fr.wiktionary.org/wiki/Conjugaison:français/abattre
        # GitHub issue #180
        self.ctx.start_page("")
        root = self.ctx.parse(
            "[[Annexe|<span>\\kə <nowiki />nu.z‿ɛ.jɔ̃.z‿a.ba.ty\\</span>]]"
        )
        link_node = root.children[0]
        self.assertEqual(link_node.kind, NodeKind.LINK)
        span_node = link_node.largs[1][0]
        self.assertTrue(isinstance(span_node, HTMLNode))
        self.assertEqual(
            span_node.children, ["\\kə <nowiki />nu.z‿ɛ.jɔ̃.z‿a.ba.ty\\"]
        )
        root = self.ctx.parse("[<nowiki/>[link]]")
        self.assertEqual(root.children, ["&lsqb;&lsqb;link&rsqb;&rsqb;"])

    def test_template_node_template_name_prop(self):
        tests = [
            ["{{:page_in_main_ns}}", ":page_in_main_ns"],  # transclude page
            ["{{Template:title}}", "title"],
            ["{{t:title}}", "title"],  # alias
            # template name could have ":"
            # https://en.wiktionary.org/wiki/Template:RQ:Schuster_Hepaticae
            ["{{RQ:Schuster Hepaticae}}", "RQ:Schuster Hepaticae"],
        ]
        self.ctx.start_page("")
        for wikitext, title in tests:
            with self.subTest(wikitext=wikitext, title=title):
                root = self.ctx.parse(wikitext)
                template_node = root.children[0]
                self.assertTrue(isinstance(template_node, TemplateNode))
                self.assertEqual(template_node.template_name, title)

    def test_left_curly_bracket_in_template(self):
        # https://en.wiktionary.org/wiki/llave
        # GitHub issue: tatuylonen/wiktextract#499
        self.ctx.start_page("llave")
        for wikitext, params in [
            ("{{m|mul|{}}", {1: "mul", 2: "{"}),
            ("{{m|mul|{ }}", {1: "mul", 2: "{ "}),
            ("{{m|mul|} }}", {1: "mul", 2: "} "}),
        ]:
            with self.subTest(wikitext=wikitext, params=params):
                root = self.ctx.parse(wikitext)
                template = root.children[0]
                self.assertTrue(isinstance(template, TemplateNode))
                self.assertEqual(template.template_name, "m")
                self.assertEqual(template.template_parameters, params)

    def test_left_curly_bracket_in_template2(self):
        # https://en.wiktionary.org/wiki/llave
        # GitHub issue: tatuylonen/wiktextract#499
        self.ctx.start_page("llave")
        root = self.ctx.parse("{{m|mul|{{ }}")
        string = self.ctx.node_to_wikitext(root)
        self.assertTrue(isinstance(string, str))
        self.assertEqual(string, "{{m|mul|{{ }}")

    def test_extension_tags(self):
        # Extension tags can be arbitrary, but we don't want to allow
        # just anything inside HTML-tag-like entities, and we also
        # need some basic data on how the tag is supposed to behave.
        extension_tags = {
            "foo": {"parents": ["phrasing"], "content": ["phrasing"]},
        }
        self.ctx.allowed_html_tags.update(extension_tags)
        self.ctx.start_page("test")
        root = self.ctx.parse("<foo>bar</foo>")
        self.assertEqual(len(root.children), 1)
        e = root.children[0]
        self.assertEqual(e.kind, NodeKind.HTML)
        self.assertEqual(len(e.children), 1)
        self.assertEqual(e.children[0], "bar")

    def test_slash_in_html_attr_value(self):
        # https://de.wiktionary.org/wiki/axitiosus
        self.ctx.start_page("axitiosus")
        root = self.ctx.parse("<ref name=Ernout/Meillte>{{template}}</ref>")
        ref_node = root.children[0]
        self.assertIsInstance(ref_node, HTMLNode)
        self.assertEqual(ref_node.tag, "ref")

    def test_nowiki_breaks_parsing_template(self):
        # https://en.wikipedia.org/wiki/Help:Wikitext#Displaying_template_calls
        self.ctx.start_page("")
        self.ctx.add_page("Template:t", 10, "template body")
        cases = [
            ("{<nowiki/>{t}}", "&lbrace;&lbrace;t&rbrace;&rbrace;"),
            ("{{<nowiki/> t}}", "&lbrace;&lbrace;<nowiki /> t&rbrace;&rbrace;"),
            (
                "{{ t <nowiki/> }}",
                "&lbrace;&lbrace; t <nowiki /> &rbrace;&rbrace;",
            ),
            ("random text {{ t | <nowiki/> }}", "random text template body"),
            (
                "{{ #ifeq<nowiki/>: inYes | inYes | outYes | outNo }}",
                "&lbrace;&lbrace; #ifeq<nowiki />: inYes &vert; inYes &vert; outYes &vert; outNo &rbrace;&rbrace;",  # noqa: E501
            ),
            ("{{ #ifeq: inYes<nowiki/> | inYes | outYes | outNo }}", "outNo"),
        ]
        for wikitext, result in cases:
            with self.subTest(wkitext=wikitext, result=result):
                self.assertEqual(self.ctx.expand(wikitext), result)

    def test_html_end_tag_slash_after_attr(self):
        # the "/" in "/>" should not be parsed as attribute value
        # https://en.wiktionary.org/wiki/abstract
        # GH issue tatuylonen/wiktextract#535
        self.ctx.start_page("abstract")
        root = self.ctx.parse(
            """{{en-adj|more|er}}<ref name=dict/>
# {{lb|en|obsolete}} Derived; extracted."""
        )
        self.assertEqual(len(root.children), 4)
        self.assertIsInstance(root.children[0], TemplateNode)
        self.assertEqual(root.children[0].template_name, "en-adj")
        self.assertIsInstance(root.children[1], HTMLNode)
        self.assertEqual(root.children[1].tag, "ref")
        self.assertEqual(root.children[2], "\n")
        self.assertEqual(root.children[3].kind, NodeKind.LIST)

    def test_zh_x_html(self):
        # https://zh.wiktionary.org/wiki/大家
        # https://zh.wiktionary.org/wiki/Template:Zh-x
        self.ctx.start_page("大家")
        root = self.ctx.parse(
            """<dl class="zhusex"><span lang="zh-Hant" class="Hant">example text</span><dd>translation text</dd></dl>"""  # noqa: E501
        )
        span_text = ""
        dd_text = ""
        for dl_tag in root.find_html("dl"):
            for span_tag in dl_tag.find_html("span"):
                span_text = span_tag.children[0]
            for dd_tag in dl_tag.find_html("dd"):
                dd_text = dd_tag.children[0]
        self.assertEqual(span_text, "example text")
        self.assertEqual(dd_text, "translation text")

    def test_horizontal_rule_in_template_arg(self):
        # GitHub issue tatuylonen/wiktextract#536
        self.ctx.start_page("shithole")
        root = self.ctx.parse("{{alt|en|—hole|----hole}}")
        template_node = root.children[0]
        self.assertIsInstance(template_node, TemplateNode)
        self.assertEqual(len(root.children), 1)
        self.assertEqual(
            template_node.template_parameters,
            {1: "en", 2: "—hole", 3: "----hole"},
        )

    def test_nowiki_in_html_attr_value(self):
        # https://pl.wiktionary.org/wiki/Szablon:skrót/szkielet
        # used in etymology template https://pl.wiktionary.org/wiki/Szablon:etym
        self.ctx.start_page("pies")
        self.ctx.add_page(
            "Template:skrót/szkielet",
            10,
            '<span class="short-container<nowiki/> ">text</span>',
        )
        root = self.ctx.parse("{{skrót/szkielet}}", expand_all=True)
        self.assertEqual(len(root.children), 1)
        span_node = root.children[0]
        self.assertIsInstance(span_node, HTMLNode)
        self.assertEqual(span_node.tag, "span")


# XXX implement <nowiki/> marking for links, templates
#  - https://en.wikipedia.org/wiki/Help:Wikitext#Nowiki
#  - fix test_nowiki11 and continue
#  - basically <nowiki/> can be anywhere between {{}}[[]] or in first
#    argument (before first pipe or first colon) OR in nested structure
#    in any parameter
#  - however, escaping outer structure does not escape inner structures
#  - test nowiki in HTML tags (must go right after <)

# Note: Magic links (e.g., ISBN, RFC) are not supported and there is
# currently no plan to start supporting them unless someone comes up
# with a real need.  They are disabled by default in MediaWiki since
# version 1.28 and Wiktionary does not really seem to use them and
# they do not seem particularly important.  See
# https://www.mediawiki.org/wiki/Help:Magic_links

# XXX currently handling of <nowiki> does not conform.  Check out and test
# all examples on: https://en.wikipedia.org/wiki/Help:Wikitext

# XXX test nowiki vs. table markup.  See last paragraph before subtitle "Pre"
# on https://en.wikipedia.org/wiki/Help:Wikitext

# XXX change how <pre> parser tag works.  Preprocess by escaping?
# XXX <pre> should quote spaces to &nbsp; and newlines to &#10;?

# XXX add code for expanding templates (early) in table attributes, tag
# attributes, etc.  Generally, must change table attribute syntax to
# allow templates.

# XXX check if some templates are predefined, e.g. {{^|...}} (the void template)
# It would seem that they are.  Also {{!}} (|) etc.

# XXX test {{unsupported|]}} and {{unsupported|[}}
