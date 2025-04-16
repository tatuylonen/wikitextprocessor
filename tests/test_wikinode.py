# Tests for WikiText parsing
#
# Copyright (c) 2020-2021 Tatu Ylonen.  See file LICENSE and https://ylonen.org

import unittest

from wikitextprocessor import Wtp


class WikiNodeTests(unittest.TestCase):
    def setUp(self):
        self.ctx = Wtp()

    def tearDown(self):
        self.ctx.close_db_conn()

    def template_args(self, text: str, expected: dict) -> None:
        self.ctx.start_page("test")
        root = self.ctx.parse(text)
        tnode = root.children[0]
        print(f"{expected=} -> {tnode.template_parameters}")
        self.assertEqual(expected, tnode.template_parameters)

    def test_template_args1(self):
        self.template_args("{{test|a|b}}", {1: "a", 2: "b"})

    def test_template_args2(self):
        self.template_args("{{test|1=a|2=b}}", {1: "a", 2: "b"})

    def test_template_args3(self):
        self.template_args("{{test|2=b|1=a}}", {1: "a", 2: "b"})

    def test_template_args4(self):
        self.template_args("{{test|b|1=a}}", {1: "a", 2: "b"})

