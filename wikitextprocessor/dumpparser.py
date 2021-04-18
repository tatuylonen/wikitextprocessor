# WikiMedia dump file parser for Wiktionary, Wikipedia, and other projects.
#
# Copyright (c) 2018-2021 Tatu Ylonen.  See file LICENSE and https://ylonen.org

import re
import sys
import bz2
import json
import html
import traceback
import subprocess

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


class DumpParser(object):
    """This class is used for XML parsing the MediaWiki dump file."""

    __slots__ = (
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

    def __init__(self):
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

def make_iter(f):
    dp = DumpParser()
    dp.buf = b""
    dp.ofs = 0

    def handle_start(tag, args):
        """This is called whenever an XML start tag is encountered."""
        assert isinstance(tag, str)
        assert isinstance(args, bytes)
        dp.args = args
        dp.tag = tag
        dp.stack.append(tag)
        dp.data = []
        if tag == "page":
            dp.text = None
            dp.title = None
            dp.redirect = None
            dp.model = None
        elif tag in xml_stack_ignore:
            dp.stack_ignore = True

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
        ptag = dp.stack.pop()
        if ptag in xml_stack_ignore:
            dp.stack_ignore = False
        if tag in ignore_xml_tags or dp.stack_ignore:
            return None

        data = b"".join(dp.data)
        data = data.decode("utf-8")
        dp.data = []

        if tag == "title":
            dp.title = data
        elif tag == "text":
            dp.text = data
        elif tag == "redirect":
            attrs = parse_attrs(dp.args)
            dp.redirect = attrs.get("title")
        elif tag == "page":
            if dp.redirect:
                return "redirect", dp.title, dp.redirect
            return dp.model, dp.title, dp.text
        elif tag == "model":
            dp.model = data
        else:
            attrs = parse_attrs(dp.args)
            print("UNSUPPORTED", tag, len(data), attrs)
        return None

    def article_iter():
        try:
            while not dp.aborted:
                more_data = f.read(64 * 1024)
                if not more_data:
                    rest = dp.buf[dp.ofs:]
                    dp.data.append(rest)
                    break
                dp.buf = dp.buf[dp.ofs:] + more_data
                dp.ofs = 0
                for m in re.finditer(tag_re, dp.buf):
                    before = dp.buf[dp.ofs:m.start()]
                    if before:
                        dp.data.append(before)
                    dp.ofs = m.end()
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
            print("GOT EXCEPTION", str(e))
            traceback.print_exc()
            raise

    return article_iter()


def process_input(path, page_cb):
    """Processes the entire input once, calling chunk_fn for each chunk.
    A chunk is a list of data, where ``data`` is a dict
    containing at least "title" and "text" keys.  This returns a list
    of the values returned by ``chunk_fn`` in arbitrary order.  Each return
    value must be json-serializable."""
    assert isinstance(path, str)
    assert callable(page_cb)

    # Open the input file, optionally decompressing on the fly (in a parallel
    # process to maximize concurrency).  This requires the ``buffer`` program.
    subp = None
    if path.endswith(".bz2"):
        # cmd = "bzcat {} | buffer -m 16M".format(path)
        cmd = "bzcat {}".format(path)
        subp = subprocess.Popen(["/bin/sh", "-c", cmd], stdout=subprocess.PIPE,
                                bufsize=256*1024)
        wikt_f = subp.stdout
    else:
        wikt_f = open(path, "rb", buffering=(256 * 1024))

    # Create an iterator that produces chunks of articles to process.
    lst = []
    for model, title, text in make_iter(wikt_f):
        title = html.unescape(title)
        text = html.unescape(text)
        ret = page_cb(model, title, text)
        if ret is not None:
            lst.append(ret)

    return lst


def process_dump(ctx, path, page_handler):
    """Parses a WikiMedia dump file ``path`` (which should point to a
    "<project>-<date>-pages-articles.xml.bz2" file.  This calls
    ``page_handler(title, page)`` for each raw page.  This implements
    the first phase of processing a dump - copying it to a temporary
    file with some preprocessing.  The Wtp.reprocess() must then be
    called to actually process the data."""
    assert isinstance(path, str)
    assert callable(page_handler)

    def phase1_page_handler(model, title, text):
        """Handler for pages in Phase 1, for extracting special pages and saving
        data about all pages."""
        ctx.add_page(model, title, text)

    # Run Phase 1 in a single thread; this mostly just extracts pages into
    # a temporary file.
    process_input(path, phase1_page_handler)

    # Analyze which templates should be expanded before parsing
    if not ctx.quiet:
        print("Analyzing which templates should be expanded before parsing")
        sys.stdout.flush()
    ctx.analyze_templates()

# XXX parse <namespaces> and use that in both Python and Lua code

# XXX parse <case> to determine whether titles are case-sensitive
