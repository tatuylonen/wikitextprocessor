# WikiMedia dump file parser for Wiktionary, Wikipedia, and other projects.
#
# Copyright (c) 2018-2020 Tatu Ylonen.  See file LICENSE and https://ylonen.org

import re
import bz2
import json
import html
import traceback
import subprocess
import multiprocessing
from lxml import etree
from .wiktlangs import wiktionary_languages
from .page import parse_page
from .config import WiktionaryConfig

# These XML tags are ignored when parsing.
ignore_xml_tags = set(["sha1", "comment", "username", "timestamp",
                       "sitename", "dbname", "base", "generator", "case",
                       "ns", "restrictions", "contributor", "username",
                       "minor", "parentid", "namespaces", "revision",
                       "siteinfo", "mediawiki",
                       "id", "revision", "namespace", "format",
                       # "model",
])

# Other tags are ignored inside these tags.
xml_stack_ignore = ("contributor",)


class WiktionaryTarget(object):
    """This class is used for XML parsing the Wiktionary dump file."""

    __slots__ = (
        "capture_cb",
        "config",
        "tag",
        "stack",
        "stack_ignore",
        "text",
        "title",
        "redirect",
        "model",
        "aborted",
        "data",
        "args",
        "buf",
        "ofs",
    )

    def __init__(self, config, capture_cb):
        assert isinstance(config, WiktionaryConfig)
        assert capture_cb is None or callable(capture_cb)
        self.capture_cb = capture_cb
        self.config = config
        self.tag = None
        self.stack = []
        self.stack_ignore = False
        self.text = None
        self.title = None
        self.redirect = None
        self.model = None
        self.aborted = False
        self.data = []
        self.args = b""

tag_re = re.compile(
    rb"""(?s)<!--[^\0]*?-->|"""
    rb"""<([^>\s]+)"""
    rb"""(\s+[^"'>/=\s]+\b(\s*=\s*("[^"]*"|'[^']*'|[^ \t\n"'`=<>]*))?)*?"""
    rb"""\s*(/\s*)?>""")

arg_re = re.compile(
    rb"""([^"'>/=\s]+)(\s*=\s*("[^"]*"|'[^']*'|[^ \t\n"'`=<>]*))?"""
)

def make_article_iter(f, ctx, config):
    words = []

    def word_cb(data):
        words.append(data)

    ctx.buf = b""
    ctx.ofs = 0

    def handle_start(tag, args):
        """This is called whenever an XML start tag is encountered."""
        assert isinstance(tag, str)
        assert isinstance(args, bytes)
        ctx.args = args
        ctx.tag = tag
        ctx.stack.append(tag)
        ctx.data = []
        if tag == "page":
            ctx.text = None
            ctx.title = None
            ctx.redirect = None
            ctx.model = None
        elif tag in xml_stack_ignore:
            ctx.stack_ignore = True

    def parse_attrs(args):
        attrs = {}
        for m in re.finditer(arg_re, args):
            name = m.group(1).decode("utf-8")
            if m.group(2):
                value = m.group(3).decode("utf-8")
            else:
                value = ""
            if value.startswith("'") or value.startswith('"'):
                value = value[1:-1]
            attrs[name] = value
        return attrs

    def handle_end(tag):
        """This function is called whenever an XML end tag is encountered."""
        ptag = ctx.stack.pop()
        if ptag in xml_stack_ignore:
            ctx.stack_ignore = False
        if tag in ignore_xml_tags or ctx.stack_ignore:
            return None

        data = b"".join(ctx.data)
        data = data.decode("utf-8")
        ctx.data = []

        if tag == "title":
            ctx.title = data
        elif tag == "text":
            ctx.text = data
        elif tag == "redirect":
            attrs = parse_attrs(ctx.args)
            ctx.redirect = attrs.get("title")
        elif tag == "page":
            title = ctx.title
            ctx.config.num_pages += 1

            # If a capture callback has been provided and returns False,
            # skip this page.
            if ctx.capture_cb and not ctx.capture_cb(title, ctx.text):
                return None

            if ctx.redirect:
                if ctx.config.capture_redirects:
                    data = {"redirect": ctx.redirect, "title": title}
                    return data

            # Parse the page, and call ``word_cb`` for each captured
            # word.
            data = {"title": title, "text": ctx.text,
                    "model": ctx.model}
            return data
        elif tag == "model":
            ctx.model = data
        else:
            attrs = parse_attrs(ctx.args)
            print("UNSUPPORTED", tag, len(data), attrs)
        return None

    def article_iter():
        try:
            while not ctx.aborted:
                more_data = f.read(64 * 1024)
                if not more_data:
                    rest = ctx.buf[ctx.ofs:]
                    ctx.data.append(rest)
                    break
                ctx.buf = ctx.buf[ctx.ofs:] + more_data
                ctx.ofs = 0
                for m in re.finditer(tag_re, ctx.buf):
                    before = ctx.buf[ctx.ofs:m.start()]
                    if before:
                        ctx.data.append(before)
                    ctx.ofs = m.end()
                    tag = m.group(1)
                    if not tag:
                        continue
                    tag = tag.lower().decode("utf-8")
                    args = m.group(2) or b""
                    close = m.group(5)
                    if tag.startswith("/"):
                        tag = tag[1:]
                        art = handle_end(tag)
                        if art:
                            yield art
                    elif close:
                        handle_start(tag, args)
                        art = handle_end(tag)
                        if art:
                            yield art
                    else:
                        handle_start(tag, args)
        except Exception as e:
            print("GOT EXC", str(e))
            traceback.print_exc()
            raise

    return article_iter()

def make_chunk_iter(f, ctx, config):
    assert isinstance(ctx, WiktionaryTarget)
    assert isinstance(config, WiktionaryConfig)

    chunk_len = 200
    config_kwargs = config.to_kwargs()
    chunk = []
    for art in make_article_iter(f, ctx, config):
        chunk.append(art)
        if len(chunk) >= chunk_len:
            yield [config_kwargs, chunk]
            chunk = []
    if chunk:
        yield [config_kwargs, chunk]


def process_input(ctx, path, config, make_iter, chunk_fn):
    """Processes the entire input once, calling chunk_fn for each chunk.
    A chunk is a list (config_kwargs, data) where ``data`` is a dict
    containing at least "title" and "text" keys.  This returns a list
    of the values returned by ``chunk_fn`` in arbitrary order.  Each return
    value must be json-serializable."""
    assert isinstance(path, str)
    assert isinstance(config, WiktionaryConfig)
    assert callable(make_iter)
    assert callable(chunk_fn)

    # Open the input file, optionally decompressing on the fly (in a parallel
    # process to maximize concurrency).  This requires the ``buffer`` program.
    subp = None
    if path.endswith(".bz2"):
        cmd = "bzcat {} | buffer -m 16M".format(path)
        subp = subprocess.Popen(["/bin/sh", "-c", cmd], stdout=subprocess.PIPE,
                                bufsize=256*1024)
        wikt_f = subp.stdout
    else:
        wikt_f = open(path, "rb", buffering=(256 * 1024))

    # Create an iterator that produces chunks of articles to process.
    iter = make_iter(wikt_f, ctx, config)

    # Process the chunks in parallel and combine results into a list.
    # The order of the resulting values is arbitrary.
    pool = multiprocessing.Pool()
    try:
        results = list(pool.imap_unordered(chunk_fn, iter))
    finally:
        wikt_f.close()
        if subp:
            subp.kill()
            subp.wait()

    return results


def capture_specials_fn(dt):
    """Captures certain special pages that are needed for processing other
    pages."""
    assert isinstance(dt, dict)
    title = dt["title"]
    if "redirect" in dt:
        idx = title.find(":")
        if idx > 3:
            cat = title[:idx]
            rest = title[idx + 1:]
            return [["#redirect", title, dt["redirect"]]]
        return []
    text = dt["text"]
    model = dt["model"]
    #print(title)

    if model in ("css", "javascript", "sanitized-css", "json"):
        return []

    if title.endswith("/documentation"):
        return []

    idx = title.find(":")
    if idx > 3:
        cat = title[:idx]
        rest = title[idx + 1:]
        if "redirect" in dt:
            return [[cat, rest, dt["redirect"]]]
        if cat == "Category":
            return [[cat, rest, text]]
        elif cat == "Module":
            if model == "Scribunto":
                return [["Scribunto", rest, text]]
            return [[cat, rest, text]]
        elif cat == "Template":
            return [[cat, rest, text]]
        elif cat == "Citations":
            return []
        elif cat == "Reconstruction":
            # print("Reconstruction", rest)
            return []
        elif cat == "Appendix":
            # print("Appendix", rest)
            return []
        elif cat == "Rhymes":
            return []
        elif cat == "Wiktionary":
            return []
        elif cat == "Thread":
            return []
        elif cat == "Index":
            return []
        elif cat == "Thesaurus":
            if rest.endswith("/translations"):
                return [["Translations", title[:-len("/translations")], text]]
            return [[cat, title, text]]
        elif cat == "MediaWiki":
            return []
        elif cat == "Concordance":
            return []
        elif cat == "Sign gloss":
            return []
        elif cat == "Help":
            return []
        elif cat == "File":
            return []

    if model == "Scribunto":
        print("Unexpected Scribunto:", title)
        return []

    if title.endswith("/translations"):
        return [["Translations", title[:-len("/translations")], text]]

    return []


def capture_chunk_fn(chunk):
    assert isinstance(chunk, (list, tuple)) and len(chunk) == 2
    lst = []
    for dt in chunk[1]:
        lst.extend(capture_specials_fn(dt))
    return lst


def article_fn(config, data):
    assert isinstance(config, WiktionaryConfig)
    assert isinstance(data, dict)
    if "redirect" in data:
        return [data]
    title = data["title"]
    text = data["text"]
    model = data["model"]

    # Skip code pages here
    if model in ("css", "sanitized-css", "javascript",
                 "Scribunto", "json"):
        return []

    # Skip pages with certain prefixes
    idx = title.find(":")
    if idx > 3:
        cat = title[:idx]
        if cat in ("Category",
                   "Module",
                   "Template",
                   "Citations",
                   "Reconstruction",
                   "Appendix",
                   "Rhymes",
                   "Wiktionary",
                   "Thread",
                   "Index",
                   "Thesaurus",
                   "MediaWiki",
                   "Concordance",
                   "Sign gloss",
                   "Help",
                   "File"):
            return []

    # Skip special translation pages (these are handled in a separate pass)
    if title.endswith("/translations"):
        return []

    # Decode entities.  This assumes only HTML entities used in Wiktionary XML.
    text = html.unescape(text)

    # Decode the page.
    return parse_page(title, text, config)


def article_chunk_fn(chunk):
    assert isinstance(chunk, (list, tuple)) and len(chunk) == 2
    config_kwargs = chunk[0]
    config = WiktionaryConfig(**config_kwargs)
    lst = []
    for data in chunk[1]:
        lst.extend(article_fn(config, data))
    stats = config.to_return()
    return stats, lst


def process_dump(ctx, path, page_handler):
    """Parses a WikiMedia dump file ``path`` (which should point
    to a "<project>-<date>-pages-articles.xml.bz2" file.  This
    calls ``page_handler(title, page)`` for each raw page.  This works in
    two phases - in the first phase this calls ctx.collect_specials() for
    each page to collect raw pages, especially templates and Lua modules.
    Then this goes over the articles a second time, calling page_handler
    for each page (this automatically calls ctx.start_page(title) for
    each page before calling page_handler).  The page_handler will be called
    in parallel using the multiprocessing package, and thus it cannot
    save data in ``ctx`` or global variables.  It can only return its results.
    This function will return a list containing all the results returned by
    page_handler (in arbirary order)."""
    assert isinstance(path, str)
    assert callable(page_handler)

    # Run Phase 1 in a single thread; this mostly just extracts pages into
    # a temporary file.
    print("First pass - extracting macros and certain special pages")
    process_input(ctx, path, phase1_page_handler)

    def phase2_handler(title):
        data = ctx.read_by_title(title)
        assert data
        XXX


    # For Phase 2, process pages in parallel
    pool = multiprocessing.Pool()
    lst = []
    for ret in pool.imap_unordered(phase2_handler,
                                   [x[0] for x in ctx.page_seq]):
        lst.append(ret)
        if len(lst) % 1000 == 0:
            print("  ... {}/{} pages ({:.1%}) processed"
                  .format(len(lst), len(ctx.page_seq),
                          len(lst) / len(ctx.page_seq)))

    return lst
