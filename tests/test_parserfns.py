from unittest import TestCase


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
