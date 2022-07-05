# Definition of the processing context for Wikitext processing, and code for
# expanding templates, parser functions, and Lua macros.
#
# Copyright (c) 2020-2022 Tatu Ylonen.  See file LICENSE and https://ylonen.org

import os
import re
import sys
import html
import time
import pickle
import datetime
import tempfile
import traceback
import collections
import urllib.parse
import html.entities
import multiprocessing
from .parserfns import (PARSER_FUNCTIONS, call_parser_function, tag_fn)
from .wikihtml import ALLOWED_HTML_TAGS
from .luaexec import call_lua_sandbox
from .parser import parse_encoded, NodeKind
from .common import (MAGIC_FIRST, MAGIC_LAST, MAX_MAGICS, MAGIC_NOWIKI_CHAR)
from .dumpparser import process_dump
from .node_expand import to_wikitext, to_html, to_text

# Set of HTML tags that need an explicit end tag.
PAIRED_HTML_TAGS = set(k for k, v in ALLOWED_HTML_TAGS.items()
                       if not v.get("no-end-tag"))

# Warning: this function is not re-entrant.  We store ctx and page_handler
# in global variables during dump processing, because they may not be
# pickleable.
_global_ctx = None
_global_page_handler = None
_global_page_autoload = True

def phase2_page_handler(dt):
    """Helper function for calling the Phase2 page handler (see
    reprocess()).  This is a global function in order to make this
    pickleable.  The implication is that process() and reprocess() are not
    re-entrant (i.e., cannot be called safely from multiple threads or
    recursively)"""
    ctx = _global_ctx
    autoload = _global_page_autoload
    model, title = dt
    start_t = time.time()

    # XXX Enable this to debug why extraction hangs.  This writes the path
    # of each file being processed into /tmp/wiktextract-*.  Once a hang
    # has been observed, these files contain page(s) that hang.  They should
    # be checked before aborting the process, as an interrupt might delete
    # them.
    debug_hangs = True
    try:
        debug_path = "/tmp/wiktextract-{}".format(os.getpid())
        with open(debug_path, "w") as f:
            f.write(title + "\n")

        ctx.start_page(title)
        if autoload:
            data = ctx.read_by_title(title)
            assert isinstance(data, str)
        else:
            data = None
        try:
            ret = _global_page_handler(model, title, data)
            return True, title, start_t, ret
        except Exception as e:
            lst = traceback.format_exception(type(e), value=e,
                                             tb=e.__traceback__)
            msg = ("=== EXCEPTION while parsing page \"{}\":\n".format(title) +
                   "".join(lst))
            return False, title, start_t, msg

    finally:
        if debug_hangs:
            os.remove(debug_path)


class Wtp(object):
    """Context used for processing wikitext and for expanding templates,
    parser functions and Lua macros.  The indended usage pattern is to
    initialize this context once (this holds template and module definitions),
    and then using the context for processing many pages."""
    __slots__ = (
        "buf",		 # Buffer for reading/writing tmp_file
        "buf_ofs",	 # Offset into buf
        "buf_used",	 # Number of bytes in the buffer when reading
        "buf_size",      # Allocated size of buf, in bytes
        "cache_file",	 # Prefix to cache files (instead of temporary file)
        "cache_file_old",  # Using pre-existing cache file
        "cookies",	 # Mapping from magic cookie -> expansion data
        "debugs",	 # List of debug messages (cleared for each new page)
        "errors",	 # List of error messages (cleared for each new page)
        "fullpage",	 # The unprocessed text of the current page (or None)
        "lua",		 # Lua runtime or None if not yet initialized
        "lua_depth",     # Recursion depth in Lua calls
        "lua_invoke",	 # Lua function used to invoke a Lua module
        "lua_reset_env", # Function to reset Lua environment
        "lua_path",	 # Path to Lua modules
        "modules",	 # Lua code for defined Lua modules
        "need_pre_expand",  # Set of template names to be expanded before parse
        "num_threads",   # Number of parallel threads to use
        "page_contents",  # Full content for selected pages (e.g., Thesaurus)
        "page_seq",	 # All content pages (title, model, ofs, len) in order
        "quiet",	 # If True, don't print any messages during processing
        "redirects",	 # Redirects in the wikimedia project
        "rev_ht",	 # Mapping from text to magic cookie
        "expand_stack",	 # Saved stack before calling Lua function
        "templates",     # dict temlate name -> definition
        "title",         # current page title
        "tmp_file",	 # Temporary file used to store templates and pages
        "tmp_ofs",	 # Next write offset
        "transient_pages",     # Unsaved pages added by extraction application
        "transient_templates", # Unsaved templates added by application
        "warnings",	 # List of warning messages (cleared for each new page)
        # Data for parsing
        "beginning_of_line", # Parser at beginning of line
        "wsp_beginning_of_line",  # Parser at beginning of line + whitespace
        "linenum",	 # Current line number
        "pre_parse",	 # XXX is pre-parsing still needed?
        "parser_stack",	 # Parser stack
        "section",	 # Section within page, for error messages
        "subsection",    # Subsection within page, for error messages
        "suppress_special",  # XXX never set to True???
    )
    def __init__(self, num_threads=None, cache_file=None, quiet=False):
        assert num_threads is None or isinstance(num_threads, int)
        assert cache_file is None or isinstance(cache_file, str)
        assert quiet in (True, False)
        if num_threads is None:
            import platform
            if platform.system() in ("Windows", "Darwin"):
                # Default num_threads to 1 on Windows and MacOS, as they
                # apparently don't use fork() for multiprocessing.Pool()
                num_threads = 1
        self.buf_ofs = 0
        self.buf_size = 4 * 1024 * 1024
        self.buf = bytearray(self.buf_size)
        self.cache_file = cache_file
        self.cache_file_old = False
        self.cookies = []
        self.errors = []
        self.warnings = []
        self.debugs = []
        self.section = None
        self.subsection = None
        self.lua = None
        self.lua_invoke = None
        self.lua_reset_env = None
        self.lua_depth = 0
        self.quiet = quiet
        self.rev_ht = {}
        self.expand_stack = []
        self.parser_stack = None
        self.num_threads = num_threads
        self.transient_pages = {}
        self.transient_templates = {}
        # Some predefined templates
        self.need_pre_expand = None

        # Open cache file if it exists; otherwise create new cache file or
        # temporary file and reset saved pages.
        self.tmp_file = None
        if self.cache_file:
            try:
                # Load self.templates, self.page_contents, self.page_seq,
                # self.redirects
                with open(self.cache_file + ".pickle", "rb") as f:
                    dt = pickle.load(f)
                version, dt = dt
                if version == 1:
                    # Cache file version is compatible
                    self.tmp_file = open(self.cache_file, "rb", buffering=0)
                    self.page_contents, self.page_seq, self.redirects, \
                        self.templates, self.need_pre_expand = dt
                    self.need_pre_expand = set(self.need_pre_expand)
                    self.cache_file_old = True
            except (FileNotFoundError, EOFError):
                pass
        if self.tmp_file is None:
            self._reset_pages()
        self.tmp_ofs = 0
        self.buf_ofs = 0

    def _reset_pages(self):
        """Resets any stored pages and gets ready to receive more pages."""
        self.tmp_file = None
        self.page_contents = {}
        self.page_seq = []
        self.redirects = {}
        self.templates = {}
        self.need_pre_expand = None
        self.cache_file_old = False
        # Add predefined templates
        self.templates["!"] = "|"
        self.templates["!-"] = "|-"
        self.templates[self._canonicalize_template_name("((")] = \
            "&lbrace;&lbrace;"  # {{((}}
        self.templates[self._canonicalize_template_name("))")] = \
            "&rbrace;&rbrace;"  # {{))}}
        # Create cache file or temporary file
        if self.cache_file:
            # Create new cache file
            try:
                os.remove(self.cache_file)
            except FileNotFoundError:
                pass
            try:
                os.remove(self.cache_file + ".pickle")
            except FileNotFoundError:
                pass
            self.tmp_file = open(self.cache_file, "w+b", buffering=0)
        else:
            # Create temporary file
            self.tmp_file = tempfile.TemporaryFile(mode="w+b", buffering=0)

    def _fmt_errmsg(self, kind, msg, trace):
        assert isinstance(kind, str)
        assert isinstance(msg, str)
        assert isinstance(trace, (str, type(None)))
        loc = self.title
        if self.section:
            loc += "/" + self.section
        if self.subsection:
            loc += "/" + self.subsection
        if self.expand_stack:
            msg += " at {}".format(self.expand_stack)
        if self.parser_stack:
            titles = []
            for node in self.parser_stack:
                if node.kind in (NodeKind.LEVEL2, NodeKind.LEVEL3,
                                 NodeKind.LEVEL4, NodeKind.LEVEL5,
                                 NodeKind.LEVEL6):
                    if not node.args:
                        continue
                    lst = map(lambda x: x if isinstance(x, str) else "???",
                              node.args[0])
                    title = "".join(lst)
                    titles.append(title.strip())
            msg += " parsing "  + "/".join(titles)
        if trace:
            msg += "\n" + trace
        print("{}: {}: {}".format(loc, kind,msg))
        sys.stdout.flush()

    def error(self, msg, trace=None):
        """Prints an error message to stdout.  The error is also saved in
        self.errors."""
        assert isinstance(msg, str)
        assert isinstance(trace, (str, type(None)))
        self.errors.append({"msg": msg, "trace": trace,
                            "title": self.title,
                            "section": self.section,
                            "subsection": self.subsection,
                            "path": tuple(self.expand_stack)})
        self._fmt_errmsg("ERROR", msg, trace)

    def warning(self, msg, trace=None):
        """Prints a warning message to stdout.  The error is also saved in
        self.warnings."""
        assert isinstance(msg, str)
        assert isinstance(trace, (str, type(None)))
        self.warnings.append({"msg": msg, "trace": trace,
                              "title": self.title,
                              "section": self.section,
                              "subsection": self.subsection,
                              "path": tuple(self.expand_stack)})
        self._fmt_errmsg("WARNING", msg, trace)

    def debug(self, msg, trace=None):
        """Prints a debug message to stdout.  The error is also saved in
        self.debug."""
        assert isinstance(msg, str)
        assert isinstance(trace, (str, type(None)))
        self.debugs.append({"msg": msg, "trace": trace,
                            "title": self.title,
                            "section": self.section,
                            "subsection": self.subsection,
                            "path": tuple(self.expand_stack)})
        self._fmt_errmsg("DEBUG", msg, trace)

    def to_return(self):
        """Returns a dictionary with errors, warnings, and debug messages
        from the context.  Note that the values are reset whenever starting
        processing a new word.  The value returned by this function is
        JSON-compatible and can easily be returned by a paralle process."""
        return {
            "errors": self.errors,
            "warnings": self.warnings,
            "debugs": self.debugs,
        }

    def _canonicalize_template_name(self, name):
        """Canonicalizes a template name by making its first character
        uppercase and replacing underscores by spaces and sequences of
        whitespace by a single whitespace."""
        assert isinstance(name, str)
        if name.lower().startswith("template:"):
            name = name[9:]
        name = re.sub(r"_", " ", name)
        name = re.sub(r"\s+", " ", name)
        name = re.sub(r"\(", "%28", name)
        name = re.sub(r"\)", "%29", name)
        name = re.sub(r"&", "%26", name)
        name = re.sub(r"\+", "%2B", name)
        name = name.strip()
        #if name:
        #    name = name[0].upper() + name[1:]
        return name

    def _canonicalize_parserfn_name(self, name):
        """Canonicalizes a parser function name by making its first character
        uppercase and replacing underscores by spaces and sequences of
        whitespace by a single whitespace."""
        assert isinstance(name, str)
        name = re.sub(r"_", " ", name)
        name = re.sub(r"\s+", " ", name)
        name = name.strip()
        if name not in PARSER_FUNCTIONS:
            name = name.lower()  # Parser function names are case-insensitive
        return name

    def _save_value(self, kind, args, nowiki):
        """Saves a value of a particular kind and returns a unique magic
        cookie for it."""
        assert kind in ("T",  # Template {{ ... }}
                        "A",  # Template argument {{{ ... }}}
                        "L",  # link
                        "E",  # external link
                        "N",  # nowiki text
        )
        assert isinstance(args, (list, tuple))
        assert nowiki in (True, False)
        # print("save_value", kind, args, nowiki)
        args = tuple(args)
        v = (kind, args, nowiki)
        if v in self.rev_ht:
            return self.rev_ht[v]
        idx = len(self.cookies)
        if idx >= MAX_MAGICS:
            ctx.error("too many templates, arguments, or parser function calls")
            return ""
        self.cookies.append(v)
        ch = chr(MAGIC_FIRST + idx)
        self.rev_ht[v] = ch
        ret = ch
        return ret

    def _encode(self, text):
        """Encode all templates, template arguments, and parser function calls
        in the text, from innermost to outermost."""

        def vbar_split(v):
            args = list(m.group(1) for m in re.finditer(
                r"(?si)\|((<\s*([-a-zA-z0-9]+)\b[^>]*>[^][{}]*?<\s*/\s*\3\s*>|"
                r"[^|])*)", "|" + v))
            return args

        def repl_arg(m):
            """Replacement function for template arguments."""
            nowiki = m.group(0).find(MAGIC_NOWIKI_CHAR) >= 0
            orig = m.group(1)
            args = vbar_split(orig)
            return self._save_value("A", args, nowiki)

        def repl_arg_err(m):
            """Replacement function for template arguments, with error."""
            nowiki = m.group(0).find(MAGIC_NOWIKI_CHAR) >= 0
            prefix = m.group(1)
            orig = m.group(2)
            args = vbar_split(orig)
            self.debug("heuristically added missing }} to template arg {}"
                         .format(args[0].strip()))
            return prefix + self._save_value("A", args, nowiki)

        def repl_templ(m):
            """Replacement function for templates {{name|...}} and parser
            functions."""
            nowiki = m.group(0).find(MAGIC_NOWIKI_CHAR) >= 0
            v = m.group(1)
            args = vbar_split(v)
            return self._save_value("T", args, nowiki)

        def repl_templ_err(m):
            """Replacement function for templates {{name|...}} and parser
            functions, with error."""
            nowiki = m.group(0).find(MAGIC_NOWIKI_CHAR) >= 0
            prefix = m.group(1)
            v = m.group(2)
            args = vbar_split(v)
            self.debug("heuristically added missing }} to template {}"
                         .format(args[0].strip()))
            return prefix + self._save_value("T", args, nowiki)

        def repl_link(m):
            """Replacement function for links [[...]]."""
            nowiki = m.group(0).find(MAGIC_NOWIKI_CHAR) >= 0
            orig = m.group(1)
            args = vbar_split(orig)
            return self._save_value("L", args, nowiki)

        def repl_extlink(m):
            """Replacement function for external links [...].  This is also
            used to replace bracketed sections, such as [...]."""
            nowiki = m.group(0).find(MAGIC_NOWIKI_CHAR) >= 0
            orig = m.group(1)
            # Extlinks usually separate args by spaces, but this should do no
            # harm here.
            args = vbar_split(orig)
            return self._save_value("E", args, nowiki)

        # Main loop of encoding.  We encode repeatedly, always the innermost
        # template, argument, or parser function call first.  We also encode
        # links as they affect the interpretation of templates.
        # As a preprocessing step, remove comments from the text.
        text = re.sub(r"(?s)<!\s*--.*?--\s*>", "", text)
        while True:
            prev = text
            # Encode template arguments.  We repeat this until there are
            # no more matches, because otherwise we could encode the two
            # innermost braces as a template transclusion.
            while True:
                prev2 = text
                # Encode links.
                while True:
                    text = re.sub(r"(?s)\[" + MAGIC_NOWIKI_CHAR +
                                  r"?\[([^][{}]+)\]" +
                                  MAGIC_NOWIKI_CHAR + r"?\]",
                                  repl_link, text)
                    if text == prev2:
                        break
                    prev2 = text
                # Encode external links.
                text = re.sub(r"(?s)\[([^][{}<>]+)\]", repl_extlink, text)
                # Encode template arguments
                text = re.sub(r"(?s)\{" + MAGIC_NOWIKI_CHAR +
                              r"?\{" + MAGIC_NOWIKI_CHAR +
                              r"?\{(([^{}]|\{\|[^{}]*\|\})*?)\}" +
                              MAGIC_NOWIKI_CHAR + r"?\}" +
                              MAGIC_NOWIKI_CHAR + r"?\}",
                              repl_arg, text)
                if text == prev2:
                    # When everything else has been done, see if we can find
                    # template arguments that have one missing closing bracket.
                    # This is so common in Wiktionary that I'm suspecting it
                    # might be allowed by the MediaWiki parser.
                    # This needs to be done before processing templates, as
                    # otherwise the argument with a missing closing brace would
                    # be interpreted as a template.
                    text = re.sub(r"(?s)([^{])\{" + MAGIC_NOWIKI_CHAR +
                                  r"?\{" + MAGIC_NOWIKI_CHAR +
                                  r"?\{([^{}]*?)\}" +
                                  MAGIC_NOWIKI_CHAR + r"?\}",
                                  repl_arg_err, text)
                    if text != prev2:
                        continue
                    break
            # Replace template invocation
            text = re.sub(r"(?si)\{" + MAGIC_NOWIKI_CHAR +
                          r"?\{(("
                          r"\{\|[^{}]*?\|\}|"
                          r"\}[^{}]|"
                          r"[^{}](\{[^{}|])?"
                          r")+?)\}" +
                          MAGIC_NOWIKI_CHAR + r"?\}",
                          repl_templ, text)
            # We keep looping until there is no change during the iteration
            if text == prev:
                # When everything else has been done, see if we can find
                # template calls that have one missing closing bracket.
                # This is so common in Wiktionary that I'm suspecting it
                # might be allowed by the MediaWiki parser.  We must allow
                # tables {| ... |} inside these.
                text = re.sub(r"(?s)([^{])\{" + MAGIC_NOWIKI_CHAR +
                              r"?\{(([^{}]|\{\|[^{}]*\|\}|\}[^{}])+?)\}",
                              repl_templ_err, text)
                if text != prev:
                    continue
                # Replace remaining brackets and braces by corresponding
                # character entities
                # XXX
                break
            prev = text
        # Replace any remaining braces etc by corresponding character entities
        #text = re.sub(r"\{([&|])", r"&lbrace;\1", text)
        #text = re.sub(r"\{([&|])", r"&lbrace;\1", text)
        #text = re.sub(r"[^|]\}", r"\1&rbrace;", text)
        #text = re.sub(r"[^|]\}", r"\1&rbrace;", text)
        #text = re.sub(r"\|", "&vert;", text)
        return text

    def _template_to_body(self, title, text):
        """Extracts the portion to be transcluded from a template body.  This
        returns an str."""
        assert isinstance(title, str)
        assert isinstance(text, str)
        # Remove all comments
        text = re.sub(r"(?s)<!\s*--.*?--\s*>", "", text)
        # Remove all text inside <noinclude> ... </noinclude>
        text = re.sub(r"(?is)<\s*noinclude\s*>.*?<\s*/\s*noinclude\s*>",
                      "", text)
        # Handle <noinclude> without matching </noinclude> by removing the
        # rest of the file
        text = re.sub(r"(?is)<\s*noinclude\s*>.*", "", text)
        text = re.sub(r"(?is)<\s*noinclude\s*/\s*>", "", text)
        # Apparently unclosed <!-- at the end of a template body is ignored
        text = re.sub(r"(?s)<!\s*--.*", "", text)
        # <onlyinclude> tags, if present, include the only text that will be
        # transcluded.  All other text is ignored.
        onlys = list(re.finditer(r"(?is)<\s*onlyinclude\s*>(.*?)"
                                 r"<\s*/\s*onlyinclude\s*>|"
                                 r"<\s*onlyinclude\s*/\s*>",
                                 text))
        if onlys:
            text = "".join(m.group(1) or "" for m in onlys)
        # Remove <includeonly>.  They mark text that is not visible on the page
        # itself but is included in transclusion.  Also text outside these tags
        # is included in transclusion.
        text = re.sub(r"(?is)<\s*(/\s*)?includeonly\s*(/\s*)?>", "", text)
        return text

    def add_page(self, model, title, text, transient=False):
        """Collects information about the page.  For templates and modules,
        this keeps the content in memory.  For other pages, this saves the
        content in a temporary file so that it can be accessed later.  There
        must be enough space on the volume containing the temporary file
        to store the entire contents of the uncompressed WikiMedia dump.
        The content is saved because it is common for Wiktionary Lua macros
        to access content from arbitrary pages.  Furthermore, this way we
        only need to decompress and parse the dump file once.  ``model``
        is "wikitext" for normal pages, "redirect" for redirects (in which
        case ``text`` is the page pointed to), or "Scribunto" for Lua code;
        other values may also be encountered.  If ``transient`` is True, then
        this page will not be saved but will replace any saved page.  This can
        be used, for example, to add Lua code for data extraction, or for
        debugging Lua modules."""
        assert isinstance(model, str)
        assert isinstance(title, str)
        assert isinstance(text, str)
        assert transient in (True, False)

        if transient:
            self.transient_pages[title] = (title, model, text)
            if (title.startswith("Template:") and
                not title.endswith("/documentation") and
                not title.endswith("/testcases")):
                name = self._canonicalize_template_name(title)
                body = self._template_to_body(title, text)
                self.transient_templates[name] = body
            return

        # If we have previously analyzed pages and this is called again,
        # reset all previously saved pages (e.g., in case we are to update
        # existing cache file).
        if self.need_pre_expand is not None:
            self._reset_pages()

        # Save the page in our temporary file and metadata in memory
        rawtext = text.encode("utf-8")
        if self.buf_ofs + len(rawtext) > self.buf_size:
            bufview = memoryview(self.buf)[0: self.buf_ofs]
            self.tmp_file.write(bufview)
            self.buf_ofs = 0
        ofs = self.tmp_ofs
        self.tmp_ofs += len(rawtext)
        if len(rawtext) >= self.buf_ofs:
            self.tmp_file.write(rawtext)
        else:
            self.buf[self.buf_ofs: self.buf_ofs + len(rawtext)] = rawtext
        # XXX should we canonicalize title in page_contents
        self.page_contents[title] = (title, model, ofs, len(rawtext))
        self.page_seq.append((model, title))
        if not self.quiet and len(self.page_seq) % 10000 == 0:
            print("  ... {} raw pages collected"
                  .format(len(self.page_seq)))
            sys.stdout.flush()

        if model == "redirect":
            self.redirects[title] = text
            return
        if not title.startswith("Template:"):
            return
        if title.endswith("/documentation"):
            return
        if title.endswith("/testcases"):
            return

        # It is a template
        name = self._canonicalize_template_name(title)
        body = self._template_to_body(title, text)
        assert isinstance(body, str)
        self.templates[name] = body

    def _analyze_template(self, name, body):
        """Analyzes a template body and returns a set of the canonicalized
        names of all other templates it calls and a boolean that is True
        if it should be pre-expanded before final parsing and False if it
        need not be pre-expanded.  The pre-expanded flag is determined
        based on that body only; the caller should propagate it to
        templates that include the given template.  This does not work for
        template and template function calls where the name is generated by
        other expansions."""
        assert isinstance(body, str)
        included_templates = set()
        pre_expand = False

        # Determine if the template starts with a list item
        # XXX should we expand other templates that produce list items???
        contains_list = re.match(r"(?s)^[#*;:]", body) is not None

        # Remove paired tables
        prev = body
        while True:
            unpaired_text = re.sub(
                r"(?s)(^|\n)\{\|([^\n]|\n+[^{|]|\n+\|[^}]|\n+\{[^|])*?\n+\|\}",
                r"", prev)
            if unpaired_text == prev:
                break
            prev = unpaired_text
        #print("unpaired_text {!r}".format(unpaired_text))

        # Determine if the template contains an unpaired table
        contains_unpaired_table = re.search(r"(?s)(^|\n)(\{\||\|\})",
                                            unpaired_text) is not None

        # Determine if the template contains table element tokens
        # outside paired table start/end.  We only try to look for
        # these outside templates, as it is common to write each
        # template argument on its own line starting with a "|".
        outside = unpaired_text
        while True:
            #print("=== OUTSIDE ITER")
            prev = outside
            while True:
                newt = re.sub(r"(?s)\{\{\{([^{}]|\}[^}]|\}\}[^}])*?\}\}\}",
                              "", prev)
                if newt == prev:
                    break
                prev = newt
            #print("After arg elim: {!r}".format(newt))
            newt = re.sub(r"(?s)\{\{([^{}]|\}[^}])*?\}\}", "", newt)
            #print("After templ elim: {!r}".format(newt))
            if newt == outside:
                break
            outside = newt
        # For now, we'll ignore !! and || as well as |
        m = re.search(r"(?s)(^|\n)(\|\+|\|-|\!)", outside)
        contains_table_element = m is not None
        # if contains_table_element:
        #     print("contains_table_element {!r} at {}"
        #           .format(m.group(0), m.start()))
        #     print("... {!r} ...".format(outside[m.start() - 10:m.end() + 10]))
        #     print(repr(outside))

        # Check for unpaired HTML tags
        tag_cnts = collections.defaultdict(int)
        for m in re.finditer(r"(?si)<\s*(/\s*)?({})\b\s*[^>]*(/\s*)?>"
                             r"".format("|".join(PAIRED_HTML_TAGS)), outside):
            start_slash = m.group(1)
            tagname = m.group(2)
            end_slash = m.group(3)
            if start_slash:
                tag_cnts[tagname] -= 1
            elif not end_slash:
                tag_cnts[tagname] += 1
        contains_unbalanced_html = any(v != 0 for v in tag_cnts.values())
        # if contains_unbalanced_html:
        #     print(name, "UNBALANCED HTML")
        #     for k, v in tag_cnts.items():
        #         if v != 0:
        #             print("  {} {}".format(v, k))

        # Determine whether this template should be pre-expanded
        pre_expand = (contains_list or contains_unpaired_table or
                      contains_table_element or contains_unbalanced_html)

        # if pre_expand:
        #     print(name,
        #           {"list": contains_list,
        #            "unpaired_table": contains_unpaired_table,
        #            "table_element": contains_table_element,
        #            "unbalanced_html": contains_unbalanced_html,
        #            "pre_expand": pre_expand,
        #     })

        # Determine which other templates are called from unpaired text.
        # None of the flags we currently gather propagate outside a paired
        # table start/end.
        for m in re.finditer(r"(?s)(^|[^{])(\{\{)?\{\{([^{]*?)(\||\}\})",
                             unpaired_text):
            name = m.group(3)
            name = re.sub(r"(?si)<\s*nowiki\s*/\s*>", "", name)
            name = self._canonicalize_template_name(name)
            if not name:
                continue
            included_templates.add(name)

        return included_templates, pre_expand

    def analyze_templates(self):
        """Analyzes templates to determine which of them might create elements
        essential to parsing Wikitext syntax, such as table start or end
        tags.  Such templates generally need to be expanded before
        parsing the page."""
        self.need_pre_expand = set()
        included_map = collections.defaultdict(set)
        expand_q = []
        for name, body in self.templates.items():
            included_templates, pre_expand = self._analyze_template(name, body)
            for x in included_templates:
                included_map[x].add(name)
            if pre_expand:
                self.need_pre_expand.add(name)
                expand_q.append(name)

        # XXX consider encoding template bodies here (also need to save related
        # cookies).  This could speed up their expansion, where the first
        # operation is to encode them.  (Consider whether cookie numbers from
        # nested template expansions could conflict)

        # Propagate pre_expand from lower-level templates to all templates that
        # refer to them
        while expand_q:
            name = expand_q.pop()
            if name not in included_map:
                continue
            for inc in included_map[name]:
                if inc in self.need_pre_expand:
                    continue
                #print("propagating EXP {} -> {}".format(name, inc))
                self.need_pre_expand.add(inc)
                expand_q.append(name)

        # Copy template definitions to redirects to them
        for k, v in self.redirects.items():
            if not k.startswith("Template:"):
                # print("Unhandled redirect src", k)
                continue
            if not v.startswith("Template:"):
                # print("Unhandled redirect dst", v)
                continue
            k = self._canonicalize_template_name(k)
            v = self._canonicalize_template_name(v)
            if v not in self.templates:
                # print("{} redirects to non-existent template {}".format(k, v))
                continue
            if k in self.templates:
                # print("{} -> {} is redirect but already in templates"
                #       .format(k, v))
                continue
            self.templates[k] = self.templates[v]
            if v in self.need_pre_expand:
                self.need_pre_expand.add(k)

        # Save cache data
        if self.cache_file is not None and not self.cache_file_old:
            with open(self.cache_file + ".pickle", "wb") as f:
                pickle.dump((1, (self.page_contents, self.page_seq,
                                 self.redirects, self.templates,
                                 list(sorted(self.need_pre_expand)))),
                            f)

    def start_page(self, title):
        """Starts a new page for expanding Wikitext.  This saves the title and
        full page source in the context.  Calling this is mandatory
        for each page; expand_wikitext() can then be called multiple
        times for the same page.  This clears the self.errors,
        self.warnings, and self.debugs lists and any current section
        or subsection."""
        assert isinstance(title, str)
        self.title = title
        self.errors = []
        self.warnings = []
        self.debugs = []
        self.section = None
        self.subsection = None
        self.cookies = []
        self.rev_ht = {}
        self.expand_stack = [title]

    def start_section(self, title):
        """Starts processing a new section of the current page.  Calling this
        is optional, but can help provide better error messages.  This clears
        any current subsection."""
        assert title is None or isinstance(title, str)
        self.section = title
        self.subsection = None

    def start_subsection(self, title):
        """Starts processing a new subsection of the current section on the
        current page.  Calling this is optional, but can help provide better
        error messages."""
        assert title is None or isinstance(title, str)
        self.subsection = title

    def _unexpanded_template(self, args, nowiki):
        """Formats an unexpanded template (whose arguments may have been
            partially or fully expanded)."""
        if nowiki:
            return ("&lbrace;&lbrace;" +
                    "&vert;".join(args) +
                    "&rbrace;&rbrace;")
        return "{{" + "|".join(args) + "}}"

    def _unexpanded_arg(self, args, nowiki):
        """Formats an unexpanded template argument reference."""
        if nowiki:
            return ("&lbrace;&lbrace;&lbrace;" +
                    "&vert;".join(args) +
                    "&rbrace;&rbrace;&rbrace;")
        return "{{{" + "|".join(args) + "}}}"

    def _unexpanded_link(self, args, nowiki):
        """Formats an unexpanded link."""
        if nowiki:
            return "&lsqb;&lsqb;" + "&vert;".join(args) + "&rsqb;&rsqb;"
        return "[[" + "|".join(args) + "]]"

    def _unexpanded_extlink(self, args, nowiki):
        """Formats an unexpanded external link."""
        if nowiki:
            return "&lsqb;" + "&vert;".join(args) + "&rsqb;"
        return "[" + "|".join(args) + "]"

    def preprocess_text(self, text):
        """Preprocess the text by handling <nowiki> and comments."""
        assert isinstance(text, str)
        # print("PREPROCESS_TEXT: {!r}".format(text))

        def _nowiki_sub_fn(m):
            """This function escapes the contents of a <nowiki> ... </nowiki>
            pair."""
            text = m.group(1)
            return self._save_value("N", (text,), False)

        text = re.sub(r"(?si)<\s*nowiki\s*>(.*?)<\s*/\s*nowiki\s*>",
                      _nowiki_sub_fn, text)
        text = re.sub(r"(?si)<\s*nowiki\s*/\s*>", MAGIC_NOWIKI_CHAR, text)
        text = re.sub(r"(?s)<!\s*--.*?--\s*>", "", text)
        # print("PREPROCESSED_TEXT: {!r}".format(text))
        return text

    def expand(self, text, parent=None, pre_expand=False,
               template_fn=None, post_template_fn=None,
               templates_to_expand=None,
               expand_parserfns=True, expand_invoke=True, quiet=False,
               timeout=None):
        """Expands templates and parser functions (and optionally Lua macros)
        from ``text`` (which is from page with title ``title``).
        ``templates_to_expand`` should be None to expand all
        templates, or a set or dictionary whose keys are those
        canonicalized template names that should be expanded; if
        ``pre_expand`` is set to True, then only templates needing
        pre-expansion before parsing plus those in
        ``templates_to_expand`` are expanded.  ``template_fn``, if
        given, will be be called as template_fn(name, args_ht) to
        expand templates; if it is not defined or returns None, the
        default expansion will be used (it can also be used to capture
        template arguments).  If ``post_template_fn`` is given, it
        will be called as post_template_fn(name, args_ht, expanded)
        and if it returns other than None, its return value will
        replace the template expansion.  This returns the text with
        the given templates expanded."""
        assert isinstance(text, str)
        assert parent is None or (isinstance(parent, (list, tuple)) and
                                  len(parent) == 2)
        assert pre_expand in (True, False)
        assert template_fn is None or callable(template_fn)
        assert post_template_fn is None or callable(post_template_fn)
        assert isinstance(templates_to_expand, (set, dict, type(None)))
        assert self.title is not None  # start_page() must have been called
        assert quiet in (False, True)
        assert timeout is None or isinstance(timeout, (int, float))

        # Handle <nowiki> in a preprocessing step
        text = self.preprocess_text(text)

        # If requesting to pre_expand, then add templates needing pre-expand
        # to those to be expanded (and don't expand everything).
        if pre_expand:
            if self.need_pre_expand is None:
                if self.cache_file and not self.cache_file_old:
                    raise RuntimeError("You have specified a cache file "
                                       "but have not properly initialized "
                                       "the cache file.")
                raise RuntimeError("analyze_templates() must be run first to "
                                   "determine which templates need pre-expand")
            if templates_to_expand is not None:
                templates_to_expand = (set(templates_to_expand) |
                                       set(self.need_pre_expand))
            else:
                templates_to_expand = self.need_pre_expand

        # Create set or dict of all defined templates
        if self.transient_templates:
            all_templates = (set(self.templates) |
                             set(self.transient_templates))
        else:
            all_templates = self.templates

        # If templates_to_expand is None, then expand all known templates
        if templates_to_expand is None:
            templates_to_expand = all_templates

        def invoke_fn(invoke_args, expander, parent):
            """This is called to expand a #invoke parser function."""
            assert isinstance(invoke_args, (list, tuple))
            assert callable(expander)
            assert isinstance(parent, (tuple, type(None)))
            # print("INVOKE_FN", invoke_args, parent)
            # sys.stdout.flush()

            # Use the Lua sandbox to execute a Lua macro.  This will initialize
            # the Lua environment and store it in self.lua if it does not
            # already exist (it needs to be re-created for each new page).
            ret = call_lua_sandbox(self, invoke_args, expander, parent, timeout)
            # print("invoke_fn: invoke_args={} parent={} LUA ret={!r}"
            #       .format(invoke_args, parent, ret))
            return ret

        def expand_recurse(coded, parent, templates_to_expand):
            """This function does most of the work for expanding encoded
            templates, arguments, and parser functions."""
            assert isinstance(coded, str)
            assert isinstance(parent, (tuple, type(None)))
            assert isinstance(templates_to_expand, (set, dict))

            def expand_args(coded, argmap):
                assert isinstance(coded, str)
                assert isinstance(argmap, dict)
                parts = []
                pos = 0
                for m in re.finditer(r"[{:c}-{:c}]"
                                     .format(MAGIC_FIRST, MAGIC_LAST),
                                     coded):
                    new_pos = m.start()
                    if new_pos > pos:
                        parts.append(coded[pos:new_pos])
                    pos = m.end()
                    ch = m.group(0)
                    idx = ord(ch) - MAGIC_FIRST
                    kind, args, nowiki = self.cookies[idx]
                    assert isinstance(args, tuple)
                    if nowiki:
                        # If this template/link/arg has <nowiki />, then just
                        # keep it as-is (it won't be expanded)
                        parts.append(ch)
                        continue
                    if kind == "T":
                        # Template transclusion or parser function call.
                        # Expand its arguments.
                        new_args = tuple(map(lambda x: expand_args(x, argmap),
                                             args))
                        parts.append(self._save_value(kind, new_args, nowiki))
                        continue
                    if kind == "A":
                        # Template argument reference
                        if len(args) > 2:
                            self.debug("too many args ({}) in argument "
                                       "reference: {!r}"
                                       .format(len(args), args))
                        self.expand_stack.append("ARG-NAME")
                        k = expand_recurse(expand_args(args[0], argmap),
                                           parent, all_templates).strip()
                        self.expand_stack.pop()
                        if k.isdigit():
                            k = int(k)
                        else:
                            k = re.sub(r"\s+", " ", k).strip()
                        v = argmap.get(k, None)
                        if v is not None:
                            parts.append(v)
                            continue
                        if len(args) >= 2:
                            self.expand_stack.append("ARG-DEFVAL")
                            ret = expand_args(args[1], argmap)
                            self.expand_stack.pop()
                            parts.append(ret)
                            continue
                        # The argument is not defined (or name is empty)
                        arg = self._unexpanded_arg([str(k)], nowiki)
                        parts.append(arg)
                        continue
                    if kind == "L":
                        # Link to another page
                        new_args = list(expand_args(x, argmap)
                                        for x in args)
                        parts.append(self._unexpanded_link(new_args, nowiki))
                        continue
                    if kind == "E":
                        # Link to another page
                        new_args = list(expand_args(x, argmap)
                                        for x in args)
                        parts.append(self._unexpanded_extlink(new_args, nowiki))
                        continue
                    if kind == "N":
                        parts.append(ch)
                        continue
                    self.error("expand_arg: unsupported cookie kind {!r} in {}"
                               .format(kind, m.group(0)))
                    parts.append(m.group(0))
                parts.append(coded[pos:])
                return "".join(parts)

            def expand_parserfn(fn_name, args):
                if not expand_parserfns:
                    if not args:
                        return "{{" + fn_name + "}}"
                    return "{{" + fn_name + ":" + "|".join(args) + "}}"
                # Call parser function
                self.expand_stack.append(fn_name)
                expander = lambda arg: expand_recurse(arg, parent,
                                                      all_templates)
                if fn_name == "#invoke":
                    if not expand_invoke:
                        return "{{#invoke:" + "|".join(args) + "}}"
                    ret = invoke_fn(args, expander, parent)
                else:
                    ret = call_parser_function(self, fn_name, args, expander)
                self.expand_stack.pop()  # fn_name
                # XXX if lua code calls frame:preprocess(), then we should
                # apparently encode and expand the return value, similarly to
                # template bodies (without argument expansion)
                # XXX current implementation of preprocess() does not match!!!
                return str(ret)

            # Main code of expand_recurse()
            parts = []
            pos = 0
            for m in re.finditer(r"[{:c}-{:c}]"
                                 .format(MAGIC_FIRST, MAGIC_LAST),
                                 coded):
                new_pos = m.start()
                if new_pos > pos:
                    parts.append(coded[pos:new_pos])
                pos = m.end()
                ch = m.group(0)
                idx = ord(ch) - MAGIC_FIRST
                if idx >= len(self.cookies):
                    parts.append(ch)
                    continue
                kind, args, nowiki = self.cookies[idx]
                assert isinstance(args, tuple)
                if kind == "T":
                    if nowiki:
                        parts.append(self._unexpanded_template(args, nowiki))
                        continue
                    # Template transclusion or parser function call
                    # Limit recursion depth
                    if len(self.expand_stack) >= 100:
                        self.error("too deep recursion during template "
                                   "expansion")
                        parts.append(
                            '<strong class="error">too deep recursion '
                            'while expanding template {}</strong>'
                            .format(self._unexpanded_template(args, True)))
                        continue

                    # Expand template/parserfn name
                    self.expand_stack.append("TEMPLATE_NAME")
                    tname = expand_recurse(args[0], parent, templates_to_expand)
                    self.expand_stack.pop()

                    # Strip safesubst: and subst: prefixes
                    tname = tname.strip()
                    if tname[:10].lower() == "safesubst:":
                        tname = tname[10:]
                    elif tname[:6].lower() == "subst:":
                        tname = tname[6:]

                    # Check if it is a parser function call
                    ofs = tname.find(":")
                    if ofs > 0:
                        # It might be a parser function call
                        fn_name = self._canonicalize_parserfn_name(tname[:ofs])
                        # Check if it is a recognized parser function name
                        if (fn_name in PARSER_FUNCTIONS or
                            fn_name.startswith("#")):
                            ret = expand_parserfn(fn_name,
                                                  (tname[ofs + 1:].lstrip(),) +
                                                  args[1:])
                            parts.append(ret)
                            continue

                    # As a compatibility feature, recognize parser functions
                    # also as the first argument of a template (withoout colon),
                    # whether there are more arguments or not.  This is used
                    # for magic words and some parser functions have an implicit
                    # compatibility template that essentially does this.
                    fn_name = self._canonicalize_parserfn_name(tname)
                    if fn_name in PARSER_FUNCTIONS or fn_name.startswith("#"):
                        ret = expand_parserfn(fn_name, args[1:])
                        parts.append(ret)
                        continue

                    # Otherwise it must be a template expansion
                    name = tname
                    name = self._canonicalize_template_name(name)

                    # Check for undefined templates
                    if name not in all_templates:
                        # XXX tons of these in enwiktionary-20201201 ???
                        #self.debug("undefined template {!r}.format(tname))
                        parts.append('<strong class="error">Template:{}'
                                     '</strong>'
                                     .format(html.escape(name)))
                        continue

                    # If this template is not one of those we want to expand,
                    # return it unexpanded (but with arguments possibly
                    # expanded)
                    if name not in templates_to_expand:
                        # Note: we will still expand parser functions in its
                        # arguments, because those parser functions could
                        # refer to its parent frame and fail if expanded
                        # after eliminating the intermediate templates.
                        new_args = list(expand_recurse(x, parent,
                                                       templates_to_expand)
                                        for x in args)
                        parts.append(self._unexpanded_template(new_args,
                                                               nowiki))
                        continue

                    # Construct and expand template arguments
                    self.expand_stack.append(name)
                    ht = {}
                    num = 1
                    for i in range(1, len(args)):
                        arg = str(args[i])
                        m = re.match(r"""(?s)^\s*([^][&<>="']+?)\s*="""
                                     """\s*(.*?)\s*$""",
                                     arg)
                        if m:
                            # Note: Whitespace is stripped by the regexp
                            # around named parameter names and values per
                            # https://en.wikipedia.org/wiki/Help:Template
                            # (but not around unnamed parameters)
                            k, arg = m.groups()
                            if k.isdigit():
                                k = int(k)
                                if k < 1 or k > 1000:
                                    self.debug("invalid argument number {} "
                                               "for template {!r}"
                                               .format(k, name))
                                    k = 1000
                                if num <= k:
                                    num = k + 1
                            else:
                                self.expand_stack.append("ARGNAME")
                                k = expand_recurse(k, parent, all_templates)
                                k = re.sub(r"\s+", " ", k).strip()
                                self.expand_stack.pop()
                        else:
                            k = num
                            num += 1
                        # Expand arguments in the context of the frame where
                        # they are defined.  This makes a difference for
                        # calls to #invoke within a template argument (the
                        # parent frame would be different).
                        self.expand_stack.append("ARGVAL-{}".format(k))
                        arg = expand_recurse(arg, parent, all_templates)
                        self.expand_stack.pop()
                        ht[k] = arg

                    # Expand the body, either using ``template_fn`` or using
                    # normal template expansion
                    t = None
                    # print("EXPANDING TEMPLATE: {} {}".format(name, ht))
                    if template_fn is not None:
                        t = template_fn(urllib.parse.unquote(name), ht)
                        # print("TEMPLATE_FN {}: {} {} -> {}"
                        #      .format(template_fn, name, ht, repr(t)))
                    if t is None:
                        if name in self.transient_templates:
                            body = self.transient_templates[name]
                        else:
                            body = self.templates[name]
                        # XXX optimize by pre-encoding bodies during
                        # preprocessing
                        # (Each template is typically used many times)
                        # Determine if the template starts with a list item
                        contains_list = (re.match(r"(?s)^[#*;:]", body)
                                         is not None)
                        if contains_list:
                            body = "\n" + body
                        encoded_body = self._encode(body)
                        # Expand template arguments recursively.  The arguments
                        # are already expanded.
                        encoded_body = expand_args(encoded_body, ht)
                        # Expand the body using the calling template/page as
                        # the parent frame for any parserfn calls
                        new_title = tname.strip()
                        for prefix in ("Media", "Special", "Main", "Talk",
                                       "User",
                                       "User_talk", "Project", "Project_talk",
                                       "File", "Image", "File_talk",
                                       "MediaWiki", "MediaWiki_talk",
                                       "Template", "Template_talk",
                                       "Help", "Help_talk", "Category",
                                       "Category_talk", "Module",
                                       "Module_talk"):
                            if tname.startswith(prefix + ":"):
                                break
                        else:
                            new_title = "Template:" + new_title
                        new_parent = (new_title, ht)
                        # print("expanding template body for {} {}"
                        #       .format(name, ht))
                        # XXX no real need to expand here, it will expanded on
                        # next iteration anyway (assuming parent unchanged)
                        # Otherwise expand the body
                        t = expand_recurse(encoded_body, new_parent,
                                           templates_to_expand)

                    # If a post_template_fn has been supplied, call it now
                    # to capture or alter the expansion
                    # print("TEMPLATE EXPANDED: {} {} -> {!r}"
                    #       .format(name, ht, t))
                    if post_template_fn is not None:
                        t2 = post_template_fn(urllib.parse.unquote(name), ht, t)
                        if t2 is not None:
                            t = t2

                    assert isinstance(t, str)
                    self.expand_stack.pop()  # template name
                    parts.append(t)
                elif kind == "A":
                    parts.append(self._unexpanded_arg(args, nowiki))
                elif kind == "L":
                    if nowiki:
                        parts.append(self._unexpanded_link(args, nowiki))
                    else:
                        # Link to another page
                        self.expand_stack.append("[[link]]")
                        new_args = list(expand_recurse(x, parent,
                                                       templates_to_expand)
                                        for x in args)
                        self.expand_stack.pop()
                        parts.append(self._unexpanded_link(new_args, nowiki))
                elif kind == "E":
                    if nowiki:
                        parts.append(self._unexpanded_extlink(args, nowiki))
                    else:
                        # Link to an external page
                        self.expand_stack.append("[extlink]")
                        new_args = list(expand_recurse(x, parent,
                                                       templates_to_expand)
                                        for x in args)
                        self.expand_stack.pop()
                        parts.append(self._unexpanded_extlink(new_args, nowiki))
                elif kind == "N":
                    parts.append(ch)
                else:
                    self.error("expand: unsupported cookie kind {!r} in {}"
                               .format(kind, m.group(0)))
                    parts.append(m.group(0))
            parts.append(coded[pos:])
            return "".join(parts)

        # Encode all template calls, template arguments, and parser function
        # calls on the page.  This is an inside-out operation.
        encoded = self._encode(text)

        # Recursively expand the selected templates.  This is an outside-in
        # operation.
        expanded = expand_recurse(encoded, parent, templates_to_expand)

        # Expand any remaining magic cookies and remove nowiki char
        expanded = self._finalize_expand(expanded)
        return expanded

    def _finalize_expand(self, text):
        """Expands any remaining magic characters (to their original values)
        and removes nowiki characters."""
        # print("_finalize_expand: {!r}".format(text))

        def magic_repl(m):
            idx = ord(m.group(0)) - MAGIC_FIRST
            if idx >= len(self.cookies):
                return m.group(0)
            kind, args, nowiki = self.cookies[idx]
            if kind == "T":
                return self._unexpanded_template(args, nowiki)
            if kind == "A":
                return self._unexpanded_arg(args, nowiki)
            if kind == "L":
                return self._unexpanded_link(args, nowiki)
            if kind == "E":
                return self._unexpanded_extlink(args, nowiki)
            if kind == "N":
                return "<nowiki>" + args[0] + "</nowiki>"
            self.error("magic_repl: unsupported cookie kind {!r}"
                       .format(kind))
            return ""

        # Keep expanding magic cookies until they have all been expanded.
        # We might get them from, e.g., unexpanded_template()
        while True:
            prev = text
            text = re.sub(r"[{:c}-{:c}]".format(MAGIC_FIRST, MAGIC_LAST),
                          magic_repl, text)
            if prev == text:
                break

        # Convert the special <nowiki /> character back to <nowiki />.
        # This is done at the end of normal expansion.
        text = re.sub(MAGIC_NOWIKI_CHAR, "<nowiki />", text)
        return text

    def process(self, path, page_handler, phase1_only=False):
        """Parses a WikiMedia dump file ``path`` (which should point to a
        "<project>-<date>-pages-articles.xml.bz2" file.  This calls
        ``page_handler(model, title, page)`` for each raw page.  This
        works in two phases - in the first phase this calls
        ctx.collect_specials() for each page to collect raw pages,
        especially templates and Lua modules.  Then this goes over the
        articles a second time, calling page_handler for each page
        (this automatically calls ctx.start_page(title) for each page
        before calling page_handler).  The page_handler will be called
        in parallel using the multiprocessing package, and thus it
        cannot save data in ``ctx`` or global variables.  It can only
        return its results.  This function will return an iterator
        that yields all the results returned by page_handler (in
        arbirary order), except None values will be ignored.  This
        function is not re-entrant.  NOTE: THIS FUNCTION RETURNS
        ITERATOR AND THE RESULT MUST BE ITERATED FOR THIS TO DO
        SOMETHING."""
        assert isinstance(path, str)
        assert callable(page_handler)
        # Process the dump and copy it to temporary file (Phase 1)
        process_dump(self, path, page_handler)
        if phase1_only:
            return []

        # Reprocess all the pages that we captured in Phase 1
        return self.reprocess(page_handler)

    def reprocess(self, page_handler, autoload=True):
        """Reprocess all pages captured by self.process() or explicit calls to
        self.add_page().  This calls page_handler(model, title, text)
        for each page, and returns of list of their return values
        (ignoring None values).  If ``autoload`` is set to False, then
        ``text`` will be None, and the page handler must use
        self.read_by_title(title) to read the page contents (this may be
        useful for scanning the cache for just a few pages quickly).  This may
        call page_handler in parallel, and thus page_handler should
        not attempt to save anything between calls and should not
        modify global data.  This function is not re-entrant.
        NOTE: THIS FUNCTION RETURNS ITERATOR AND THE RESULT MUST BE ITERATED
        FOR THIS TO DO SOMETHING."""
        assert callable(page_handler)
        assert autoload in (True, False)
        global _global_ctx
        global _global_page_handler
        global _global_page_autoload
        _global_ctx = self
        _global_page_handler = page_handler
        _global_page_autoload = autoload

        if self.num_threads == 1:
            # Single-threaded version (without subprocessing).  This is
            # primarily intended for debugging.
            for model, title in self.page_seq:
                success, ret_title, t, ret = phase2_page_handler((model,
                                                                  title))
                assert ret_title == title
                if not success:
                    print(ret)  # Print error in parent process - do not remove
                    lines = ret.split("\n")
                    msg = lines[0]
                    trace = "\n".join(lines[1:])
                    if msg.find("EXCEPTION") >= 0:
                        self.error(msg, trace=trace)
                    continue
                if ret is not None:
                    yield ret
        else:
            # Process pages using multiple parallel processes (the normal
            # case)
            if self.num_threads is None:
                pool = multiprocessing.Pool()
            else:
                pool = multiprocessing.Pool(self.num_threads)
            cnt = 0
            start_t = time.time()
            last_t = time.time()
            for success, title, t, ret in \
                pool.imap_unordered(phase2_page_handler, self.page_seq):
                if t + 300 < time.time():
                    print("====== REPROCESS GOT OLD RESULT ({:.1f}s): {}"
                          .format(time.time() - t, title))
                sys.stdout.flush()
                if not success:
                    # Print error in parent process - do not remove
                    print(ret)
                    sys.stdout.flush()
                    continue
                if ret is not None:
                    yield ret
                cnt += 1
                if (not self.quiet and
                    # cnt % 1000 == 0 and
                    time.time() - last_t > 1):
                    remaining = len(self.page_seq) - cnt
                    secs = (time.time() - start_t) / cnt * remaining
                    print("  ... {}/{} pages ({:.1%}) processed, "
                          "{:02d}:{:02d}:{:02d} remaining"
                          .format(cnt, len(self.page_seq),
                                  cnt / len(self.page_seq),
                                  int(secs / 3600),
                                  int(secs / 60 % 60),
                                  int(secs % 60)))
                    sys.stdout.flush()
                    last_t = time.time()
            pool.close()
            pool.join()

        sys.stderr.flush()
        sys.stdout.flush()

    def page_exists(self, title):
        """Returns True if the given page exists, and False if it does not
        exist."""
        assert isinstance(title, str)
        if title.startswith("Main:"):
            title = title[5:]
        # XXX should we canonicalize title?
        if title in self.transient_pages:
            return True
        return title in self.page_contents

    def read_by_title(self, title):
        """Reads the contents of the page.  Returns None if the page does
        not exist."""
        assert isinstance(title, str)
        if title.startswith("Main:"):
            title = title[5:]
        # XXX should we canonicalize title?
        if title in self.transient_pages:
            title, model, text = self.transient_pages[title]
            return text
        if title not in self.page_contents:
            return None
        # The page seems to exist
        title, model, ofs, page_size = self.page_contents[title]
        # Use os.pread() so that we won't change the file offset; otherwise we
        # might cause a race condition with parallel scanning of the temporary
        # file.
        rawdata = os.pread(self.tmp_file.fileno(), page_size, ofs)
        return rawdata.decode("utf-8")

    def parse(self, text, pre_expand=False, expand_all=False,
              additional_expand=None, template_fn=None, post_template_fn=None):
        """Parses the given text into a parse tree (WikiNode tree).  If
        ``pre_expand`` is True, then before parsing this will expand
        those templates that have been detected to potentially
        influence the parsing results (e.g., they might produce table
        start or end or table rows).  Likewise, if ``expand_all`` is
        True, this will expand all templates that have definitions
        (usually all of them).  If ``additional_expand`` is given, it
        should be a set of additional templates to expand.  Parser
        function calls and Lua macro invocations are expanded if they
        are inside expanded templates."""
        assert isinstance(text, str)
        assert pre_expand in (True, False)
        assert expand_all in (True, False)
        assert additional_expand is None or isinstance(additional_expand, set)

        # Preprocess.  This may also add some MAGIC_NOWIKI_CHARs.
        text = self.preprocess_text(text)

        # Expand some or all templates in the text as requested
        if expand_all:
            text = self.expand(text, template_fn=template_fn,
                               post_template_fn=post_template_fn)
        elif pre_expand or additional_expand:
            text = self.expand(text, pre_expand=pre_expand,
                               templates_to_expand=additional_expand,
                               template_fn=template_fn,
                               post_template_fn=post_template_fn)

        # print("parse:", repr(text))

        # The Wikitext syntax is not context-free.  Also, tokenizing the
        # syntax properly does not seem to be possible without reference to
        # the overall structure.  We handle this with inside-out parsing
        # (which I haven't seen used elsewhere though it may have been).
        # The basic idea is that we replace template / template argument /
        # parser function call by a magic character, starting from the
        # innermost one, and then keep doing this until there is no more work
        # to do.  This allows us to disambiguate how braces group into
        # double and triple brace groups.  After the encoding, we do
        # a more traditional parsing of the rest, recursing into encoded parts.
        encoded = self._encode(text)
        root = parse_encoded(self, encoded)  # In parser.py
        # print("parse tree: {}".format(root))
        return root

    def node_to_wikitext(self, node, node_handler_fn=None):
        """Converts the given parse tree node back to Wikitext."""
        v = to_wikitext(node, node_handler_fn=node_handler_fn)
        return v

    def node_to_html(self, node, template_fn=None, post_template_fn=None,
                     node_handler_fn=None):
        """Converts the given parse tree node to HTML."""
        return to_html(self, node, template_fn=template_fn,
                       post_template_fn=post_template_fn,
                       node_handler_fn=node_handler_fn)

    def node_to_text(self, node, template_fn=None, post_template_fn=None,
                     node_handler_fn=None):
        """Converts the given parse tree node to plain text."""
        return to_text(self, node, template_fn=template_fn,
                       post_template_fn=post_template_fn,
                       node_handler_fn=node_handler_fn)
