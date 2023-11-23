from unittest import TestCase
from unittest.mock import Mock, patch

from wikitextprocessor import Wtp
from wikitextprocessor.luaexec import fetch_language_name


class TestLua(TestCase):
    def setUp(self):
        self.wtp = Wtp()

    def tearDown(self):
        self.wtp.close_db_conn()

    def test_fetchlanguage(self):
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


    @patch("requests.get")
    def test_intewiki_map(self, mock_requests_get):
        mock_result = Mock()
        mock_result.json = Mock(
            return_value={
                "batchcomplete": True,
                "query": {
                    "interwikimap": [
                        {
                            "prefix": "en",
                            "local": True,
                            "language": "English",
                            "bcp47": "en",
                            "url": "https://en.wikipedia.org/wiki/$1",
                            "protorel": False
                        },
                    ]
                }
            }
        )
        mock_requests_get.return_value = mock_result
        self.wtp.add_page("Module:test", 828, """
        local export = {}

        function export.test()
          return mw.site.interwikiMap().en.url
        end

        return export
        """)
        self.wtp.start_page("test")
        self.assertEqual(
            self.wtp.expand("{{#invoke:test|test}}"),
            "https://en.wikipedia.org/wiki/$1"
        )
