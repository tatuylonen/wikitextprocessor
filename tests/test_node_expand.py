# Tests for WikiText parsing
#
# Copyright (c) 2020-2021 Tatu Ylonen.  See file LICENSE and https://ylonen.org

import unittest
from unittest.mock import patch

from wikitextprocessor import Page, Wtp


class NodeExpTests(unittest.TestCase):
    def setUp(self):
        self.ctx = Wtp()

    def tearDown(self):
        self.ctx.close_db_conn()

    def backcvt(self, text, expected):
        self.ctx.start_page("test")
        root = self.ctx.parse(text)
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        t = self.ctx.node_to_wikitext(root)
        self.assertEqual(t, expected)

    def tohtml(self, text, expected):
        self.ctx.start_page("test")
        root = self.ctx.parse(text)
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        t = self.ctx.node_to_html(root)
        self.assertEqual(t, expected)

    def totext(self, text, expected):
        self.ctx.start_page("test")
        root = self.ctx.parse(text)
        self.assertEqual(self.ctx.errors, [])
        self.assertEqual(self.ctx.warnings, [])
        t = self.ctx.node_to_text(root)
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
        self.backcvt(
            "abc\n*a\n*# c\n*# d\n* b\ndef", "abc\n*a\n*# c\n*# d\n* b\ndef"
        )

    # https://github.com/tatuylonen/wikitextprocessor/issues/84
    # See test_parser/test_list_cont1
    # def test_list4(self):
    #     self.backcvt("abc\n*a\n**b\n*:c\n", "abc\n*a\n**b\n*:c\n")

    def test_pre1(self):
        self.backcvt("a<pre>foo\n  bar</pre>b", "a<pre>foo\n  bar</pre>b")

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

    def test_templatearg3a(self):
        self.backcvt("{{{|a}}}", "{{{|a}}}")

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
        self.backcvt(
            "https://wikipedia.org/x/y?a=7%255",
            "[https://wikipedia.org/x/y?a=7%255]",
        )

    # This test is incorrect: the |} token requires it to be on a new
    # line, after ^\n\s*
    # def test_table1(self):
    #     self.backcvt("{| |}", "\n{| \n\n|}\n")

    def test_table2(self):
        self.backcvt('{| class="x"\n|}', '\n{| class="x"\n\n|}\n')

    def test_tablecaption1(self):
        self.backcvt("{|\n|+\ncapt\n|}", "\n{| \n\n|+ \n\ncapt\n\n|}\n")

    def test_tablerowcell1(self):
        self.backcvt(
            "{|\n|- a=1\n| cell\n|}", '\n{| \n\n|- a="1"\n\n| cell\n\n\n|}\n'
        )

    def test_tablerowhdr1(self):
        self.backcvt(
            "{|\n|- a=1\n! cell\n|}", '\n{| \n\n|- a="1"\n\n! cell\n\n\n|}\n'
        )

    def test_magicword1(self):
        self.backcvt("a\n__TOC__\nb", "a\n\n__TOC__\n\nb")

    def test_html1(self):
        self.backcvt("a<b>foo</b>b", "a<b>foo</b>b")

    def test_html2(self):
        self.backcvt(
            'a<span class="bar">foo</span>b', 'a<span class="bar">foo</span>b'
        )

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

    def test_text6(self):
        # Undefined "foo"
        self.totext("{{{foo}}}", "{{{foo}}}")

    def test_text7(self):
        # default to "foo"
        self.totext("{{{|foo}}}", "foo")

    def test_text8(self):
        # default to "foo"
        self.totext("{{{bar|foo}}}", "foo")

    def test_text9(self):
        # default to "foo"
        self.totext("{{{bar|{{{baz|foo}}}}}}", "foo")

    @patch(
        "wikitextprocessor.Wtp.get_page",
        return_value=Page(
            "Template:blank template", 10, None, False, "", "wikitext"
        ),
    )
    def test_blank_template(self, mock_get_page) -> None:
        """
        Test the case when a template's body is an empty string in the database.
        """
        self.totext("{{blank template}}", "")

    def test_language_converter_placeholder(self) -> None:
        # "-{}-" template argument shouldn't be cleaned before invoke Lua module
        # GitHub issue #59
        self.ctx.lang_code = "zh"
        # https://zh.wiktionary.org/wiki/Template:Ja-romanization_of
        self.ctx.add_page(
            "Template:Ja-romanization of",
            10,
            "{{#invoke:form of/templates|form_of_t|-{}-|withcap=1|lang=ja}}",
        )
        # https://zh.wiktionary.org/wiki/Module:Form_of/templates
        self.ctx.add_page(
            "Module:Form of/templates",
            828,
            """
            local export = {}
            function export.form_of_t(frame)
                if frame.args[1] ~= "-{}-" then
                    error("Incorrect first parameter")
                end
                local template_args = frame:getParent().args
                return "[[" .. template_args[1] .. "#日語|-{" ..
                          template_args[1] .."}-]]</i></span> " ..
                          frame.args[1] .. "</span>"
            end
            return export
            """,
            model="Scribunto",
        )
        self.ctx.db_conn.commit()
        self.ctx.start_page("test_page")
        self.assertEqual(
            self.ctx.expand("{{ja-romanization of|まんが}}"),
            "[[まんが#日語|まんが]]</i></span> </span>",
        )

    def test_lua_module_args_not_unescaped(self):
        # https://en.wiktionary.org/wiki/Gendergap
        self.ctx.add_page(
            "Template:quote-journal",
            10,
            "{{#invoke:quote|quote_t|type=journal}}",
        )
        self.ctx.add_page(
            "Module:quote",
            828,
            """
            local export = {}
            function export.quote_t(frame)
                return frame:getParent().args.title
            end
            return export
            """,
            model="Scribunto",
        )
        self.ctx.start_page("Gendergap")
        self.assertEqual(
            self.ctx.expand(
                "{{quote-journal|de|title=re&colon;publica 2014, der 1.}}"
            ),
            "re&colon;publica 2014, der 1.",
        )

    def test_auto_newline_before_paser_function(self):
        # GitHub pull #150 for wiktextract issue #403
        self.ctx.start_page("newline")
        self.assertEqual(self.ctx.expand("{{#if: true | text}}"), "text")
        self.assertEqual(self.ctx.expand("{{#if: true | * list}}"), "\n* list")
