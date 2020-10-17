import unittest
import collections
from wikitextprocessor import Wtp

class LongTests(unittest.TestCase):

    def test_long(self):
        # Just parse through the data and make sure that we find some words
        # This takes about 0.5 minutes.

        titles = collections.defaultdict(int)
        redirects = collections.defaultdict(int)
        num_redirects = 0

        def page_cb(model, title, text):
            nonlocal num_redirects
            print("page_cb:", model, title)
            assert model in ("wikitext", "redirect", "Scribunto")
            if model == "redirect":
                titles[title] += 1
                redirects[text] += 1
                num_redirects += 1
                return
            titles[title] += 1
            return "A"

        path = "tests/test-pages-articles.xml.bz2"
        print("Parsing test data")
        ctx = Wtp()
        ret = ctx.process(path, page_cb)
        print("Test data parsing complete")
        assert num_redirects > 0
        assert len(titles) > 100
        assert all(x == 1 for x in titles.values())
        assert len(redirects) > 1
