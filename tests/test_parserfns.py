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
