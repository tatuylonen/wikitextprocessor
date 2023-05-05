import unittest
import collections
from wikitextprocessor import Wtp
import platform


def page_cb(page):
    # Note: this may be called in a separate thread and thus cannot
    # update external variables
    return page.title, page.redirect_to


class LongTests(unittest.TestCase):

    def runonce(self, num_threads):
        # Just parse through the data and make sure that we find some words
        path = "tests/test-pages-articles.xml.bz2"
        print("Parsing test data")
        ctx = Wtp(num_threads=num_threads)
        ret = ctx.process(path, page_cb, {0, 4, 10, 14, 100, 110, 118, 828})
        titles = collections.defaultdict(int)
        redirects = collections.defaultdict(int)
        for title, redirect_to in ret:
            titles[title] += 1
            if redirect_to is not None:
                redirects[redirect_to] += 1

        print("Test data parsing complete")
        assert sum(redirects.values()) > 0
        assert len(titles) > 100
        assert all(x == 1 for x in titles.values())
        assert len(redirects) > 1

    def test_long_singlethread(self):
        self.runonce(1)

    @unittest.skipIf(platform.system() in ["Darwin", "Windows"], "Multiprocess only works on Linux")
    def test_long_twothread(self):
        self.runonce(2)

    @unittest.skipIf(platform.system() in ["Darwin", "Windows"], "Multiprocess only works on Linux")
    def test_long_multiprocessing(self):
        self.runonce(None)
