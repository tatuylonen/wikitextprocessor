# Definition of the processing context for Wikitext processing, and code for
# expanding templates, parser functions, and Lua macros.
#
# Copyright (c) 2020-2022, 2024 Tatu Ylonen.  See file LICENSE and https://ylonen.org

import json
import logging
import re
import sqlite3
import sys
import tempfile
import urllib.parse
from collections import defaultdict, deque
from collections.abc import Callable, Sequence, Set
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from types import TracebackType
from typing import (
    TYPE_CHECKING,
    Iterator,
    Optional,
    TypedDict,
    Union,
)

from .common import (
    MAGIC_FIRST,
    MAGIC_LBRACKET_CHAR,
    MAGIC_NOWIKI_CHAR,
    MAGIC_RBRACKET_CHAR,
    MAGIC_RE_PATTERN,
    MAX_MAGICS,
    URL_STARTS,
    add_newline_to_expansion,
    nowiki_quote,
)
from .logging_utils import logger
from .luaexec import call_lua_sandbox
from .node_expand import NodeHandlerFnCallable, to_html, to_text, to_wikitext
from .parser import (
    KIND_TO_LEVEL,
    GeneralNode,
    WikiNode,
    parse_encoded,
    set_html_tag_data,
    set_inside_html_tags_re,
)
from .parserfns import PARSER_FUNCTIONS, call_parser_function
from .wikihtml import ALLOWED_HTML_TAGS, HTMLTagData

if TYPE_CHECKING:
    from lupa.lua51 import (
        LuaNumber,
        LuaRuntime,
        _LuaTable,
    )


NamespaceDataEntry = TypedDict(
    "NamespaceDataEntry",
    {
        "aliases": list[str],
        "content": bool,
        "id": int,
        "issubject": bool,
        "istalk": bool,
        "name": str,
    },
    total=True,  # fields are obligatory
)

JsonValues = Union[str, int, float, list, dict, bool, None]
# Can't specify _LuaTable contents further, so no use specifying the Dict either
ParentData = tuple[str, Union["_LuaTable", dict[Union[int, str], str]]]
TemplateArgs = dict[Union[int, str], str]
TemplateFnCallable = Callable[
    [
        str,  # name
        TemplateArgs,  # arguments
    ],
    Optional[str],  # expanded output
]
PostTemplateFnCallable = Callable[
    [
        str,  # name
        TemplateArgs,  # arguments
        str,  # previously expanded from templatefn
    ],
    Optional[str],  # finalized expanded output
]


class ErrorMessageData(TypedDict):
    msg: str
    trace: str
    title: Optional[str]
    section: Optional[str]
    subsection: Optional[str]
    called_from: str
    path: tuple[str, ...]


class CollatedErrorReturnData(TypedDict):
    errors: list[ErrorMessageData]
    warnings: list[ErrorMessageData]
    debugs: list[ErrorMessageData]


CookieData = tuple[str, Sequence[str], bool]

CookieChar = str

EMPTY_NAMESPACEDATA: NamespaceDataEntry = {
    "id": -1,
    "name": "NAMESPACE_DATA_ERROR",
    "aliases": [],
    "content": False,
    "istalk": False,
    "issubject": False,
}


@dataclass
class Page:
    title: str
    namespace_id: int
    redirect_to: Optional[str] = None
    need_pre_expand: bool = False
    body: Optional[str] = None
    model: Optional[str] = None


class BegLineDisableManager:
    """A 'context manager'-style object to use with `with` that increments
    and decrements a counter used as a flag to see whether the parser
    should care about tokens at the beginning of a line, used in magic_fn
    to disable parsing when just looping through arguments"""

    def __init__(self, ctx: "Wtp") -> None:
        self.ctx = ctx

    def __enter__(self) -> None:
        self.ctx.begline_disable_counter += 1
        self.ctx.begline_enabled = False

    def __exit__(
        self,
        exc_type: type[BaseException],
        exc_value: BaseException,
        trace: TracebackType,
    ) -> None:
        self.ctx.begline_disable_counter -= 1
        if self.ctx.begline_disable_counter < 1:
            self.ctx.begline_enabled = True


LINKS = (
    # `[[something<abcd>]]`
    # XXX this regex seems to be too complex,
    # could you replace it with just [^][{}]*?
    r"(?<!\[)"
    + r"\["
    + MAGIC_NOWIKI_CHAR
    + r"?\[("
    + r"(((?!\]\])[^[\|\n])*((?!\[\[)[^]\n])+)"
    + r"(\|(((?!\]\])[^[])*((?!\[\[)[^]])+))?"  # after pipe no newlines, optnl.
    + r")\]"
    + MAGIC_NOWIKI_CHAR
    + r"?\]"
)
# (?<!\[)    # negative lookbehind,
#            # [[[ breaks the link completely,
#            # the whole thing is not parsed as a link or url
# \[MAGIC_NOWIKI?\[      # start brackets
# (, optnl.
#   (
#     (?!\]\])    # negative lookahead, no ]] allowed
#     [^[\n]
#   )*    # no [ or newlines allowed
#   (
#      (?!\[\[)   # no [[ allowed
#      [^]\n]    # no ] or newlines
#   )+
# )
# (\|  # after a |, newlines are allowed, the below is the same as above
#   (((?!\]\])[^[])*((?!\[\[)[^]])+)
# )?
# \]MAGIC_NOWIKI?\]

LINKS_RE = re.compile(LINKS)

# Encode external links: [something]
# [test]]+ breaks in sandbox, so prevent with negative lookahead
EXTERNAL_LINKS = r"\[([^][{}<>|\n]+)\](?!\])"

EXTERNAL_LINKS_RE = re.compile(EXTERNAL_LINKS)

# Encode template arguments: {{{arg}}}, {{{..{|..|}..}}}
TEMPLATE_ARGUMENTS = (
    r"\{"
    + MAGIC_NOWIKI_CHAR
    + r"?\{"
    + MAGIC_NOWIKI_CHAR
    + r"?\{(("
    + r"[^{}]|"  # No curly brackets (except inside cookies)
    + r"\{\|[^{}]*\|\}"  # Outermost table brackets accepted?
    + r")*?)\}"
    + MAGIC_NOWIKI_CHAR
    + r"?\}"
    + MAGIC_NOWIKI_CHAR
    + r"?\}"
)

TEMPLATE_ARGUMENTS_RE = re.compile(TEMPLATE_ARGUMENTS)

TEMPLATES = (
    r"\{" + MAGIC_NOWIKI_CHAR + r"?\{((?:"
    r"[^{}]{?|"  # lone possible { and also default "any"
    r"}(?=[^{}])|"  # lone `}`, (?=...) is not consumed (lookahead)
    r"-{}-|"  # GitHub issue #59 Chinese wiktionary special `-{}-`
    r"}{|"  # latex argument: "<math>\frac{1}{2}</math>"
    r")+?)\}" + MAGIC_NOWIKI_CHAR + r"?\}"
)

TEMPLATES_RE = re.compile(TEMPLATES)

ALL_BRACKETS_RE = re.compile(
    r"("
    + r"|".join((LINKS, EXTERNAL_LINKS, TEMPLATE_ARGUMENTS, TEMPLATES))
    + r")"
)


class Wtp:
    """Context used for processing wikitext and for expanding templates,
    parser functions and Lua macros.  The intended usage pattern is to
    initialize this context once (this holds template and module definitions),
    and then using the context for processing many pages."""

    __slots__ = (
        "db_path",  # Database path
        "db_conn",  # Database connection
        "cookies",  # Mapping from magic cookie -> expansion data
        "debugs",  # List of debug messages (cleared for each new page)
        "errors",  # List of error messages (cleared for each new page)
        "fullpage",  # The unprocessed text of the current page (or None)
        "lua",  # Lua runtime or None if not yet initialized
        "lua_invoke",  # Lua function used to invoke a Lua module
        "lua_reset_env",  # Lua function to reset Lua environment
        "lua_clear_loaddata_cache",  # Lua function to clear mw.loadData() cache
        "lua_path",  # Path to Lua modules
        "rev_ht",  # Mapping from text to magic cookie
        "expand_stack",  # Saved stack before calling Lua function
        "title",  # current page title
        "warnings",  # List of warning messages (cleared for each new page)
        # Data for parsing
        "beginning_of_line",  # Parser at beginning of line
        "wsp_beginning_of_line",  # Parser at beginning of line + whitespace
        "begline_enabled",  # in magic_fn, beginning_of_line = False
        "begline_disable_counter",
        "begline_disabled",  # context-managerish thing for begline_en..
        "linenum",  # Current line number
        "pre_parse",  # XXX is pre-parsing still needed?
        "parser_stack",  # Parser stack
        "section",  # Section within page, for error messages
        "subsection",  # Subsection within page, for error messages
        "suppress_special",  # XXX never set to True???
        "data_folder",
        "NAMESPACE_DATA",
        "LOCAL_NS_NAME_BY_ID",  # Local namespace names dictionary
        "NS_ID_BY_LOCAL_NAME",
        "lang_code",
        # Python functions for overriding template expanded text
        "template_override_funcs",
        "lua_env_stack",
        "lua_frame_stack",
        "project",  # "wiktionary" or "wikipedia"
        "strip_marker_cache",
        "allowed_html_tags",
        "html_permitted_parents",
        "paired_html_tags",
        "inside_html_tags_re",
        "invoke_aliases",
    )

    def __init__(
        self,
        db_path: Optional[Union[str, Path]] = None,
        lang_code="en",
        template_override_funcs: dict[str, Callable[[Sequence[str]], str]] = {},
        project: str = "wiktionary",
        extension_tags: Optional[dict[str, HTMLTagData]] = None,
        invoke_aliases: Optional[set[str]] = None,
        file_aliases: Optional[set[str]] = None,
        quiet: bool = False,
    ):
        if isinstance(db_path, str):
            self.db_path: Optional[Path] = Path(db_path)
        else:
            self.db_path = db_path
        self.cookies: list[CookieData] = []
        self.errors: list[ErrorMessageData] = []
        self.warnings: list[ErrorMessageData] = []
        self.debugs: list[ErrorMessageData] = []
        self.section: Optional[str] = None
        self.subsection: Optional[str] = None
        self.lua: Optional["LuaRuntime"] = None
        self.lua_invoke: Optional[
            Callable[
                [str, str, "_LuaTable", str, Optional[LuaNumber]],
                tuple[bool, str],
            ]
        ] = None
        self.lua_reset_env: Optional[Callable[[], "_LuaTable"]] = None
        self.lua_clear_loaddata_cache: Optional[Callable[[], None]] = None
        self.rev_ht: dict[CookieData, str] = {}
        self.expand_stack: list[str] = []  # XXX: this has a confusing name
        self.parser_stack: list["WikiNode"] = []
        self.lang_code = lang_code  # dump file language code
        self.data_folder = files("wikitextprocessor") / "data" / lang_code
        self.init_namespace_data()
        self.create_db()
        self.template_override_funcs = template_override_funcs
        self.beginning_of_line = False
        self.begline_enabled = True
        self.begline_disable_counter = 0
        self.begline_disabled = BegLineDisableManager(self)
        self.wsp_beginning_of_line = False
        self.title: Optional[str] = None
        self.section = None
        self.subsection = None
        self.linenum = 1
        self.pre_parse = False
        self.suppress_special = False
        self.lua_env_stack: deque["_LuaTable"] = deque()
        self.lua_frame_stack: deque["_LuaTable"] = deque()
        self.project = project
        self.strip_marker_cache: defaultdict[str, int] = defaultdict(int)
        self.allowed_html_tags: dict[str, HTMLTagData] = ALLOWED_HTML_TAGS
        if extension_tags is not None:
            self.allowed_html_tags.update(extension_tags)
        # Set of HTML tags that need an explicit end tag.
        self.paired_html_tags: set[str] = set(
            k
            for k, v in self.allowed_html_tags.items()
            if not v.get("no-end-tag")
        )
        self.html_permitted_parents: dict[str, set[str]] = set_html_tag_data(
            self
        )
        self.inside_html_tags_re: re.Pattern = set_inside_html_tags_re(self)
        self.invoke_aliases = {"#invoke"}
        if invoke_aliases is not None:
            self.invoke_aliases |= invoke_aliases
        if not quiet:
            logger.setLevel(logging.DEBUG)

    def create_db(self) -> None:
        from .wikidata import init_wikidata_cache

        if self.db_path is None:
            temp_file = tempfile.NamedTemporaryFile(
                prefix="wikitextprocessor_tempdb", delete=False
            )
            self.db_path = Path(temp_file.name)
            temp_file.close()

        if self.backup_db_path.exists():
            self.db_path.unlink(True)
            self.backup_db_path.rename(self.db_path)

        self.db_conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.db_conn.executescript(
            """
        CREATE TABLE IF NOT EXISTS pages (
        title TEXT,
        namespace_id INTEGER,
        redirect_to TEXT,
        need_pre_expand INTEGER,
        body TEXT,
        model TEXT,
        PRIMARY KEY(title, namespace_id));

        PRAGMA journal_mode = WAL;
        """
        )
        init_wikidata_cache(self)

    @property
    def backup_db_path(self) -> Path:
        assert self.db_path
        return self.db_path.with_stem(self.db_path.stem + "_backup")

    def backup_db(self) -> None:
        self.backup_db_path.unlink(True)
        self.db_conn.commit()
        backup_conn = sqlite3.connect(self.backup_db_path)
        with backup_conn:
            self.db_conn.backup(backup_conn)
        backup_conn.close()

    def close_db_conn(self) -> None:
        assert self.db_path
        self.db_conn.close()
        if self.db_path.parent.samefile(Path(tempfile.gettempdir())):
            for path in self.db_path.parent.glob(self.db_path.name + "*"):
                # also remove SQLite -wal and -shm file
                path.unlink(True)

    def has_analyzed_templates(self) -> bool:
        for (result,) in self.db_conn.execute(
            "SELECT count(*) > 0 FROM pages WHERE need_pre_expand = 1"
        ):
            return result == 1
        return False

    def build_sql_where_query(
        self,
        namespace_ids: Optional[list[int]] = None,
        include_redirects: bool = True,
        model: Optional[str] = None,
        search_pattern: Optional[str] = None,
    ) -> tuple[str, tuple[Union[str, int], ...]]:
        and_strs = []
        where_str = ""
        query_values: list[Union[int, str]] = []
        if namespace_ids is not None:
            and_strs.append(
                f"namespace_id IN ({','.join('?' * len(namespace_ids))})"
            )
            query_values.extend(namespace_ids)
        if not include_redirects:
            and_strs.append("redirect_to IS NULL")
        if search_pattern:
            and_strs.append("body LIKE ?")
            query_values.append(search_pattern)
        if model is not None:
            and_strs.append("model = ?")
            query_values.append(model)

        if len(and_strs) > 0:
            where_str = " WHERE " + " AND ".join(and_strs)

        return where_str, tuple(query_values)

    def saved_page_nums(
        self,
        namespace_ids: Optional[list[int]] = None,
        include_redirects: bool = True,
        model: Optional[str] = None,
        search_pattern: Optional[str] = None,
    ) -> int:
        query_str = "SELECT count(*) FROM pages"

        where_str, query_values = self.build_sql_where_query(
            namespace_ids,
            include_redirects,
            model,
            search_pattern,
        )

        query_str += where_str

        for result in self.db_conn.execute(query_str, query_values):
            return result[0]

        return 0  # Mainly to satisfy the type checker

    def init_namespace_data(self) -> None:
        with self.data_folder.joinpath("namespaces.json").open(
            encoding="utf-8"
        ) as f:
            self.NAMESPACE_DATA: dict[str, NamespaceDataEntry] = json.load(f)
            self.LOCAL_NS_NAME_BY_ID: dict[int, str] = {
                data["id"]: data["name"]
                for data in self.NAMESPACE_DATA.values()
            }
            self.NS_ID_BY_LOCAL_NAME: dict[str, int] = {
                data["name"]: data["id"]
                for data in self.NAMESPACE_DATA.values()
            }

    def _fmt_errmsg(self, kind: str, msg: str, trace: Optional[str]) -> None:
        assert isinstance(kind, str)
        assert isinstance(msg, str)
        assert isinstance(trace, (str, type(None)))
        loc = self.title or "ERROR_TITLE"
        if self.section is not None:
            loc += "/" + self.section
        if self.subsection is not None:
            loc += "/" + self.subsection
        if self.expand_stack:
            msg += " at {}".format(self.expand_stack)
        if self.parser_stack:
            titles: list[str] = []
            for node in self.parser_stack:
                if node.kind in KIND_TO_LEVEL:
                    if not node.largs:
                        continue
                    lst = (
                        x if isinstance(x, str) else "???"
                        for x in node.largs[0]
                    )
                    title = "".join(lst)
                    titles.append(title.strip())
            msg += " parsing " + "/".join(titles)
        if trace:
            msg += "\n" + trace
        print("{}: {}: {}".format(loc, kind, msg))
        sys.stdout.flush()

    def error(
        self, msg: str, trace: Optional[str] = None, sortid="XYZunsorted"
    ) -> None:
        """Prints an error message to stdout.  The error is also saved in
        self.errors."""
        assert isinstance(msg, str)
        assert isinstance(trace, (str, type(None)))
        assert isinstance(sortid, str)
        # sortid should be a static string only used to sort
        # error messages into buckets based on where they
        # have been called. There was previously some code for
        # inspecting the stack trace here that did the same
        # thing, but it was a bit costly.
        self.errors.append(
            {
                "msg": msg,
                "trace": trace or "",
                "title": self.title or "ERROR_TITLE",
                "section": self.section or "",
                "subsection": self.subsection or "",
                "called_from": sortid,
                "path": tuple(self.expand_stack),
            }
        )
        self._fmt_errmsg("ERROR", msg, trace)

    def warning(
        self, msg: str, trace: Optional[str] = None, sortid="XYZunsorted"
    ) -> None:
        """Prints a warning message to stdout.  The error is also saved in
        self.warnings."""
        assert isinstance(msg, str)
        assert isinstance(trace, (str, type(None)))
        assert isinstance(sortid, str)

        self.warnings.append(
            {
                "msg": msg,
                "trace": trace or "",
                "title": self.title or "ERROR_TITLE",
                "section": self.section or "",
                "subsection": self.subsection or "",
                "called_from": sortid,
                "path": tuple(self.expand_stack),
            }
        )
        self._fmt_errmsg("WARNING", msg, trace)

    def debug(
        self, msg: str, trace: Optional[str] = None, sortid="XYZunsorted"
    ) -> None:
        """Prints a debug message to stdout.  The error is also saved in
        self.debug."""
        assert isinstance(msg, str)
        assert isinstance(trace, (str, type(None)))
        assert isinstance(sortid, str)

        self.debugs.append(
            {
                "msg": msg,
                "trace": trace or "",
                "title": self.title or "ERROR_TITLE",
                "section": self.section or "",
                "subsection": self.subsection or "",
                "called_from": sortid,
                "path": tuple(self.expand_stack),
            }
        )
        self._fmt_errmsg("DEBUG", msg, trace)

    def to_return(self) -> CollatedErrorReturnData:
        """Returns a dictionary with errors, warnings, and debug messages
        from the context.  Note that the values are reset whenever starting
        processing a new word.  The value returned by this function is
        JSON-compatible and can easily be returned by a parallel process."""
        return {
            "errors": self.errors,
            "warnings": self.warnings,
            "debugs": self.debugs,
        }

    def _canonicalize_parserfn_name(self, name: str) -> str:
        """Canonicalizes a parser function name by replacing underscores by
        spaces and sequences of whitespace by a single whitespace."""
        name = re.sub(r"[\s_]+", " ", name)
        if name not in PARSER_FUNCTIONS:
            name = name.lower()  # Parser function names are case-insensitive
        return name

    def _save_value(
        self, kind: str, args: Sequence[str], nowiki: bool
    ) -> CookieChar:
        """Saves a value of a particular kind and returns a unique magic
        cookie character for it."""
        assert kind in (
            "T",  # Template {{ ... }}
            "A",  # Template argument {{{ ... }}}
            "L",  # link
            "E",  # external link
            "N",  # nowiki text
        )
        assert isinstance(args, (list, tuple))
        assert nowiki in (True, False)
        # print("save_value", kind, args, nowiki)
        args = tuple(args)
        v: CookieData = (kind, args, nowiki)
        if v in self.rev_ht:
            return self.rev_ht[v]
        idx = len(self.cookies)
        if idx >= MAX_MAGICS:
            self.error(
                "too many templates, arguments, or parser function calls",
                sortid="core/372",
            )
            return ""
        self.cookies.append(v)
        ch = chr(MAGIC_FIRST + idx)
        self.rev_ht[v] = ch
        return ch

    def _encode(self, text: str) -> str:
        """Encode all templates, template arguments, and parser function calls
        in the text, from innermost to outermost."""

        def vbar_split(v: str) -> list[str]:
            args = list(
                m.group(1)
                for m in re.finditer(
                    # re.X = ignore whitespace and comments, re.I = ignore case
                    r"""(?xi)\|(
                            (
                                <([-a-zA-Z0-9]+)\b[^>]*(?<!/)>  # html start tag
                                    [^][{}]*?  # element contents
                                               # (including `|`'s)
                                    </\3\s*>   # end tag
                            |   [^|]           # everything else
                            )*
                          )""",
                    "|" + v,  # first/only argument needs a vbar
                )
            )
            return args

        def repl_arg(m: re.Match) -> CookieChar:
            """Replacement function for template arguments."""
            nowiki = MAGIC_NOWIKI_CHAR in m.group(0)
            orig = m.group(1)
            args = vbar_split(orig)
            return self._save_value("A", args, nowiki)

        # def repl_arg_err(m):
        #     """Replacement function for template arguments, with error."""
        #     nowiki = MAGIC_NOWIKI_CHAR in m.group(0)
        #     prefix = m.group(1)
        #     orig = m.group(2)
        #     args = vbar_split(orig)
        #     self.debug(
        #         "heuristically added missing }} to template arg {}"
        #         # a single "}" needs to be escaped as "}}" with .format
        #         .format(args[0].strip()),
        #         sortid="core/405",
        #     )
        #     return prefix + self._save_value("A", args, nowiki)

        def repl_templ(m: re.Match) -> Union[CookieChar, str]:
            # I know CookieChar == str, this is just for documentation.
            """Replacement function for templates {{name|...}} and parser
            functions."""
            whole_match = m.group(0)
            nowiki = False
            if whole_match.startswith(
                "{" + MAGIC_NOWIKI_CHAR
            ) or whole_match.endswith(MAGIC_NOWIKI_CHAR + "}"):
                nowiki = True  # <nowiki/> inside `{{` or `}}`
            args = vbar_split(m.group(1))
            if len(args) == 0 or args[0] == "":
                # Templates without a first argument (template name)
                # are just rendered as text in wikimedia stuff.
                return (
                    "&lbrace;&lbrace;"
                    + "&vert;".join(args)
                    + "&rbrace;&rbrace;"
                )
            first_arg = args[0].strip()
            if not first_arg.startswith("#") and MAGIC_NOWIKI_CHAR in args[0]:
                nowiki = True  # <nowiki/> before first pipe
            if (
                first_arg.startswith("#")
                and ":" in first_arg
                and MAGIC_NOWIKI_CHAR in first_arg[: first_arg.index(":")]
            ):
                nowiki = True  # <nowiki/> before parser function name

            # print("REPL_TEMPL: args={}".format(args))
            return self._save_value("T", args, nowiki)

        # def repl_templ_err(m):
        #     """Replacement function for templates {{name|...}} and parser
        #     functions, with error."""
        #     nowiki = MAGIC_NOWIKI_CHAR in m.group(0)
        #     prefix = m.group(1)
        #     v = m.group(2)
        #     args = vbar_split(v)
        #     self.debug(
        #         "heuristically added missing }} to template {}"
        #         # a single "}" needs to be escaped as "}}" with .format
        #         .format(args[0].strip()),
        #         sortid="core/427",
        #     )
        #     return prefix + self._save_value("T", args, nowiki)

        def repl_link(m: re.Match) -> CookieChar:
            """Replacement function for links [[...]]."""
            m2 = ALL_BRACKETS_RE.search(
                # check to see if link contains something that should be
                # handled first
                m.group(0)[2:-2],
            )
            if m2:
                # print(f"{m.group(0)=}, {m.group(0)=}")
                return m.group(0)
            nowiki = MAGIC_NOWIKI_CHAR in m.group(0)
            orig = m.group(1)
            if MAGIC_NOWIKI_CHAR in orig:
                # check if nowiki tag is direct child
                root = parse_encoded(self, orig)
                nowiki = False
                for child in root.children:
                    if isinstance(child, str) and "<nowiki />" in child:
                        nowiki = True
                        break
            args = vbar_split(orig)
            # print("REPL_LINK: orig={!r}".format(orig))

            if (len(args) == 2 and "#" in args[0] and args[1] == "") or (
                not any(s.strip() for s in args)
            ):
                # empty [[ ]] links should really be rendered as
                # [[#Language]], where language is the section we're in,
                # but if something relies on this behavior I will eat my
                # chocolate hat. Let's just return escaped brackets.
                # If there are two args in vbar and the first one contains
                # a `#` and the other is empty, likewise. More than two in
                # args means the link has at least one `|` character...
                return "&#91;&#91;" + m.group(0)[2:-2] + "&#93;&#93;"
            return self._save_value("L", args, nowiki)

        def repl_extlink(m: re.Match) -> CookieChar:
            """Replacement function for external links [...].  This is also
            used to replace bracketed sections, such as [...]."""

            # parse as text if <nowiki/> tag at the start
            nowiki = (
                re.match(r"\[\s*" + MAGIC_NOWIKI_CHAR, m.group(0)) is not None
            )
            orig = m.group(1)
            if not orig.startswith(URL_STARTS):
                return MAGIC_LBRACKET_CHAR + orig + MAGIC_RBRACKET_CHAR
            args = [orig]
            return self._save_value("E", args, nowiki)

        # Main loop of encoding.  We encode repeatedly, always the innermost
        # template, argument, or parser function call first.  We also encode
        # links as they affect the interpretation of templates.
        # As a preprocessing step, remove comments from the text.
        text = re.sub(r"(?s)<!--.*?-->", "", text)
        while True:
            prev = text
            # Encode template arguments.  We repeat this until there are
            # no more matches, because otherwise we could encode the two
            # innermost braces as a template transclusion.
            # KJ: This inside-out parsing seems to work because wikitext
            # can't parse ambiguous stuff either:
            # {{ {{NAMESPACE}}}}  <- parses "correctly" as a broken template
            # {{{{NAMESPACE}}}}  <- parses incorrectly as `{{{{NAMESPACE}}}}`

            while True:
                prev2 = text
                # Encode links.
                while True:
                    text = LINKS_RE.sub(repl_link, text)
                    if text == prev2:
                        break
                    prev2 = text
                # Encode external links: [something]
                text = EXTERNAL_LINKS_RE.sub(repl_extlink, text)
                # Encode template arguments: {{{arg}}}, {{{..{|..|}..}}}
                text = TEMPLATE_ARGUMENTS_RE.sub(repl_arg, text)
                if text == prev2:
                    # When everything else has been done, see if we can find
                    # template arguments that have one missing closing bracket.
                    # This is so common in Wiktionary that I'm suspecting it
                    # might be allowed by the MediaWiki parser.
                    # This needs to be done before processing templates, as
                    # otherwise the argument with a missing closing brace would
                    # be interpreted as a template.
                    # Note: we don't want to do this for {{{!}}, as that is
                    # sometimes used inside {{#if|...}} for table start/end.
                    # XXX rejecting all possibly erroneous arguments because
                    # they contain a ! anywhere is not ideal.
                    # text = re.sub(
                    #     r"([^{]){"  # {{{{{1... is incorrect in wikitext
                    #     + MAGIC_NOWIKI_CHAR
                    #     + r"?{"
                    #     + MAGIC_NOWIKI_CHAR
                    #     + r"?{([^{}!]*?)}"
                    #     + MAGIC_NOWIKI_CHAR
                    #     + r"?}",
                    #     repl_arg_err,
                    #     text,
                    # )
                    # if text != prev2:
                    #     continue
                    break
            # Replace template invocation
            text = TEMPLATES_RE.sub(repl_templ, text)
            # We keep looping until there is no change during the iteration
            if text == prev:
                # When everything else has been done, see if we can find
                # template calls that have one missing closing bracket.
                # This is so common in Wiktionary that I'm suspecting it
                # might be allowed by the MediaWiki parser.  We must allow
                # tables {| ... |} inside these.
                # text = re.sub(
                #     r"([^{])\{"  # Leave a space between ambiguous brackets
                #     + MAGIC_NOWIKI_CHAR
                #     + r"?{(("
                #     + r"[^{}]|"
                #     + r"{\|[^{}]*?\|}|"  # Table brackets
                #     + r"}[^{}])+?)}", # Missing bracket
                #     repl_templ_err,
                #     text,
                # )
                # if text != prev:
                #     continue
                break
            prev = text
        # Replace any remaining braces etc by corresponding character entities
        # text = re.sub(r"\{([&|])", r"&lbrace;\1", text)
        # text = re.sub(r"\{([&|])", r"&lbrace;\1", text)
        # text = re.sub(r"[^|]\}", r"\1&rbrace;", text)
        # text = re.sub(r"[^|]\}", r"\1&rbrace;", text)
        # text = re.sub(r"\|", "&vert;", text)
        text = text.replace(MAGIC_LBRACKET_CHAR, "[")
        text = text.replace(MAGIC_RBRACKET_CHAR, "]")
        return text

    def _template_to_body(self, title: str, text: Optional[str]) -> str:
        """Extracts the portion to be transcluded from a template body."""
        assert isinstance(title, str)
        assert isinstance(text, str), (
            f"{text=!r} was passed " "into _template_to_body"
        )
        # Remove all comments
        text = re.sub(r"(?s)<!--.*?-->", "", text)
        # Remove all text inside <noinclude> ... </noinclude>
        text = re.sub(r"(?is)<noinclude\s*>.*?</noinclude\s*>", "", text)
        # Handle <noinclude> without matching </noinclude> by removing the
        # rest of the file.  <noinclude/> is handled specially elsewhere, as
        # it appears to be used as a kludge to prevent normal interpretation
        # of e.g. [[ ... ]] by placing it between the brackets.
        text = re.sub(r"(?is)<noinclude\s*>.*", "", text)
        # Apparently unclosed <!-- at the end of a template body is ignored
        text = re.sub(r"(?s)<!--.*", "", text)
        # <onlyinclude> tags, if present, include the only text that will be
        # transcluded.  All other text is ignored.
        onlys = list(
            re.finditer(
                r"(?is)<onlyinclude\s*>(.*?)"
                r"</onlyinclude\s*>|"
                r"<onlyinclude\s*/>",
                text,
            )
        )
        if onlys:
            text = "".join(m.group(1) or "" for m in onlys)
        # Remove <includeonly>.  They mark text that is not visible on the page
        # itself but is included in transclusion.  Also text outside these tags
        # is included in transclusion.
        text = re.sub(r"(?is)<\s*(/\s*)?includeonly\s*(/\s*)?>", "", text)
        return text

    def add_page(
        self,
        title: str,
        namespace_id: Optional[int],
        body: Optional[str] = None,
        redirect_to: Optional[str] = None,
        need_pre_expand: bool = False,
        model: Optional[str] = "wikitext",
    ) -> None:
        """Collects information about the page and save page text to a
        SQLite database file."""
        if model is None:
            model = "wikitext"
        if namespace_id:
            ns_prefix = self.LOCAL_NS_NAME_BY_ID.get(namespace_id, "") + ":"
        else:
            ns_prefix = ""
        if namespace_id != 0 and not title.startswith(ns_prefix):
            title = ns_prefix + title

        if title.startswith("Main:"):
            title = title[5:]

        if (
            namespace_id
            == self.NAMESPACE_DATA.get("Template", {"id": None}).get("id")
            and redirect_to is None
        ):
            body = self._template_to_body(title, body)

        self.db_conn.execute(
            """INSERT INTO pages (title, namespace_id, body,
        redirect_to, need_pre_expand, model) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(title, namespace_id) DO UPDATE SET
        body=excluded.body, redirect_to=excluded.redirect_to,
        need_pre_expand=excluded.need_pre_expand, model=excluded.model""",
            (title, namespace_id, body, redirect_to, need_pre_expand, model),
        )

    def analyze_templates(
        self,
        check_template_func: Callable[["Wtp", Page], tuple[set[str], bool]],
    ) -> None:
        """
        Analyzes templates to determine which of them might create elements
        essential to parsing Wikitext syntax, such as section heading nodes.
        Such templates generally need to be expanded before parsing the page.
        """

        logger.info(
            "Analyzing which templates should be expanded before parsing"
        )
        template_ns_data = self.NAMESPACE_DATA.get("Template")
        assert template_ns_data is not None
        template_ns_id = template_ns_data["id"]
        template_ns_local_name = template_ns_data["name"]
        expand_stack: list[Page] = []
        # the keys of included_map are template names without
        # the namespace prefix
        included_map: defaultdict[str, set[str]] = defaultdict(set)

        for page in self.get_all_pages([template_ns_id]):
            if page.body is not None:
                used_templates, pre_expand = check_template_func(self, page)
                for used_template in used_templates:
                    included_map[used_template].add(page.title)
                if pre_expand:
                    self.set_template_pre_expand(page.title)
                    expand_stack.append(page)

        # XXX consider encoding template bodies here (also need to save related
        # cookies).  This could speed up their expansion, where the first
        # operation is to encode them.  (Consider whether cookie numbers from
        # nested template expansions could conflict)

        # Propagate pre_expand from lower-level templates to all templates that
        # refer to them
        while len(expand_stack) > 0:
            page = expand_stack.pop()
            title_no_ns_prefix = page.title.removeprefix(
                template_ns_local_name + ":"
            )
            if title_no_ns_prefix not in included_map:
                continue

            for template_title in included_map[title_no_ns_prefix]:
                self.get_page.cache_clear()  # avoid infinite loop
                template = self.get_page(template_title, template_ns_id)
                if not template or template.need_pre_expand:
                    continue
                # print("propagating EXP {} -> {}".format(name, inc))
                self.set_template_pre_expand(template.title)
                expand_stack.append(template)

        # Also set `need_pre_expand` value for redirected source templates
        query_str = """
        UPDATE pages SET need_pre_expand = 1
        FROM pages AS dest
        WHERE pages.redirect_to = dest.title
        AND pages.namespace_id = dest.namespace_id
        AND dest.need_pre_expand = 1
        AND pages.need_pre_expand = 0
        """
        self.db_conn.execute(query_str)

        # set `need_pre_expand` value to redirected destination page
        query_str = """
        UPDATE pages SET need_pre_expand = 1
        FROM pages AS source
        WHERE pages.title = source.redirect_to
        AND pages.namespace_id = source.namespace_id
        AND source.need_pre_expand = 1
        AND pages.need_pre_expand = 0
        """
        self.db_conn.execute(query_str)
        self.db_conn.commit()

    def set_template_pre_expand(self, name: str) -> None:
        self.db_conn.execute(
            "UPDATE pages SET need_pre_expand = 1 WHERE title = ?", (name,)
        )

    def start_page(self, title: str) -> None:
        """Starts a new page for expanding Wikitext.  This saves the title and
        full page source in the context.  Calling this is mandatory
        for each page; expand_wikitext() can then be called multiple
        times for the same page.  This clears the self.errors,
        self.warnings, and self.debugs lists and any current section
        or subsection."""
        self.title = title
        self.errors = []
        self.warnings = []
        self.debugs = []
        self.section = None
        self.subsection = None
        self.cookies = []
        self.rev_ht = {}
        self.expand_stack = [title]
        if self.lua_clear_loaddata_cache is not None:
            self.lua_clear_loaddata_cache()
        self.lua_env_stack.clear()
        self.lua_frame_stack.clear()
        self.strip_marker_cache.clear()

    def start_section(self, title: Optional[str]) -> None:
        """Starts processing a new section of the current page.  Calling this
        is optional, but can help provide better error messages.  This clears
        any current subsection."""
        assert title is None or isinstance(title, str)
        self.section = title
        self.subsection = None

    def start_subsection(self, title: Optional[str]) -> None:
        """Starts processing a new subsection of the current section on the
        current page.  Calling this is optional, but can help provide better
        error messages."""
        assert title is None or isinstance(title, str)
        self.subsection = title

    def _unexpanded_template(self, args: Sequence[str], nowiki: bool) -> str:
        """Formats an unexpanded template (whose arguments may have been
        partially or fully expanded)."""
        if nowiki:
            return "&lbrace;&lbrace;" + "&vert;".join(args) + "&rbrace;&rbrace;"
        return "{{" + "|".join(args) + "}}"

    def _unexpanded_arg(self, args: Sequence[str], nowiki: bool) -> str:
        """Formats an unexpanded template argument reference."""
        if nowiki:
            return (
                "&lbrace;&lbrace;&lbrace;"
                + "&vert;".join(args)
                + "&rbrace;&rbrace;&rbrace;"
            )
        return "{{{" + "|".join(args) + "}}}"

    def _unexpanded_link(self, args: Sequence[str], nowiki: bool) -> str:
        """Formats an unexpanded link."""
        if nowiki:
            return "&lsqb;&lsqb;" + "&vert;".join(args) + "&rsqb;&rsqb;"
        return "[[" + "|".join(args) + "]]"

    def _unexpanded_extlink(self, args: Sequence[str], nowiki: bool) -> str:
        """Formats an unexpanded external link."""
        if nowiki:
            return "&lsqb;" + "&vert;".join(args) + "&rsqb;"
        return "[" + "|".join(args) + "]"

    def preprocess_text(self, text: str) -> str:
        """Preprocess the text by handling <nowiki> and comments."""
        assert isinstance(text, str)
        # print("PREPROCESS_TEXT: {!r}".format(text))

        def _nowiki_sub_fn(m: re.Match) -> CookieChar:
            """This function escapes the contents of a <nowiki> ... </nowiki>
            pair."""
            nowiki_content = m.group(1)
            return self._save_value("N", (nowiki_content,), True)

        text = re.sub(
            r"(?si)<nowiki\s*>(.*?)</nowiki\s*>", _nowiki_sub_fn, text
        )
        text = re.sub(r"(?si)<nowiki\s*/>", MAGIC_NOWIKI_CHAR, text)
        text = re.sub(r"(?s)<!--.*?-->", "", text)
        # print("PREPROCESSED_TEXT: {!r}".format(text))
        return text

    def expand(
        self,
        text: str,
        parent: Optional[ParentData] = None,
        pre_expand=False,
        template_fn: Optional[TemplateFnCallable] = None,
        post_template_fn: Optional[PostTemplateFnCallable] = None,
        templates_to_expand: Optional[Set[str]] = None,
        templates_to_not_expand: Optional[Set[str]] = None,
        expand_parserfns=True,
        expand_invoke=True,
        quiet=False,
        timeout: Optional[Union[int, float]] = None,
    ) -> str:
        """Expands templates and parser functions (and optionally Lua macros)
        from ``text`` (which is from page with title ``title``).
        ``templates_to_expand`` should be None to expand all
        templates, or a set or dictionary whose keys are those
        canonicalized template names that should be expanded; if
        ``pre_expand`` is set to True, then only templates needing
        pre-expansion before parsing plus those in
        ``templates_to_expand`` are expanded, ignoring those in
        ``templates_to_not_expand`` (which will preserve their name,
        so that they can be extracted later as a node).
        ``template_fn``, if given, will be be called as
        template_fn(name, args_ht) to expand templates;
        if it is not defined or returns None, the
        default expansion will be used (it can also be used to capture
        template arguments).  If ``post_template_fn`` is given, it
        will be called as post_template_fn(name, args_ht, expanded)
        and if it returns other than None, its return value will
        replace the template expansion.  This returns the text with
        the given templates expanded."""
        assert isinstance(text, str)
        assert parent is None or (
            isinstance(parent, tuple) and len(parent) == 2
        )
        assert pre_expand in (True, False)
        assert template_fn is None or callable(template_fn)
        assert post_template_fn is None or callable(post_template_fn)
        assert isinstance(templates_to_expand, (set, frozenset, type(None)))
        assert self.title is not None  # start_page() must have been called
        assert quiet in (False, True)
        assert timeout is None or isinstance(timeout, (int, float))

        # Handle <nowiki> in a preprocessing step
        text = self.preprocess_text(text)

        def invoke_fn(
            invoke_args: Sequence[str],
            expander: Callable,
            parent: Optional[ParentData],
        ) -> str:
            """This is called to expand a #invoke parser function."""
            assert isinstance(invoke_args, (list, tuple))
            assert callable(expander)
            assert isinstance(parent, tuple) or parent is None
            # print("INVOKE_FN", invoke_args, parent)
            # sys.stdout.flush()

            # Use the Lua sandbox to execute a Lua macro.  This will initialize
            # the Lua environment and store it in self.lua if it does not
            # already exist (it needs to be re-created for each new page).
            ret = call_lua_sandbox(self, invoke_args, expander, parent, timeout)
            # print("invoke_fn: invoke_args={} parent={} LUA ret={!r}"
            #       .format(invoke_args, parent, ret))
            return ret

        def expand_recurse(
            coded: str, parent: Optional[ParentData], expand_all: bool
        ) -> str:
            """This function does most of the work for expanding encoded
            templates, arguments, and parser functions."""
            assert isinstance(coded, str)
            assert parent is None or isinstance(parent, tuple)
            # print("parent = {!r}".format(parent))
            # print("expand_recurse coded={!r}".format(coded))

            def expand_args(coded: str, argmap: TemplateArgs) -> str:
                assert isinstance(coded, str)
                assert isinstance(argmap, dict)
                parts: list[str] = []
                pos = 0
                for m in MAGIC_RE_PATTERN.finditer(coded):
                    new_pos = m.start()
                    if new_pos > pos:
                        parts.append(coded[pos:new_pos])
                    pos = m.end()
                    ch = m.group(0)
                    idx = ord(ch) - MAGIC_FIRST
                    kind, args, nowiki = self.cookies[idx]
                    # print(f"{kind=}, {args=}, {argmap=}")
                    assert isinstance(args, tuple)
                    if nowiki:
                        # If this template/link/arg has <nowiki />, then just
                        # keep it as-is (it won't be expanded)
                        parts.append(ch)
                        continue
                    if kind == "T":
                        # Template transclusion or parser function call.
                        # Expand its arguments.
                        new_args = tuple(
                            expand_args(x, argmap).removesuffix("\n")
                            for x in args
                        )
                        parts.append(self._save_value(kind, new_args, nowiki))
                        continue
                    if kind == "A":
                        # Template argument reference
                        if len(args) > 2 and any(
                            len(arg.strip()) > 0 for arg in args[2:]
                        ):
                            self.debug(
                                "too many args ({}) in argument "
                                "reference: {!r}".format(len(args), args),
                                sortid="core/1021",
                            )
                        self.expand_stack.append("ARG-NAME")
                        k: Union[int, str]
                        k = expand_recurse(
                            expand_args(args[0], argmap), parent, True
                        ).strip()
                        self.expand_stack.pop()
                        if k.isdigit():
                            k = int(k)
                        else:
                            k = re.sub(r"\s+", " ", k).strip()
                        v = argmap.get(k, None)
                        if v is not None:
                            parts.append(v.removesuffix("\n"))
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
                        new_args = tuple(expand_args(x, argmap) for x in args)
                        parts.append(self._unexpanded_link(new_args, nowiki))
                        continue
                    if kind == "E":
                        # Link to another page
                        new_args = tuple(expand_args(x, argmap) for x in args)
                        parts.append(self._unexpanded_extlink(new_args, nowiki))
                        continue
                    if kind == "N":
                        parts.append(ch)
                        continue
                    self.error(
                        "expand_arg: unsupported cookie kind {!r} in {}".format(
                            kind, m.group(0)
                        ),
                        sortid="core/1062",
                    )
                    parts.append(m.group(0))
                parts.append(coded[pos:])
                # print(f"{parts=}")

                return "".join(parts)

            def expand_parserfn(fn_name: str, args: Sequence[str]) -> str:
                if not expand_parserfns:
                    if not args:
                        return "{{" + fn_name + "}}"
                    return "{{" + fn_name + ":" + "|".join(args) + "}}"
                # Call parser function
                self.expand_stack.append(fn_name)

                def expander(arg: str) -> str:
                    return expand_recurse(arg, parent, True)

                if fn_name in self.invoke_aliases:
                    if not expand_invoke:
                        return "{{#invoke:" + "|".join(args) + "}}"
                    ret = invoke_fn(args, expander, parent)
                    # print(f"invoke: {ret=!r}")
                else:
                    ret = call_parser_function(self, fn_name, args, expander)
                self.expand_stack.pop()  # fn_name
                # XXX if lua code calls frame:preprocess(), then we should
                # apparently encode and expand the return value, similarly to
                # template bodies (without argument expansion)
                # XXX current implementation of preprocess() does not match!!!
                return str(ret)

            # Main code of expand_recurse()
            parts: list[str] = []
            pos = 0
            for m in MAGIC_RE_PATTERN.finditer(coded):
                new_pos = m.start()
                if new_pos > pos:
                    parts.append(coded[pos:new_pos])
                pos = m.end()
                ch = m.group(0)
                idx = ord(ch) - MAGIC_FIRST
                if idx >= len(self.cookies):
                    # not found in the cookies
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
                        self.error(
                            "too deep recursion during template expansion",
                            sortid="core/1115",
                        )
                        parts.append(
                            '<strong class="error">too deep recursion '
                            "while expanding template {}</strong>".format(
                                self._unexpanded_template(args, True)
                            )
                        )
                        continue

                    # Expand template/parserfn name
                    self.expand_stack.append("TEMPLATE_NAME")
                    tname = expand_recurse(args[0], parent, expand_all)
                    self.expand_stack.pop()

                    # Remove <noinvoke/>

                    tname = re.sub(r"<noinclude\s*/>", "", tname)

                    # Strip safesubst: and subst: prefixes
                    # XXX if safesubst -> invert expand mode and strip
                    # 'safesubst:' from tname
                    # XXX if subst -> invert expand mode, strip
                    # only if expand mode is true
                    tname = (
                        tname.strip()
                        .removeprefix("subst:")
                        .removeprefix("SUBST:")
                        .removeprefix("safesubst:")
                        .removeprefix("SAFESUBST:")
                    )

                    # Check if it is a parser function call
                    ofs = tname.find(":")
                    if ofs > 0:
                        # It might be a parser function call
                        fn_name = self._canonicalize_parserfn_name(tname[:ofs])
                        # Check if it is a recognized parser function name
                        if fn_name in PARSER_FUNCTIONS or fn_name.startswith(
                            "#"
                        ):
                            self.expand_stack.append(fn_name)
                            ret = expand_parserfn(
                                fn_name, (tname[ofs + 1 :].lstrip(),) + args[1:]
                            )
                            self.expand_stack.pop()
                            parts.append(ret)
                            continue

                    # As a compatibility feature, recognize parser functions
                    # also as the first argument of a template (without colon),
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

                    if name in self.template_override_funcs and not nowiki:
                        # print("Name in template_overrides: {}".format(name))
                        new_args = tuple(
                            expand_recurse(x, parent, expand_all) for x in args
                        )
                        parts.append(
                            self.template_override_funcs[name](
                                new_args,
                            )
                        )
                        continue

                    # If this template is not one of those we want to expand,
                    # return it unexpanded (but with arguments possibly
                    # expanded)
                    if not expand_all and not self.check_template_need_expand(
                        name, templates_to_expand, templates_to_not_expand
                    ):
                        # Note: we will still expand parser functions in its
                        # arguments, because those parser functions could
                        # refer to its parent frame and fail if expanded
                        # after eliminating the intermediate templates.
                        new_args = tuple(
                            expand_recurse(x, parent, expand_all) for x in args
                        )
                        parts.append(
                            self._unexpanded_template(new_args, nowiki)
                        )
                        continue

                    # Construct and expand template arguments
                    self.expand_stack.append("Template:" + name)
                    if detect_expand_template_loop(self.expand_stack):
                        parts.append(
                            '<strong class="error">Template loop detected: '
                            f"[[:Template:{name}]]</strong>"
                        )
                        self.expand_stack.pop()
                        self.warning(
                            f"Template loop detected: {name}",
                            sortid="core/1422",
                        )
                        continue
                    ht: TemplateArgs = {}
                    num = 1
                    for i in range(1, len(args)):
                        arg = str(args[i])
                        k: Union[str, int]
                        m2 = re.match(
                            r"""(?s)^\s*([^][&<>="]+?)\s*=\s*(.*?)\s*$""",
                            arg,
                        )
                        if m2:
                            # Note: Whitespace is stripped by the regexp
                            # around named parameter names and values per
                            # https://en.wikipedia.org/wiki/Help:Template
                            # (but not around unnamed parameters)
                            k, arg = m2.groups()
                            if k.isdigit():
                                k = int(k)
                            else:
                                self.expand_stack.append("ARGNAME")
                                k = expand_recurse(k, parent, True)
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
                        arg = expand_recurse(arg, parent, True)
                        self.expand_stack.pop()
                        ht[k] = arg

                    # Expand the body, either using ``template_fn`` or using
                    # normal template expansion
                    t: Optional[str] = None
                    # print("EXPANDING TEMPLATE: {} {}".format(name, ht))
                    if template_fn is not None:
                        self.expand_stack.append("TEMPLATE_FN")
                        t = template_fn(urllib.parse.unquote(name), ht)
                        self.expand_stack.pop()
                        # print("TEMPLATE_FN {}: {} {} -> {}"
                        #      .format(template_fn, name, ht, repr(t)))
                    if t is None:
                        template_ns = self.NAMESPACE_DATA["Template"]
                        ns_id = template_ns["id"]
                        if ":" in name:
                            # https://www.mediawiki.org/wiki/Help:Templates#Usage
                            # transclude page {{:ns_name:title}} or {{:title}}
                            name = name.removeprefix(":")
                            if ":" in name:
                                ns_id = self.NAMESPACE_DATA.get(
                                    name[: name.find(":")], {}
                                ).get("id", ns_id)  # type: ignore
                            else:  # main namespace
                                ns_id = 0

                        template_page = self.get_page_resolve_redirect(
                            name, ns_id
                        )
                        if template_page is not None:
                            body = template_page.body
                            if TYPE_CHECKING:
                                assert body is not None
                            # XXX optimize by pre-encoding bodies during
                            # preprocessing
                            # (Each template is typically used many times)
                            # Determine if the template starts with a list item
                            if body.startswith(("#", "*", ";", ":")):
                                body = "\n" + body
                            body = self.preprocess_text(body)
                            encoded_body = self._encode(body)
                            # Expand template arguments recursively.
                            # The arguments are already expanded.
                            encoded_body = expand_args(encoded_body, ht)
                            # Expand the body using the calling template/page
                            # as the parent frame for any parserfn calls
                            new_parent = (template_page.title, ht)
                            # print("expanding template body for {} {}"
                            #       .format(name, ht))
                            # XXX no real need to expand here, it will expanded
                            #  on next iteration anyway (assuming parent
                            # unchanged). Otherwise expand the body
                            t = expand_recurse(
                                encoded_body, new_parent, expand_all
                            )
                        else:
                            # template doesn't exist
                            t = f"[[:{template_ns['name']}:{name}]]"

                    # If a post_template_fn has been supplied, call it now
                    # to capture or alter the expansion
                    # print("TEMPLATE EXPANDED: {} {} -> {!r}"
                    #       .format(name, ht, t))
                    t = add_newline_to_expansion(t)
                    if post_template_fn is not None and t:
                        t2 = post_template_fn(urllib.parse.unquote(name), ht, t)
                        if t2 is not None:
                            t = t2

                    assert isinstance(t, str)  # No body
                    self.expand_stack.pop()  # template name
                    parts.append(t)
                elif kind == "A":
                    if nowiki:
                        parts.append(self._unexpanded_arg(args, nowiki))
                        continue
                    self.expand_stack.append("ARGVAL-NO-TEMPLATE")
                    t = expand_args(ch, {})
                    self.expand_stack.pop()
                    parts.append(t)
                    continue
                elif kind == "L":
                    if nowiki:
                        parts.append(self._unexpanded_link(args, nowiki))
                    else:
                        # Link to another page
                        self.expand_stack.append("[[link]]")
                        new_args = tuple(
                            expand_recurse(x, parent, expand_all) for x in args
                        )
                        self.expand_stack.pop()
                        parts.append(self._unexpanded_link(new_args, nowiki))
                elif kind == "E":
                    if nowiki:
                        parts.append(self._unexpanded_extlink(args, nowiki))
                    else:
                        # Link to an external page
                        self.expand_stack.append("[extlink]")
                        new_args = tuple(
                            expand_recurse(x, parent, expand_all) for x in args
                        )
                        self.expand_stack.pop()
                        parts.append(self._unexpanded_extlink(new_args, nowiki))
                elif kind == "N":
                    parts.append(ch)
                else:
                    self.error(
                        "expand: unsupported cookie kind {!r} in {}".format(
                            kind, m.group(0)
                        ),
                        sortid="core/1334",
                    )
                    parts.append(m.group(0))
            parts.append(coded[pos:])
            return "".join(parts)

        # Encode all template calls, template arguments, and parser function
        # calls on the page.  This is an inside-out operation.
        encoded = self._encode(text)

        # Recursively expand the selected templates.  This is an outside-in
        # operation.
        expanded = expand_recurse(encoded, parent, not pre_expand)

        # Expand any remaining magic cookies and remove nowiki char
        expanded = self._finalize_expand(expanded)

        # Remove LanguageConverter markups:
        # https://www.mediawiki.org/wiki/Writing_systems/Syntax
        # but ignore `-{}-` template argument placeholder: #59
        if not pre_expand and self.lang_code == "zh" and text != "-{}-":
            expanded = expanded.replace("-{", "").replace("}-", "")

        return expanded

    def _finalize_expand(self, text: str) -> str:
        """Expands any remaining magic characters (to their original values)
        and removes nowiki characters."""
        # print("_finalize_expand: {!r}".format(text))

        def magic_repl(m: re.Match) -> str:
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
                if not args[0]:
                    return "<nowiki/>"
                return nowiki_quote(args[0])
            self.error(
                "magic_repl: unsupported cookie kind {!r}".format(kind),
                sortid="core/1373",
            )
            return ""

        # Keep expanding magic cookies until they have all been expanded.
        # We might get them from, e.g., unexpanded_template()
        while True:
            prev = text
            text = MAGIC_RE_PATTERN.sub(magic_repl, text)
            if prev == text:
                break

        # Convert the special <nowiki /> character back to <nowiki />.
        # This is done at the end of normal expansion.
        text = text.replace(MAGIC_NOWIKI_CHAR, "<nowiki />")

        # broken external url kludge: we don't want to have external
        # urls that are not correct, but we can't just return the
        # brackets as is inside the substitution loop, because that breaks
        # the loop, so we replace the characters and now return them.
        text = text.replace(MAGIC_LBRACKET_CHAR, "[")
        text = text.replace(MAGIC_RBRACKET_CHAR, "]")
        # print("    _finalize_expand:{!r}".format(text))
        return text

    @lru_cache(maxsize=1000)
    def get_page(
        self,
        title: str,
        namespace_id: Optional[int] = None,
        no_redirect: bool = False,
    ) -> Optional[Page]:
        # " " in Lua Module name is replaced by "_" in Wiktionary Lua code
        # when call `require`
        title = title.replace("_", " ")
        if title.startswith("Main:"):
            title = title[5:]
        if len(title) == 0:
            return None

        upper_case_title = title  # the first letter is upper case
        if namespace_id is not None and namespace_id != 0:
            local_ns_name = self.LOCAL_NS_NAME_BY_ID[namespace_id]
            ns_prefix = local_ns_name + ":"
            if not title.startswith(ns_prefix):
                if title.lower().startswith(
                    self.namespace_prefixes(namespace_id)
                ):
                    # replace lower case and alias prefix
                    title = ns_prefix + title[title.index(":") + 1 :]
                else:
                    title = ns_prefix + title

            # page title is case-sensitive except the first character
            # https://www.mediawiki.org/wiki/Manual:Page_title#Naming_restrictions
            template_name = title[len(ns_prefix) :]
            upper_case_title = (
                ns_prefix + template_name[0].upper() + template_name[1:]
            )

        query_str = """
        SELECT title, namespace_id, redirect_to, need_pre_expand, body, model
        FROM pages
        WHERE title = ?
        """
        query_values: list[Union[str, int]] = [title]
        if namespace_id is not None:
            query_str += " AND namespace_id = ?"
            query_values.append(namespace_id)
        if no_redirect:
            query_str += " AND redirect_to IS NULL"
        if upper_case_title != title:
            query_str = query_str + " UNION ALL " + query_str
            query_values = query_values + [upper_case_title] + query_values[1:]

        query_str += " LIMIT 1"
        try:
            for result in self.db_conn.execute(query_str, tuple(query_values)):
                return Page(
                    title=result[0],
                    namespace_id=result[1],
                    redirect_to=result[2],
                    need_pre_expand=result[3] == 1,
                    body=result[4],
                    model=result[5],
                )
        except sqlite3.ProgrammingError as e:
            raise sqlite3.ProgrammingError(
                f"{' '.join(e.args)}"
                f" Current database file path: {self.db_path}"
            ) from e
        return None

    def page_exists(self, title: str, namespace_id: Optional[int] = 0) -> bool:
        return self.get_page(title, namespace_id) is not None

    def get_all_pages(
        self,
        namespace_ids: Optional[list[int]] = None,
        include_redirects: bool = True,
        model: Optional[str] = None,
        search_pattern: Optional[str] = None,
    ) -> Iterator[Page]:
        query_str = """
        SELECT title, namespace_id, redirect_to, need_pre_expand, body, model
        FROM pages
        """
        where_str, query_values = self.build_sql_where_query(
            namespace_ids, include_redirects, model, search_pattern
        )
        query_str += where_str  # + " ORDER BY title ASC"
        # Seems that ORDER BY title doesn't actually matter in this case;
        # for other orderings it does, title just happens to be default
        # print("Getting all pages for query:"
        #       f"{query_str=!r}, {placeholders=!r}")

        for result in self.db_conn.execute(query_str, query_values):
            yield Page(
                title=result[0],
                namespace_id=result[1],
                redirect_to=result[2],
                need_pre_expand=result[3],
                body=result[4],
                model=result[5],
            )

    def check_template_need_expand(
        self,
        name: str,
        expand_names: Optional[Set[str]] = None,
        not_expand_names: Optional[Set[str]] = None,
    ) -> bool:
        page = self.get_page(name, self.NAMESPACE_DATA["Template"]["id"])
        if page is None:
            return False

        if expand_names is None and not_expand_names is not None:
            return name not in not_expand_names and page.need_pre_expand
        if expand_names is not None and not_expand_names is None:
            return name in expand_names or page.need_pre_expand
        if expand_names is not None and not_expand_names is not None:
            return name not in not_expand_names and (
                name in expand_names or page.need_pre_expand
            )

        return page.need_pre_expand

    def get_page_resolve_redirect(
        self, title: str, namespace_id: Optional[int]
    ) -> Optional[Page]:
        page = self.get_page(title, namespace_id)
        if page is None:
            return None
        if page.redirect_to is not None:
            return self.get_page(page.redirect_to, namespace_id, True)
        return page

    def get_page_body(
        self, title: str, namespace_id: Optional[int]
    ) -> Optional[str]:
        page = self.get_page_resolve_redirect(title, namespace_id)
        return None if page is None else page.body

    def parse(
        self,
        text: str,
        pre_expand=False,
        expand_all=False,
        additional_expand: Optional[set[str]] = None,
        do_not_pre_expand: Optional[set[str]] = None,
        template_fn: Optional[TemplateFnCallable] = None,
        post_template_fn: Optional[PostTemplateFnCallable] = None,
    ) -> WikiNode:
        """Parses the given text into a parse tree (WikiNode tree).  If
        ``pre_expand`` is True, then before parsing this will expand
        those templates that have been detected to potentially
        influence the parsing results (e.g., they might produce table
        start or end or table rows).  Likewise, if ``expand_all`` is
        True, this will expand all templates that have definitions
        (usually all of them).  If ``additional_expand`` is given, it
        should be a set of additional templates to expand, and
        ``do_not_pre_expand`` is the opposite and shouldn't be.  Parser
        function calls and Lua macro invocations are expanded if they
        are inside expanded templates."""
        assert isinstance(text, str)
        assert pre_expand in (True, False)
        assert expand_all in (True, False)
        assert additional_expand is None or isinstance(
            additional_expand, (set, frozenset)
        )
        assert do_not_pre_expand is None or isinstance(
            do_not_pre_expand, (set, frozenset)
        )

        # Preprocess.  This may also add some MAGIC_NOWIKI_CHARs.
        text = self.preprocess_text(text)

        # Expand some or all templates in the text as requested
        if expand_all:
            text = self.expand(
                text, template_fn=template_fn, post_template_fn=post_template_fn
            )
            text = self.preprocess_text(text)
            # print(f"PARSE EXPAND ALL: {text=!r}")
        elif pre_expand or additional_expand:
            text = self.expand(
                text,
                pre_expand=pre_expand,
                templates_to_expand=additional_expand,
                templates_to_not_expand=do_not_pre_expand,
                template_fn=template_fn,
                post_template_fn=post_template_fn,
            )
            text = self.preprocess_text(text)

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

    def node_to_wikitext(
        self,
        node: GeneralNode,
        node_handler_fn: Optional[NodeHandlerFnCallable] = None,
    ) -> str:
        """Converts the given parse tree node back to Wikitext."""
        v = to_wikitext(node, node_handler_fn=node_handler_fn)
        return v

    def node_to_html(
        self,
        node: GeneralNode,
        template_fn: Optional[TemplateFnCallable] = None,
        post_template_fn: Optional[PostTemplateFnCallable] = None,
        node_handler_fn: Optional[NodeHandlerFnCallable] = None,
    ) -> str:
        """Converts the given parse tree node to HTML."""
        return to_html(
            self,
            node,
            template_fn=template_fn,
            post_template_fn=post_template_fn,
            node_handler_fn=node_handler_fn,
        )

    def node_to_text(
        self,
        node,
        template_fn=None,
        post_template_fn=None,
        node_handler_fn=None,
    ):
        """Converts the given parse tree node to plain text."""
        return to_text(
            self,
            node,
            template_fn=template_fn,
            post_template_fn=post_template_fn,
            node_handler_fn=node_handler_fn,
        )

    def namespace_prefixes(
        self, ns_id: int, lower: bool = True, suffix: str = ":"
    ) -> tuple[str, ...]:
        """Based on given namespace name, create a tuple of aliases"""
        for ns, ns_data in self.NAMESPACE_DATA.items():
            if ns_data["id"] == ns_id:
                prefixes = tuple(
                    map(
                        lambda x: x.lower() + suffix if lower else x + suffix,
                        [ns_data["name"]] + ns_data["aliases"],
                    )
                )
                if ns != ns_data["name"]:
                    if lower:
                        ns = ns.lower()
                    prefixes += (ns + suffix,)
                return prefixes

        return ()

    def create_strip_marker(self, node: str, content: str) -> str:
        # https://www.mediawiki.org/wiki/Strip_marker
        # GitHub issue tatuylonen/wiktextract#238
        if node == "nowiki":
            num = self.strip_marker_cache.get(node, 0)
            num_str = format(num, "08x")
            self.strip_marker_cache[node] = num + 1
        else:
            num = self.strip_marker_cache.get(
                content, self.strip_marker_cache.get("preprocess", 0)
            )
            num_str = str(num)
            if content not in self.strip_marker_cache:
                self.strip_marker_cache["preprocess"] += 1
                self.strip_marker_cache[content] = num
        return f"""\x7f'"`UNIQ--{node}-{num_str}-QINU`"'\x7f"""


def detect_expand_template_loop(stack: list[str]) -> bool:
    stack_len = len(stack)
    if stack_len < 2 or stack[-1] not in stack[:-1]:
        return False
    for size in range(1, stack_len // 2 + 1):
        for i in range(stack_len - size):
            if (stack_len - i) % size == 0:
                pattern = stack[i : i + size]
                if pattern * ((stack_len - i) // size) == stack[i:]:
                    return True
    return False
