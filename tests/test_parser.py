# Tests for WikiText parsing
#
# Copyright (c) 2020-2022 Tatu Ylonen.  See file LICENSE and https://ylonen.org

import unittest
from wikitextprocessor import Wtp
from wikitextprocessor.parser import (print_tree, NodeKind, WikiNode)


def parse_with_ctx(title, text, **kwargs):
    assert isinstance(title, str)
    assert isinstance(text, str)
    ctx = Wtp()
    ctx.analyze_templates()
    ctx.start_page(title)
    root = ctx.parse(text, **kwargs)
    # print("parse_with_ctx: root", type(root), root)
    return root, ctx


def parse(title, text, **kwargs):
    root, ctx = parse_with_ctx(title, text, **kwargs)
    assert isinstance(root, WikiNode)
    assert isinstance(ctx, Wtp)
    return root


class ParserTests(unittest.TestCase):

    def test_empty(self):
        tree = parse("test", "")
        self.assertEqual(tree.kind, NodeKind.ROOT)
        self.assertEqual(tree.children, [])
        self.assertEqual(tree.args, [["test"]])

    def test_text(self):
        tree = parse("test", "some text")
        self.assertEqual(tree.children, ["some text"])

    def test_text2(self):
        tree = parse("test", "some:text")
        self.assertEqual(tree.children, ["some:text"])

    def test_text3(self):
        tree = parse("test", "some|text")
        self.assertEqual(tree.children, ["some|text"])

    def test_text4(self):
        tree = parse("test", "some}}text")
        self.assertEqual(tree.children, ["some}}text"])

    def test_text5(self):
        tree = parse("test", "some* text")
        self.assertEqual(tree.children, ["some* text"])

    def test_hdr2a(self):
        tree = parse("test", "==Foo==")
        assert len(tree.children) == 1
        child = tree.children[0]
        self.assertEqual(child.kind, NodeKind.LEVEL2)
        self.assertEqual(child.args, [["Foo"]])
        self.assertEqual(child.children, [])

    def test_hdr2b(self):
        tree = parse("test", "== Foo:Bar ==\nZappa\n")
        assert len(tree.children) == 1
        child = tree.children[0]
        self.assertEqual(child.kind, NodeKind.LEVEL2)
        self.assertEqual(child.args, [["Foo:Bar"]])
        self.assertEqual(child.children, ["\nZappa\n"])

    def test_hdr2c(self):
        tree = parse("test", "=== Foo:Bar ===\nZappa\n")
        assert len(tree.children) == 1
        child = tree.children[0]
        self.assertEqual(child.kind, NodeKind.LEVEL3)
        self.assertEqual(child.args, [["Foo:Bar"]])
        self.assertEqual(child.children, ["\nZappa\n"])

    def test_hdr23a(self):
        tree = parse("test", "==Foo==\na\n===Bar===\nb\n===Zappa===\nc\n")
        assert len(tree.children) == 1
        h2 = tree.children[0]
        self.assertEqual(h2.kind, NodeKind.LEVEL2)
        self.assertEqual(len(h2.children), 3)
        self.assertEqual(h2.children[0], "\na\n")
        h3a = h2.children[1]
        h3b = h2.children[2]
        self.assertEqual(h3a.kind, NodeKind.LEVEL3)
        self.assertEqual(h3b.kind, NodeKind.LEVEL3)
        self.assertEqual(h3a.args, [["Bar"]])
        self.assertEqual(h3a.children, ["\nb\n"])
        self.assertEqual(h3b.args, [["Zappa"]])
        self.assertEqual(h3b.children, ["\nc\n"])

    def test_hdr23b(self):
        tree = parse("test", "==Foo==\na\n===Bar===\nb\n==Zappa==\nc\n")
        assert len(tree.children) == 2
        h2a = tree.children[0]
        h2b = tree.children[1]
        self.assertEqual(h2a.kind, NodeKind.LEVEL2)
        self.assertEqual(h2b.kind, NodeKind.LEVEL2)
        self.assertEqual(len(h2a.children), 2)
        self.assertEqual(h2a.children[0], "\na\n")
        h3a = h2a.children[1]
        self.assertEqual(h3a.kind, NodeKind.LEVEL3)
        self.assertEqual(h3a.args, [["Bar"]])
        self.assertEqual(h3a.children, ["\nb\n"])
        self.assertEqual(h2b.args, [["Zappa"]])
        self.assertEqual(h2b.children, ["\nc\n"])

    def test_hdr23456(self):
        tree = parse("test", """
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
""")
        self.assertEqual(len(tree.children), 2)
        h2 = tree.children[1]
        h3 = h2.children[1]
        h4 = h3.children[1]
        h5 = h4.children[1]
        h6 = h5.children[1]
        self.assertEqual(h6.kind, NodeKind.LEVEL6)
        self.assertEqual(h6.children, ["\ndasfasddasfdas\n"])

    def test_hdr_anchor(self):
        tree = parse("test", """==<Span id="anchor">hdr text</span>==\ndata""")
        self.assertEqual(len(tree.children), 1)
        h = tree.children[0]
        self.assertEqual(h.kind, NodeKind.LEVEL2)
        self.assertEqual(len(h.args), 1)
        self.assertEqual(len(h.args[0]), 1)
        a = h.args[0][0]
        self.assertEqual(a.kind, NodeKind.HTML)
        self.assertEqual(a.args, "span")
        self.assertEqual(a.attrs.get("id"), "anchor")
        self.assertEqual(a.children, ["hdr text"])
        self.assertEqual(h.children, ["\ndata"])

    def test_nowiki1(self):
        tree = parse("test", "==Foo==\na<nowiki>\n===Bar===\nb</nowiki>\n==Zappa==\nc\n")
        assert len(tree.children) == 2
        h2a = tree.children[0]
        h2b = tree.children[1]
        self.assertEqual(h2a.kind, NodeKind.LEVEL2)
        self.assertEqual(h2b.kind, NodeKind.LEVEL2)
        self.assertEqual(h2a.children,
                         ["\na\n&equals;&equals;&equals;Bar"
                          "&equals;&equals;&equals;\nb\n"])
        self.assertEqual(h2b.args, [["Zappa"]])
        self.assertEqual(h2b.children, ["\nc\n"])

    def test_nowiki2(self):
        tree = parse("test", "<<nowiki/>foo>")
        assert tree.children == ["<<nowiki />foo>"]

    def test_nowiki3(self):
        tree = parse("test", "&<nowiki/>amp;")
        self.assertEqual(tree.children, ["&<nowiki />amp;"])

    def test_nowiki4(self):
        tree, ctx = parse_with_ctx("test", "a</nowiki>b")
        self.assertEqual(tree.children, ["a</nowiki>b"])
        self.assertEqual(len(ctx.debugs), 1)

    def test_nowiki5(self):
        tree = parse("test", "<nowiki />#b")
        self.assertEqual(tree.children, ["<nowiki />#b"])

    def test_nowiki6(self):
        tree = parse("test", "a<nowiki>\n</nowiki>b")
        self.assertEqual(tree.children, ["a\nb"])

    def test_nowiki7(self):
        tree = parse("test", "a<nowiki>\nb</nowiki>c")
        self.assertEqual(tree.children, ["a\nbc"])

    def test_nowiki8(self):
        tree = parse("test", "'<nowiki />'Italics' markup'<nowiki/>'")
        self.assertEqual(tree.children, ["'<nowiki />'Italics' markup'<nowiki />'"])

    def test_nowiki9(self):
        tree = parse("test", "<nowiki>[[Example]]</nowiki>")
        self.assertEqual(tree.children, ["&lsqb;&lsqb;Example&rsqb;&rsqb;"])

    def test_nowiki10(self):
        tree = parse("test", "<nowiki><!-- revealed --></nowiki>")
        self.assertEqual(tree.children, ["&lt;&excl;-- revealed --&gt;"])

    def test_nowiki11(self):
        tree = parse("test", "__HIDDENCAT<nowiki />__")
        self.assertEqual(tree.children, ["__HIDDENCAT<nowiki />__"])

    def test_nowiki12(self):
        tree = parse("test", "[<nowiki />[x]]")
        self.assertEqual(tree.children, ["&lsqb;&lsqb;x&rsqb;&rsqb;"])

    def test_nowiki13(self):
        tree = parse("test", "[[x]<nowiki />]")
        self.assertEqual(tree.children, ["&lsqb;&lsqb;x&rsqb;&rsqb;"])

    def test_nowiki14(self):
        tree = parse("test", "[[<nowiki />x]]")
        self.assertEqual(tree.children, ["&lsqb;&lsqb;<nowiki />x&rsqb;&rsqb;"])

    def test_nowiki15(self):
        tree = parse("test", "{<nowiki />{x}}")
        self.assertEqual(tree.children, ["&lbrace;&lbrace;x&rbrace;&rbrace;"])

    def test_nowiki16(self):
        tree = parse("test", "{{x}<nowiki />}")
        self.assertEqual(tree.children, ["&lbrace;&lbrace;x&rbrace;&rbrace;"])

    def test_nowiki17(self):
        tree = parse("test", "{{x<nowiki />}}")
        self.assertEqual(tree.children,
                         ["&lbrace;&lbrace;x<nowiki />&rbrace;&rbrace;"])

    def test_nowiki18(self):
        tree = parse("test", "{{<nowiki />{x}}}")
        self.assertEqual(tree.children,
                         ["&lbrace;&lbrace;&lbrace;x&rbrace;&rbrace;&rbrace;"])

    def test_nowiki19(self):
        tree = parse("test", "{<nowiki />{{x}}}")
        self.assertEqual(tree.children,
                         ["&lbrace;&lbrace;&lbrace;x&rbrace;&rbrace;&rbrace;"])

    def test_nowiki20(self):
        tree = parse("test", "{{{x|1}<nowiki />}}")
        self.assertEqual(tree.children,
                         ["&lbrace;&lbrace;&lbrace;x&vert;1"
                          "&rbrace;&rbrace;&rbrace;"])

    def test_nowiki21(self):
        tree = parse("test", "{{{x}}<nowiki />}")
        self.assertEqual(tree.children,
                         ["&lbrace;&lbrace;&lbrace;x&rbrace;&rbrace;&rbrace;"])

    def test_nowiki22(self):
        tree = parse("test", "{{{x<nowiki />|}}}")
        self.assertEqual(tree.children,
                         ["&lbrace;&lbrace;&lbrace;x<nowiki />&vert;"
                          "&rbrace;&rbrace;&rbrace;"])

    def test_entity_expand(self):
        tree = parse("test", "R&amp;D")
        self.assertEqual(tree.children, ["R&amp;D"])

    def test_processonce1(self):
        tree = parse("test", "&amp;amp;")
        self.assertEqual(tree.children, ["&amp;amp;"])

    def test_html1(self):
        tree = parse("test", "<b>foo</b>")
        self.assertEqual(len(tree.children), 1)
        a = tree.children[0]
        self.assertEqual(a.kind, NodeKind.HTML)
        self.assertEqual(a.args, "b")
        self.assertEqual(a.children, ["foo"])

    def test_html2(self):
        tree = parse("test", """<div style='color: red' width="40" """
                     """max-width=100 bogus>red text</DIV>""")
        self.assertEqual(len(tree.children), 1)
        a = tree.children[0]
        self.assertEqual(a.kind, NodeKind.HTML)
        self.assertEqual(a.args, "div")
        self.assertEqual(a.attrs.get("style", False), "color: red")
        self.assertEqual(a.attrs.get("width", False), "40")
        self.assertEqual(a.attrs.get("max-width", False), "100")
        self.assertEqual(a.attrs.get("bogus", False), "")
        self.assertEqual(a.children, ["red text"])

    def test_html3(self):
        tree = parse("test", """<br class="big" />""")
        self.assertEqual(len(tree.children), 1)
        h = tree.children[0]
        self.assertEqual(h.kind, NodeKind.HTML)
        self.assertEqual(h.args, "br")
        self.assertEqual(h.attrs.get("class", False), "big")
        self.assertEqual(h.children, [])

    def test_html4(self):
        tree, ctx = parse_with_ctx("test", """<div><span>foo</span></div>""")
        self.assertEqual(len(tree.children), 1)
        a = tree.children[0]
        self.assertEqual(a.kind, NodeKind.HTML)
        self.assertEqual(a.args, "div")
        self.assertEqual(len(a.children), 1)
        b = a.children[0]
        self.assertEqual(b.kind, NodeKind.HTML)
        self.assertEqual(b.args, "span")
        self.assertEqual(b.children, ["foo"])
        self.assertEqual(ctx.errors, [])

    def test_html5(self):
        tree, ctx = parse_with_ctx("test", """<div><span>foo</div></span>""")
        self.assertEqual(len(tree.children), 2)
        a, rest = tree.children
        self.assertEqual(rest, "</span>")
        self.assertEqual(a.kind, NodeKind.HTML)
        self.assertEqual(a.args, "div")
        self.assertEqual(len(a.children), 1)
        b = a.children[0]
        self.assertEqual(b.kind, NodeKind.HTML)
        self.assertEqual(b.args, "span")
        self.assertEqual(b.children, ["foo"])
        self.assertEqual(len(ctx.debugs), 2)

    def test_html6(self):
        tree, ctx = parse_with_ctx("test", """<div><span>foo</div>""")
        self.assertEqual(len(tree.children), 1)
        a = tree.children[0]
        self.assertEqual(a.kind, NodeKind.HTML)
        self.assertEqual(a.args, "div")
        self.assertEqual(len(a.children), 1)
        b = a.children[0]
        self.assertEqual(b.kind, NodeKind.HTML)
        self.assertEqual(b.args, "span")
        self.assertEqual(b.children, ["foo"])
        self.assertEqual(len(ctx.debugs), 1)

    def test_html7(self):
        tree, ctx = parse_with_ctx("test", """<ul><li>foo<li>bar</ul>""")
        self.assertEqual(len(tree.children), 1)
        a = tree.children[0]
        self.assertEqual(a.kind, NodeKind.HTML)
        self.assertEqual(a.args, "ul")
        self.assertEqual(len(a.children), 2)
        b, c = a.children
        self.assertEqual(b.kind, NodeKind.HTML)
        self.assertEqual(b.args, "li")
        self.assertEqual(b.children, ["foo"])
        self.assertEqual(c.kind, NodeKind.HTML)
        self.assertEqual(c.args, "li")
        self.assertEqual(c.children, ["bar"])
        self.assertEqual(ctx.errors, [])

    def test_html8(self):
        tree, ctx = parse_with_ctx("test", "==Title==\n<ul><li>foo<li>bar</ul>"
                                   "</div>")
        self.assertEqual(len(tree.children), 1)
        h = tree.children[0]
        self.assertEqual(h.kind, NodeKind.LEVEL2)
        self.assertEqual(h.args, [["Title"]])
        self.assertEqual(len(h.children), 3)
        x, a, rest = h.children
        self.assertEqual(rest, "</div>")
        self.assertEqual(x, "\n")
        self.assertEqual(a.kind, NodeKind.HTML)
        self.assertEqual(a.args, "ul")
        self.assertEqual(len(a.children), 2)
        b, c = a.children
        self.assertEqual(b.kind, NodeKind.HTML)
        self.assertEqual(b.args, "li")
        self.assertEqual(b.children, ["foo"])
        self.assertEqual(c.kind, NodeKind.HTML)
        self.assertEqual(c.args, "li")
        self.assertEqual(c.children, ["bar"])
        self.assertEqual(len(ctx.debugs), 1)

    def test_html9(self):
        tree, ctx = parse_with_ctx("test", "<b <!-- bar -->>foo</b>")
        self.assertEqual(len(tree.children), 1)
        a = tree.children[0]
        assert isinstance(a, WikiNode)
        self.assertEqual(a.kind, NodeKind.HTML)
        self.assertEqual(a.args, "b")
        self.assertEqual(a.children, ["foo"])
        self.assertEqual(ctx.errors, [])

    def test_html10(self):
        tree, ctx = parse_with_ctx("test", "<br />")
        self.assertEqual(ctx.errors, [])
        self.assertEqual(len(tree.children), 1)
        a = tree.children[0]
        assert isinstance(a, WikiNode)
        self.assertEqual(a.kind, NodeKind.HTML)
        self.assertEqual(a.args, "br")
        self.assertEqual(a.children, [])

    def test_html11(self):
        tree, ctx = parse_with_ctx("test", "<wbr>")  # Omits closing tag
        self.assertEqual(ctx.errors, [])
        self.assertEqual(len(tree.children), 1)
        a = tree.children[0]
        assert isinstance(a, WikiNode)
        self.assertEqual(a.kind, NodeKind.HTML)
        self.assertEqual(a.args, "wbr")
        self.assertEqual(a.children, [])

    def test_html12(self):
        tree, ctx = parse_with_ctx("test", "<tt><nowiki>{{f|oo}}</nowiki></tt>")
        self.assertEqual(ctx.errors, [])
        self.assertEqual(len(tree.children), 1)
        a = tree.children[0]
        assert isinstance(a, WikiNode)
        self.assertEqual(a.kind, NodeKind.HTML)
        self.assertEqual(a.args, "tt")
        self.assertEqual(a.children,
                         ["&lbrace;&lbrace;f&vert;oo&rbrace;&rbrace;"])

    def test_html13(self):
        tree, ctx = parse_with_ctx("test", "<span>[</span>")
        self.assertEqual(ctx.errors, [])
        self.assertEqual(len(tree.children), 1)
        a = tree.children[0]
        assert isinstance(a, WikiNode)
        self.assertEqual(a.kind, NodeKind.HTML)
        self.assertEqual(a.args, "span")
        self.assertEqual(a.children, ["["])

    def test_html14(self):
        tree, ctx = parse_with_ctx("test", "a<3>b")
        self.assertEqual(ctx.errors, [])
        self.assertEqual(ctx.warnings, [])
        self.assertEqual(ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        self.assertEqual(tree.children, ["a<3>b"])

    def test_html15(self):
        tree, ctx = parse_with_ctx("test", "<DIV>foo</DIV>")
        self.assertEqual(ctx.errors, [])
        self.assertEqual(ctx.warnings, [])
        self.assertEqual(ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        a = tree.children[0]
        assert isinstance(a, WikiNode)
        self.assertEqual(a.kind, NodeKind.HTML)
        self.assertEqual(a.args, "div")
        self.assertEqual(a.children, ["foo"])

    def test_html16(self):
        tree, ctx = parse_with_ctx("test",
            """<TABLE ALIGN=RIGHT border="1" cellpadding="5" cellspacing="0">
            <TR ALIGN=RIGHT><TD>'''Depth'''</TD></TR></TABLE>""")
        self.assertEqual(ctx.errors, [])
        self.assertEqual(ctx.warnings, [])
        self.assertEqual(ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        a = tree.children[0]
        assert isinstance(a, WikiNode)
        self.assertEqual(a.kind, NodeKind.HTML)

    def test_html17(self):
        tree, ctx = parse_with_ctx("test",
            """<table>
            <tr><th>Depth
            <tr><td>4
            <tr><td>5
            </table>""")
        self.assertEqual(ctx.errors, [])
        self.assertEqual(ctx.warnings, [])
        self.assertEqual(ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        a = tree.children[0]
        assert isinstance(a, WikiNode)
        self.assertEqual(a.kind, NodeKind.HTML)

    def test_html18(self):
        tree, ctx = parse_with_ctx("test", """<DIV


                                            >foo</DIV>""")
        self.assertEqual(ctx.errors, [])
        self.assertEqual(ctx.warnings, [])
        self.assertEqual(ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        a = tree.children[0]
        assert isinstance(a, WikiNode)
        self.assertEqual(a.kind, NodeKind.HTML)
        self.assertEqual(a.args, "div")
        self.assertEqual(a.children, ["foo"])

    def test_html_unknown(self):
        tree, ctx = parse_with_ctx("test", "<unknown>foo</unknown>")
        self.assertNotEqual(ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        self.assertEqual(tree.children, ["<unknown>foo</unknown>"])

    def test_html_section1(self):
        tree, ctx = parse_with_ctx("test", "a<section begin=foo />b")
        self.assertEqual(tree.children, ["ab"])
        self.assertEqual(len(ctx.warnings), 0)
        self.assertEqual(len(ctx.debugs), 0)

    def test_html_section2(self):
        tree, ctx = parse_with_ctx("test", "a</section>b")
        self.assertEqual(tree.children, ["ab"])
        self.assertEqual(len(ctx.debugs), 1)

    def test_italic1(self):
        tree = parse("test", "a ''italic test'' b")
        self.assertEqual(len(tree.children), 3)
        a, b, c = tree.children
        self.assertEqual(a, "a ")
        self.assertEqual(b.kind, NodeKind.ITALIC)
        self.assertEqual(b.children, ["italic test"])
        self.assertEqual(c, " b")

    def test_italic2(self):
        # Italic is frequently used in enPR in Wiktionary to italicize
        # certain parts of the pronunciation, followed by a single quote.
        tree = parse("test", "a''test'''b")
        self.assertEqual(len(tree.children), 3)
        a, b, c = tree.children
        self.assertEqual(a, "a")
        self.assertEqual(b.kind, NodeKind.ITALIC)
        self.assertEqual(b.children, ["test"])
        self.assertEqual(c, "'b")

    def test_italic3(self):
        tree = parse("test", "a''t{{test}}t''b")
        self.assertEqual(len(tree.children), 3)
        a, b, c = tree.children
        self.assertEqual(a, "a")
        self.assertEqual(b.kind, NodeKind.ITALIC)
        self.assertEqual(len(b.children), 3)
        ba, bb, bc = b.children
        self.assertEqual(ba, "t")
        self.assertEqual(bb.kind, NodeKind.TEMPLATE)
        self.assertEqual(bb.args, [["test"]])
        self.assertEqual(bc, "t")
        self.assertEqual(c, "b")

    def test_italic4(self):
        tree = parse("test", "a''t<span>test</span>t''b")
        self.assertEqual(len(tree.children), 3)
        a, b, c = tree.children
        self.assertEqual(a, "a")
        self.assertEqual(b.kind, NodeKind.ITALIC)
        self.assertEqual(len(b.children), 3)
        ba, bb, bc = b.children
        self.assertEqual(ba, "t")
        self.assertEqual(bb.kind, NodeKind.HTML)
        self.assertEqual(bb.args, "span")
        self.assertEqual(bc, "t")
        self.assertEqual(c, "b")

    def test_italic5(self):
        tree = parse("test", "a''t[[test]]t''b")
        self.assertEqual(len(tree.children), 3)
        a, b, c = tree.children
        self.assertEqual(a, "a")
        self.assertEqual(b.kind, NodeKind.ITALIC)
        self.assertEqual(len(b.children), 2)
        ba, bb = b.children
        self.assertEqual(ba, "t")
        self.assertEqual(bb.kind, NodeKind.LINK)
        self.assertEqual(bb.args, [["test"]])
        self.assertEqual(bb.children, ["t"])
        self.assertEqual(c, "b")

    def test_italic6(self):
        tree, ctx = parse_with_ctx("test", "''[[M|''M'']]''")
        self.assertEqual(ctx.errors, [])
        self.assertEqual(ctx.warnings, [])
        self.assertEqual(ctx.debugs, [])
        # XXX

    def test_bold1(self):
        tree = parse("test", "a '''bold test''' b")
        self.assertEqual(len(tree.children), 3)
        a, b, c = tree.children
        self.assertEqual(a, "a ")
        self.assertEqual(b.kind, NodeKind.BOLD)
        self.assertEqual(b.children, ["bold test"])
        self.assertEqual(c, " b")

    def test_bold2(self):
        tree, ctx = parse_with_ctx("test", "'''C''''est")
        self.assertEqual(len(tree.children), 2)
        a, b = tree.children
        self.assertEqual(a.kind, NodeKind.BOLD)
        self.assertEqual(a.children, ["C"])
        self.assertEqual(b, "'est")
        t = ctx.node_to_wikitext(tree)
        self.assertEqual(t, "'''C''''est")
        def node_handler(node):
            if node.kind == NodeKind.BOLD:
                return node.children
            return None
        t = ctx.node_to_html(tree, node_handler_fn=node_handler)
        self.assertEqual(t, "C'est")

    def test_bolditalic1(self):
        tree, ctx = parse_with_ctx("test", "a '''''bold italic test''''' b")
        self.assertEqual(ctx.errors, [])
        self.assertEqual(ctx.warnings, [])
        self.assertEqual(ctx.debugs, [])
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
        tree, ctx = parse_with_ctx("test",
                                   "''' ''bold italic test'''<nowiki/>''")
        self.assertEqual(ctx.errors, [])
        self.assertEqual(ctx.warnings, [])
        self.assertEqual(ctx.debugs, [])
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
        tree, ctx = parse_with_ctx("test",
                                   "'' '''bold italic test''<nowiki/>'''")
        self.assertEqual(ctx.errors, [])
        self.assertEqual(ctx.warnings, [])
        self.assertEqual(ctx.debugs, [])
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
        tree, ctx = parse_with_ctx("test", "'' '''bold italic test'''''")
        self.assertEqual(ctx.errors, [])
        self.assertEqual(ctx.warnings, [])
        self.assertEqual(ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        self.assertEqual(tree.children[0].kind, NodeKind.ITALIC)
        a, b = tree.children[0].children
        self.assertEqual(a, " ")
        self.assertEqual(b.kind, NodeKind.BOLD)
        self.assertEqual(b.children, ["bold italic test"])

    def test_bolditalic5(self):
        tree, ctx = parse_with_ctx("test", "''' ''bold italic test'''''")
        self.assertEqual(ctx.errors, [])
        self.assertEqual(ctx.warnings, [])
        self.assertEqual(ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        self.assertEqual(tree.children[0].kind, NodeKind.BOLD)
        a, b = tree.children[0].children
        self.assertEqual(a, " ")
        self.assertEqual(b.kind, NodeKind.ITALIC)
        self.assertEqual(b.children, ["bold italic test"])

    def test_bolditalic6(self):
        tree, ctx = parse_with_ctx("test", """''X'''B'''Y''""")
        self.assertEqual(ctx.errors, [])
        self.assertEqual(ctx.warnings, [])
        self.assertEqual(ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        self.assertEqual(tree.children[0].kind, NodeKind.ITALIC)

    def test_bolditalic7(self):
        tree, ctx = parse_with_ctx("test", """''S '''''n''''' .''""")
        self.assertEqual(ctx.errors, [])
        self.assertEqual(ctx.warnings, [])
        self.assertEqual(ctx.debugs, [])
        self.assertEqual(len(tree.children), 3)
        self.assertEqual(tree.children[0].kind, NodeKind.ITALIC)
        self.assertEqual(tree.children[1].kind, NodeKind.BOLD)
        self.assertEqual(tree.children[2].kind, NodeKind.ITALIC)

    def test_hline(self):
        tree = parse("test", "foo\n*item\n----\nmore")
        self.assertEqual(len(tree.children), 4)
        a, b, c, d = tree.children
        self.assertEqual(a, "foo\n")
        self.assertEqual(b.kind, NodeKind.LIST)
        self.assertEqual(c.kind, NodeKind.HLINE)
        self.assertEqual(d, "\nmore")

    def test_list_html(self):
        tree = parse("test", "foo\n*item\n\n<strong>bar</strong>")
        self.assertEqual(len(tree.children), 4)
        a, b, c, d = tree.children
        self.assertEqual(a, "foo\n")
        self.assertEqual(b.kind, NodeKind.LIST)
        self.assertEqual(c, "\n")
        self.assertEqual(d.kind, NodeKind.HTML)

    def test_ul(self):
        tree = parse("test", "foo\n\n* item1\n** item1.1\n** item1.2\n"
                     "* item2\n")
        self.assertEqual(len(tree.children), 2)
        a, b = tree.children
        self.assertEqual(a, "foo\n\n")
        self.assertEqual(b.kind, NodeKind.LIST)
        self.assertEqual(b.args, "*")
        self.assertEqual(len(b.children), 2)
        ba, bb = b.children
        self.assertEqual(ba.kind, NodeKind.LIST_ITEM)
        self.assertEqual(ba.args, "*")
        self.assertEqual(len(ba.children), 2)
        baa, bab = ba.children
        self.assertEqual(baa, " item1\n")
        self.assertEqual(bab.kind, NodeKind.LIST)
        self.assertEqual(bab.args, "**")
        self.assertEqual(len(bab.children), 2)
        baba, babb = bab.children
        self.assertEqual(baba.kind, NodeKind.LIST_ITEM)
        self.assertEqual(baba.args, "**")
        self.assertEqual(baba.children, [" item1.1\n"])
        self.assertEqual(babb.kind, NodeKind.LIST_ITEM)
        self.assertEqual(babb.args, "**")
        self.assertEqual(babb.children, [" item1.2\n"])
        self.assertEqual(bb.kind, NodeKind.LIST_ITEM)
        self.assertEqual(bb.args, "*")
        self.assertEqual(bb.children, [" item2\n"])

    def test_ol(self):
        tree = parse("test", "foo\n\n# item1\n##item1.1\n## item1.2\n"
                     "# item2\n")
        self.assertEqual(len(tree.children), 2)
        a, b = tree.children
        self.assertEqual(a, "foo\n\n")
        self.assertEqual(b.kind, NodeKind.LIST)
        self.assertEqual(b.args, "#")
        self.assertEqual(len(b.children), 2)
        ba, bb = b.children
        self.assertEqual(ba.kind, NodeKind.LIST_ITEM)
        self.assertEqual(ba.args, "#")
        self.assertEqual(len(ba.children), 2)
        baa, bab = ba.children
        self.assertEqual(baa, " item1\n")
        self.assertEqual(bab.kind, NodeKind.LIST)
        self.assertEqual(bab.args, "##")
        self.assertEqual(len(bab.children), 2)
        baba, babb = bab.children
        self.assertEqual(baba.kind, NodeKind.LIST_ITEM)
        self.assertEqual(baba.args, "##")
        self.assertEqual(baba.children, ["item1.1\n"])
        self.assertEqual(babb.kind, NodeKind.LIST_ITEM)
        self.assertEqual(babb.args, "##")
        self.assertEqual(babb.children, [" item1.2\n"])
        self.assertEqual(bb.kind, NodeKind.LIST_ITEM)
        self.assertEqual(bb.args, "#")
        self.assertEqual(bb.children, [" item2\n"])

    def test_dl(self):
        tree = parse("test", """; Mixed definition lists
; item 1 : definition
:; sub-item 1 plus term
:: two colons plus definition
:; sub-item 2 : colon plus definition
; item 2
: back to the main list
""")
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.LIST)
        self.assertEqual(t.args, ";")
        self.assertNotIn("head", t.attrs)
        self.assertNotIn("def", t.attrs)
        self.assertEqual(len(t.children), 3)
        a, b, c = t.children
        self.assertEqual(a.kind, NodeKind.LIST_ITEM)
        self.assertEqual(a.args, ";")
        self.assertEqual(a.children, [" Mixed definition lists\n"])
        self.assertEqual(a.attrs, {})
        self.assertEqual(b.kind, NodeKind.LIST_ITEM)
        self.assertEqual(b.args, ";")
        self.assertEqual(b.children, [" item 1 "])
        self.assertNotIn("head", b.attrs)
        self.assertIn("def", b.attrs)
        bdef = b.attrs.get("def")
        self.assertEqual(len(bdef), 2)
        self.assertEqual(bdef[0], " definition\n")
        bdef1 = bdef[1]
        self.assertEqual(bdef1.kind, NodeKind.LIST)
        self.assertEqual(bdef1.args, ":;")
        self.assertNotIn("head", bdef1.attrs)
        self.assertNotIn("def", bdef1.attrs)
        self.assertEqual(len(bdef1.children), 2)
        bdef1a, bdef1b = bdef1.children
        self.assertEqual(bdef1a.kind, NodeKind.LIST_ITEM)
        self.assertEqual(bdef1a.args, ":;")
        self.assertEqual(bdef1a.children, [" sub-item 1 plus term\n"])
        self.assertNotIn("head", bdef1a.attrs)
        self.assertEqual(bdef1a.attrs.get("def"),
                         [" two colons plus definition\n"])
        self.assertEqual(bdef1b.kind, NodeKind.LIST_ITEM)
        self.assertEqual(bdef1b.args, ":;")
        self.assertEqual(bdef1b.children, [" sub-item 2 "])
        self.assertNotIn("head", bdef1b.attrs)
        self.assertEqual(bdef1b.attrs.get("def"), [" colon plus definition\n"])
        self.assertEqual(c.kind, NodeKind.LIST_ITEM)
        self.assertEqual(c.args, ";")
        self.assertNotIn("head", c.attrs)
        self.assertEqual(c.attrs.get("def"), [" back to the main list\n"])
        self.assertEqual(c.children, [" item 2\n"])

    def test_list_cont1(self):
        tree = parse("test", """#list item A1
##list item B1
##list item B2
#:continuing list item A1
#list item A2
""")
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.LIST)
        self.assertEqual(len(t.children), 2)
        a, b = t.children
        self.assertEqual(a.kind, NodeKind.LIST_ITEM)
        self.assertEqual(a.args, "#")
        self.assertEqual(len(a.children), 3)
        aa, ab, ac = a.children
        self.assertEqual(aa, "list item A1\n")
        self.assertEqual(ab.kind, NodeKind.LIST)
        self.assertEqual(ab.args, "##")
        self.assertEqual(len(ab.children), 2)
        aba, abb = ab.children
        self.assertEqual(aba.kind, NodeKind.LIST_ITEM)
        self.assertEqual(aba.args, "##")
        self.assertEqual(aba.children, ["list item B1\n"])
        self.assertEqual(abb.kind, NodeKind.LIST_ITEM)
        self.assertEqual(abb.args, "##")
        self.assertEqual(abb.children, ["list item B2\n"])
        self.assertEqual(ac, "continuing list item A1\n")
        self.assertEqual(b.kind, NodeKind.LIST_ITEM)
        self.assertEqual(b.args, "#")
        self.assertEqual(b.children, ["list item A2\n"])

    def test_list_cont2(self):
        tree = parse("test", """# list item
   A1
#list item B1
""")
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
        tree = parse("test", """# list item\n#: sub-item\n""")
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
        tree = parse("test", "# item1\nFoo\n")
        self.assertEqual(len(tree.children), 2)
        a, b = tree.children
        self.assertEqual(a.kind, NodeKind.LIST)
        self.assertEqual(a.args, "#")
        self.assertEqual(len(a.children), 1)
        aa = a.children[0]
        self.assertEqual(aa.kind, NodeKind.LIST_ITEM)
        self.assertEqual(aa.args, "#")
        self.assertEqual(aa.children, [" item1\n"])
        self.assertEqual(b, "Foo\n")

    # This test is wrong. Disabled.
    # def test_listend2(self):
    #     tree = parse("test", "#\nitem1\nFoo\n")
    #     self.assertEqual(len(tree.children), 2)
    #     a, b = tree.children
    #     self.assertEqual(a.kind, NodeKind.LIST)
    #     self.assertEqual(a.args, "#")
    #     self.assertEqual(len(a.children), 1)
    #     aa = a.children[0]
    #     self.assertEqual(aa.kind, NodeKind.LIST_ITEM)
    #     self.assertEqual(aa.args, "#")
    #     self.assertEqual(aa.children, ["\nitem1\n"])
    #     self.assertEqual(b, "Foo\n")

    def test_liststart1(self):
        tree = parse("test", "==Foo==\n#item1")
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.LEVEL2)
        self.assertEqual(t.args, [["Foo"]])
        self.assertEqual(len(t.children), 2)
        x, a = t.children
        self.assertEqual(x, "\n")
        self.assertEqual(a.kind, NodeKind.LIST)
        self.assertEqual(a.args, "#")
        self.assertEqual(len(a.children), 1)
        b = a.children[0]
        self.assertEqual(b.kind, NodeKind.LIST_ITEM)
        self.assertEqual(b.args, "#")
        self.assertEqual(b.children, ["item1"])

    def test_liststart2(self):
        tree = parse("test", "{{Foo|\n#item1}}")
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TEMPLATE)
        self.assertEqual(t.children, [])
        self.assertEqual(len(t.args), 2)
        a, b = t.args
        self.assertEqual(a, ["Foo"])
        self.assertIsInstance(b, list)
        ba, bb = b
        self.assertEqual(ba, "\n")
        self.assertEqual(bb.kind, NodeKind.LIST)
        self.assertEqual(bb.args, "#")
        self.assertEqual(len(bb.children), 1)
        bba = bb.children[0]
        self.assertEqual(bba.kind, NodeKind.LIST_ITEM)
        self.assertEqual(bba.args, "#")
        self.assertEqual(bba.children, ["item1"])

    def test_link1(self):
        tree = parse("test", "a [[Main Page]] b")
        self.assertEqual(len(tree.children), 3)
        a, b, c = tree.children
        self.assertEqual(a, "a ")
        self.assertEqual(b.kind, NodeKind.LINK)
        self.assertEqual(b.args, [["Main Page"]])
        self.assertEqual(b.children, [])
        self.assertEqual(c, " b")

    def test_link2(self):
        tree = parse("test", "[[Help:Contents]]")
        self.assertEqual(len(tree.children), 1)
        p = tree.children[0]
        self.assertEqual(p.kind, NodeKind.LINK)
        self.assertEqual(p.args, [["Help:Contents"]])
        self.assertEqual(p.children, [])

    def test_link3(self):
        tree = parse("test", "[[#See also|different text]]")
        self.assertEqual(len(tree.children), 1)
        p = tree.children[0]
        self.assertEqual(p.kind, NodeKind.LINK)
        self.assertEqual(p.args, [["#See also"], ["different text"]])
        self.assertEqual(p.children, [])

    def test_link4(self):
        tree = parse("test", "[[User:John Doe|]]")
        self.assertEqual(len(tree.children), 1)
        p = tree.children[0]
        self.assertEqual(p.kind, NodeKind.LINK)
        self.assertEqual(p.args, [["User:John Doe"], []])
        self.assertEqual(p.children, [])

    def test_link5(self):
        tree = parse("test", "[[Help]]<nowiki />ful advise")
        self.assertEqual(len(tree.children), 2)
        a, b = tree.children
        self.assertEqual(a.kind, NodeKind.LINK)
        self.assertEqual(a.args, [["Help"]])
        self.assertEqual(a.children, [])
        self.assertEqual(b, "<nowiki />ful advise")

    def test_link6(self):
        tree, ctx = parse_with_ctx("test", "[[of [[musk]]]]")
        self.assertEqual(ctx.errors, [])
        self.assertEqual(ctx.warnings, [])
        self.assertEqual(ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        a = tree.children[0]
        self.assertEqual(a.kind, NodeKind.LINK)
        b = a.args[0][-1]
        self.assertEqual(b.kind, NodeKind.LINK)

    def test_link_trailing(self):
        tree = parse("test", "[[Help]]ing heal")
        self.assertEqual(len(tree.children), 2)
        a, b = tree.children
        self.assertEqual(a.kind, NodeKind.LINK)
        self.assertEqual(a.args, [["Help"]])
        self.assertEqual(a.children, ["ing"])
        self.assertEqual(b, " heal")

    def test_url1(self):
        tree = parse("test", "this https://wikipedia.com link")
        self.assertEqual(len(tree.children), 3)
        a, b, c = tree.children
        self.assertEqual(a, "this ")
        self.assertEqual(b.kind, NodeKind.URL)
        self.assertEqual(b.args, [["https://wikipedia.com"]])
        self.assertEqual(b.children, [])
        self.assertEqual(c, " link")

    def test_url2(self):
        tree = parse("test", "this [https://wikipedia.com] link")
        self.assertEqual(len(tree.children), 3)
        a, b, c = tree.children
        self.assertEqual(a, "this ")
        self.assertEqual(b.kind, NodeKind.URL)
        self.assertEqual(b.args, [["https://wikipedia.com"]])
        self.assertEqual(b.children, [])
        self.assertEqual(c, " link")

    def test_url3(self):
        tree = parse("test", "this [https://wikipedia.com here] link")
        self.assertEqual(len(tree.children), 3)
        a, b, c = tree.children
        self.assertEqual(a, "this ")
        self.assertEqual(b.kind, NodeKind.URL)
        self.assertEqual(b.args, [["https://wikipedia.com"], ["here"]])
        self.assertEqual(b.children, [])
        self.assertEqual(c, " link")

    def test_url4(self):
        tree = parse("test", "this [https://wikipedia.com here multiword] link")
        self.assertEqual(len(tree.children), 3)
        a, b, c = tree.children
        self.assertEqual(a, "this ")
        self.assertEqual(b.kind, NodeKind.URL)
        self.assertEqual(b.args, [["https://wikipedia.com"],
                                  ["here multiword"]])
        self.assertEqual(b.children, [])
        self.assertEqual(c, " link")

    def test_url5(self):
        tree, ctx = parse_with_ctx("test", "<ref>https://wiktionary.org</ref>")
        self.assertEqual(ctx.errors, [])
        self.assertEqual(ctx.warnings, [])
        self.assertEqual(ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        a = tree.children[0]
        self.assertEqual(a.kind, NodeKind.HTML)
        self.assertEqual(len(a.children), 1)
        b = a.children[0]
        self.assertEqual(b.kind, NodeKind.URL)
        self.assertEqual(b.args, [["https://wiktionary.org"]])

    def test_url6(self):
        tree, ctx = parse_with_ctx("test", "Ed[ward] Foo")
        self.assertEqual(ctx.errors, [])
        self.assertEqual(ctx.warnings, [])
        self.assertEqual(ctx.debugs, [])
        self.assertEqual(tree.children, ["Ed[ward] Foo"])

    def test_preformatted1(self):
        tree = parse("test", """
 Start each line with a space.
 Text is '''preformatted''' and
 markups can be done.
Next para""")
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
        tree = parse("test", """
 <nowiki>
def foo(x):
  print(x)
</nowiki>""")
        self.assertEqual(len(tree.children), 2)
        self.assertEqual(tree.children[0], "\n")
        p = tree.children[1]
        self.assertEqual(p.kind, NodeKind.PREFORMATTED)
        self.assertEqual(p.children, [" \ndef foo(x)&colon;\n  print(x)\n"])

    def test_pre1(self):
        tree, ctx = parse_with_ctx(
            "test",
            """\n<PRE>preformatted &amp; '''not bold''' text</pre> after""")
        self.assertEqual(ctx.errors, [])
        self.assertEqual(ctx.warnings, [])
        self.assertEqual(ctx.debugs, [])
        self.assertEqual(len(tree.children), 3)
        a, b, c = tree.children
        self.assertEqual(a, "\n")
        self.assertEqual(b.kind, NodeKind.PRE)
        self.assertEqual(b.children, ["preformatted &amp; '''not bold''' text"])
        self.assertEqual(c, " after")

    def test_pre2(self):
        tree = parse("test", """<PRE style="color: red">line1\nline2</pre>""")
        self.assertEqual(len(tree.children), 1)
        h = tree.children[0]
        self.assertEqual(h.kind, NodeKind.PRE)
        self.assertEqual(h.args, [])
        self.assertEqual(h.attrs.get("_close", False), False)
        self.assertEqual(h.attrs.get("_also_close", False), False)
        self.assertEqual(h.attrs.get("style", False), "color: red")

    def test_pre3(self):
        tree, ctx = parse_with_ctx(
            "test", """<PRE style="color: red">line1\n  line2</pre>""")
        self.assertEqual(len(tree.children), 1)
        h = tree.children[0]
        self.assertEqual(h.kind, NodeKind.PRE)
        self.assertEqual(h.args, [])
        self.assertEqual(h.attrs.get("_close", False), False)
        self.assertEqual(h.attrs.get("_also_close", False), False)
        self.assertEqual(h.attrs.get("style", False), "color: red")
        self.assertEqual(h.children, ["line1\n  line2"])

    # XXX reconsider how pre should work.
    # def test_pre3(self):
    #     tree = parse("test", """<pre>The <pre> tag ignores [[wiki]] ''markup'' as does the <nowiki>tag</nowiki>.</pre>""")
    #     self.assertEqual(len(tree.children), 1)
    #     a = tree.children[0]
    #     self.assertEqual(a.kind, NodeKind.PRE)
    #     self.assertEqual(a.children,
    #                      ["The &lt;pre&gt; tag ignores &lbsqb;&lsqb;wiki"
    #                       "&rsqb;&rsqb; &apos;&apos;markup&apos;&apos; as "
    #                       "does the &lt;nowiki&gt;tag&lt;/nowiki&gt;."])

    def test_comment1(self):
        tree = parse("test", "foo<!-- not\nshown-->bar")
        self.assertEqual(tree.children, ["foobar"])

    def test_comment2(self):
        tree = parse("test", "foo<!-- not\nshown-->bar <!-- second --> now")
        self.assertEqual(tree.children, ["foobar  now"])

    def test_comment3(self):
        tree = parse("test", "fo<nowiki>o<!-- not\nshown-->b</nowiki>ar")
        self.assertEqual(tree.children,
                         ["foo&lt;&excl;-- not\nshown--&gt;bar"])

    def test_magicword1(self):
        tree = parse("test", "a __NOTOC__ b")
        self.assertEqual(len(tree.children), 3)
        a, b, c = tree.children
        self.assertEqual(a, "a ")
        self.assertEqual(b.kind, NodeKind.MAGIC_WORD)
        self.assertEqual(b.args, "__NOTOC__")
        self.assertEqual(b.children, [])
        self.assertEqual(c, " b")

    def test_template1(self):
        tree = parse("test", "a{{foo}}b")
        self.assertEqual(len(tree.children), 3)
        a, b, c = tree.children
        self.assertEqual(a, "a")
        self.assertEqual(b.kind, NodeKind.TEMPLATE)
        self.assertEqual(b.args, [["foo"]])
        self.assertEqual(b.children, [])
        self.assertEqual(c, "b")

    def test_template2(self):
        tree = parse("test", "{{foo|bar||z|1-1/2|}}")
        self.assertEqual(len(tree.children), 1)
        b = tree.children[0]
        self.assertEqual(b.kind, NodeKind.TEMPLATE)
        self.assertEqual(b.args, [["foo"], ["bar"], [], ["z"], ["1-1/2"], []])
        self.assertEqual(b.children, [])

    def test_template3(self):
        tree = parse("test", "{{\nfoo\n|\nname=testi|bar\n|\nbaz}}")
        self.assertEqual(len(tree.children), 1)
        b = tree.children[0]
        self.assertEqual(b.kind, NodeKind.TEMPLATE)
        self.assertEqual(b.args, [["\nfoo\n"], ["\nname=testi"], ["bar\n"],
                                  ["\nbaz"]])
        self.assertEqual(b.children, [])

    def test_template4(self):
        tree = parse("test", "{{foo bar|name=test word|tässä}}")
        self.assertEqual(len(tree.children), 1)
        b = tree.children[0]
        self.assertEqual(b.kind, NodeKind.TEMPLATE)
        self.assertEqual(b.args, [["foo bar"], ["name=test word"],
                                  ["tässä"]])
        self.assertEqual(b.children, [])

    def test_template5(self):
        tree = parse("test", "{{foo bar|name=test word|tässä}}")
        self.assertEqual(len(tree.children), 1)
        b = tree.children[0]
        self.assertEqual(b.kind, NodeKind.TEMPLATE)
        self.assertEqual(b.args, [["foo bar"], ["name=test word"],
                                  ["tässä"]])
        self.assertEqual(b.children, [])

    def test_template6(self):
        tree = parse("test", "{{foo bar|{{nested|[[link]]}}}}")
        self.assertEqual(len(tree.children), 1)
        b = tree.children[0]
        self.assertEqual(b.kind, NodeKind.TEMPLATE)
        self.assertEqual(len(b.args), 2)
        self.assertEqual(b.args[0], ["foo bar"])
        c = b.args[1]
        self.assertIsInstance(c, list)
        self.assertEqual(len(c), 1)
        d = c[0]
        self.assertEqual(d.kind, NodeKind.TEMPLATE)
        self.assertEqual(len(d.args), 2)
        self.assertEqual(d.args[0], ["nested"])
        self.assertEqual(len(d.args[1]), 1)
        e = d.args[1][0]
        self.assertEqual(e.kind, NodeKind.LINK)
        self.assertEqual(e.args, [["link"]])

    def test_template7(self):
        tree = parse("test", "{{{{{foo}}}|bar}}")
        self.assertEqual(len(tree.children), 1)
        b = tree.children[0]
        self.assertEqual(b.kind, NodeKind.TEMPLATE)
        self.assertEqual(len(b.args), 2)
        c = b.args[0]
        self.assertIsInstance(c, list)
        self.assertEqual(len(c), 1)
        d = c[0]
        self.assertEqual(d.kind, NodeKind.TEMPLATE_ARG)
        self.assertEqual(d.args, [["foo"]])
        self.assertEqual(d.children, [])
        self.assertEqual(b.args[1], ["bar"])

    def test_template8(self):
        # Namespace specifiers, e.g., {{int:xyz}} should not generate
        # parser functions
        tree = parse("test", "{{int:xyz}}")
        self.assertEqual(len(tree.children), 1)
        b = tree.children[0]
        self.assertEqual(b.kind, NodeKind.TEMPLATE)
        self.assertEqual(b.args, [["int:xyz"]])

    def test_template9(self):
        # Main namespace references, e.g., {{:xyz}} should not
        # generate parser functions
        tree = parse("test", "{{:xyz}}")
        self.assertEqual(len(tree.children), 1)
        b = tree.children[0]
        self.assertEqual(b.kind, NodeKind.TEMPLATE)
        self.assertEqual(b.args, [[":xyz"]])

    def test_template10(self):
        tree = parse("test", "{{{{a}} }}")
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TEMPLATE)
        self.assertEqual(t.children, [])
        self.assertEqual(len(t.args), 1)
        tt = t.args[0][0]
        self.assertEqual(tt.kind, NodeKind.TEMPLATE)
        self.assertEqual(tt.args, [["a"]])
        self.assertEqual(tt.children, [])

    def test_template11(self):
        tree = parse("test", "{{{{{a}}}}}")
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TEMPLATE)
        self.assertEqual(t.children, [])
        self.assertEqual(len(t.args), 1)
        tt = t.args[0][0]
        self.assertEqual(tt.kind, NodeKind.TEMPLATE_ARG)
        self.assertEqual(tt.args, [["a"]])
        self.assertEqual(tt.children, [])

    def test_template12(self):
        tree = parse("test", "{{{{{a|}}}}}")
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TEMPLATE)
        self.assertEqual(t.children, [])
        self.assertEqual(len(t.args), 1)
        tt = t.args[0][0]
        self.assertEqual(tt.kind, NodeKind.TEMPLATE_ARG)
        self.assertEqual(tt.args, [["a"], []])
        self.assertEqual(tt.children, [])

    def test_template13(self):
        tree = parse("test", "{{ {{a|}}}}")
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TEMPLATE)
        self.assertEqual(t.children, [])
        self.assertEqual(len(t.args), 1)
        self.assertEqual(t.args[0][0], " ")
        tt = t.args[0][1]
        self.assertEqual(tt.kind, NodeKind.TEMPLATE)
        self.assertEqual(tt.args, [["a"], []])
        self.assertEqual(tt.children, [])

    def test_template14(self):
        tree, ctx = parse_with_ctx("test", "{{x|[}}")
        self.assertEqual(ctx.errors, [])
        self.assertEqual(ctx.warnings, [])
        self.assertEqual(ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TEMPLATE)
        self.assertEqual(t.children, [])
        self.assertEqual(t.args, [["x"], ["["]])

    def test_template15(self):
        tree, ctx = parse_with_ctx("test", "{{x|]}}")
        self.assertEqual(ctx.errors, [])
        self.assertEqual(ctx.warnings, [])
        self.assertEqual(ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TEMPLATE)
        self.assertEqual(t.children, [])
        self.assertEqual(t.args, [["x"], ["]"]])

    def test_template16(self):
        # This example is from Wiktionary: Unsupported titles/Less than three
        tree, ctx = parse_with_ctx("test", "{{x|<3}}")
        self.assertEqual(ctx.errors, [])
        self.assertEqual(ctx.warnings, [])
        self.assertEqual(ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TEMPLATE)
        self.assertEqual(t.children, [])
        self.assertEqual(t.args, [["x"], ["<3"]])

    def test_template17(self):
        tree, ctx = parse_with_ctx("test", "{{x|3>}}")
        self.assertEqual(ctx.errors, [])
        self.assertEqual(ctx.warnings, [])
        self.assertEqual(ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TEMPLATE)
        self.assertEqual(t.children, [])
        self.assertEqual(t.args, [["x"], ["3>"]])

    def test_templatevar1(self):
        tree = parse("test", "{{{foo}}}")
        self.assertEqual(len(tree.children), 1)
        b = tree.children[0]
        self.assertEqual(b.kind, NodeKind.TEMPLATE_ARG)
        self.assertEqual(b.args, [["foo"]])
        self.assertEqual(b.children, [])

    def test_templatevar2(self):
        tree = parse("test", "{{{foo|bar|baz}}}")
        self.assertEqual(len(tree.children), 1)
        b = tree.children[0]
        self.assertEqual(b.kind, NodeKind.TEMPLATE_ARG)
        self.assertEqual(b.args, [["foo"], ["bar"], ["baz"]])
        self.assertEqual(b.children, [])

    def test_templatevar3(self):
        tree = parse("test", "{{{{{{foo}}}|bar|baz}}}")
        self.assertEqual(len(tree.children), 1)
        b = tree.children[0]
        self.assertEqual(b.kind, NodeKind.TEMPLATE_ARG)
        c = b.args[0][0]
        self.assertEqual(c.kind, NodeKind.TEMPLATE_ARG)
        self.assertEqual(c.args, [["foo"]])
        self.assertEqual(b.args[1:], [["bar"], ["baz"]])
        self.assertEqual(b.children, [])

    def test_templatevar4(self):
        tree = parse("test", "{{{{{{1}}}}}}")
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TEMPLATE_ARG)
        self.assertEqual(t.children, [])
        self.assertEqual(len(t.args), 1)
        tt = t.args[0][0]
        self.assertEqual(tt.kind, NodeKind.TEMPLATE_ARG)
        self.assertEqual(tt.args, [["1"]])
        self.assertEqual(tt.children, [])

    def test_templatevar5(self):
        tree = parse("test", "{{{{{{1|}}}}}}")
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TEMPLATE_ARG)
        self.assertEqual(t.children, [])
        self.assertEqual(len(t.args), 1)
        tt = t.args[0][0]
        self.assertEqual(tt.kind, NodeKind.TEMPLATE_ARG)
        self.assertEqual(tt.args, [["1"], []])
        self.assertEqual(tt.children, [])

    def test_parserfn1(self):
        tree = parse("test", "{{CURRENTYEAR}}x")
        self.assertEqual(len(tree.children), 2)
        b = tree.children[0]
        self.assertEqual(b.kind, NodeKind.PARSER_FN)
        self.assertEqual(b.args, [["CURRENTYEAR"]])
        self.assertEqual(b.children, [])
        self.assertEqual(tree.children[1], "x")

    def test_parserfn2(self):
        tree = parse("test", "{{PAGESIZE:TestPage}}")
        self.assertEqual(len(tree.children), 1)
        b = tree.children[0]
        self.assertEqual(b.kind, NodeKind.PARSER_FN)
        self.assertEqual(b.args, [["PAGESIZE"], ["TestPage"]])
        self.assertEqual(b.children, [])

    def test_parserfn3(self):
        tree = parse("test", "{{#invoke:testmod|testfn|testarg1|testarg2}}")
        self.assertEqual(len(tree.children), 1)
        b = tree.children[0]
        self.assertEqual(b.kind, NodeKind.PARSER_FN)
        self.assertEqual(b.args, [["#invoke"], ["testmod"], ["testfn"],
                                  ["testarg1"], ["testarg2"]])
        self.assertEqual(b.children, [])

    def test_table_empty(self):
        tree = parse("test", "{| |}")
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TABLE)
        self.assertEqual(t.args, [])
        self.assertEqual(t.children, [])

    def test_table_simple(self):
        tree = parse("test",
                     "{|\n|Orange||Apple||more\n|-\n|Bread||Pie||more\n|}")
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TABLE)
        self.assertEqual(t.args, [])
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
        tree = parse("test",
                     "{|\n|-\n|Orange||Apple||more\n|-\n|Bread||Pie||more\n|}")
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TABLE)
        self.assertEqual(t.args, [])
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
        tree = parse("test", "{|\n\t|Cell\n|}")
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
        tree = parse("test", "{|\n\t!Cell\n|}")
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
        tree = parse("test", """[[foo|<b>bar</b>]]""", expand_all=True)
        self.assertEqual(tree.kind, NodeKind.ROOT)
        lnk = tree.children[0]
        self.assertEqual(lnk.kind, NodeKind.LINK)
        lnkargs = lnk.args
        self.assertEqual(lnkargs[0][0], "foo")
        self.assertEqual(lnkargs[1][0].kind, NodeKind.HTML)
        self.assertEqual(lnkargs[1][0].children[0], "bar")

    def test_html_in_link2(self):
        # expand_all=True here causes the #if-template to be parsed away,
        # and parses the HTML inside the LINK. Without it, the parse-tree
        # would still have an outer node for the #if and the HTML would
        # be just the string '<b>ppp</b>'.
        tree = parse("test",
                     """{{#if:x|[[foo|<b>ppp</b>]] bar}}""",
                     expand_all=True)
        # print_tree(tree, 2)
        self.assertEqual(tree.kind, NodeKind.ROOT)
        lnk = tree.children[0]
        lnkargs = lnk.args
        self.assertEqual(lnkargs[0][0], "foo")
        self.assertEqual(lnkargs[1][0].kind, NodeKind.HTML)
        self.assertEqual(lnkargs[1][0].children[0], "ppp")
        self.assertEqual(tree.children[1], " bar")

    def test_table_hdr1(self):
        tree = parse("test", "{|\n!Header\n|}")
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
        tree = parse("test", "{|\n{{#if:a|!!b|!!c}}\n|}", pre_expand=True)
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
        tree = parse("test", "{|\n|-\n\t!Header\n|}")
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
        tree = parse("test",
                     "{|\n|+ cap!!tion!||text\n!H1!!H2!!H3\n|"
                     "-\n|Orange||Apple||more!!\n|-\n|Bread||Pie||more\n|}")
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TABLE)
        self.assertEqual(t.args, [])
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
        tree, ctx = parse_with_ctx("test", """{| class="table"
|+ class="caption" |cap!!tion!||text
! class="h1" |H1!!class="h2"|H2!!class="h3"|H3|x
|- class="row1"
|class="cell1"|Orange||class="cell2"|Apple||class="cell3"|more!!
|- class="row2"
|Bread||Pie||more!
|}""")
        self.assertEqual(ctx.errors, [])
        self.assertEqual(ctx.warnings, [])
        self.assertEqual(ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TABLE)
        self.assertEqual(t.attrs.get("class"), "table")
        self.assertEqual(t.args, [])
        self.assertEqual(len(t.children), 4)
        c, h, a, b = t.children
        self.assertEqual(c.kind, NodeKind.TABLE_CAPTION)
        self.assertEqual(c.attrs.get("class"), "caption")
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
        tree, ctx = parse_with_ctx("test", """{|
|-
| style="width=20%" |
! colspan=2 | Singular
|}""")
        self.assertEqual(ctx.errors, [])
        self.assertEqual(ctx.warnings, [])
        self.assertEqual(ctx.debugs, [])
        print(tree)
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TABLE)
        self.assertEqual(t.attrs, {})
        self.assertEqual(t.args, [])
        self.assertEqual(len(t.children), 1)
        r = t.children[0]
        self.assertEqual(r.kind, NodeKind.TABLE_ROW)
        self.assertEqual(r.attrs, {})
        self.assertEqual(r.args, [])
        self.assertEqual(len(r.children), 2)
        aa, ab = r.children
        self.assertEqual(aa.kind, NodeKind.TABLE_CELL)
        self.assertEqual(aa.attrs.get("style"), "width=20%")
        self.assertEqual(aa.children, ["\n"])
        self.assertEqual(ab.kind, NodeKind.TABLE_HEADER_CELL)
        self.assertEqual(ab.attrs.get("colspan"), "2")
        self.assertEqual(ab.children, [" Singular\n"])

    def test_table_rowhdrs(self):
        tree = parse("test", """{| class="wikitable"
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
|}""")
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TABLE)
        self.assertEqual(t.attrs.get("class"), "wikitable")
        self.assertEqual(t.args, [])
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
        tree = parse("test", """{|
|-
! foo || bar
|}""")
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
        tree, ctx = parse_with_ctx("test",
                                   "{|\n! Hdr\n||bar\n| |baz\n| zap\n|}")
        print(tree)
        self.assertEqual(ctx.errors, [])
        self.assertEqual(ctx.warnings, [])
        self.assertEqual(ctx.debugs, [])
        self.assertEqual(len(tree.children), 1)
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.TABLE)
        self.assertEqual(len(t.children), 1)
        row = t.children[0]
        self.assertEqual(row.kind, NodeKind.TABLE_ROW)
        self.assertEqual(len(row.children), 5)
        for c, kind in zip(row.children,
                           [NodeKind.TABLE_HEADER_CELL,
                            NodeKind.TABLE_CELL,
                            NodeKind.TABLE_CELL,
                            NodeKind.TABLE_CELL,
                            NodeKind.TABLE_CELL]):
            self.assertEqual(c.kind, kind)

    def test_table_bang1(self):
        # Testing that the single exclamation mark in the middle of a table
        # cell is handled correctly as text.
        text = """
{| class="translations" role="presentation" style="width:100%;" data-gloss="country in Southern Africa"
|-
* Nama: {{t|naq|!Aǂkhib|m}}
|}"""
        tree, ctx = parse_with_ctx("test", text)
        self.assertEqual(ctx.errors, [])
        self.assertEqual(ctx.warnings, [])
        self.assertEqual(ctx.debugs, [])

    def test_error1(self):
        tree, ctx = parse_with_ctx("test", "'''")
        self.assertEqual(ctx.errors, [])
        self.assertEqual(ctx.warnings, [])  # Warning now disabled
        self.assertEqual(ctx.debugs, [])  # Warning now disabled

    def test_error2(self):
        tree, ctx = parse_with_ctx("test", "=== ''' ===")
        self.assertEqual(ctx.errors, [])
        self.assertEqual(ctx.warnings, [])  # Warning now disabled
        self.assertEqual(ctx.debugs, [])

    def test_error3(self):
        tree, ctx = parse_with_ctx("test", "=== Test ======")
        self.assertNotEqual(ctx.debugs, [])

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
        tree, ctx = parse_with_ctx("test", "{{foo|''x}}")
        self.assertEqual(len(ctx.warnings), 0)
        self.assertEqual(len(ctx.debugs), 0)
        self.assertEqual(tree.children[0].kind, NodeKind.TEMPLATE)

    def test_error7(self):
        # This is not actually an error; bold is not processed inside
        # template args
        tree, ctx = parse_with_ctx("test", "{{{foo|'''x}}}")
        self.assertEqual(len(ctx.warnings), 0)
        self.assertEqual(len(ctx.debugs), 0)
        self.assertEqual(tree.children[0].kind, NodeKind.TEMPLATE_ARG)

    def test_error8(self):
        tree, ctx = parse_with_ctx("test", "</pre>")
        self.assertEqual(len(ctx.debugs), 1)

    def test_error9(self):
        tree, ctx = parse_with_ctx("test", "</nowiki>")
        self.assertEqual(len(ctx.debugs), 1)

    def test_error10(self):
        tree, ctx = parse_with_ctx("test", "{| ''\n|-\n'' |}")
        self.assertEqual(ctx.warnings, [])  # Warning now disabled
        self.assertEqual(ctx.debugs, [])  # Warning now disabled

    def test_error11(self):
        tree, ctx = parse_with_ctx("test", "{| ''\n|+\n'' |}")
        self.assertEqual(ctx.warnings, [])  # Warning now disabled
        self.assertEqual(ctx.debugs, [])  # Warning now disabled

    def test_error12(self):
        tree, ctx = parse_with_ctx("test", "'''''")
        self.assertEqual(ctx.warnings, [])  # Warning now disabled
        self.assertEqual(ctx.debugs, [])  # Warning now disabled

    def test_plain1(self):
        tree = parse("test", "]]")
        self.assertEqual(tree.children, ["]]"])

    def test_plain2(self):
        tree = parse("test", "]")
        self.assertEqual(tree.children, ["]"])

    def test_plain3(self):
        tree = parse("test", "}}")
        self.assertEqual(tree.children, ["}}"])

    def test_plain4(self):
        tree = parse("test", "}}}")
        self.assertEqual(tree.children, ["}}}"])

    def test_plain5(self):
        tree = parse("test", "|+")
        self.assertEqual(tree.children, ["|+"])

    def test_plain6(self):
        tree = parse("test", "|}")
        self.assertEqual(tree.children, ["|}"])

    def test_plain7(self):
        tree = parse("test", "|+")
        self.assertEqual(tree.children, ["|+"])

    def test_plain8(self):
        tree = parse("test", "|")
        self.assertEqual(tree.children, ["|"])

    def test_plain9(self):
        tree = parse("test", "||")
        self.assertEqual(tree.children, ["||"])

    def test_plain10(self):
        tree = parse("test", "!")
        self.assertEqual(tree.children, ["!"])

    def test_plain11(self):
        tree = parse("test", "!!")
        self.assertEqual(tree.children, ["!!"])

    def test_plain12(self):
        tree = parse("test", "|-")
        self.assertEqual(tree.children, ["|-"])

    def test_plain13(self):
        tree = parse("test", "&lt;nowiki />")
        self.assertEqual(tree.children, ["&lt;nowiki />"])

    def test_plain14(self):
        tree, ctx = parse_with_ctx("test", "a < b < c")
        self.assertEqual(ctx.errors, [])
        self.assertEqual(ctx.warnings, [])
        self.assertEqual(ctx.debugs, [])
        self.assertEqual(tree.children, ["a < b < c"])

    def test_nonsense1(self):
        tree = parse("test", "<pre />")
        t = tree.children[0]
        self.assertEqual(t.kind, NodeKind.PRE)

    def test_nonsense2(self):
        tree, ctx = parse_with_ctx("test", "{{{{{{{{")
        self.assertEqual(tree.children, ["{{{{{{{{"])
        self.assertEqual(ctx.errors, [])

    def test_nonsense3(self):
        tree, ctx = parse_with_ctx("test", "}}}}}}}}")
        self.assertEqual(tree.children, ["}}}}}}}}"])
        self.assertEqual(ctx.errors, [])

    def test_nonsense4(self):
        tree, ctx = parse_with_ctx("test", "|}}}}}}}}")
        self.assertEqual(tree.children, ["|}}}}}}}}"])
        self.assertEqual(ctx.errors, [])

    def test_nonsense5(self):
        tree, ctx = parse_with_ctx("test", "{|''foo''\n|-\n|}")
        self.assertEqual(ctx.errors, [])

    def test_nonsense6(self):
        tree, ctx = parse_with_ctx("test", "{|\n|-''foo''\n|col\n|}")
        self.assertEqual(ctx.errors, [])

    def test_print_tree(self):
        tree = parse("test", """{| class="wikitable"
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
|}""")
        print_tree(tree)

    def test_str(self):
        tree = parse("test", """{| class="wikitable"
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
|}""")
        x = str(tree)  # This print is part of the text, do not remove
        assert isinstance(x, str)

    def test_repr(self):
        tree = parse("test", """{| class="wikitable"
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
|}""")
        x = repr(tree)
        assert isinstance(x, str)

    def test_file_animal(self):
        with open("tests/animal.txt", "r") as f:
            tree, ctx = parse_with_ctx("animal", f.read())
            self.assertEqual(ctx.errors, [])

    def test_file_Babel(self):
        with open("tests/Babel.txt", "r") as f:
            tree, ctx = parse_with_ctx("Babel", f.read(), pre_expand=True)
            self.assertEqual(ctx.errors, [])

    def test_file_fi_gradation(self):
        with open("tests/fi-gradation.txt", "r") as f:
            tree, ctx = parse_with_ctx("fi-gradation", f.read(), pre_expand=True)
            self.assertEqual(ctx.errors, [])

    def test_newline_template_argument_in_list(self):
        # new line characters in template arguments shouldn't pop the parser
        # stack to break the template node.
        origin_wikitext = """#*{{  foo
|bar
|baz
}}"""
        tree, ctx = parse_with_ctx("test_page", origin_wikitext)
        a = tree.children[0]
        b = a.children[0]
        t = b.children[0]
        assert(t.children == [])
        assert(t.args == [['  foo\n'], ['bar\n'], ['baz\n']])

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
