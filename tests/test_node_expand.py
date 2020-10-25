# Tests for WikiText parsing
#
# Copyright (c) 2020 Tatu Ylonen.  See file LICENSE and https://ylonen.org

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
        t = ctx.node_to_wikitext(root)
        self.assertEqual(t, expected)

    def test_basic1(self):
        self.backcvt("", "")

    def test_basic2(self):
        self.backcvt("foo bar\nxyz\n", "foo bar\nxyz\n")

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
