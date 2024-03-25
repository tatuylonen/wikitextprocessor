from unittest import TestCase
from unittest.mock import patch


class MockRequests:
    def __init__(self, ok, result):
        self.ok = ok
        self.result = result

    def json(self):
        return self.result


class TestLua(TestCase):
    def setUp(self):
        from wikitextprocessor import Wtp

        self.wtp = Wtp()

    def tearDown(self):
        self.wtp.close_db_conn()

    def test_fetchlanguage(self):
        self.wtp.add_page(
            "Module:test",
            828,
            body="""
            local export = {}
            function export.test()
              value = mw.language.fetchLanguageName("fr")
              value = value .. " " .. mw.language.fetchLanguageName("fr", "en")
              return value
            end
            return export
            """,
            model="Scribunto",
        )
        self.wtp.start_page("")
        self.assertEqual(
            self.wtp.expand("{{#invoke:test|test}}"), "français French"
        )

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

    def test_extension_tag_nowiki_strip_marker(self):
        # GitHub issue tatuylonen/wiktextract#238
        self.wtp.add_page(
            "Module:test",
            828,
            """
        local export = {}

        function export.test(frame)
          return frame:extensionTag("nowiki", "") ..
            frame:extensionTag("nowiki", "")
        end

        return export
        """,
        )
        self.wtp.start_page("test")
        self.assertEqual(
            self.wtp.expand("{{#invoke:test|test}}"),
            """\x7f'"`UNIQ--nowiki-00000000-QINU`"'\x7f"""
            """\x7f'"`UNIQ--nowiki-00000001-QINU`"'\x7f""",
        )

    def test_preprocess_heading_strip_marker(self):
        # GitHub issue tatuylonen/wiktextract#238
        self.wtp.add_page(
            "Module:test",
            828,
            """
        local export = {}

        function export.test(frame)
          return frame:preprocess("==a==") ..
            frame:preprocess("==a==") ..
            frame:preprocess("==b==") ..
            frame:preprocess("=b=")
        end

        return export
        """,
        )
        self.wtp.start_page("test")
        self.assertEqual(
            self.wtp.expand("{{#invoke:test|test}}"),
            """==\x7f'"`UNIQ--h-0-QINU`"'\x7fa=="""
            """==\x7f'"`UNIQ--h-0-QINU`"'\x7fa=="""
            """==\x7f'"`UNIQ--h-1-QINU`"'\x7fb=="""
            """=\x7f'"`UNIQ--h-2-QINU`"'\x7fb=""",
        )

    def test_mw_html(self):
        self.wtp.add_page(
            "Module:test",
            828,
            body="""
            local export = {}
            function export.test()
                local wikiHtml = mw.html.create( '' )
                wikiHtml:tag('span')
                        :wikitext('foo')
                        :done()
                return tostring(wikiHtml)
            end
            return export
            """,
            model="Scribunto",
        )
        self.wtp.start_page("")
        self.assertEqual(
            # Should not result in "<><span>foo</span>" or
            # <><span>foo</span></> due to the empty string in `create('')`
            self.wtp.expand("{{#invoke:test|test}}"),
            "<span>foo</span>",
        )

    @patch(
        "wikitextprocessor.wikidata.query_wikidata",
        return_value={
            "item": {"value": "http://www.wikidata.org/entity/Q42"},
            "itemLabel": {"value": "Douglas Adams"},
            "itemDescription": {
                "value": "English author and humourist (1952–2001)"
            },
        },
    )
    def test_wikibase_getEntityIdForTitle(self, mock_query) -> None:
        self.wtp.add_page(
            "Module:test",
            828,
            """
local export = {}
function export.test(frame)
  local a = mw.wikibase.getEntityIdForTitle("Douglas Adams", "enwiki")
  local b = mw.wikibase.getEntityIdForTitle("Douglas Adams", "enwiki")
  return  a .. b
end
return export""",
            model="Scribunto",
        )
        self.wtp.start_page("")
        self.assertEqual(self.wtp.expand("{{#invoke:test|test}}"), "Q42Q42")
        mock_query.assert_called_once()  # use db cache

    def test_wikibase_getBadges(self) -> None:
        # getBadge is unimplemented, because we don't really need badge data
        # for parsing. If this test fails, someone might have implemented
        # getBadge properly, so you need to implement this as a proper test.
        self.wtp.add_page(
            "Module:test",
            828,
            """
local export = {}
function export.test(frame)
  local a = mw.wikibase.getBadges("Douglas Adams", "enwiki")
  if type(a) == 'table' and next(a) == nil then
      return 'foo'
  end
  return  'bar'
end
return export""",
            model="Scribunto",
        )
        self.wtp.start_page("")
        self.assertEqual(self.wtp.expand("{{#invoke:test|test}}"), "foo")

    @patch("wikitextprocessor.wikidata.query_wikidata", return_value={})
    def test_wikibase_getEntityIdForTitle_no_result(self, mock_query):
        self.wtp.add_page(
            "Module:test",
            828,
            """
local export = {}
function export.test(frame)
  local a = mw.wikibase.getEntityIdForTitle("not exist page", "enwiki")
  local b = mw.wikibase.getEntityIdForTitle("not exist page", "enwiki")
  return a
end
return export""",
            model="Scribunto",
        )
        self.wtp.start_page("")
        self.assertEqual(self.wtp.expand("{{#invoke:test|test}}"), "")
        mock_query.assert_called_once()  # use db cache

    def test_ext_data_get(self) -> None:
        # mw.ext.data.get is unimplemented; we do not want to pull data from
        # commons. Usually mw.ext.data.get loads data from static .tab files
        # and converts them to JSON -> table (with certain specific fields,
        # like .schema), but when retrieval fails it returns a { false } table.
        # https://fr.wikipedia.org/wiki/Module:Tabular_data
        self.wtp.add_page(
            "Module:test",
            828,
            """
local export = {}
function export.test(frame)
  local a = mw.ext.data.get("Douglas Adams", "_")
  _, val = next(a)
  if type(a) ~= 'table' then
      return 'bar'
  end
  if a.schema == nil then
      return 'bar'
  end
  if a.schema.fields == nil then
      return 'bar'
  end
  if type(a.schema.fields) ~= "table" then
      return 'bar'
  end
  if a.data == nil then
      return 'bar'
  end
  if type(a.data) ~= "table" then
      return 'bar'
  end
  return  'foo'
end
return export""",
            model="Scribunto",
        )
        self.wtp.start_page("")
        self.assertEqual(self.wtp.expand("{{#invoke:test|test}}"), "foo")

    def test_text_decode(self):
        # GH pr #244
        self.wtp.add_page(
            "Module:test",
            828,
            """
local export = {}
function export.test(frame)
  local a = mw.text.decode("&lt;-&vert;-&#124;-&#x7c;")
  local b = mw.text.decode("&lt;-&vert;-&#124;-&#x7c;", true)
  return a .. "--" .. b
end
return export""",
            model="Scribunto",
        )
        self.wtp.start_page("")
        self.assertEqual(
            self.wtp.expand("{{#invoke:test|test}}"), "<-&vert;-|-|--<-|-|-|"
        )

    @patch(
        "requests.get",
        return_value=MockRequests(True, {"entities": {"Q42": {"id": "Q42"}}}),
    )
    def test_wikidata_get_entity(self, mock_request):
        self.wtp.add_page(
            "Module:test",
            828,
            """
local export = {}
function export.test(frame)
  local a = mw.wikibase.getEntity("Q42")
  local b = mw.wikibase.getEntity("Q42")
  return a:getId() .. b:getId()
end
return export""",
            model="Scribunto",
        )
        self.wtp.start_page("")
        self.assertEqual(self.wtp.expand("{{#invoke:test|test}}"), "Q42Q42")
        mock_request.assert_called_once()
