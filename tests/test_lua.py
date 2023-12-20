from unittest import TestCase
from unittest.mock import patch


class TestLua(TestCase):
    def setUp(self):
        from wikitextprocessor import Wtp

        self.wtp = Wtp()

    def tearDown(self):
        self.wtp.close_db_conn()

    def test_fetchlanguage(self):
        from wikitextprocessor.luaexec import fetch_language_name

        self.assertEqual(fetch_language_name("fr", None), "français")
        self.assertEqual(fetch_language_name("fr", "en"), "French")

    def test_isolated_lua_env(self):
        # each Lua moudle uses by `#invoke` runs in cloned environment
        self.wtp.add_page(
            "Module:a",
            828,
            """
        local export = {}

        value = "a"

        function export.func()
          return mw.getCurrentFrame():expandTemplate{title="b"} .. " " .. value
        end

        return export
        """,
            model="Scribunto",
        )
        self.wtp.add_page(
            "Module:b",
            828,
            """
        local export = {}

        value = 'b'

        function export.func()
            return value
        end

        return export
        """,
            model="Scribunto",
        )
        self.wtp.add_page(
            "Module:c",
            828,
            """
        local export = {}

        function export.func()
            return value or "c"
        end

        return export
        """,
            model="Scribunto",
        )
        self.wtp.add_page("Template:a", 10, "{{#invoke:a|func}}")
        self.wtp.add_page("Template:b", 10, "{{#invoke:b|func}}")
        self.wtp.add_page(
            "Template:c", 10, "{{#invoke:b|func}} {{#invoke:c|func}}"
        )
        self.wtp.start_page("test lua env")
        self.assertEqual(self.wtp.expand("{{c}}"), "b c")
        self.assertEqual(self.wtp.expand("{{a}}"), "b a")

    def test_cloned_lua_env(self):
        # https://fr.wiktionary.org/wiki/responsable des services généraux
        # https://fr.wiktionary.org/wiki/Module:section
        self.wtp.add_page(
            "Module:a",
            828,
            """
        local export = {}

        b = require("Module:b")
        c = require("Module:c")

        function export.func()
            return c.func()
        end

        return export
        """,
            model="Scribunto",
        )
        self.wtp.add_page(
            "Module:b",
            828,
            """
        local export = {}

        function export.func()
            return "b"
        end

        return export
        """,
            model="Scribunto",
        )
        self.wtp.add_page(
            "Module:c",
            828,
            """
        local export = {}

        function export.func()
            return b.func()
        end

        return export
        """,
            model="Scribunto",
        )
        self.wtp.start_page("test lua env")
        self.assertEqual(self.wtp.expand("{{#invoke:a|func}}"), "b")

    @patch(
        "wikitextprocessor.interwiki.get_interwiki_data",
        return_value=[
            {
                "prefix": "en",
                "local": True,
                "language": "English",
                "bcp47": "en",
                "url": "https://en.wikipedia.org/wiki/$1",
                "protorel": False,
            }
        ],
    )
    def test_intewiki_map(self, mock_func):
        from wikitextprocessor.interwiki import init_interwiki_map

        init_interwiki_map(self.wtp)
        self.wtp.add_page(
            "Module:test",
            828,
            """
        local export = {}

        function export.test()
          return mw.site.interwikiMap().en.url
        end

        return export
        """,
        )
        self.wtp.start_page("test")
        self.assertEqual(
            self.wtp.expand("{{#invoke:test|test}}"),
            "https://en.wikipedia.org/wiki/$1",
        )

    @patch(
        "wikitextprocessor.wikidata.query_wikidata",
        return_value={
            "itemLabel": {"value": "Humphry Davy"},
            "itemDescription": {"value": "British chemist"},
        },
    )
    def test_wikibase_label_and_desc(self, mock_func):
        # https://en.wiktionary.org/wiki/sodium
        # https://en.wiktionary.org/wiki/Module:coinage
        self.wtp.add_page(
            "Module:test",
            828,
            """
        local export = {}

        function export.test()
          local coiner = "Q131761"
          return mw.wikibase.getDescription(coiner) .. " " ..
            mw.wikibase.getLabel(coiner)
        end

        return export
        """,
        )
        self.wtp.start_page("test")
        self.assertEqual(
            self.wtp.expand("{{#invoke:test|test}}"),
            "British chemist Humphry Davy",
        )
        mock_func.assert_called_once()  # use db cache
