import unittest

from wikitextprocessor import Wtp
from wikitextprocessor.luaexec import fetch_language_name


class TestLua(unittest.TestCase):
    def setUp(self):
        self.wtp = Wtp()

    def tearDown(self):
        self.wtp.close_db_conn()

    def test_fetchlanguage(self):
        self.assertEqual(fetch_language_name("fr", None), "français")
        self.assertEqual(fetch_language_name("fr", "en"), "French")
