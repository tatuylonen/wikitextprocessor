from unittest import TestCase
from unittest.mock import patch


class TestParserFunctions(TestCase):
    def setUp(self) -> None:
        from wikitextprocessor import Wtp

        self.wtp = Wtp()

    def tearDown(self) -> None:
        self.wtp.close_db_conn()

    def test_time_fn_with_mediawiki_timestamp(self) -> None:
        # GitHub issue #211
        # https://fr.wikipedia.org/wiki/Arabie_saoudite
        self.wtp.start_page("Arabie saoudite")
        self.assertEqual(
            self.wtp.expand("{{#time:j F Y|20130914013636}}"),
            "14 September 2013",
        )

    def test_coordinates_fn(self) -> None:
        self.wtp.start_page("Test")
        self.assertEqual(
            self.wtp.expand("{{#coordinates|foo|bar|baz}}"),
            "",
        )

    def test_pagesize_fn(self) -> None:
        self.wtp.add_page("sizetestA", 0, body="AAAAAAA" * 1000)
        self.wtp.add_page("sizetestB", 0, body="ÄÄÄÄÄÄÄ" * 1000)
        self.wtp.start_page("Test")
        self.assertEqual(
            self.wtp.expand("{{PAGESIZE:sizetestA|R}}"),
            "7,000",
        )
        self.assertEqual(
            self.wtp.expand("{{PAGESIZE:sizetestB|R}}"),
            "14,000",
        )
        self.assertEqual(
            self.wtp.expand("{{PAGESIZE:sizetestA}}"),
            "7000",
        )
        self.assertEqual(
            self.wtp.expand("{{PAGESIZE:sizetestB}}"),
            "14000",
        )

    def test_filepath_fn1(self) -> None:
        self.wtp.start_page("Test")
        self.assertEqual(
            self.wtp.expand("{{filepath:foo.jpg}}"), "//unimplemented/foo.jpg"
        )

    def test_filepath_fn2(self) -> None:
        self.wtp.start_page("Test")
        self.assertEqual(
            self.wtp.expand("{{filepath:foo.jpg|nowiki}}"),
            "//unimplemented/foo.jpg",
        )

    def test_filepath_fn3(self) -> None:
        self.wtp.start_page("Test")
        self.assertEqual(
            self.wtp.expand("{{filepath:foo.jpg|300|nowiki}}"),
            "//unimplemented/foo.jpg",
        )

    def test_filepath_fn4(self) -> None:
        self.wtp.start_page("Test")
        self.assertEqual(self.wtp.expand("{{filepath}}"), "")

    @patch(
        "wikitextprocessor.wikidata.query_wikidata",
        return_value={
            "value": {"type": "literal", "value": "Douglas Noël Adams"},
            "itemLabel": {
                "xml:lang": "en",
                "type": "literal",
                "value": "Douglas Adams",
            },
            "itemDescription": {
                "xml:lang": "en",
                "type": "literal",
                "value": "English author and humourist (1952–2001)",
            },
            "propLabel": {
                "xml:lang": "en",
                "type": "literal",
                "value": "birth name",
            },
        },
    )
    def test_statements_parser_func(self, mock_query):
        self.wtp.start_page("Don't panic")
        expanded = self.wtp.expand("{{#statements:P1477|from=Q42}}")
        self.assertEqual(expanded, "Douglas Noël Adams")
        expanded = self.wtp.expand("{{#statements:birth name|from=Q42}}")
        self.assertEqual(expanded, "Douglas Noël Adams")
        # Template: https://en.wiktionary.org/wiki/Template:R:ru:STsSRJa
        # page: https://en.wiktionary.org/wiki/резвиться
        expanded = self.wtp.expand(
            "{{#statements:birth name|from={{#if: true| Q42}}}}"
        )
        self.assertEqual(expanded, "Douglas Noël Adams")
        mock_query.assert_called_once()  # use db cache

    @patch(
        "wikitextprocessor.wikidata.query_wikidata",
        return_value={
            "value": {
                "datatype": "http://www.w3.org/2001/XMLSchema#dateTime",
                "type": "literal",
                "value": "1868-01-01T00:00:00Z",
            },
            "itemLabel": {"type": "literal", "value": "Q114098115"},
            "propLabel": {
                "xml:lang": "en",
                "type": "literal",
                "value": "publication date",
            },
        },
    )
    def test_statements_publication_date(self, mock_query):
        # https://en.wiktionary.org/wiki/расплавить
        # https://en.wiktionary.org/wiki/Template:R:ru:fr:Ganot1868
        self.wtp.start_page("расплавить")
        expanded = self.wtp.expand("{{#statements:P577|from=Q114098115}}")
        self.assertEqual(expanded, "1868")

    @patch(
        "wikitextprocessor.wikidata.query_wikidata",
        return_value={
            "valueLabel": {"type": "literal", "value": "1868-01-01T00:00:00Z"},
            "itemLabel": {"type": "literal", "value": "Douglas Adams"},
            "itemDescription": {
                "type": "literal",
                "value": "English author and humourist (1952–2001)",
            },
            "p": {
                "type": "uri",
                "value": "http://www.wikidata.org/entity/P569",
            },
            "value": {
                "datatype": "http://www.w3.org/2001/XMLSchema#dateTime",
                "type": "literal",
                "value": "1952-03-11T00:00:00Z",
            },
        },
    )
    def test_statements_date(self, mock_query):
        # https://www.wikidata.org/wiki/Wikidata:How_to_use_data_on_Wikimedia_projects
        self.wtp.start_page("")
        expanded = self.wtp.expand("{{#statements:date of birth|from=Q42}}")
        self.assertEqual(expanded, "11 March 1952")

    def test_timel(self):
        from datetime import datetime, timezone

        self.wtp.start_page("")
        expanded = self.wtp.expand("{{#timel:c}}")
        time = datetime.fromisoformat(expanded)
        delta = datetime.now(timezone.utc) - time
        self.assertLess(abs(delta.total_seconds()), 1)

    def test_rel2abs(self):
        # https://www.mediawiki.org/wiki/Help:Extension:ParserFunctions##rel2abs
        self.wtp.start_page("test")
        test_cases = (
            (
                "{{#rel2abs: /quok | Help:Foo/bar/baz }}",
                "Help:Foo/bar/baz/quok",
            ),
            (
                "{{#rel2abs: ./quok | Help:Foo/bar/baz }}",
                "Help:Foo/bar/baz/quok",
            ),
            ("{{#rel2abs: ../quok | Help:Foo/bar/baz }}", "Help:Foo/bar/quok"),
            ("{{#rel2abs: ../. | Help:Foo/bar/baz }}", "Help:Foo/bar"),
            (
                "{{#rel2abs: ../quok/. | Help:Foo/bar/baz }}",
                "Help:Foo/bar/quok",
            ),
            ("{{#rel2abs: ../../quok | Help:Foo/bar/baz }}", "Help:Foo/quok"),
            ("{{#rel2abs: ../../../quok | Help:Foo/bar/baz }}", "quok"),
            ("{{#rel2abs: b }}", "b"),
            ("{{#rel2abs: /b }}", "test/b"),
        )
        for wikitext, result in test_cases:
            with self.subTest(wikitext=wikitext, result=result):
                self.assertEqual(self.wtp.expand(wikitext), result)

    def test_ns_empty_str(self):
        # https://ru.wiktionary.org/wiki/Шаблон:--lang--
        self.wtp.start_page("test")
        self.assertEqual(self.wtp.expand("{{ns:0}}"), "")
        self.assertEqual(self.wtp.expand("{{ns:}}"), "")

    def test_int(self):
        # https://nl.wiktionary.org/wiki/Module:ISOdate
        self.wtp.start_page("test")
        self.wtp.project = "wiktionary"
        self.wtp.lang_code = "nl"
        self.assertEqual(self.wtp.expand("{{int:lang}}"), "nl")
        self.wtp.project = "wikipedia"
        self.assertEqual(self.wtp.expand("{{int:lang}}"), "⧼lang⧽")
        self.assertEqual(self.wtp.expand("{{int:}}"), "[[:Template:int:]]")
