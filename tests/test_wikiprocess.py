# Tests for processing WikiText templates and macros
#
# Copyright (c) 2020, 2021, 2022 Tatu Ylonen.  See file LICENSE and https://ylonen.org

import math
import time
import unittest
from typing import Optional
from unittest.mock import patch

from wikitextprocessor import Page, Wtp
from wikitextprocessor.common import MAGIC_NOWIKI_CHAR


class WikiProcTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Wtp()
        self.ctx.add_page("Template:!", 10, "|")
        self.ctx.add_page("Template:((", 10, "&lbrace;&lbrace;")
        self.ctx.add_page("Template:))", 10, "&rbrace;&rbrace;")

    def tearDown(self) -> None:
        self.ctx.close_db_conn()

    def scribunto(
        self, expected_ret: str, body: str, timeout: Optional[int] = None
    ) -> None:
        """This runs a very basic test of scribunto code."""
        self.ctx.add_page(
            "Module:testmod",
            828,
            r"""
local export = {}
function export.testfn(frame)
"""
            + body
            + """
end
return export
""",
            model="Scribunto",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{#invoke:testmod|testfn}}", timeout=timeout)
        self.assertEqual(len(self.ctx.expand_stack), 1)
        self.assertEqual(ret, expected_ret)

    def parserfn(
        self, text: str, expected_ret: str, almost_equal: bool = False
    ) -> None:
        self.ctx.start_page("Tt")
        ret = self.ctx.expand(text)
        if almost_equal:
            self.assertAlmostEqual(float(ret), expected_ret)
        else:
            self.assertEqual(ret, expected_ret)

    def test_preprocess1(self):
        self.ctx.start_page("Tt")
        ret = self.ctx.preprocess_text(
            "a<!-- foo\n -- bar\n- bar\n--- bar\n-- -->b"
        )
        self.assertEqual(ret, "ab")

    def test_preprocess2(self):
        self.ctx.start_page("Tt")
        ret = self.ctx.preprocess_text("a<nowiki />b")
        self.assertEqual(ret, "a" + MAGIC_NOWIKI_CHAR + "b")

    def test_preprocess3(self):
        self.ctx.start_page("Tt")
        ret = self.ctx.preprocess_text("<nowiki />")
        self.assertEqual(ret, MAGIC_NOWIKI_CHAR)

    def test_preprocess4(self):
        s = "a<nowiki>&amp;</nowiki>b"
        expected = "a&amp;b"
        self.ctx.start_page("Tt")
        ret = self.ctx.preprocess_text(s)
        ret = self.ctx._finalize_expand(ret)
        self.assertEqual(ret, expected)

    def test_preprocess5(self):
        s = "<nowiki>a=<>*#:!|[]{}\"'b</nowiki>"
        expected = (
            "a&equals;&lt;&gt;&ast;&num;&colon;"
            "&excl;&vert;&lsqb;&rsqb;&lbrace;"
            "&rbrace;&quot;&apos;b"
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.preprocess_text(s)
        ret = self.ctx._finalize_expand(ret)
        self.assertEqual(ret, expected)

    def test_preprocess6(self):
        s = " <nowiki>a\nb\nc</nowiki>"
        expected = " a\nb\nc"
        self.ctx.start_page("Tt")
        ret = self.ctx.preprocess_text(s)
        ret = self.ctx._finalize_expand(ret)
        self.assertEqual(ret, expected)

    def test_basic(self):
        self.parserfn("Some text", "Some text")

    def test_basic2(self):
        self.parserfn("Some [[link]] x", "Some [[link]] x")

    def test_basic3(self):
        self.parserfn("Some {{{unknown_arg}}} x", "Some {{{unknown_arg}}} x")

    def test_basic4(self):
        self.parserfn(
            "Some {{unknown template}} x",
            "Some [[:Template:unknown template]] x",
        )

    def test_basic5(self):
        self.parserfn(
            "Some {{unknown template|arg1||arg3}}",
            "Some [[:Template:unknown template]]",
        )

    def test_basic6(self):
        self.parserfn("Some [[link text]] x", "Some [[link text]] x")

    def test_basic7(self):
        self.parserfn("Some [[link|text]] x", "Some [[link|text]] x")

    def test_basic8(self):
        self.parserfn("Some [[link|t[ext]]] x", "Some [[link|t[ext]]] x")

    def test_basic9(self):
        self.ctx.add_page("Template:templ", 10, "FOO {{{1|}}}")
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("Some {{templ|[[link|t[ext]]]}} x")
        self.assertEqual(ret, "Some FOO [[link|t[ext]]] x")

    def test_basic10(self):
        self.parserfn("<span>[</span>", "<span>[</span>")
        self.assertEqual(len(self.ctx.errors), 0)
        self.assertEqual(len(self.ctx.warnings), 0)

    def test_basic11(self):
        self.parserfn("a[[foo]]b", "a[[foo]]b")

    def test_basic12(self):
        self.parserfn("a[[foo|bar]]b", "a[[foo|bar]]b")

    @patch(
        "wikitextprocessor.core.Wtp.get_page",
        return_value=Page(
            title="Template:templ",
            namespace_id=10,
            body="a[[{{{1}}}|{{{2}}}]]b",
        ),
    )
    def test_basic13(self, mock_get_page):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("A{{templ|x|y}}B")
        self.assertEqual(ret, "Aa[[x|y]]bB")

    def test_basic14(self):
        self.ctx.add_page(
            "Template:templ", 10, "a[[{{t2|z|zz-{{{1}}}}}|{{{2}}}]]b"
        )
        self.ctx.add_page("Template:t2", 10, "t2{{{1}}}#{{{2}}}")
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("A{{templ|x|y}}B")
        self.assertEqual(ret, "Aa[[t2z#zz-x|y]]bB")

    @patch(
        "wikitextprocessor.core.Wtp.get_page",
        return_value=Page(
            title="Template:templ",
            namespace_id=10,
            body="a[[:{{{1}}}:{{{2}}}|({{{1}}})]]b",
        ),
    )
    def test_basic15(self, mock_get_page):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand(
            "A{{templ|hu|állati|langname=Hungarian|interwiki=1}}B"
        )
        self.assertEqual(ret, "Aa[[:hu:állati|(hu)]]bB")

    @patch(
        "wikitextprocessor.core.Wtp.get_page",
        return_value=Page(
            title="Template:templ",
            namespace_id=10,
            body="a[[:{{{1}}}:{{{2}}}|({{{1}}})]]b",
        ),
    )
    def test_basic16(self, mock_get_page):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand(
            "A{{templ|hu|állati|langname=Hungarian|interwiki=1}}B"
        )
        self.assertEqual(ret, "Aa[[:hu:állati|(hu)]]bB")

    @patch(
        "wikitextprocessor.core.Wtp.get_page",
        return_value=Page(
            title="Template:templ",
            namespace_id=10,
            body="a{{#ifeq:{{{interwiki|}}}|1|[[:{{{1}}}:{{{2}}}|({{{1}}})]]}}b",
        ),
    )
    def test_basic17(self, mock_get_page):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand(
            "A{{templ|hu|állati|langname=Hungarian|interwiki=1}}B"
        )
        self.assertEqual(ret, "Aa[[:hu:állati|(hu)]]bB")

    def test_if1(self):
        self.parserfn("{{#if:|T|F}}", "F")

    def test_if2(self):
        self.parserfn("{{#if:x|T|F}}", "T")

    def test_if3(self):
        self.parserfn("a{{#if:|T}}b", "ab")

    def test_if4(self):
        self.parserfn("a{{#if:x|T}}b", "aTb")

    def test_ifeq1(self):
        self.parserfn("{{#ifeq:a|b|T|F}}", "F")

    def test_ifeq2(self):
        self.parserfn("{{#ifeq:a|a|T|F}}", "T")

    def test_ifeq3(self):
        self.parserfn("{{#ifeq: a |a|T|F}}", "T")

    def test_ifeq4(self):
        self.parserfn("{{#ifeq: ||T|F}}", "T")

    def test_ifeq5(self):
        self.parserfn("a{{#ifeq:a||T}}b", "ab")

    def test_iferror1(self):
        self.parserfn("{{#iferror:|T|F}}", "F")

    def test_iferror2(self):
        self.parserfn("{{#iferror:foo<div>bar</div>bar|T|F}}", "F")

    def test_iferror3(self):
        self.parserfn("{{#iferror:Error|T|F}}", "F")

    def test_iferror4(self):
        self.parserfn('{{#iferror:class="error"|T|F}}', "F")

    def test_iferror5(self):
        self.parserfn('{{#iferror:<span class="error">foo</foo>|T|F}}', "T")

    def test_iferror6(self):
        self.parserfn('{{#iferror:aa<div\nclass="error"\n>foo</div>|T|F}}', "T")

    def test_iferror7(self):
        self.parserfn("{{#iferror:{{#expr:}}|T|F}}", "T")

    def test_iferror8(self):
        self.parserfn("{{#iferror:{{#expr:!!!}}|T|F}}", "T")

    def test_iferror9(self):
        self.parserfn(
            "x{{#iferror: {{#expr: 1 + 2 }} | error | correct }}y", "xcorrecty"
        )

    def test_iferror10(self):
        self.parserfn(
            "{{#iferror: {{#expr: 1 + X }} | error | correct }}", "error"
        )

    def test_iferror11(self):
        self.parserfn("{{#iferror: {{#expr: 1 + 2 }} | error }}", "3")

    def test_iferror12(self):
        self.parserfn("{{#iferror: {{#expr: 1 + X }} | error }}", "error")

    def test_iferror13(self):
        self.parserfn("{{#iferror: {{#expr: 1 + X }} }}", "")

    def test_iferror14(self):
        self.parserfn(
            "{{#iferror: {{#expr: . }} | error | correct }}", "correct"
        )

    def test_iferror15(self):
        self.parserfn(
            '{{#iferror: <strong class="error">a</strong> '
            "| error | correct }}",
            "error",
        )

    def test_ifexpr1(self):
        self.parserfn("a{{#ifexpr:1+3>2|T|F}}b", "aTb")

    def test_ifexpr2(self):
        self.parserfn("a{{#ifexpr:1-4>sin(pi/2)|T|F}}b", "aFb")

    def test_ifexist1(self):
        self.parserfn("{{#ifexist:Nonexxxx|T|F}}", "F")

    def test_ifexist2(self):
        self.parserfn("{{#ifexist:Nonexxxx|T}}", "")

    @patch(
        "wikitextprocessor.core.Wtp.get_page",
        return_value=Page(title="Test title", namespace_id=0, body="FOO"),
    )
    def test_ifexist3(self, mock_get_page):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{#ifexist:Test title|T|F}}")
        self.assertEqual(ret, "T")

    def test_switch1(self):
        self.parserfn("{{#switch:a|a=one|b=two|three}}", "one")

    def test_switch2(self):
        self.parserfn("{{#switch:b|a=one|b=two|three}}", "two")

    def test_switch3(self):
        self.parserfn("{{#switch:c|a=one|b=two|three}}", "three")

    def test_switch4(self):
        self.parserfn("{{#switch:|a=one|b=two|three}}", "three")

    def test_switch5(self):
        self.parserfn("{{#switch:|a=one|#default=three|b=two}}", "three")

    def test_switch6(self):
        self.parserfn("{{#switch:b|a=one|#default=three|b=two}}", "two")

    def test_switch7(self):
        self.parserfn("{{#switch:c|a=one|c|d=four|b=two}}", "four")

    def test_switch8(self):
        self.parserfn("{{#switch:d|a=one|c|d=four|b=two}}", "four")

    def test_switch9(self):
        self.parserfn("{{#switch:b|a=one|c|d=four|b=two}}", "two")

    def test_switch10(self):
        self.parserfn("{{#switch:e|a=one|c|d=four|b=two}}", "")

    def test_switch11(self):
        self.parserfn(
            "{{#switch: d |\na\n=\none\n|\nc\n|"
            "\nd\n=\nfour\n|\nb\n=\ntwo\n}}",
            "four",
        )

    def test_switch12(self):
        self.parserfn("{{#switch:|a=one|=empty|three}}", "empty")

    # XXX test that both sides of switch are evaluated

    def test_categorytree1(self):
        # Currently, the implementation is just a stub that returns the empty
        # string.
        self.parserfn("{{#categorytree:Foo|mode=all}}", "")

    @patch(
        "wikitextprocessor.core.Wtp.get_page",
        return_value=Page(
            title="Test title",
            namespace_id=0,
            body="""
<section begin="foo" />
=== Test section ===
A
<section end="foo" />

=== Other section ===
B

<SECTION BEGIN=foo />
MORE
<section end=foo />

<section begin="bar" />
NOT
<section end="bar" />
""",
        ),
    )
    def test_lst_fn(self, mock_get_page):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{#lst:testpage|foo}}")
        self.assertEqual(
            ret,
            """
=== Test section ===
A

MORE
""",
        )

    def test_tag1(self):
        self.parserfn("{{#tag:br}}", "<br />")

    def test_tag2(self):
        self.parserfn("{{#tag:div|foo bar}}", "<div>foo bar</div>")

    def test_tag3(self):
        self.parserfn(
            """{{#tag:div|foo bar|class=foo|id=me}}""",
            """<div class="foo" id="me">foo bar</div>""",
        )

    def test_tag4(self):
        self.parserfn(
            """{{#tag:div|foo bar|class=foo|text=m"e'a}}""",
            """<div class="foo" text="m&quot;e&#x27;a">""" """foo bar</div>""",
        )

    def test_tag5(self):
        self.parserfn(
            "{{#tag:div|foo bar<dangerous>z}}", "<div>foo bar<dangerous>z</div>"
        )

    def test_tag6(self):
        self.parserfn("{{#tag:nowiki|foo bar}}", "foo bar")

    def test_tag7(self):
        self.parserfn("{{#tag:nowiki|&amp;}}", "&amp;")

    def test_tag8(self):
        self.parserfn("{{{#tag:nowiki}}{!}}", "{{!}}")

    def test_fullpagename1(self):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{FULLPAGENAME}}")
        self.assertEqual(ret, "Tt")

    def test_fullpagename2(self):
        self.ctx.start_page("Help:Tt/doc")
        ret = self.ctx.expand("{{FULLPAGENAME}}")
        self.assertEqual(ret, "Help:Tt/doc")

    def test_fullpagename3(self):
        self.ctx.start_page("Help:Tt/doc")
        ret = self.ctx.expand("{{FULLPAGENAME:Template:Mark/doc}}")
        self.assertEqual(ret, "Template:Mark/doc")

    def test_pagename1(self):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{PAGENAME}}")
        self.assertEqual(ret, "Tt")

    def test_pagename2(self):
        self.ctx.start_page("Help:Tt/doc")
        ret = self.ctx.expand("{{PAGENAME}}")
        self.assertEqual(ret, "Tt/doc")

    def test_pagename3(self):
        self.ctx.start_page("Help:Tt/doc")
        ret = self.ctx.expand("{{PAGENAME:Template:Mark/doc}}")
        self.assertEqual(ret, "Mark/doc")

    def test_pagenamee1(self):
        self.ctx.start_page("Test page")
        ret = self.ctx.expand("{{PAGENAMEE}}")
        self.assertEqual(ret, "Test_page")

    def test_pagenamee2(self):
        self.ctx.start_page("Help:test page/doc")
        ret = self.ctx.expand("{{PAGENAMEE}}")
        self.assertEqual(ret, "test_page/doc")

    def test_rootpagenamee1(self):
        self.ctx.start_page("Test page")
        ret = self.ctx.expand("{{ROOTPAGENAMEE}}")
        self.assertEqual(ret, "Test_page")

    def test_rootpagenamee2(self):
        self.ctx.start_page("Help:test page/doc/bar/foo")
        ret = self.ctx.expand("{{ROOTPAGENAMEE}}")
        self.assertEqual(ret, "test_page")

    def test_fullpagenamee1(self):
        self.ctx.start_page("Test page")
        ret = self.ctx.expand("{{FULLPAGENAMEE}}")
        self.assertEqual(ret, "Test_page")

    def test_fullpagenamee2(self):
        self.ctx.start_page("Help:test page/doc")
        ret = self.ctx.expand("{{FULLPAGENAMEE}}")
        self.assertEqual(ret, "Help:test_page/doc")

    def test_basepagename1(self):
        self.ctx.start_page("Help:Tt/doc/subdoc")
        ret = self.ctx.expand("{{BASEPAGENAME}}")
        self.assertEqual(ret, "Tt/doc")

    def test_basepagename2(self):
        self.ctx.start_page("Test title")
        ret = self.ctx.expand("{{BASEPAGENAME}}")
        self.assertEqual(ret, "Test title")

    def test_subpagename1(self):
        self.ctx.start_page("Help:Tt/doc/subdoc")
        ret = self.ctx.expand("{{SUBPAGENAME}}")
        self.assertEqual(ret, "subdoc")

    def test_subpagename2(self):
        self.ctx.start_page("Help:Tt/doc/subdoc")
        ret = self.ctx.expand("{{SUBPAGENAME:Template:test/subtest}}")
        self.assertEqual(ret, "subtest")

    def test_subpagename3(self):
        self.ctx.start_page("Help:Tt")
        ret = self.ctx.expand("{{SUBPAGENAME}}")
        self.assertEqual(ret, "Tt")

    def test_subpagename4(self):
        self.ctx.start_page("Help:Tt")
        ret = self.ctx.expand("{{SUBPAGENAME:Foo/bar}}")
        self.assertEqual(ret, "bar")

    def test_subpagename5(self):
        self.ctx.start_page("Help:Tt/doc")
        ret = self.ctx.expand("{{SUBPAGENAME}}")
        self.assertEqual(ret, "doc")

    def test_subpagename6(self):
        self.ctx.start_page("Help:Tt")
        ret = self.ctx.expand("{{SUBPAGENAME:Help:TestPage}}")
        self.assertEqual(ret, "TestPage")

    def test_talkpagename1(self):
        self.ctx.start_page("Help:Tt")
        ret = self.ctx.expand("{{TALKPAGENAME}}")
        self.assertEqual(ret, "Help talk:Tt")

    def test_talkpagename2(self):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{TALKPAGENAME}}")
        self.assertEqual(ret, "Talk:Tt")

    def test_talkpagename3(self):
        self.ctx.start_page("X:Tt")
        ret = self.ctx.expand("{{TALKPAGENAME}}")
        self.assertEqual(ret, "Talk:X:Tt")

    def test_namespace1(self):
        self.ctx.start_page("Help:Tt/doc")
        ret = self.ctx.expand("{{NAMESPACE}}")
        self.assertEqual(ret, "Help")

    def test_namespace2(self):
        self.ctx.start_page("Tt/doc")
        ret = self.ctx.expand("{{NAMESPACE}}")
        self.assertEqual(ret, "")

    def test_namespace3(self):
        self.ctx.start_page("Help:Tt/doc")
        ret = self.ctx.expand("{{NAMESPACE:Template:Kk}}")
        self.assertEqual(ret, "Template")

    def test_revisionid1(self):
        # We emulate miser mode here, always returning a dash.
        self.parserfn("{{REVISIONID}}", "-")

    def test_revisionuser1(self):
        # We just always return a dummy user
        self.parserfn("{{REVISIONUSER}}", "AnonymousUser")

    def test_uc(self):
        self.parserfn("{{uc:foo}}", "FOO")

    def test_lc(self):
        self.parserfn("{{lc:FOO}}", "foo")

    def test_lcfirst(self):
        self.parserfn("{{lcfirst:FOO}}", "fOO")

    def test_ucfirst(self):
        self.parserfn("{{ucfirst:foo}}", "Foo")

    def test_formatnum1(self):
        self.parserfn("{{formatnum:987654321.654321}}", "987,654,321.654321")

    def test_formatnum2(self):
        self.parserfn("{{formatnum:9.6}}", "9.6")

    def test_formatnum3(self):
        self.parserfn("{{formatnum:123}}", "123")

    def test_formatnum4(self):
        self.parserfn("{{formatnum:1234}}", "1,234")

    def test_formatnum5(self):
        self.parserfn("{{formatnum:1234.778}}", "1,234.778")

    def test_formatnum6(self):
        self.parserfn("{{formatnum:123456}}", "123,456")

    def test_formatnum7(self):
        self.parserfn("{{formatnum:1234.778|NOSEP}}", "1234.778")

    def test_formatnum8(self):
        self.parserfn("{{formatnum:00001}}", "00,001")

    def test_formatnum9(self):
        self.parserfn("{{formatnum:1,000,001.07|R}}", "1000001.07")

    def test_formatnum10(self):
        self.parserfn("{{formatnum:12345}}", "12,345")

    def test_dateformat1(self):
        self.parserfn("{{#dateformat:25 dec 2009|ymd}}", "2009 Dec 25")

    def test_dateformat2(self):
        self.parserfn("{{#dateformat:25 dec 2009|mdy}}", "Dec 25, 2009")

    def test_dateformat3(self):
        self.parserfn("{{#dateformat:25 dec 2009|ISO 8601}}", "2009-12-25")

    def test_dateformat4(self):
        self.parserfn("{{#dateformat:25 dec 2009}}", "2009-12-25")

    def test_dateformat5(self):
        self.parserfn("{{#dateformat:25 dec 2009|dmy}}", "25 Dec 2009")

    def test_dateformat6(self):
        self.parserfn("{{#dateformat:2011-11-09|dmy}}", "09 Nov 2011")

    def test_dateformat7(self):
        self.parserfn("{{#dateformat:2011 Nov 9|dmy}}", "09 Nov 2011")

    def test_dateformat8(self):
        self.parserfn("{{#dateformat:2011 NovEmber 9|dmy}}", "09 Nov 2011")

    def test_dateformat9(self):
        self.parserfn("{{#dateformat:25 December|mdy}}", "Dec 25")

    def test_dateformat10(self):
        self.parserfn("{{#dateformat:25 December|dmy}}", "25 Dec")

    def test_formatdate1(self):
        self.parserfn("{{#formatdate:25 December|dmy}}", "25 Dec")

    def test_formatdate2(self):
        self.parserfn("{{#formatdate: launched 2000 }}", "launched 2000")

    def test_formatdate3(self):
        self.parserfn(
            "{{#formatdate: totally bogus date }}", "totally bogus date"
        )

    def test_fullurl1(self):
        self.parserfn(
            "{{fullurl:Test page|action=edit}}",
            "//en.wiktionary.org/wiki/Test_page?action=edit",
        )

    # XXX implement and test interwiki prefixes for fullurl

    def test_urlencode1(self):
        self.parserfn("{{urlencode:x:y/z k}}", "x%3Ay%2Fz+k")

    def test_urlencode2(self):
        self.parserfn("{{urlencode:x:y/z kä|QUERY}}", "x%3Ay%2Fz+k%C3%A4")

    def test_urlencode3(self):
        self.parserfn("{{urlencode:x:y/z kä|WIKI}}", "x:y/z_k%C3%A4")

    def test_urlencode4(self):
        self.parserfn("{{urlencode:x:y/z kä|PATH}}", "x%3Ay%2Fz%20k%C3%A4")

    def test_achorencode1(self):
        self.parserfn("{{anchorencode:x:y/z kä}}", "x:y/z_kä")

    def test_ns1(self):
        self.parserfn("{{ns:6}}", "File")

    def test_ns2(self):
        self.parserfn("{{ns:File}}", "File")

    def test_ns3(self):
        self.parserfn("{{ns:Image}}", "File")

    def test_ns4(self):
        self.parserfn("{{ns:Nonexistentns}}", "[[:Template:ns:Nonexistentns]]")

    def test_titleparts1(self):
        self.parserfn("{{#titleparts:foo}}", "foo")

    def test_titleparts2(self):
        self.parserfn("{{#titleparts:foo/bar/baz}}", "foo/bar/baz")

    def test_titleparts3(self):
        self.parserfn("{{#titleparts:Help:foo/bar/baz}}", "Help:foo/bar/baz")

    def test_titleparts4(self):
        self.parserfn("{{#titleparts:foo|1|-1}}", "foo")

    def test_titleparts5(self):
        self.parserfn("{{#titleparts:foo/bar/baz|1|-2}}", "bar")

    def test_titleparts6(self):
        self.parserfn("{{#titleparts:Help:foo/bar/baz|2|1}}", "foo/bar")

    def test_titleparts7(self):
        self.parserfn("{{#titleparts:Help:foo/bar/baz||-2}}", "bar/baz")

    def test_titleparts8(self):
        self.parserfn("{{#titleparts:Help:foo/bar/baz|2}}", "Help:foo")

    def test_expr1(self):
        self.parserfn(
            "{{#expr}}",
            '<strong class="error">Expression error near '
            "&lt;end&gt;</strong>",
        )

    def test_expr2(self):
        self.parserfn("{{#expr|1 + 2.34}}", "3.34")

    def test_expr3(self):
        self.parserfn("{{#expr|1 + 2.34}}", "3.34")

    def test_expr4(self):
        self.parserfn("{{#expr|-12}}", "-12")

    def test_expr5(self):
        self.parserfn("{{#expr|-trunc12}}", "-12")

    def test_expr6(self):
        self.parserfn("{{#expr|-trunc(-2^63)}}", "9223372036854775808")

    def test_expr7(self):
        self.parserfn("{{#expr|-trunc(-2^63)}}", "9223372036854775808")

    def test_expr8(self):
        self.parserfn("{{#expr|2e3}}", "2000")

    def test_expr9(self):
        self.parserfn("{{#expr|-2.3e-4}}", "-0.00022999999999999998")

    def test_expr10(self):
        self.parserfn("{{#expr|(trunc2)e(trunc-3)}}", "0.002")

    def test_expr11(self):
        self.parserfn("{{#expr|(trunc2)e(trunc0)}}", "2")

    def test_expr12(self):
        self.parserfn("{{#expr|(trunc2)e(trunc18)}}", "2000000000000000000")

    def test_expr13(self):
        self.parserfn("{{#expr|6e(5-2)e-2}}", "60")

    def test_expr14(self):
        self.parserfn("{{#expr|1e.5}}", "3.1622776601683795")

    def test_expr15(self):
        self.parserfn("{{#expr|exp43}}", "4727839468229346304")

    def test_expr16(self):
        self.parserfn("{{#expr|exp trunc0}}", "1")

    def test_expr17(self):
        self.parserfn("{{#expr|ln2}}", "0.6931471805599453")

    def test_expr18(self):
        self.parserfn("{{#expr|ln trunc1}}", "0")

    def test_expr19(self):
        self.parserfn("{{#expr|ln.5e-323}}", "-744.4400719213812")

    def test_expr20(self):
        self.parserfn("{{#expr|abs-2}}", "2")

    def test_expr21(self):
        self.parserfn("{{#expr|sqrt 4}}", "2")

    def test_expr22(self):
        self.parserfn("{{#expr|trunc1.2}}", "1")

    def test_expr23(self):
        self.parserfn("{{#expr|trunc-1.2}}", "-1")

    def test_expr24(self):
        self.parserfn("{{#expr|floor1.2}}", "1")

    def test_expr25(self):
        self.parserfn("{{#expr|floor-1.2}}", "-2")

    def test_expr26(self):
        self.parserfn("{{#expr|ceil1.2}}", "2")

    def test_expr27(self):
        self.parserfn("{{#expr|ceil-1.2}}", "-1")

    def test_expr28(self):
        self.parserfn("{{#expr|sin(30*pi/180)}}", "0.49999999999999994")

    def test_expr29(self):
        self.parserfn("{{#expr|cos.1}}", "0.9950041652780258")

    def test_expr30(self):
        self.parserfn("{{#expr|tan.1}}", 0.10033467208545055, True)

    def test_expr31(self):
        self.parserfn("{{#expr|asin.1}}", "0.1001674211615598")

    def test_expr32(self):
        self.parserfn("{{#expr|acos.1}}", "1.4706289056333368")

    def test_expr33(self):
        self.parserfn("{{#expr|atan.1}}", "0.09966865249116204")

    def test_expr34(self):
        self.parserfn("{{#expr|not0}}", "1")

    def test_expr35(self):
        self.parserfn("{{#expr|not1}}", "0")

    def test_expr36(self):
        self.parserfn("{{#expr|not trunc2.1}}", "0")

    def test_expr37(self):
        self.parserfn("{{#expr|2^3}}", "8")

    def test_expr38(self):
        self.parserfn("{{#expr|2^-3}}", "0.125")

    def test_expr39(self):
        self.parserfn("{{#expr|2*3}}", "6")

    def test_expr40(self):
        self.parserfn("{{#expr|(trunc2)*3}}", "6")

    def test_expr41(self):
        self.parserfn("{{#expr|1 + 2 * 3}}", "7")

    def test_expr42(self):
        self.parserfn("{{#expr|4/2}}", "2")

    def test_expr43(self):
        self.parserfn("{{#expr|5 div 2}}", "2.5")

    def test_expr44(self):
        self.parserfn("{{#expr|5 mod 2}}", "1")

    def test_expr45(self):
        self.parserfn("{{#expr|5+2}}", "7")

    def test_expr46(self):
        self.parserfn("{{#expr|5.1--2.7}}", "7.8")

    def test_expr47(self):
        self.parserfn("{{#expr|9.876round2}}", "9.88")

    def test_expr48(self):
        self.parserfn("{{#expr|trunc1234round trunc-2}}", "1200")

    def test_expr49(self):
        self.parserfn("{{#expr|3.0=3}}", "1")

    def test_expr50(self):
        self.parserfn("{{#expr|3.1=3.0}}", "0")

    def test_expr51(self):
        self.parserfn("{{#expr|3.0<>3.0}}", "0")

    def test_expr52(self):
        self.parserfn("{{#expr|3.1!=3.0}}", "1")

    def test_expr53(self):
        self.parserfn("{{#expr|3.0<3.1}}", "1")

    def test_expr54(self):
        self.parserfn("{{#expr|3.0<3.0}}", "0")

    def test_expr55(self):
        self.parserfn("{{#expr|3.1>3.0}}", "1")

    def test_expr56(self):
        self.parserfn("{{#expr|3.1>3.1}}", "0")

    def test_expr57(self):
        self.parserfn("{{#expr|3.1>=3.0}}", "1")

    def test_expr58(self):
        self.parserfn("{{#expr|3.1>=3.1}}", "1")

    def test_expr59(self):
        self.parserfn("{{#expr|3.0<=3.1}}", "1")

    def test_expr60(self):
        self.parserfn("{{#expr|3.0<=3.0}}", "1")

    def test_expr61(self):
        self.parserfn("{{#expr|3.1<=3.0}}", "0")

    def test_expr62(self):
        self.parserfn("{{#expr|e}}", str(math.e))

    def test_expr63(self):
        self.parserfn("{{#expr|pi}}", str(math.pi))

    def test_expr64(self):
        self.parserfn("{{#expr|+trunc1.1}}", "1")

    def test_expr65(self):
        self.parserfn("{{#expr|.}}", "0")

    def test_padleft1(self):
        self.parserfn("{{padleft:xyz|5}}", "00xyz")

    def test_padleft2(self):
        self.parserfn("{{padleft:xyz|5|_}}", "__xyz")

    def test_padleft3(self):
        self.parserfn("{{padleft:xyz|5|abc}}", "abxyz")

    def test_padleft4(self):
        self.parserfn("{{padleft:xyz|2}}", "xyz")

    def test_padleft5(self):
        self.parserfn("{{padleft:|1|xyz}}", "x")

    def test_padright1(self):
        self.parserfn("{{padright:xyz|5}}", "xyz00")

    def test_padright2(self):
        self.parserfn("{{padright:xyz|5|_}}", "xyz__")

    def test_padright3(self):
        self.parserfn("{{padright:xyz|5|abc}}", "xyzab")

    def test_padright4(self):
        self.parserfn("{{padright:xyz|2}}", "xyz")

    def test_padright5(self):
        self.parserfn("{{padright:|1|xyz}}", "x")

    def test_time1(self):
        self.ctx.start_page("Tt")
        t1 = time.time()
        ret = self.ctx.expand("{{#time:U}}")
        t2 = time.time()
        self.assertLessEqual(int(t1), float(ret))
        self.assertLessEqual(float(ret), t2)

    def test_time2(self):
        self.parserfn("{{#time:Y|January 3, 1999}}", "1999")

    def test_time3(self):
        self.parserfn("{{#time:y|January 3, 1999}}", "99")

    def test_time4(self):
        self.parserfn("{{#time:L|January 3, 1999}}", "0")

    def test_time5(self):
        self.parserfn("{{#time:L|January 3, 2004}}", "1")

    def test_time6(self):
        self.parserfn("{{#time:L|January 3, 2100}}", "0")

    def test_time7(self):
        self.parserfn("{{#time:L|January 3, 2400}}", "1")

    def test_time8(self):
        self.parserfn("{{#time:o|January 1, 2000}}", "1999")

    def test_time9(self):
        self.parserfn("{{#time:o|January 10, 2000}}", "2000")

    def test_time10(self):
        self.parserfn("{{#time:o|January 1, 2007}}", "2007")

    def test_time11(self):
        self.parserfn("{{#time:n|February 7, 2007}}", "2")

    def test_time12(self):
        self.parserfn("{{#time:m|February 7, 2007}}", "02")

    def test_time13(self):
        self.parserfn("{{#time:j|February 7, 2007}}", "7")

    def test_time14(self):
        self.parserfn("{{#time:d|February 7, 2007}}", "07")

    def test_time15(self):
        self.parserfn("{{#time:M|February 7, 2007|en}}", "Feb")

    def test_time16(self):
        self.parserfn("{{#time:F|February 7, 2007|en}}", "February")

    def test_time17(self):
        # XXX month should really be in genitive
        # Also test tokenization of format string
        self.parserfn(
            """{{#time:Yxgd "(foo)"|February 7, 2007|en}}""",
            "2007February07 (foo)",
        )

    def test_time18(self):
        self.parserfn("{{#time:z|January 6, 2007}}", "5")

    def test_time19(self):
        self.parserfn("{{#time:W|January 2, 2007}}", "01")

    def test_time20(self):
        self.parserfn("{{#time:W|February 2, 2007}}", "05")

    def test_time21(self):
        self.parserfn("{{#time:N|February 4, 2007}}", "7")

    def test_time22(self):
        self.parserfn("{{#time:w|February 4, 2007}}", "0")

    def test_time23(self):
        self.parserfn("{{#time:D|February 4, 2007|en}}", "Sun")

    def test_time24(self):
        self.parserfn("{{#time:l|February 4, 2007|en}}", "Sunday")

    def test_time25(self):
        self.parserfn("{{#time:A|February 4, 2007 10:00|en}}", "AM")

    def test_time26(self):
        self.parserfn("{{#time:A|February 4, 2007 21:00|en}}", "PM")

    def test_time27(self):
        self.parserfn("{{#time:g|February 4, 2007 21:00|en}}", "9")

    def test_time28(self):
        self.parserfn("{{#time:h|February 4, 2007 21:00|en}}", "09")

    def test_time29(self):
        self.parserfn("{{#time:G|February 4, 2007 09:00|en}}", "9")

    def test_time30(self):
        self.parserfn("{{#time:H|February 4, 2007 21:00|en}}", "21")

    def test_time31(self):
        self.parserfn("{{#time:H|February 4, 2007 09:00|en}}", "09")

    def test_time32(self):
        self.parserfn("{{#time:i|February 4, 2007 21:11:22|en}}", "11")

    def test_time33(self):
        self.parserfn("{{#time:s|February 4, 2007 21:11:22|en}}", "22")

    def test_time34(self):
        self.parserfn("{{#time:e|February 4, 2007 10:00}}", "UTC")

    # def test_time34(self):
    #    # This requires Python 3.7 ?
    #    # XXX also different timezone name formats, so the test does not work
    #    tzname = datetime.datetime.now().astimezone().tzname()
    #    self.parserfn("{{#time:e|February 4, 2007 10:00||1}}", tzname)
    # XXX should also test T

    def test_time35(self):
        self.parserfn("{{#time:H|February 4, 2007 10:00||1}}", "10")

    def test_time36(self):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{#time:I}}")
        self.assertIn(ret, ["0", "1"])

    def test_time37(self):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{#time:0}}")
        self.assertEqual(len(ret), 5)

    def test_time38(self):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{#time:P}}")
        self.assertEqual(len(ret), 6)

    def test_time39(self):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{#time:Z}}")
        self.assertLessEqual(0, int(ret))
        self.assertLess(int(ret), 24 * 3600)

    def test_time40(self):
        self.parserfn("{{#time:t|February 4, 2007 10:00}}", "28")

    def test_time41(self):
        self.parserfn("{{#time:t|February 4, 2004 10:00}}", "29")

    def test_time42(self):
        self.parserfn("{{#time:t|July 4, 2004 10:00}}", "31")

    def test_time43(self):
        self.parserfn(
            "{{#time:c|July 4, 2004 10:11:22}}", "2004-07-04T10:11:22+00:00"
        )

    def test_time44(self):
        self.parserfn(
            "{{#time:r|22 oct 2020 19:00:59}}",
            "Thu, 22 Oct 2020 19:00:59 +0000",
        )

    def test_time45(self):
        self.parserfn("{{#time:z|February 2, 2007}}", "32")

    def test_len1(self):
        self.parserfn("{{#len: xyz }}", "3")

    def test_len2(self):
        self.parserfn("{{#len: xyz }}", "3")

    def test_pos1(self):
        self.parserfn("{{#pos: xyzayz |yz}}", "1")

    def test_pos2(self):
        self.parserfn("{{#pos: xyzayz |zz}}", "")

    def test_pos3(self):
        self.parserfn("{{#pos: xyz ayz }}", "3")

    def test_rpos1(self):
        self.parserfn("{{#rpos: xyzayz |yz}}", "4")

    def test_rpos2(self):
        self.parserfn("{{#rpos: xyzayz |zz}}", "-1")

    def test_rpos3(self):
        self.parserfn("{{#rpos: xy za yz }}", "5")

    def test_sub1(self):
        self.parserfn("{{#sub: xyzayz |3}}", "ayz")

    def test_sub2(self):
        self.parserfn("{{#sub:Icecream|3}}", "cream")

    def test_sub3(self):
        self.parserfn("{{#sub:Icecream|0|3}}", "Ice")

    def test_sub4(self):
        self.parserfn("{{#sub:Icecream|-3}}", "eam")

    def test_sub5(self):
        self.parserfn("{{#sub:Icecream|3|3}}", "cre")

    def test_sub6(self):
        self.parserfn("{{#sub:Icecream|3|-3}}", "cr")

    def test_sub7(self):
        self.parserfn("{{#sub:Icecream|-3|2}}", "ea")

    def test_sub8(self):
        self.parserfn("{{#sub:Icecream|3|0}}", "cream")

    def test_sub9(self):
        self.parserfn("{{#sub:Icecream|3|-6}}", "")

    def test_pad1(self):
        self.parserfn("{{#pad:Ice|10|xX}}", "xXxXxXxIce")

    def test_pad2(self):
        self.parserfn("{{#pad:Ice|5|x|left}}", "xxIce")

    def test_pad3(self):
        self.parserfn("{{#pad:Ice|5|x|right}}", "Icexx")

    def test_pad4(self):
        self.parserfn("{{#pad:Ice|5|x|center}}", "xIcex")

    def test_pad5(self):
        self.parserfn("{{#pad:Ice|5|x}}", "xxIce")

    def test_replace1(self):
        self.parserfn("{{#replace:Icecream|e|E}}", "IcEcrEam")

    def test_replace2(self):
        self.parserfn("{{#replace:Icecream|e|}}", "Iccram")

    def test_replace3(self):
        self.parserfn("{{#replace:Icecream|ea|EAEA}}", "IcecrEAEAm")

    def test_explode1(self):
        self.parserfn("{{#explode:And if you tolerate this| |2}}", "you")

    def test_explode2(self):
        self.parserfn("{{#explode:String/Functions/Code|/|-1}}", "Code")

    def test_explode3(self):
        self.parserfn(
            "{{#explode:Split%By%Percentage%Signs|%|2}}", "Percentage"
        )

    def test_explode4(self):
        self.parserfn(
            "{{#explode:And if you tolerate this thing| |2|3}}",
            "you tolerate this thing",
        )

    def test_f_urlencode1(self):
        self.parserfn("{{#urlencode:x:y/z kä}}", "x%3Ay%2Fz+k%C3%A4")

    def test_f_urldecode1(self):
        self.parserfn("{{#urldecode:x%3Ay%2Fz+k%C3%A4}}", "x:y/z kä")

    def test_subjectspace1(self):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{SUBJECTSPACE}}")
        self.assertEqual(ret, "")

    def test_subjectspace2(self):
        self.ctx.start_page("Reconstruction:Tt")
        ret = self.ctx.expand("{{SUBJECTSPACE}}")
        self.assertEqual(ret, "Reconstruction")

    def test_subjectspace3(self):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{SUBJECTSPACE:Reconstruction:foo}}")
        self.assertEqual(ret, "Reconstruction")

    def test_talkspace1(self):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{TALKSPACE}}")
        self.assertEqual(ret, "Talk")

    def test_talkspace2(self):
        self.ctx.start_page("Reconstruction:Tt")
        ret = self.ctx.expand("{{TALKSPACE}}")
        self.assertEqual(ret, "Reconstruction talk")

    def test_talkspace3(self):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{TALKSPACE:Reconstruction:foo}}")
        self.assertEqual(ret, "Reconstruction talk")

    def test_localurl1(self):
        self.ctx.start_page("test page")
        ret = self.ctx.expand("{{localurl}}")
        self.assertEqual(ret, "/wiki/test_page")

    def test_localurl2(self):
        self.ctx.start_page("test page")
        ret = self.ctx.expand("{{localurl|Reconstruction:another title}}")
        self.assertEqual(ret, "/wiki/Reconstruction:another_title")

    def test_currentmonthname1(self):
        self.ctx.start_page("test page")
        ret = self.ctx.expand("{{CURRENTMONTHNAME}}")
        self.assertIn(
            ret,
            [
                "January",
                "February",
                "March",
                "April",
                "May",
                "June",
                "July",
                "August",
                "September",
                "October",
                "November",
                "December",
            ],
        )

    def test_server1(self):
        self.parserfn("{{SERVER}}", "//en.wiktionary.org")

    def test_servername1(self):
        self.parserfn("{{SERVERNAME}}", "en.wiktionary.org")

    def test_currentmonthabbrev1(self):
        self.ctx.start_page("test page")
        ret = self.ctx.expand("{{CURRENTMONTHABBREV}}")
        self.assertIn(
            ret,
            [
                "Jan",
                "Feb",
                "Mar",
                "Apr",
                "May",
                "Jun",
                "Jul",
                "Aug",
                "Sep",
                "Oct",
                "Nov",
                "Dec",
            ],
        )

    @patch(
        "wikitextprocessor.core.Wtp.get_page",
        return_value=Page(
            title="Template:template", namespace_id=10, body="test content"
        ),
    )
    def test_template1(self, mock_get_page):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("a{{template}}b")
        self.assertEqual(ret, "atest contentb")

    @patch(
        "wikitextprocessor.core.Wtp.get_page",
        return_value=Page(
            title="Template:template", namespace_id=10, body=" test content "
        ),
    )
    def test_template2(self, mock_get_page):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("a{{template}}b")
        self.assertEqual(ret, "a test content b")

    @patch(
        "wikitextprocessor.core.Wtp.get_page",
        return_value=Page(
            title="Template:template", namespace_id=10, body="* test content\n"
        ),
    )
    def test_template3(self, mock_get_page):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("a{{template}}b")
        self.assertEqual(ret, "a\n* test content\nb")

    @patch(
        "wikitextprocessor.core.Wtp.get_page",
        return_value=Page(
            title="Template:template",
            namespace_id=10,
            body="test {{{1}}} content",
        ),
    )
    def test_template4(self, mock_get_page):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{template}}")
        self.assertEqual(ret, "test {{{1}}} content")

    @patch(
        "wikitextprocessor.core.Wtp.get_page",
        return_value=Page(
            title="Template:template",
            namespace_id=10,
            body="test {{{1}}} content",
        ),
    )
    def test_template5(self, mock_get_page):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{template|foo}}")
        self.assertEqual(ret, "test foo content")

    @patch(
        "wikitextprocessor.core.Wtp.get_page",
        return_value=Page(
            title="Template:template",
            namespace_id=10,
            body="test {{{1}}} content",
        ),
    )
    def test_template6(self, mock_get_page):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{template|}}")
        self.assertEqual(ret, "test  content")

    @patch(
        "wikitextprocessor.core.Wtp.get_page",
        return_value=Page(
            title="Template:template",
            namespace_id=10,
            body="test {{{1|}}} content",
        ),
    )
    def test_template7(self, mock_get_page):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{template}}")
        self.assertEqual(ret, "test  content")

    @patch(
        "wikitextprocessor.core.Wtp.get_page",
        return_value=Page(
            title="Template:template",
            namespace_id=10,
            body="test {{{1|def}}} content",
        ),
    )
    def test_template8(self, mock_get_page):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{template}}")
        self.assertEqual(ret, "test def content")

    @patch(
        "wikitextprocessor.core.Wtp.get_page",
        return_value=Page(
            title="Template:template",
            namespace_id=10,
            body="test {{{1|def}}} content",
        ),
    )
    def test_template9(self, mock_get_page):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{template|foo}}")
        self.assertEqual(ret, "test foo content")

    @patch(
        "wikitextprocessor.core.Wtp.get_page",
        return_value=Page(
            title="Template:template",
            namespace_id=10,
            body="test {{{{{{1}}}}}} content",
        ),
    )
    def test_template10(self, mock_get_page):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{template|2|foo|bar}}")
        self.assertEqual(ret, "test foo content")

    @patch(
        "wikitextprocessor.core.Wtp.get_page",
        return_value=Page(
            title="Template:template",
            namespace_id=10,
            body="test {{{{{{1}}}}}} content",
        ),
    )
    def test_template11(self, mock_get_page):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{template|3|foo|bar}}")
        self.assertEqual(ret, "test bar content")

    @patch(
        "wikitextprocessor.core.Wtp.get_page",
        return_value=Page(
            title="Template:template",
            namespace_id=10,
            body="test {{{foo|{{{1}}}}}} content",
        ),
    )
    def test_template12(self, mock_get_page):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{template}}")
        self.assertEqual(ret, "test {{{1}}} content")

    @patch(
        "wikitextprocessor.core.Wtp.get_page",
        return_value=Page(
            title="Template:template",
            namespace_id=10,
            body="test {{{foo|{{{1}}}}}} content",
        ),
    )
    def test_template13(self, mock_get_page):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{template|foo=zap}}")
        self.assertEqual(ret, "test zap content")

    @patch(
        "wikitextprocessor.core.Wtp.get_page",
        return_value=Page(
            title="Template:template",
            namespace_id=10,
            body="test {{{foo|{{{1}}}}}} content",
        ),
    )
    def test_template14(self, mock_get_page):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{template|Zap}}")
        self.assertEqual(ret, "test Zap content")

    @patch(
        "wikitextprocessor.core.Wtp.get_page",
        return_value=Page(
            title="Template:template",
            namespace_id=10,
            body="test {{{foo|{{{1}}}}}} content",
        ),
    )
    def test_template15(self, mock_get_page):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{template|bar=kak|Zap}}")
        self.assertEqual(ret, "test Zap content")

    def test_template17(self):
        self.ctx.add_page("Template:template1", 10, "a{{template2|{{{1}}}}}b")
        self.ctx.add_page("Template:template2", 10, "x{{{1}}}y")
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{template1|zz}}")
        self.assertEqual(ret, "axzzyb")

    def test_template18(self):
        self.ctx.add_page("Template:template1", 10, "a{{template2|{{{1}}}}}b")
        self.ctx.add_page("Template:template2", 10, "{{#if:{{{1}}}|x|y}}")
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{template1|zz}}")
        self.assertEqual(ret, "axb")

    def test_template19(self):
        self.ctx.add_page("Template:template1", 10, "a{{template2|{{{1}}}}}b")
        self.ctx.add_page("Template:template2", 10, "{{#if:{{{1}}}|x|y}}")
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{template1|}}")
        self.assertEqual(ret, "ayb")

    def test_template20(self):
        self.ctx.add_page("Template:template1", 10, "a{{template2|{{{1}}}}}b")
        self.ctx.add_page("Template:template2", 10, "{{#if:{{{1}}}|x|y}}")
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{template1}}")
        self.assertEqual(ret, "axb")  # condition expands to {{{1}}}

    def test_template21(self):
        self.ctx.add_page("Template:template1", 10, "a{{template2|{{{1}}}}}b")
        self.ctx.add_page("Template:template2", 10, "c{{template3|{{{1}}}}}d")
        self.ctx.add_page("Template:template3", 10, "f{{{1}}}g")
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{template1}}")
        self.assertEqual(ret, "acf{{{1}}}gdb")

    def test_template22(self):
        self.ctx.add_page("Template:template1", 10, "a{{template2|{{{1}}}}}b")
        self.ctx.add_page("Template:template2", 10, "c{{template3|{{{1}}}}}d")
        self.ctx.add_page("Template:template3", 10, "f{{{1}}}g")
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{template1|}}")
        self.assertEqual(ret, "acfgdb")

    def test_template23(self):
        self.ctx.add_page("Template:template1", 10, "a{{template2|{{{1}}}}}b")
        self.ctx.add_page("Template:template2", 10, "c{{template3|{{{1}}}}}d")
        self.ctx.add_page("Template:template3", 10, "f{{{1}}}g")
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{template1|zz}}")
        self.assertEqual(ret, "acfzzgdb")

    def test_template24a(self):
        self.ctx.add_page("Template:template", 10, "a{{{1}}}b")
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{template|{{!}}}}")
        self.assertEqual(ret, "a|b")

    def test_template24b(self):
        self.ctx.add_page("Template:template", 10, "a{{{1}}}b")
        self.ctx.add_page("Template:!-", 10, "|-")
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{template|{{!-}}}}")
        self.assertEqual(ret, "a|-b")

    def test_template24c(self):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand(
            "{{#if:true|before{{#if:true|{{!}}|false}}after}}"
        )
        self.assertEqual(ret, "before|after")

    def test_template24d(self):
        self.ctx.add_page(
            "Template:t1", 10, "before{{#if:true|{{!}}|false}}after"
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{#if:true|{{t1}}}}")
        self.assertEqual(ret, "before|after")

    def test_template24e(self):
        self.ctx.add_page(
            "Template:t1", 10, "before{{#if:true|{{!}}|false}}after"
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{|\n||first||{{t1}}||last\n|}")
        self.assertEqual(ret, "{|\n||first||before|after||last\n|}")

    def test_template24f(self):
        self.ctx.add_page("Template:row", 10, "||bar\n{{!}} {{!}}baz\n| zap")
        self.ctx.add_page("Template:t1", 10, "{|\n! Hdr\n{{row|foo}}\n|}")
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{t1}}")
        self.assertEqual(ret, "\n{|\n! Hdr\n||bar\n| |baz\n| zap\n|}")

    def test_template25(self):
        # This example is from
        # https://www.mediawiki.org/wiki/Extension:Scribunto/Lua_reference_manual#frame:getTitle,
        # under frame:expandTemplate examples
        self.ctx.add_page("Template:template", 10, "a{{{1}}}b")
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{template|{{((}}!{{))}}}}")
        self.assertEqual(ret, "a&lbrace;&lbrace;!&rbrace;&rbrace;b")

    @patch(
        "wikitextprocessor.core.Wtp.get_page",
        return_value=Page(
            title="Template:foo",
            namespace_id=10,
            body="a{{{1}}}b",
        ),
    )
    def test_template26(self, mock_get_page):
        # This tests that the "=" is not interpretated as indicating argument
        # name on the left.
        self.ctx.start_page("Tt")
        ret = self.ctx.expand('{{foo|<span class="foo">bar</span>}}')
        self.assertEqual(ret, 'a<span class="foo">bar</span>b')

    @patch(
        "wikitextprocessor.core.Wtp.get_page",
        return_value=Page(
            title="Template:foo",
            namespace_id=10,
            body="a{{foo}}b",
        ),
    )
    def test_template27(self, mock_get_page):
        # Test infinite recursion in template expansion
        self.ctx.start_page("Tt")
        self.assertEqual(
            self.ctx.expand("{{foo}}"),
            'a<strong class="error">Template loop detected: '
            "[[:Template:foo]]</strong>b",
        )

    @patch(
        "wikitextprocessor.core.Wtp.get_page",
        return_value=Page(
            title="Template:foo",
            namespace_id=10,
            body="a{{{1}}}b",
        ),
    )
    def test_template28(self, mock_get_page):
        # Test | inside <math> in template argument
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{foo|x <math> 1 | 2 </math> y}}")
        self.assertEqual(ret, "ax <math> 1 | 2 </math> yb")

    @patch(
        "wikitextprocessor.core.Wtp.get_page",
        return_value=Page(
            title="Template:template",
            namespace_id=10,
            body="a{{{zz foo|}}}b",
        ),
    )
    def test_template29(self, mock_get_page):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{template|1|zz foo=2|bar=3}}")
        self.assertEqual(ret, "a2b")

    @patch(
        "wikitextprocessor.core.Wtp.get_page",
        return_value=Page(
            title="Template:t1",
            namespace_id=10,
            body="[<noinclude/>[foo]]",
        ),
    )
    def test_template30(self, mock_get_page):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{t1}}")
        self.assertEqual(ret, "[<noinclude/>[foo]]")

    def test_unbalanced1(self):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{#switch:p|p=q|r={{tc}}|s=t}}")
        self.assertEqual(ret, "q")

    def test_unbalanced2(self):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{#switch:p|p=q|r={{tc}}|s=t}}")
        self.assertEqual(ret, "q")

    @patch(
        "wikitextprocessor.core.Wtp.get_page",
        return_value=Page(title="Template:tc", namespace_id=10, body="X"),
    )
    def test_unbalanced3(self, mock_get_page):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{#switch:r|p=q|r={{tc}}|s=t}}")
        self.assertEqual(ret, "X")

    def test_unbalanced4(self):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{#switch:p|p=q|r=tc}}|s=t}}")
        self.assertEqual(ret, "q|s=t}}")

    @patch(
        "wikitextprocessor.core.Wtp.get_page",
        return_value=Page(title="Template:tc", namespace_id=10, body="X"),
    )
    def test_unbalanced5(self, mock_get_page):
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{#switch:p|p=q|r={{tc|s=t}}")
        self.assertEqual(ret, "{{#switch:p|p=q|r=X")

    def test_redirect1(self):
        self.ctx.add_page(
            "Template:oldtemp", 10, redirect_to="Template:testtemp"
        )
        self.ctx.add_page("Template:testtemp", 10, "a{{{1}}}b")
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{oldtemp|foo}}")
        self.assertEqual(ret, "afoob")

    def test_invoke1(self):
        self.ctx.start_page("Tt")
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return "in test"
end
return export
""",
        )
        ret = self.ctx.expand("a{{#invoke:testmod|testfn}}b")
        self.assertEqual(ret, "ain testb")

    def test_invoke2(self):
        self.scribunto("0", """return tostring(#frame.args)""")

    def test_invoke4a(self):
        self.ctx.start_page("Tt")
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return frame.args[1]
end
return export
""",
        )
        ret = self.ctx.expand("{{#invoke:testmod|testfn|a|b|foo=bar}}")
        self.assertEqual(ret, "a")

    def test_invoke4b(self):
        self.ctx.start_page("Tt")
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return frame.args["1"]
end
return export
""",
        )
        ret = self.ctx.expand("{{#invoke:testmod|testfn|a|b|foo=bar}}")
        self.assertEqual(ret, "a")

    def test_invoke4c(self):
        self.ctx.start_page("Tt")
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return frame.args["foo"]
end
return export
""",
        )
        ret = self.ctx.expand("{{#invoke:testmod|testfn|a|b|foo=bar}}")
        self.assertEqual(ret, "bar")

    def test_invoke5(self):
        self.ctx.start_page("Tt")
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return frame.args.foo
end
return export
""",
        )
        ret = self.ctx.expand("{{#invoke:testmod|testfn|foo=bar|a}}")
        self.assertEqual(ret, "bar")

    def test_invoke6(self):
        self.ctx.start_page("Tt")
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return frame.args["foo"]
end
return export
""",
        )
        ret = self.ctx.expand("{{#invoke:testmod|testfn|foo=bar|a}}")
        self.assertEqual(ret, "bar")

    def test_invoke7(self):
        self.ctx.add_page(
            "Template:testtempl",
            10,
            "{{#invoke:testmod|testfn|foo={{{1}}}|{{{2}}}}}",
        )
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return frame.args["foo"]
end
return export
""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{testtempl|a|b}}")
        self.assertEqual(ret, "a")

    def test_invoke9(self):
        self.ctx.add_page(
            "Template:testtempl",
            10,
            "{{#invoke:testmod|testfn|foo={{{1}}}|{{{2}}}}}",
        )
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return frame.args.foo
end
return export
""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{testtempl|a|b}}")
        self.assertEqual(ret, "a")

    def test_invoke10(self):
        self.ctx.add_page(
            "Template:testtempl",
            10,
            "{{#invoke:testmod|testfn|foo={{{1}}}|{{{2}}}}}",
        )
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return frame.args[1]
end
return export
""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{testtempl|a|b}}")
        self.assertEqual(ret, "b")

    def test_invoke11(self):
        self.ctx.add_page(
            "Template:testtempl", 10, "{{#invoke:testmod|testfn}}"
        )
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return tostring(frame.args.foo)
end
return export
""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{testtempl}}")
        self.assertEqual(ret, "nil")

    def test_invoke12(self):
        # Testing that intervening template call does not mess up arguments
        # (this was once a bug)
        self.ctx.add_page(
            "Template:testtempl", 10, "{{templ2|{{#invoke:testmod|testfn}}}}"
        )
        self.ctx.add_page("Template:templ2", 10, "{{{1}}}")
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return tostring(frame:getParent().args[1])
end
return export
""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{testtempl|arg1}}")
        self.assertEqual(ret, "arg1")

    def test_invoke14(self):
        # Testing that argument names are handled correctly if = inside HTML tag
        self.ctx.add_page(
            "Template:testtempl",
            10,
            '{{#invoke:testmod|testfn|<span class="foo">bar</span>}}',
        )
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return tostring(frame.args[1])
end
return export
""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{testtempl}}")
        self.assertEqual(ret, """<span class="foo">bar</span>""")

    def test_invoke15(self):
        # Testing safesubst:
        self.ctx.add_page(
            "Template:testtempl", 10, "{{safesubst:#invoke:testmod|testfn}}"
        )
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return "correct"
end
return export
""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{testtempl}}")
        self.assertEqual(ret, "correct")

    def test_invoke16(self):
        # Testing safesubst:, with space before
        self.ctx.add_page(
            "Template:testtempl", 10, "{{ safesubst:#invoke:testmod|testfn}}"
        )
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return "correct"
end
return export
""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{testtempl}}")
        self.assertEqual(ret, "correct")

    def test_invoke17(self):
        # Testing safesubst: coming from template
        self.ctx.add_page(
            "Template:testtempl", 10, "{{ {{templ2}}#invoke:testmod|testfn}}"
        )
        self.ctx.add_page("Template:templ2", 10, "safesubst:")
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return "correct"
end
return export
""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{testtempl}}")
        self.assertEqual(ret, """correct""")

    def test_invoke18(self):
        # Tests whitespaces within #invoke
        self.ctx.add_page(
            "Template:testtempl", 10, "{{#invoke:\ntestmod\n|\ntestfn\n}}"
        )
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return "correct"
end
return export
""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{testtempl}}")
        self.assertEqual(ret, "correct")

    def test_invoke19(self):
        # Tests fetching a frame argument that does not exist
        self.ctx.add_page(
            "Template:testtempl", 10, "{{#invoke:testmod|testfn}}"
        )
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return tostring(frame.args.nonex) .. tostring(frame:getParent().args.nonex2)
end
return export
""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{testtempl}}")
        self.assertEqual(ret, """nilnil""")

    def test_invoke20(self):
        self.ctx.add_page(
            "Template:testtempl", 10, "{{#invoke:testmod|testfn}}"
        )
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  local v = frame:getParent().args[1]
  if v == "a<1>" then return "yes" else return "no" end
end
return export
""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{testtempl|a<1>}}")
        self.assertEqual(ret, "yes")

    def test_invoke21(self):
        self.ctx.add_page(
            "Template:testtempl", 10, "{{#invoke:testmod|testfn}}"
        )
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  local v = next(frame.args)
  if v then return "HAVE-ARGS" else return "NO-ARGS" end
end
return export
""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{testtempl}}")
        self.assertEqual(ret, "NO-ARGS")

    def test_invoke22(self):
        self.ctx.add_page(
            "Template:testtempl", 10, "{{#invoke:testmod|testfn|x}}"
        )
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  local k, v = next(frame.args)
  return tostring(k) .. "=" .. tostring(v)
end
return export
""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{testtempl}}")
        self.assertEqual(ret, """1=x""")

    def test_frame_parent1(self):
        self.ctx.add_page(
            "Template:testtempl", 10, "{{#invoke:testmod|testfn}}"
        )
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return tostring(frame:getParent().args[1])
end
return export
""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{testtempl}}")
        self.assertEqual(ret, "nil")

    def test_frame_parent2(self):
        self.ctx.add_page(
            "Template:testtempl", 10, "{{#invoke:testmod|testfn}}"
        )
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return frame:getParent().args[1]
end
return export
""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{testtempl|foo|bar}}")
        self.assertEqual(ret, "foo")

    def test_frame_parent3(self):
        self.ctx.add_page(
            "Template:testtempl", 10, "{{#invoke:testmod|testfn}}"
        )
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return frame:getParent().args[2]
end
return export
""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{testtempl|foo|bar}}")
        self.assertEqual(ret, "bar")

    def test_frame_parent4(self):
        self.ctx.add_page(
            "Template:testtempl", 10, "{{#invoke:testmod|testfn}}"
        )
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return tostring(frame:getParent().args[3])
end
return export
""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{testtempl|foo|bar}}")
        self.assertEqual(ret, "nil")

    def test_frame_parent5(self):
        self.ctx.add_page(
            "Template:testtempl", 10, "{{#invoke:testmod|testfn}}"
        )
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return frame:getParent().args.foo
end
return export
""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{testtempl|foo|bar|foo=zap}}")
        self.assertEqual(ret, "zap")

    def test_frame_parent6(self):
        self.ctx.add_page(
            "Template:testtempl", 10, "{{#invoke:testmod|testfn}}"
        )
        self.ctx.add_page("Template:testtempl2", 10, "foo{{{1|}}}")
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  local parent = frame:getParent()
  return parent.args[1] .. parent.args[2]
end
return export
""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{testtempl|{{testtempl2|zz}}|yy}}")
        self.assertEqual(ret, "foozzyy")

    def test_frame_parent7(self):
        self.ctx.add_page(
            "Template:testtempl", 10, "{{#invoke:testmod|testfn}}"
        )
        self.ctx.add_page("Template:testtempl2", 10, "foo{{{1|}}}")
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return frame:getTitle()
end
return export
""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{testtempl|{{testtempl2|zz}}|yy}}")
        self.assertEqual(ret, "Module:testmod")

    def test_frame_parent8(self):
        self.ctx.add_page(
            "Template:testtempl", 10, "{{#invoke:testmod|testfn}}"
        )
        self.ctx.add_page("Template:testtempl2", 10, "foo{{{1|}}}")
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return frame:getParent():getTitle()
end
return export
""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{testtempl|{{testtempl2|zz}}|yy}}")
        self.assertEqual(ret, "Template:testtempl")

    def test_frame_parent9(self):
        # parent of parent should be nil
        self.ctx.add_page(
            "Template:testtempl", 10, "{{#invoke:testmod|testfn}}"
        )
        self.ctx.add_page("Template:testtempl2", 10, "{{testtempl}}")
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return frame:getParent():getParent()
end
return export
""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{testtempl2}}")
        self.assertEqual(ret, "")  # nil

    def test_frame_callParserFunction1(self):
        self.scribunto(
            "<br />",
            """
        return frame:callParserFunction("#tag", {"br"})""",
        )

    def test_frame_callParserFunction2(self):
        self.scribunto(
            "<br />",
            """
        return frame:callParserFunction{name = "#tag", args = {"br"}}""",
        )

    def test_frame_callParserFunction3(self):
        self.scribunto(
            "<br />",
            """
        return frame:callParserFunction("#tag", "br")""",
        )

    def test_frame_callParserFunction4(self):
        self.scribunto(
            "<div>content</div>",
            """
        return frame:callParserFunction("#tag", "div", "content")""",
        )

    def test_frame_getArgument1(self):
        self.ctx.start_page("Tt")
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return frame:getArgument(1).expand()
end
return export
""",
        )
        ret = self.ctx.expand("{{#invoke:testmod|testfn|a|b}}")
        self.assertEqual(ret, "a")

    def test_frame_getArgument2(self):
        self.ctx.start_page("Tt")
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return frame:getArgument(2).expand()
end
return export
""",
        )
        ret = self.ctx.expand("{{#invoke:testmod|testfn|a|b}}")
        self.assertEqual(ret, "b")

    def test_frame_getArgument3(self):
        self.ctx.start_page("Tt")
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return frame:getArgument(3)
end
return export
""",
        )
        ret = self.ctx.expand("{{#invoke:testmod|testfn|a|b}}")
        self.assertEqual(ret, "")  # nil

    def test_frame_getArgument4(self):
        self.ctx.start_page("Tt")
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return frame:getArgument("foo").expand()
end
return export
""",
        )
        ret = self.ctx.expand("{{#invoke:testmod|testfn|foo=bar}}")
        self.assertEqual(ret, "bar")

    def test_frame_getArgument5(self):
        self.ctx.start_page("Tt")
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return frame:getArgument{name = "foo"}.expand()
end
return export
""",
        )
        ret = self.ctx.expand("{{#invoke:testmod|testfn|foo=bar}}")
        self.assertEqual(ret, "bar")

    def test_frame_getArgument6(self):
        self.ctx.add_page(
            "Template:templ", 10, "{{#invoke:testmod|testfn|a|b}}"
        )
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return frame:getParent():getArgument(2).expand()
end
return export
""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{templ|x|y}}")
        self.assertEqual(ret, "y")

    def test_frame_preprocess1(self):
        self.ctx.add_page("Template:testtemplate", 10, "foo{{{1}}}")
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return frame:preprocess("a{{testtemplate|a}}b")
end
return export
""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{#invoke:testmod|testfn|foo=bar}}")
        self.assertEqual(ret, "afooab")

    def test_frame_preprocess2(self):
        self.ctx.add_page("Template:testtemplate", 10, "foo{{{1}}}")
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return frame:preprocess{text = "a{{testtemplate|a}}b"}
end
return export
""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{#invoke:testmod|testfn|foo=bar}}")
        self.assertEqual(ret, "afooab")

    def test_frame_argumentPairs1(self):
        self.ctx.start_page("Tt")
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  local ret = ""
  for k, v in frame:argumentPairs() do
    ret = ret .. "|" .. tostring(k) .. "=" .. tostring(v)
  end
  return ret
end
return export
""",
        )
        ret = self.ctx.expand("{{#invoke:testmod|testfn|foo=bar}}")
        self.assertEqual(ret, "|foo=bar")

    def test_frame_argumentPairs2(self):
        self.ctx.start_page("Tt")
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  local ret = ""
  for k, v in frame:argumentPairs() do
    ret = ret .. "|" .. tostring(k) .. "=" .. tostring(v)
  end
  return ret
end
return export
""",
        )
        ret = self.ctx.expand("{{#invoke:testmod|testfn|a|b}}")
        self.assertEqual(ret, "|1=a|2=b")

    def test_frame_argumentPairs3(self):
        self.ctx.add_page(
            "Template:templ", 10, "{{#invoke:testmod|testfn|a|b}}"
        )
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  local ret = ""
  for k, v in frame:getParent():argumentPairs() do
    ret = ret .. "|" .. tostring(k) .. "=" .. tostring(v)
  end
  return ret
end
return export
""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{templ|x|y}}")
        self.assertEqual(ret, "|1=x|2=y")

    def test_frame_expandTemplate1(self):
        self.ctx.add_page("Template:templ", 10, "a{{{1}}}b{{{2}}}c{{{k}}}d")
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return frame:expandTemplate{title="templ", args={"foo", "bar", k=4}}
end
return export
""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{#invoke:testmod|testfn}}")
        self.assertEqual(ret, "afoobbarc4d")

    def test_frame_expandTemplate2(self):
        self.ctx.add_page("Template:templ", 10, "a{{{1}}}b")
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return frame:expandTemplate{title="templ", args={"|"}}
end
return export
""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{#invoke:testmod|testfn}}")
        self.assertEqual(ret, "a|b")

    def test_frame_expandTemplate3(self):
        self.ctx.add_page("Template:templ", 10, "a{{{1}}}b")
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
  return frame:expandTemplate{title="templ", args={"{{!}}"}}
end
return export
""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{#invoke:testmod|testfn}}")
        self.assertEqual(ret, "a{{!}}b")

    def test_frame_extensionTag1(self):
        self.scribunto(
            "<ref>some text</ref>",
            """
        return frame:extensionTag("ref", "some text")""",
        )

    def test_frame_extensionTag2(self):
        self.scribunto(
            '<ref class="foo">some text</ref>',
            """
        return frame:extensionTag("ref", "some text", "class=foo")""",
        )

    def test_frame_extensionTag3(self):
        self.scribunto(
            '<ref class="bar" id="test">some text</ref>',
            """
        return frame:extensionTag{name="ref", content="some text",
        args={class="bar", id="test"}}""",
        )

    def test_frame_extensionTag4(self):
        self.scribunto(
            "<br />",
            """
        return frame:extensionTag("br")""",
        )

    def test_frame_extensionTag5(self):
        self.scribunto(
            "{{#tag:not_allowed_tag|}}",
            """
        return frame:extensionTag("not_allowed_tag")""",
        )

    def test_frame_extensionTag6(self):
        # Sometimes an extensionTag call might return a table of arguments
        # with values that are not strings; this is a fixed bug
        self.scribunto(
            '<ref class="1.4" id="1">some text</ref>',
            """
        return frame:extensionTag{name="ref", content="some text",
        args={class=1.4, id=1}}""",
        )

    def test_frame_newChild1(self):
        self.scribunto(
            "",
            """
        return frame:newChild():getTitle()""",
        )

    def test_frame_newChild2(self):
        self.scribunto(
            "FOO",
            """
        return frame:newChild{title="FOO"}:getTitle()""",
        )

    def test_frame_newChild3(self):
        self.scribunto(
            "FOO|1=a|2=b",
            """
        local f = frame:newChild{title="FOO", args={"a", "b"}}
        local s = {}
        for k, v in pairs(f.args) do
           table.insert(s, tostring(k) .. "=" .. tostring(v))
        end
        table.sort(s)
        return f:getTitle() .. "|" .. table.concat(s, "|")""",
        )

    def test_frame_newChild4(self):
        self.scribunto(
            "FOO|1=a|bar=c|foo=b",
            """
        local f = frame:newChild{title="FOO", args={"a", foo="b", bar="c"}}
        local s = {}
        for k, v in pairs(f.args) do
           table.insert(s, tostring(k) .. "=" .. tostring(v))
        end
        table.sort(s)
        return f:getTitle() .. "|" .. table.concat(s, "|")""",
        )

    def test_mw_text_listToText1(self):
        self.scribunto("", """return mw.text.listToText({})""")

    def test_mw_text_listToText2(self):
        self.scribunto("abba", """return mw.text.listToText({"abba"})""")

    def test_mw_text_listToText3(self):
        self.scribunto(
            "abba and jara", """return mw.text.listToText({"abba", "jara"})"""
        )

    def test_mw_text_listToText4(self):
        self.scribunto(
            "abba, jara and zara",
            """
        return mw.text.listToText({"abba", "jara", "zara"})""",
        )

    def test_mw_text_listToText5(self):
        self.scribunto(
            "abba; jara or zara",
            """
        return mw.text.listToText({"abba", "jara", "zara"}, ";", "or")""",
        )

    def test_mw_text_nowiki1(self):
        self.scribunto(
            "&num;&lsqb;foo&rsqb;&lbrace;&lbrace;a&vert;" "b&rbrace;&rbrace;",
            """
                       return mw.text.nowiki("#[foo]{{a|b}}")""",
        )

    def test_mw_text_nowiki2(self):
        self.scribunto(
            "\n&num;&lt;foo&gt;&apos;#&#61;\n&NewLine;X\n",
            r"""
        return mw.text.nowiki("\n#<foo>'#=\n\nX\n")""",
        )

    def test_mw_text_nowiki3(self):
        self.scribunto(
            "&quot;test&quot;\n&minus;---\n" "http&colon;//example.com\n",
            r"""
          return mw.text.nowiki('"test"\n----\nhttp://example.com\n')""",
        )

    def test_mw_text_split1(self):
        self.scribunto(
            "", """return table.concat(mw.text.split("", "/"), "@")"""
        )

    def test_mw_text_split2(self):
        self.scribunto(
            "abc", """return table.concat(mw.text.split("abc", "/"), "@")"""
        )

    def test_mw_text_split3(self):
        self.scribunto(
            "ab@c", """return table.concat(mw.text.split("ab/c", "/"), "@")"""
        )

    def test_mw_text_split4(self):
        self.scribunto(
            "@abc", """return table.concat(mw.text.split("/abc", "/"), "@")"""
        )

    def test_mw_text_split5(self):
        self.scribunto(
            "abc@", """return table.concat(mw.text.split("abc/", "/"), "@")"""
        )

    def test_mw_text_split6(self):
        self.scribunto(
            "a@bc@", """return table.concat(mw.text.split("a/bc/", "/"), "@")"""
        )

    def test_mw_text_split7(self):
        self.scribunto(
            "a@b@c", """return table.concat(mw.text.split("abc", ""), "@")"""
        )

    def test_mw_text_split8(self):
        self.scribunto(
            "a@a@",
            """return table.concat(mw.text.split("abcabc", "[bc]+"), "@")""",
        )

    def test_mw_text_split9(self):
        self.scribunto(
            "abcabc",
            """return table.concat(mw.text.split("abcabc", "[bc]+", true),
                                   "@")""",
        )

    def test_mw_text_split10(self):
        self.scribunto(
            "abc@abc",
            """return table.concat(mw.text.split("abc[bc]+abc", "[bc]+", true),
                                   "@")""",
        )

    def test_mw_text_split11(self):
        self.scribunto(
            "귀", """return table.concat(mw.text.split("귀", ""), "@")"""
        )

    def test_mw_ustring_find1(self):
        self.scribunto(
            "nil",
            """local s, e = mw.ustring.find("abcdef", "[b]", 1, true)
               return tostring(s)""",
        )

    def test_mw_text_gsplit1(self):
        self.scribunto(
            "ab@ab@",
            """
          local result = {}
          for v in mw.text.gsplit("abcabc", "[c]+") do
              table.insert(result, v)
          end
          return table.concat(result, "@")""",
        )

    def test_mw_text_gsplit2(self):
        self.scribunto(
            "a@b@c",
            """
          local result = {}
          for v in mw.text.gsplit("abc", "") do
              table.insert(result, v)
          end
          return table.concat(result, "@")""",
        )

    def test_mw_text_trim1(self):
        self.scribunto(
            "a b  c", r"""return mw.text.trim("   a b  c\n\r\f\t  ")"""
        )

    def test_mw_text_trim2(self):
        self.scribunto(
            "a b",
            r"""return mw.text.trim("   a b  c\n\r\f\t  ",
                                               " \n\r\f\tc")""",
        )

    def test_mw_text_tag1(self):
        self.scribunto(
            "<br />",
            """
        return mw.text.tag("br")""",
        )

    def test_mw_text_tag2(self):
        self.scribunto(
            "<h1>Test title</h1>",
            """
        return mw.text.tag("h1", nil, "Test title")""",
        )

    def test_mw_text_tag3(self):
        self.scribunto(
            "<h1>Test title</h1>",
            """
        return mw.text.tag({name="h1", content="Test title"})""",
        )

    def test_mw_text_tag4(self):
        self.scribunto(
            '<h1 class="cls">Test title</h1>',
            """
        return mw.text.tag("h1", {class="cls"}, "Test title")""",
        )

    def test_mw_text_tag5(self):
        self.scribunto(
            '<h1 class="cls">Test title</h1>',
            """
        return mw.text.tag({name="h1", attrs={class="cls"},
                            content="Test title"})""",
        )

    def test_mw_text_truncate1(self):
        self.scribunto(
            "abc",
            """
        return mw.text.truncate("abc")""",
        )

    def test_mw_text_truncate2(self):
        self.scribunto(
            "abc",
            """
        return mw.text.truncate("abc", 5)""",
        )

    def test_mw_text_truncate3(self):
        self.scribunto(
            "abc",
            """
        return mw.text.truncate("abc", 3)""",
        )

    def test_mw_text_truncate4(self):
        self.scribunto(
            "ab…",
            """
        return mw.text.truncate("abc", 2)""",
        )

    def test_mw_text_truncate5(self):
        self.scribunto(
            "abXY",
            """
        return mw.text.truncate("abcdef", 4, "XY", true)""",
        )

    def test_mw_text_truncate6(self):
        self.scribunto(
            "XYef",
            """
        return mw.text.truncate("abcdef", -4, "XY", true)""",
        )

    def test_mw_text_truncate7(self):
        self.scribunto(
            "…cdef",
            """
        return mw.text.truncate("abcdef", -4)""",
        )

    def test_mw_text_truncate8(self):
        self.scribunto(
            "aX",
            """
        return mw.text.truncate("abc", 2, "X", true)""",
        )

    def test_mw_jsonencode1(self):
        self.scribunto(
            '"x"',
            """
        return mw.text.jsonEncode("x")""",
        )

    def test_mw_jsonencode2(self):
        self.scribunto(
            "null",
            """
        return mw.text.jsonEncode(nil)""",
        )

    def test_mw_jsonencode3(self):
        self.scribunto(
            "3",
            """
        return mw.text.jsonEncode(3)""",
        )

    def test_mw_jsonencode4(self):
        self.scribunto(
            "4.1",
            """
        return mw.text.jsonEncode(4.1)""",
        )

    def test_mw_jsonencode5(self):
        self.scribunto(
            "[]",
            """
        return mw.text.jsonEncode({})""",
        )

    def test_mw_jsonencode6(self):
        self.scribunto(
            '[1, "foo"]',
            """
        return mw.text.jsonEncode({1, "foo"})""",
        )

    def test_mw_jsonencode7(self):
        self.scribunto(
            '{"1": 1, "2": "foo"}',
            """
        return mw.text.jsonEncode({1, "foo"}, mw.text.JSON_PRESERVE_KEYS)""",
        )

    def test_mw_jsonencode8(self):
        self.scribunto(
            '{"1": 1, "2": "foo", "x": 8}',
            """
        return mw.text.jsonEncode({1, "foo", x=8})""",
        )

    def test_mw_jsonencode9(self):
        self.scribunto(
            '{"1": 1, "2": "foo", "x": 8}',
            """
        return mw.text.jsonEncode({1, "foo", x=8},
                                  mw.text.JSON_PRESERVE_KEYS)""",
        )

    def test_mw_jsonencode10(self):
        self.scribunto(
            '{"1": 1, "12": 8, "2": "foo"}',
            """
        return mw.text.jsonEncode({1, "foo", [12]=8})""",
        )

    def test_mw_jsonencode11(self):
        self.scribunto(
            "true",
            """
        return mw.text.jsonEncode(true)""",
        )

    def test_mw_jsondecode1(self):
        # Note: returned nil converted to empty string
        self.scribunto(
            "",
            """
        return mw.text.jsonDecode('null')""",
        )

    def test_mw_jsondecode2(self):
        self.scribunto(
            "true",
            """
        return mw.text.jsonDecode('true')""",
        )

    def test_mw_jsondecode3(self):
        self.scribunto(
            "1",
            """
        return mw.text.jsonDecode('1')""",
        )

    def test_mw_jsondecode4(self):
        self.scribunto(
            "4.1",
            """
        return mw.text.jsonDecode('4.1')""",
        )

    def test_mw_jsondecode5(self):
        self.scribunto(
            "foo",
            """
        return mw.text.jsonDecode('"foo"')""",
        )

    def test_mw_jsondecode6(self):
        self.scribunto(
            "0",
            """
        local x = mw.text.jsonDecode('[]')
        return tostring(#x)""",
        )

    def test_mw_jsondecode7(self):
        self.scribunto(
            "4a",
            """
        local x = mw.text.jsonDecode('[4.0, "a"]')
        return x[1] .. x[2]""",
        )

    def test_mw_jsondecode8(self):
        self.scribunto(
            "35",
            """
        local x = mw.text.jsonDecode('{"1": "3", "4": "5"}')
        return x[1] .. x[4]""",
        )

    def test_mw_jsondecode9(self):
        self.scribunto(
            "35",
            """
        local x = mw.text.jsonDecode('{"1": "3", "4": "5"}',
                                     mw.text.JSON_PRESERVE_KEYS)
        return x["1"] .. x["4"]""",
        )

    def test_mw_html1(self):
        self.scribunto(
            "<table></table>",
            """
        local t = mw.html.create("table")
        return tostring(t)""",
        )

    def test_mw_html2(self):
        self.scribunto(
            "<br />",
            """
        local t = mw.html.create("br")
        return tostring(t)""",
        )

    def test_mw_html3(self):
        self.scribunto(
            "<div />",
            """
        local t = mw.html.create("div", { selfClosing = true })
        return tostring(t)""",
        )

    def test_mw_html4(self):
        self.scribunto(
            "<div>Plain text</div>",
            """
        local t = mw.html.create("div")
        t:wikitext("Plain text")
        return tostring(t)""",
        )

    def test_mw_html5(self):
        self.scribunto(
            "<span></span>",
            """
        local t = mw.html.create("div")
        t2 = t:tag("span")
        return tostring(t2)""",
        )

    def test_mw_html6(self):
        self.scribunto(
            '<div foo="bar"></div>',
            """
        local t = mw.html.create("div")
        t:attr("foo", "bar")
        return tostring(t)""",
        )

    def test_mw_html7(self):
        self.scribunto(
            '<div foo="b&quot;&gt;ar"></div>',
            """
        local t = mw.html.create("div")
        t:attr({foo='b">ar'})
        return tostring(t)""",
        )

    def test_mw_html8(self):
        self.scribunto(
            "nil",
            """
        local t = mw.html.create("div")
        return tostring(t:getAttr("foo"))""",
        )

    def test_mw_html9(self):
        self.scribunto(
            "bar",
            """
        local t = mw.html.create("div")
        t:attr("foo", "bar")
        return tostring(t:getAttr("foo"))""",
        )

    def test_mw_html10(self):
        self.scribunto(
            '<div class="bar"></div>',
            """
        local t = mw.html.create("div")
        t:addClass("bar")
        return tostring(t)""",
        )

    def test_mw_html11(self):
        self.scribunto(
            '<div class="bar foo"></div>',
            """
        local t = mw.html.create("div")
        t:addClass("bar")
        t:addClass("foo")
        t:addClass("bar")
        return tostring(t)""",
        )

    def test_mw_html11b(self):
        self.scribunto(
            '<div class="bar foo"></div>',
            """
        local t = mw.html.create("div")
        t:addClass("bar")
        :addClass()
        :addClass("foo")
        return tostring(t)""",
        )

    def test_mw_html12(self):
        self.scribunto(
            '<div style="foo:bar;"></div>',
            """
        local t = mw.html.create("div")
        t:css({foo="bar"})
        return tostring(t)""",
        )

    def test_mw_html13(self):
        self.scribunto(
            '<div style="foo:bar;width:300px;"></div>',
            """
        local t = mw.html.create("div")
        t:cssText("foo:bar;")
        t:cssText("width:300px")
        return tostring(t)""",
        )

    def test_mw_html13b(self):
        self.scribunto(
            '<div style="foo:bar;width:300px;"></div>',
            """
        local t = mw.html.create("div")
        t:cssText("foo:bar;")
        :cssText()
        :cssText("width:300px")
        return tostring(t)""",
        )

    def test_mw_html14(self):
        self.scribunto(
            '<div style="label:&quot;foo&quot;;"></div>',
            """
        local t = mw.html.create("div")
        t:cssText('label:"foo"')
        return tostring(t)""",
        )

    def test_mw_html15(self):
        self.scribunto(
            '<div style="label:&quot;foo&quot;;"></div>',
            """
        local t = mw.html.create("div")
        t:css("label", '"foo"')
        return tostring(t)""",
        )

    def test_mw_html16(self):
        self.scribunto(
            "<div><br /></div>",
            """
        local t = mw.html.create("div")
        t:node(mw.html.create("br"))
        return tostring(t)""",
        )

    def test_mw_html17(self):
        self.scribunto(
            "<div><span>A</span></div>",
            """
        local t = mw.html.create("div")
        t:node("<span>A</span>")   -- Should this be supported?
        return tostring(t)""",
        )

    def test_mw_html18(self):
        self.scribunto(
            "<span><br /></span>",
            """
        local t = mw.html.create("div")
        local t2 = t:tag("span")
        local t3 = t2:tag("br")
        return tostring(t3:done())""",
        )

    def test_mw_html19(self):
        self.scribunto(
            "<div><span><br /></span></div>",
            """
        local t = mw.html.create("div")
        local t2 = t:tag("span")
        local t3 = t2:tag("br")
        return tostring(t3:allDone())""",
        )

    def test_mw_html20(self):
        self.scribunto(
            "<div><span><br />A<hr /></span></div>",
            """
        local t = mw.html.create("div")
        local t2 = t:tag("span")
        local t3 = t2:tag("br")
        t2:wikitext("A")
        local t4 = t2:tag("hr")
        return tostring(t3:allDone())""",
        )

    def test_mw_html21(self):
        self.scribunto(
            '<div style="foo:bar;"></div>',
            """
        local t = mw.html.create("div")
        t:css("foo", "bar")
        return tostring(t)""",
        )

    def test_mw_html22(self):
        self.scribunto(
            "<span></span>",
            """
        local t = mw.html.create('span')
        :addClass( nil  )
        :wikitext( nil )
        return tostring(t)""",
        )

    def test_mw_uri1(self):
        self.scribunto(
            "b+c",
            """
        return mw.uri.encode("b c")""",
        )

    def test_mw_uri2(self):
        self.scribunto(
            "%2Ffoo%2Fb%20ar",
            """
        return mw.uri.encode("/foo/b ar", "PATH")""",
        )

    def test_mw_uri3(self):
        self.scribunto(
            "/foo/b_ar",
            """
        return mw.uri.encode("/foo/b_ar", "WIKI")""",
        )

    def test_mw_uri4(self):
        self.scribunto(
            "__foo+b%C3%A1r+%2B+baz__",
            r"""
        return mw.uri.encode("__foo b\195\161r + baz__")""",
        )

    def test_mw_uri5(self):
        self.scribunto(
            "__foo+b%C3%A1r+%2B+%2Fbaz%2F__",
            r"""
        return mw.uri.encode('__foo b\195\161r + /baz/__', 'QUERY')""",
        )

    def test_mw_uri6(self):
        self.scribunto(
            "__foo%20b%C3%A1r%20%2B%20%2Fbaz%2F__",
            r"""
        return mw.uri.encode('__foo b\195\161r + /baz/__', 'PATH')""",
        )

    def test_mw_uri7(self):
        self.scribunto(
            "__foo_b%C3%A1r_%2B_/baz/__",
            r"""
        return mw.uri.encode('__foo b\195\161r + /baz/__', 'WIKI')""",
        )

    def test_mw_uri8(self):
        self.scribunto(
            "/foo/b ar c",
            """
        return mw.uri.decode("%2Ffoo%2Fb%20ar+c")""",
        )

    def test_mw_uri9(self):
        self.scribunto(
            "/foo/b ar+c",
            """
        return mw.uri.decode("%2Ffoo%2Fb%20ar+c", "PATH")""",
        )

    def test_mw_uri10(self):
        self.scribunto(
            "foo_bar",
            """
        return mw.uri.anchorEncode("foo bar")""",
        )

    def test_mw_uri11(self):
        self.scribunto(
            "foo=b+ar&x=1",
            """
        return mw.uri.buildQueryString({foo="b ar", x=1})""",
        )

    def test_mw_uri12(self):
        self.ctx.start_page("Tt")
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
   local q = mw.uri.parseQueryString('a=1&b=a+b&c')
   return tostring(q.a) .. tostring(q.b) .. tostring(q.c) .. tostring(q.d)
end
return export
""",
        )
        ret = self.ctx.expand("{{#invoke:testmod|testfn}}")
        self.assertEqual(ret, "1a bfalsenil")

    def test_mw_uri13(self):
        self.scribunto(
            "https://wiki.local/wiki/Example?action=edit",
            r"""
        return mw.uri.canonicalUrl("Example", {action="edit"})""",
        )

    def test_mw_uri15(self):
        self.scribunto(
            "/w/index.php?action=edit&title=Example",
            r"""
        return mw.uri.localUrl("Example", {action="edit"})""",
        )

    def test_mw_uri16(self):
        self.scribunto(
            "https://wiki.local/w/index.php?action=edit&title=Example",
            'return tostring(mw.uri.fullUrl("Example", {action="edit"}))',
        )

    def test_mw_title1(self):
        self.ctx.add_page("Template:templ", 10, "{{#invoke:testmod|testfn}}")
        self.ctx.add_page(
            "Module:testmod",
            828,
            r"""
local export = {}
function export.testfn(frame)
   return mw.title.getCurrentTitle().fullText
end
return export
""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{templ}}")
        self.assertEqual(ret, "Tt")

    def test_mw_title2(self):
        self.scribunto(
            "",
            """
        local t = mw.title.makeTitle("Main", "R:L&S")
        return t.nsText""",
        )

    def test_mw_title3(self):
        self.scribunto(
            "",
            """
        local t = mw.title.new("R:L&S", "Main")
        return t.nsText""",
        )

    def test_mw_title4(self):
        self.scribunto(
            "R:L&S",
            """
        local t = mw.title.new("R:L&S", "Main")
        return t.text""",
        )

    def test_mw_title5(self):
        self.scribunto(
            "Module:R:L&S/foo/bar",
            """
        local t = mw.title.new("R:L&S/foo/bar", "Module")
        return t.prefixedText""",
        )

    def test_mw_title6(self):
        self.scribunto(
            "true",
            r"""
        return mw.title.equals(mw.title.new("Foo"), mw.title.new("Foo"))""",
        )

    def test_mw_title7(self):
        self.scribunto(
            "false",
            r"""
        return mw.title.equals(mw.title.new("Foo"), mw.title.new("Bar"))""",
        )

    def test_mw_title8(self):
        self.scribunto(
            "0",
            r"""
        return mw.title.compare(mw.title.new("Foo"), mw.title.new("Foo"))""",
        )

    def test_mw_title9(self):
        self.scribunto(
            "1",
            r"""
        return mw.title.compare(mw.title.new("Foo"), mw.title.new("Bar"))""",
        )

    def test_mw_title10(self):
        self.scribunto(
            "0",
            r"""
        return mw.title.compare(mw.title.new("Foo"), mw.title.new("Foo"))""",
        )

    def test_mw_title11(self):
        self.scribunto(
            "false",
            r"""
        return mw.title.new("Foo") <=  mw.title.new("Bar")""",
        )

    def test_mw_title12(self):
        self.scribunto(
            "true",
            r"""
        return mw.title.new("Foo") <= mw.title.new("Foo")""",
        )

    def test_mw_title13(self):
        self.scribunto(
            "true",
            r"""
        return mw.title.new("Foo") >  mw.title.new("Bar")""",
        )

    def test_mw_title14(self):
        self.scribunto(
            "Module:Foo",
            r"""
        local t = mw.title.new("Foo", "Module")
        return t.prefixedText""",
        )

    def test_mw_title15(self):
        self.scribunto(
            "User:Foo",
            r"""
        local t = mw.title.new("Foo", 2)
        return t.prefixedText""",
        )

    def test_mw_title16(self):
        self.scribunto(
            "Module:Foo",
            r"""
        local t = mw.title.new("Foo", mw.site.namespaces.Module.id)
        return t.prefixedText""",
        )

    def test_mw_title17(self):
        self.scribunto(
            "nil",
            r"""
        local t = mw.title.new("Foo", "UnknownSpace")
        return tostring(t)""",
        )

    def test_mw_title18(self):
        self.scribunto(
            "Module:Test#Frag",
            r"""
        local t = mw.title.makeTitle("Module", "Test", "Frag")
        return t.fullText""",
        )

    def test_mw_title19(self):
        self.scribunto(
            "Test",
            r"""
        local t = mw.title.makeTitle(nil, "Test")
        return t.fullText""",
        )

    def test_mw_title20(self):
        self.scribunto(
            "nil",
            r"""
        local t = mw.title.makeTitle("Main", "{{")
        return tostring(t)""",
        )

    def test_mw_title21(self):
        self.scribunto(
            "1",
            r"""
        local t = mw.title.makeTitle("Talk", "Test")
        return t.namespace""",
        )

    def test_mw_title22(self):
        self.scribunto(
            "1",
            r"""
        local t = mw.title.makeTitle("Talk", "Test")
        return t.namespace""",
        )

    def test_mw_title23(self):
        self.scribunto(
            "Frag",
            r"""
        local t = mw.title.makeTitle("Talk", "Test", "Frag")
        return t.fragment""",
        )

    def test_mw_title24(self):
        self.scribunto(
            "Talk",
            r"""
        local t = mw.title.makeTitle(1, "Test", "Frag")
        return t.nsText""",
        )

    def test_mw_title25(self):
        self.scribunto(
            "User",
            r"""
        local t = mw.title.makeTitle(3, "Test", "Frag")
        return t.subjectNsText""",
        )

    def test_mw_title26(self):
        self.scribunto(
            "Test",
            r"""
        local t = mw.title.makeTitle(3, "Test", "Frag")
        return t.text""",
        )

    def test_mw_title27(self):
        self.scribunto(
            "User talk:Test",
            r"""
        local t = mw.title.makeTitle(3, "Test", "Frag")
        return t.prefixedText""",
        )

    def test_mw_title28(self):
        self.scribunto(
            "User talk:Test#Frag",
            r"""
        local t = mw.title.makeTitle(3, "Test", "Frag")
        return t.fullText""",
        )

    def test_mw_title29(self):
        self.scribunto(
            "Test",
            r"""
        local t = mw.title.makeTitle(3, "Test/foo/bar", "Frag")
        return t.rootText""",
        )

    def test_mw_title30a(self):
        self.scribunto(
            "Test/foo",
            r"""
        local t = mw.title.makeTitle(3, "Test/foo/bar", "Frag")
        return t.baseText""",
        )

    def test_mw_title30b(self):
        self.scribunto(
            "Test/foo",
            r"""
        local t = mw.title.makeTitle(3, "Test/foo/translations", "Frag")
        return t.baseText""",
        )

    def test_mw_title31a(self):
        self.scribunto(
            "bar",
            r"""
        local t = mw.title.makeTitle(3, "Test/foo/bar", "Frag")
        return t.subpageText""",
        )

    def test_mw_title31b(self):
        self.scribunto(
            "translations",
            r"""
        local t = mw.title.makeTitle(3, "Test/foo/translations", "Frag")
        return t.subpageText""",
        )

    def test_mw_title31c(self):
        self.scribunto(
            "foobar",
            r"""
        local t = mw.title.makeTitle(3, "Proto-Germanic/foobar", "Frag")
        return t.subpageText""",
        )

    def test_mw_title32(self):
        self.scribunto(
            "false",
            r"""
        local t = mw.title.makeTitle(3, "Test/foo/bar", "Frag")
        return t.canTalk""",
        )

    def test_mw_title33(self):
        self.scribunto(
            "true",
            r"""
        local t = mw.title.makeTitle("Main", "Test")
        return t.isContentPage""",
        )

    def test_mw_title34(self):
        self.scribunto(
            "false",
            r"""
        local t = mw.title.makeTitle(3, "Test/foo/bar", "Frag")
        return t.isExternal""",
        )

    def test_mw_title35(self):
        self.scribunto(
            "false",
            r"""
        local t = mw.title.makeTitle(3, "Test/foo/bar", "Frag")
        return t.isRedirect""",
        )

    def test_mw_title36(self):
        # test for redirect that exists
        self.ctx.add_page("Main:Foo", 0, redirect_to="Main:Bar")
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
            local export = {}
            function export.testfn(frame)
            local t = mw.title.makeTitle("Main", "Foo", "Frag")
            return t.isRedirect
            end
            return export""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{#invoke:testmod|testfn}}")
        self.assertEqual(ret, "true")

    def test_mw_title37(self):
        self.scribunto(
            "false",
            r"""
        local t = mw.title.makeTitle(3, "Test/foo/bar", "Frag")
        return t.isSpecialPage""",
        )

    def test_mw_title38(self):
        self.scribunto(
            "true",
            r"""
        local t = mw.title.makeTitle(3, "Test/foo/bar", "Frag")
        return t.isSubpage""",
        )

    def test_mw_title39(self):
        self.scribunto(
            "true",
            r"""
        local t = mw.title.makeTitle(3, "Test/foo/bar", "Frag")
        return t.isTalkPage""",
        )

    def test_mw_title40(self):
        self.scribunto(
            "true",
            r"""
        local t = mw.title.makeTitle("Main", "Test/foo/bar", "Frag")
        return t:isSubpageOf(mw.title.new("Test/foo"))""",
        )

    def test_mw_title41(self):
        self.scribunto(
            "false",
            r"""
        local t = mw.title.makeTitle("Main", "Test/foo/bar", "Frag")
        return t:isSubpageOf(mw.title.new("Test/foo/baz"))""",
        )

    def test_mw_title42(self):
        self.scribunto(
            "true",
            r"""
        local t = mw.title.makeTitle("Main", "Test/foo/bar", "Frag")
        return t:inNamespace("Main")""",
        )

    def test_mw_title43(self):
        self.scribunto(
            "false",
            r"""
        local t = mw.title.makeTitle("Main", "Test/foo/bar", "Frag")
        return t:inNamespace(3)""",
        )

    def test_mw_title44(self):
        self.scribunto(
            "true",
            r"""
        local t = mw.title.makeTitle("Main", "Test/foo/bar", "Frag")
        return t:inNamespaces("Module", "Main")""",
        )

    def test_mw_title45(self):
        self.scribunto(
            "true",
            r"""
        local t = mw.title.makeTitle("User talk", "Test/foo/bar", "Frag")
        return t:hasSubjectNamespace("User")""",
        )

    def test_mw_title46(self):
        self.scribunto(
            "wikitext",
            r"""
        local t = mw.title.makeTitle(3, "Test/foo/bar", "Frag")
        return t.contentModel""",
        )

    def test_mw_title47(self):
        self.scribunto(
            "Test/foo",
            r"""
        local t = mw.title.makeTitle("Main", "Test/foo/bar", "Frag")
        return t.basePageTitle.fullText""",
        )

    def test_mw_title48(self):
        self.scribunto(
            "Test",
            r"""
        local t = mw.title.makeTitle("Main", "Test/foo/bar", "Frag")
        return t.rootPageTitle.fullText""",
        )

    def test_mw_title49(self):
        self.scribunto(
            "Talk:Test/foo/bar",
            r"""
        local t = mw.title.makeTitle("Main", "Test/foo/bar", "Frag")
        return t.talkPageTitle.fullText""",
        )

    def test_mw_title50(self):
        self.scribunto(
            "Test/foo/bar",
            r"""
        local t = mw.title.makeTitle("Talk", "Test/foo/bar", "Frag")
        return t.subjectPageTitle.fullText""",
        )

    def test_mw_title51(self):
        # test for redirect target
        self.ctx.add_page("Main:Foo", 0, redirect_to="Main:Bar")
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
            local export = {}
            function export.testfn(frame)
               local t = mw.title.makeTitle("Main", "Foo", "Frag")
               return t.redirectTarget.fullText
            end
            return export""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{#invoke:testmod|testfn}}")
        self.assertEqual(ret, "Bar")

    def test_mw_title52(self):
        self.scribunto(
            "Test/foo/bar/z",
            r"""
        local t = mw.title.makeTitle("Main", "Test/foo/bar", "Frag")
        return t:subPageTitle("z").fullText""",
        )

    def test_mw_title53(self):
        self.scribunto(
            "Test/foo/b_ar",
            r"""
        local t = mw.title.makeTitle("Main", "Test/foo/b ar", "Frag")
        return t:partialUrl()""",
        )

    def test_mw_title54(self):
        self.scribunto(
            "https://wiki.local/w/index.php?a=1&title=Test%2Ffoo%2Fb+ar#Frag",
            """
            local t = mw.title.makeTitle("Main", "Test/foo/b ar", "Frag")
            return t:fullUrl({a=1}, "http")
            """,
        )

    def test_mw_title55(self):
        self.scribunto(
            "/w/index.php?a=1&title=Test%2Ffoo%2Fb+ar#Frag",
            r"""
        local t = mw.title.makeTitle("Main", "Test/foo/b ar", "Frag")
        return t:localUrl({a=1})""",
        )

    def test_mw_title56(self):
        self.scribunto(
            "https://wiki.local/wiki/Test/foo/b_ar?a=1#Frag",
            r"""
        local t = mw.title.makeTitle("Main", "Test/foo/b ar", "Frag")
        return t:canonicalUrl({a=1})""",
        )

    def test_mw_title57(self):
        # test for redirect target
        self.ctx.add_page("Tt", 0, "RAWCONTENT")
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
            local export = {}
            function export.testfn(frame)
               local t = mw.title.getCurrentTitle().text
               local t2 = mw.title.new(t)
               local c = t2:getContent()
               return c
            end
            return export""",
        )
        self.ctx.start_page("Tt")
        ret = self.ctx.expand("{{#invoke:testmod|testfn}}")
        self.assertEqual(ret, "RAWCONTENT")

    def test_mw_title58(self):
        self.scribunto(
            "Tt",
            """
        return mw.title.getCurrentTitle().text""",
        )

    def test_mw_title59(self):
        # Turns out some modules save information betweem calls - at least
        # page title.  Thus it is necessary to reload modules for each page.
        # This tests that change in title when moving to next page is
        # properly reflected to modules.

        # First invocation to the module
        self.ctx.start_page("pt1")
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
            local title = mw.title.getCurrentTitle().text
            local export = {}
            function export.testfn(frame)
               return title
            end
            return export""",
        )
        ret = self.ctx.expand("{{#invoke:testmod|testfn}}")
        self.assertEqual(ret, "pt1")
        # Call again within same page, title should remain
        ret = self.ctx.expand("{{#invoke:testmod|testfn}}")
        self.assertEqual(ret, "pt1")
        # Second invocation to the module with a different page
        self.ctx.start_page("pt2")
        ret = self.ctx.expand("{{#invoke:testmod|testfn}}")
        self.assertEqual(ret, "pt2")

    def test_mw_clone1(self):
        self.scribunto(
            "21AAa",
            r"""
        local x = {1, "a", math.sin, foo={"a", "b"}}
        local v = mw.clone(x)
        x[1] = 2
        x.foo[1] = "AA"
        return x[1] .. v[1] .. x.foo[1] .. v.foo[1]""",
        )

    def test_mw_clone99(self):
        self.ctx.start_page("Tt")
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
            local export = {}
            function export.testfn(frame)
               local c = mw.clone(frame.args)
               return c[1] .. c.foo .. tostring(c.nonex)
            end
            return export""",
        )
        ret = self.ctx.expand("{{#invoke:testmod|testfn|a|foo=bar}}")
        self.assertEqual(ret, "abarnil")

    def test_table_getn(self):
        self.scribunto(
            "3",
            r"""
        return table.getn({"a", "b", "c"})""",
        )

    def test_math_mod(self):
        self.scribunto(
            "2",
            r"""
        return math.mod(12, 5)""",
        )

    def test_string_format1(self):
        self.scribunto(
            "00004",
            r"""
        return string.format("%05d", 4.7)""",
        )

    def test_string_format2(self):
        self.scribunto(
            "00004 % foo 1.1 -6",
            r"""
        return string.format("%05d %% %s %.1f %d", 4.7, "foo", 1.1, -6)""",
        )

    def test_string_format3(self):
        self.scribunto(
            "0004",
            r"""
        return string.format("%.4X", 4.7)""",
        )

    def test_sandbox1(self):
        # For security, Python should not be callable from Lua modules
        self.ctx.start_page("Tt")
        self.ctx.add_page(
            "Module:testmod",
            828,
            """
local export = {}
function export.testfn(frame)
    return python.eval('1')
end
return export
""",
        )
        ret = self.ctx.expand("{{#invoke:testmod|testfn}}")
        self.assertTrue(ret.startswith('<strong class="error">'))

    def test_sandbox2(self):
        # For security, dangerous Lua functions should not be callable from
        # Lua modules (only expressly allowed modules and functions should be
        # available)
        self.scribunto(
            "true",
            r"""
        return os.exit == nil""",
        )

    def test_sandbox4(self):
        self.scribunto(
            "true",
            r"""
        return _G["os"].exit == nil""",
        )

    def test_sandbox5(self):
        # This is to test the other tests, to make sure an existing function is
        # properly detected
        self.scribunto(
            "false",
            r"""
        return _G["os"].clock == nil""",
        )

    def test_dbfile1(self):
        self.ctx.add_page("Template:testmod", 10, "test content")
        self.ctx.db_conn.commit()
        self.ctx.start_page("Tt")
        ret1 = self.ctx.expand("a{{testmod}}b")
        self.assertEqual(ret1, "atest contentb")
        # Now create a new context with the same db but do not add page
        new_ctx = Wtp(db_path=self.ctx.db_path)
        new_ctx.start_page("Tt")
        ret2 = new_ctx.expand("a{{testmod}}b")
        new_ctx.close_db_conn()
        self.assertEqual(ret2, "atest contentb")

    def test_dbfile2(self):
        self.ctx.add_page("Template:testmod", 10, "test content")
        self.ctx.db_conn.commit()
        self.ctx.start_page("Tt")
        ret1 = self.ctx.expand("a{{testmod}}b")
        self.assertEqual(ret1, "atest contentb")
        # Now create a new context with the same db and update page
        new_ctx = Wtp(db_path=self.ctx.db_path)
        new_ctx.add_page("Template:testmod", 10, "test content 2")
        new_ctx.db_conn.commit()
        new_ctx.start_page("Tt")
        ret2 = new_ctx.expand("a{{testmod}}b")
        new_ctx.close_db_conn()
        self.assertEqual(ret2, "atest content 2b")

    def test_lua_max_time1(self):
        t = time.time()
        self.scribunto(
            '<strong class="error">Lua timeout error in '
            "Module:testmod function testfn</strong>",
            """
          local i = 0
          while true do
            i = i + 1
          end
          return i""",
            timeout=2,
        )
        self.assertLess(time.time() - t, 10)

    def test_link_backforth1(self):
        self.ctx.start_page("Tt")
        v = (
            "([[w:Jurchen script|Jurchen script]]: , Image: "
            "[[FIle:Da (Jurchen script).png|25px]])"
        )
        node = self.ctx.parse(v)
        t = self.ctx.node_to_wikitext(node)
        self.assertEqual(v, t)

    def test_mw_wikibase_getEntityUrl1(self):
        self.scribunto("", """return mw.wikibase.getEntityUrl()""")

    def test_gsub1(self):
        self.scribunto(
            "f(%d+)accel", """return string.gsub("f=accel", "=", "(%%d+)");"""
        )

    def test_gsub2(self):
        # This tests a Lua version compatibility kludge with string.gsub
        self.scribunto("f]oo", """return string.gsub("f=oo", "=", "%]");""")

    def test_gsub3(self):
        # This tests a Lua version compatibility kludge with string.gsub
        self.scribunto("f-oo", """return string.gsub("f=oo", "=", "%-");""")

    def test_gsub4(self):
        self.scribunto(
            "fOOf[[]]",
            """
            a = {}; a["o"] = "O";
            return mw.ustring.gsub("foof[[]]", ".", a);
            """,
        )

    def test_gsub5(self):
        self.scribunto("42", """return string.gsub("x2A", "x%x+", "42");""")

    def test_title_1_colon_e(self) -> None:
        self.scribunto("1:e", "return mw.title.new('1:e').text")

    def test_get_page_resolve_redirect_infinite_recursion(self):
        self.ctx.add_page("Template:cite-book", 10, body="cite-book")
        self.ctx.add_page(
            "Template:Cite-book", 10, redirect_to="Template:cite-book"
        )
        self.ctx.db_conn.commit()
        page = self.ctx.get_page_resolve_redirect("Template:cite-book", 10)
        self.assertEqual(page.title, "Template:cite-book")
        self.assertEqual(page.body, "cite-book")

    def test_query_page_title_case(self):
        self.ctx.add_page("Template:Q", 10, "")
        self.ctx.add_page("Template:q", 10, "")
        self.ctx.db_conn.commit()
        page = self.ctx.get_page("q", 10)
        self.assertEqual(page.title, "Template:q")

    def test_get_page_empty_title(self):
        self.assertEqual(self.ctx.get_page(""), None)

    @patch(
        "wikitextprocessor.interwiki.get_interwiki_data",
        return_value=[
            {"prefix": "s", "url": "https://en.wikisource.org/wiki/$1"}
        ],
    )
    def test_fullurl_interwiki(self, mock_get_interwiki_data):
        from wikitextprocessor.interwiki import init_interwiki_map

        init_interwiki_map(self.ctx)
        tests = [
            [
                "{{fullurl:Category:Top level}}",
                "//en.wiktionary.org/wiki/Category:Top_level",
            ],
            [
                "{{fullurl:s:Electra|action=edit}}",
                "https://en.wikisource.org/wiki/Electra?action=edit",
            ],
            [
                "{{fullurl:s:es:Electra|action=edit}}",
                "https://en.wikisource.org/wiki/es:Electra?action=edit",
            ],
            [
                # https://en.wiktionary.org/wiki/bánh_tây
                "{{fullurle:s:vi:Xứ Bắc kỳ ngày nay/1}}",
                "https://en.wikisource.org/wiki/vi:X%E1%BB%A9_B%E1%BA%AFc_k%E1%BB%B3_ng%C3%A0y_nay/1",
            ],
            ["{{fullurl:title|a=a|b=b}}", "//en.wiktionary.org/wiki/title?a=a"],
        ]
        self.ctx.start_page("")
        for wikitext, result in tests:
            with self.subTest(wikitext=wikitext, result=result):
                self.assertEqual(self.ctx.expand(wikitext), result)
        mock_get_interwiki_data.assert_called_once()

    def test_transclude_page(self):
        # https://fr.wiktionary.org/wiki/Conjugaison:français/s’abêtir
        # The "Conjugaison" namespace name is replaced with "Sign gloss" that
        # has the same namesapce id.
        self.ctx.start_page("")
        self.ctx.add_page(
            "Sign gloss:français/abêtir",
            116,
            "{{Onglets conjugaison| sél ={{{sél|1}}}}}",
        )
        self.ctx.add_page("Template:Onglets conjugaison", 10, "{{{sél|1}}}")
        self.ctx.add_page("Template:Foo:bar", 10, "foobar")
        self.ctx.add_page("page", 0, "page text")
        self.assertEqual(
            self.ctx.expand("{{:Sign gloss:français/abêtir|sél=2}}"), "2"
        )
        self.assertEqual(self.ctx.expand("{{:page}}"), "page text")
        self.assertEqual(
            self.ctx.expand("{{Template:Onglets conjugaison|sél = 3}}"), "3"
        )
        self.assertEqual(self.ctx.expand("{{Foo:bar}}"), "foobar")

    def test_get_page_with_namespace_prefixes(self):
        page = Page(
            "Template:title", 10, body="template text", model="wikitext"
        )
        self.ctx.add_page("Template:title", 10, page.body)
        self.assertEqual(self.ctx.get_page("T:title", 10), page)
        self.assertEqual(self.ctx.get_page("t:title", 10), page)
        self.ctx.start_page("")
        self.assertEqual(self.ctx.expand("{{t:title}}"), page.body)
        module_page = Page(
            "Module:title", 828, body="module text", model="Scribunto"
        )
        self.ctx.add_page(
            "Module:title", 828, module_page.body, model="Scribunto"
        )
        self.assertEqual(self.ctx.get_page("mod:title", 828), module_page)

    def test_unnamed_template_arg_end_in_newline(self):
        # https://ru.wiktionary.org/wiki/adygejski
        # newline at the end of unnamed template argument should be removed
        self.ctx.add_page("Template:test", 10, "{{{1}}}")
        self.ctx.add_page(
            "Template:testlua", 10, "{{#invoke:test|test|{{{1}}}}}"
        )
        self.ctx.add_page(
            "Module:test",
            828,
            """
            local export = {}

            function export.test(frame)
              return frame:getParent().args[1] .. "-" .. frame.args[1]
            end

            return export
            """,
        )
        self.ctx.start_page("")
        self.assertEqual(
            self.ctx.expand("{{test| \n unnamed1 \n}}"), " \n unnamed1 "
        )
        self.assertEqual(
            self.ctx.expand("{{test| \n {{test|unnamed2}} \n}}"),
            " \n unnamed2 ",
        )
        self.assertEqual(
            self.ctx.expand("{{testlua| \n unnamed3 \n}}"),
            " \n unnamed3 - \n unnamed3 ",
        )

    def test_nowiki_in_template_body(self):
        # GH issue #233
        # https://fr.wikipedia.org/wiki/Modèle:Admissibilité_à_vérifier
        self.ctx.start_page("")
        self.ctx.add_page(
            "Template:t",
            10,
            "template body <nowiki>{{t}}</nowiki>",
        )
        text = self.ctx.expand("{{t}}")
        self.assertEqual(
            text,
            "template body &lbrace;&lbrace;t&rbrace;&rbrace;",
        )

    def test_invoke_aliases(self):
        # Some wikipedias (fr.wikipedia.org) have aliases for #invoke
        self.ctx.start_page("test")
        self.ctx.invoke_aliases = self.ctx.invoke_aliases | {"#infooque"}
        self.ctx.add_page(
            "Module:test",
            828,
            """
            local export = {}

            function export.test()
              return "foo"
            end

            return export
            """,
        )
        text = self.ctx.expand("{{#infooque|test|test}}")
        self.assertEqual(
            text,
            "foo",
        )

    def test_expand_template_loop_in_lua(self):
        # tatuylonen/wiktextract#894
        self.ctx.add_page(
            "Module:link",
            828,
            """local export = {}

function export.full_link(frame)
    return frame:preprocess("{{m}}")
end

return export""",
        )
        self.ctx.add_page("Template:m", 10, "{{#invoke:link|full_link}}")
        self.ctx.start_page("今生")
        self.assertEqual(
            self.ctx.expand("{{m}}"),
            '<strong class="error">Template loop detected: '
            "[[:Template:m]]</strong>",
        )

    def test_nested_template_in_template_args(self):
        # used in nl edition language title templates
        self.ctx.add_page(
            "Template:str len",
            10,
            """{{str len/core|{{str len/core|{{str len/core|{{{1}}}}}}}}}""",
        )
        self.ctx.add_page("Template:str len/core", 10, """{{{1}}}""")
        self.ctx.start_page("doodgeboren")
        self.assertEqual(self.ctx.expand("{{str len|a}}"), "a")


# XXX Test template_fn

# XXX test post_template_fn

# XXX test expand() with expand_parserfns=false
# XXX test expand() with expand_templates=false
# XXX test expand() with template_fn (return None and return string)
# XXX test expand() with pre_only
# XXX test expand() with templates_to_expand as a given set
# XXX test expand() with templates_to_expand=None (meaning all templates)

# XXX implement #categorytree (note named arguments)

# XXX implement mw.title.makeTitle with interwiki; t.interwiki field
# XXX implement mw.title.exists by calling python get_page_info (cf isRedirect)
# XXX mw.title subpage functions should only consider those parent pages
# as subpages that actually exist

# XXX test frame:newParserValue
# XXX test frame:newTemplateParserValue
# XXX test frame:newChild

# XXX test case variations of template names and parser function names
#  - these are apparently configured for each wiki and listed in the
#    dump file
