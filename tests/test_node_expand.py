# Tests for WikiText parsing
#
# Copyright (c) 2020-2021 Tatu Ylonen.  See file LICENSE and https://ylonen.org

import unittest
from wikitextprocessor import Wtp
from wikitextprocessor.parser import WikiNode


def parse_with_ctx(title, text, **kwargs):
    assert isinstance(title, str)
    assert isinstance(text, str)
    ctx = Wtp()
    ctx.analyze_templates()
    ctx.start_page(title)
    root = ctx.parse(text, **kwargs)
    print("parse_with_ctx: root", type(root), root)
    return root, ctx


def parse(title, text, **kwargs):
    root, ctx = parse_with_ctx(title, text, **kwargs)
    assert isinstance(root, WikiNode)
    assert isinstance(ctx, Wtp)
    return root


class NodeExpTests(unittest.TestCase):

    def backcvt(self, text, expected):
        root, ctx = parse_with_ctx("test", text)
        self.assertEqual(ctx.errors, [])
        self.assertEqual(ctx.warnings, [])
        t = ctx.node_to_wikitext(root)
        self.assertEqual(t, expected)

    def tohtml(self, text, expected):
        root, ctx = parse_with_ctx("test", text)
        self.assertEqual(ctx.errors, [])
        self.assertEqual(ctx.warnings, [])
        t = ctx.node_to_html(root)
        self.assertEqual(t, expected)

    def totext(self, text, expected):
        root, ctx = parse_with_ctx("test", text)
        self.assertEqual(ctx.errors, [])
        self.assertEqual(ctx.warnings, [])
        t = ctx.node_to_text(root)
        self.assertEqual(t, expected)

    def test_basic1(self):
        self.backcvt("", "")

    def test_basic2(self):
        self.backcvt("foo bar\nxyz\n", "foo bar\nxyz\n")

    def test_basic3(self):
        self.backcvt("&amp;amp;", "&amp;amp;")

    def test_basic4(self):
        self.backcvt("{{", "{{")

    def test_title1(self):
        self.backcvt("== T1 ==\nxyz\n", "\n== T1 ==\n\nxyz\n")

    def test_title2(self):
        self.backcvt("=== T1 ===\nxyz\n", "\n=== T1 ===\n\nxyz\n")

    def test_title3(self):
        self.backcvt("==== T1 ====\nxyz\n", "\n==== T1 ====\n\nxyz\n")

    def test_title4(self):
        self.backcvt("===== T1 =====\nxyz\n", "\n===== T1 =====\n\nxyz\n")

    def test_title5(self):
        self.backcvt("====== T1 ======\nxyz\n", "\n====== T1 ======\n\nxyz\n")

    def test_hline1(self):
        self.backcvt("aaa\n----\nbbbb", "aaa\n\n----\n\nbbbb")

    def test_list1(self):
        self.backcvt("*a\n* b\n", "*a\n* b\n")

    def test_list2(self):
        self.backcvt("abc\n*a\n* b\ndef", "abc\n*a\n* b\ndef")

    def test_list3(self):
        self.backcvt("abc\n*a\n*# c\n*# d\n* b\ndef",
                     "abc\n*a\n*# c\n*# d\n* b\ndef")

    def test_list4(self):
        self.backcvt("abc\n*a\n**b\n*:c\n",
                     "abc\n*a\n**b\n*:c\n")

    def test_pre1(self):
        self.backcvt("a<pre>foo\n  bar</pre>b",
                     "a<pre>foo\n  bar</pre>b")

    def test_preformatted1(self):
        self.backcvt(" a\n b", " a\n b")

    def test_link1(self):
        self.backcvt("[[foo bar]]", "[[foo bar]]")

    def test_link2(self):
        self.backcvt("[[foo|bar]]", "[[foo|bar]]")

    def test_link3(self):
        self.backcvt("a [[foo]]s bar", "a [[foo]]s bar")

    def test_template1(self):
        self.backcvt("{{foo|a|b|c=4|{{{arg}}}}}", "{{foo|a|b|c=4|{{{arg}}}}}")

    def test_template2(self):
        self.backcvt("{{foo}}", "{{foo}}")

    def test_template3(self):
        self.backcvt("{{!}}", "{{!}}")

    def test_templatearg1(self):
        self.backcvt("{{{1}}}", "{{{1}}}")

    def test_templatearg2(self):
        self.backcvt("{{{a|def}}}", "{{{a|def}}}")

    def test_templatearg3(self):
        self.backcvt("{{{a|}}}", "{{{a|}}}")

    def test_templatearg4(self):
        self.backcvt("{{{{{templ}}}}}", "{{{{{templ}}}}}")

    def test_parserfn1(self):
        self.backcvt("{{#expr: 1 + 2}}", "{{#expr: 1 + 2}}")

    def test_parserfn2(self):
        self.backcvt("{{#expr:1+{{v}}}}", "{{#expr:1+{{v}}}}")

    def test_parserfn3(self):
        self.backcvt("{{ROOTPAGENAME}}", "{{ROOTPAGENAME:}}")

    def test_url1(self):
        self.backcvt("[https://wikipedia.org]", "[https://wikipedia.org]")

    def test_url2(self):
        self.backcvt("https://wikipedia.org/", "[https://wikipedia.org/]")

    def test_url3(self):
        self.backcvt("https://wikipedia.org/x/y?a=7%255",
                     "[https://wikipedia.org/x/y?a=7%255]")

    def test_table1(self):
        self.backcvt("{| |}", "\n{| \n\n|}\n")

    def test_table2(self):
        self.backcvt('{| class="x"\n|}', '\n{| class="x"\n\n|}\n')

    def test_tablecaption1(self):
        self.backcvt("{|\n|+\ncapt\n|}", "\n{| \n\n|+ \n\ncapt\n\n|}\n")

    def test_tablerowcell1(self):
        self.backcvt("{|\n|- a=1\n| cell\n|}",
                     '\n{| \n\n|- a="1"\n\n| cell\n\n\n|}\n')

    def test_tablerowhdr1(self):
        self.backcvt("{|\n|- a=1\n! cell\n|}",
                     '\n{| \n\n|- a="1"\n\n! cell\n\n\n|}\n')

    def test_magicword1(self):
        self.backcvt("a\n__TOC__\nb", "a\n\n__TOC__\n\nb")

    def test_html1(self):
        self.backcvt("a<b>foo</b>b", "a<b>foo</b>b")

    def test_html2(self):
        self.backcvt('a<span class="bar">foo</span>b',
                     'a<span class="bar">foo</span>b')

    def test_italic1(self):
        self.backcvt("''i''", "''i''")

    def test_bold1(self):
        self.backcvt("''b''", "''b''")

    def test_text1(self):
        self.totext("", "")

    def test_text2(self):
        self.totext("\nfoo bar ", "foo bar")

    def test_text3(self):
        self.totext("<b>foo</b>", "foo")

    def test_text4(self):
        self.totext("<h1>foo</h1><p>bar</p>", "foo\n\nbar")

    def test_text5(self):
        self.totext("foo<ref x=1>bar</ref> z", "foo z")
