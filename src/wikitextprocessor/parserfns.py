# Definitions for various parser functions supported in WikiText
#
# Copyright (c) 2020-2022 Tatu Ylonen.  See file LICENSE and https://ylonen.org

import html
import math
import re
import urllib.parse
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Union

import dateparser

from .common import MAGIC_NOWIKI_CHAR, add_newline_to_expansion, nowiki_quote
from .interwiki import get_interwiki_map

if TYPE_CHECKING:
    # Reached only by mypy or other type-checker
    from .core import Wtp

# https://www.mediawiki.org/wiki/Help:Extension:ParserFunctions
# https://www.mediawiki.org/wiki/Help:Magic_words


def capitalizeFirstOnly(s: str) -> str:
    if s:
        s = s[0].upper() + s[1:]
    return s


def if_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements #if parser function."""
    # print(f"if_fn: {args}")
    arg0: str = args[0] if args else ""
    arg1: str = args[1] if len(args) >= 2 else ""
    arg2: str = args[2] if len(args) >= 3 else ""
    v: str = expander(arg0).strip()
    if v:
        return expander(arg1).strip()
    return expander(arg2).strip()


def ifeq_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements #ifeq parser function."""
    arg0: str = args[0] if args else ""
    arg1: str = args[1] if len(args) >= 2 else ""
    arg2: str = args[2] if len(args) >= 3 else ""
    arg3: str = args[3] if len(args) >= 4 else ""
    if expander(arg0).strip() == expander(arg1).strip():
        return expander(arg2).strip()
    return expander(arg3).strip()


def iferror_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the #iferror parser function."""
    arg0: str = expander(args[0]) if args else ""
    arg1: Optional[str] = args[1] if len(args) >= 2 else None
    arg2: Optional[str] = args[2] if len(args) >= 3 else None
    if re.search(r'<[^>]*?\sclass="error"', arg0):
        if arg1 is None:
            return ""
        return expander(arg1).strip()
    if arg2 is None:
        return arg0
    return expander(arg2).strip()


def ifexpr_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements #ifexpr parser function."""
    arg0: str = args[0] if args else "0"
    arg1: str = args[1] if len(args) >= 2 else ""
    arg2: str = args[2] if len(args) >= 3 else ""
    cond: str = expr_fn(ctx, fn_name, [arg0], expander)
    try:
        ret: int = int(cond)
    except ValueError:
        ret = 0
    if ret:
        return expander(arg1).strip()
    return expander(arg2).strip()


def ifexist_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements #ifexist parser function."""
    arg0 = args[0] if args else ""
    arg1 = args[1] if len(args) >= 2 else ""
    arg2 = args[2] if len(args) >= 3 else ""
    if ctx.get_page(expander(arg0).strip()) is not None:
        return expander(arg1).strip()
    return expander(arg2).strip()


def switch_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements #switch parser function."""
    val = expander(args[0]).strip() if args else ""
    match_next = False
    defval: Optional[str] = None
    last: Optional[str] = None
    for i in range(1, len(args)):
        arg = args[i]
        m = re.match(r"(?s)^([^=]*)=(.*)$", arg)
        if not m:
            last = expander(arg).strip()
            if last == val:
                match_next = True
            continue
        k, v = m.groups()
        k = expander(k).strip()
        if k == val or match_next:
            return expander(v).strip()
        if k.lower() == "#default":
            defval = v
        last = None
    if defval is not None:
        return expander(defval).strip()
    return last or ""


def categorytree_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable
) -> str:
    """Implements the #categorytree parser function.  This function accepts
    keyed arguments."""
    assert isinstance(args, dict)
    # We don't currently really implement categorytree.  It is just recognized
    # and silently ignored.
    return ""


def lst_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """
    Implements the #lst (alias #section etc) parser function.

    https://www.mediawiki.org/wiki/Extension:Labeled_Section_Transclusion#Transclude_any_marked_part
    """
    pagetitle = expander(args[0]).strip() if args else ""
    chapter = expander(args[1]).strip() if len(args) >= 2 else ""
    text = ctx.get_page_body(pagetitle, 0)
    if text is None:
        ctx.warning(
            "{} trying to transclude chapter {!r} from non-existent "
            "page {!r}".format(fn_name, chapter, pagetitle),
            sortid="parserfns/132",
        )
        return ""

    parts: list[str] = []
    for m in re.finditer(
        r'(?si)<section\s+begin="?{}"?\s*/>(.*?)<section\s+end="?{}"?\s*/>'.format(
            re.escape(chapter), re.escape(chapter)
        ),
        text,
    ):
        parts.append(m.group(1))
    if not parts:
        ctx.warning(
            "{} could not find chapter {!r} on page {!r}".format(
                fn_name, chapter, pagetitle
            ),
            sortid="parserfns/146",
        )
    return "".join(parts)


def tag_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements #tag parser function."""
    tag = expander(args[0]).lower() if args else ""
    if tag not in ctx.allowed_html_tags and tag != "nowiki":
        ctx.warning(
            "#tag creating non-allowed tag <{}> - omitted".format(tag),
            sortid="parserfns/156",
        )
        return "{{" + fn_name + ":" + "|".join(args) + "}}"
    content = expander(args[1]) if len(args) >= 2 else ""
    attrs = []
    if len(args) > 2:
        for x in args[2:]:
            x = expander(x)
            m = re.match(r"""(?s)^([^=<>'"]+)=(.*)$""", x)
            if not m:
                ctx.warning(
                    "invalid attribute format {!r} missing name".format(x),
                    sortid="parserfns/167",
                )
                continue
            name, value = m.groups()
            if not value.startswith('"') and not value.startswith("'"):
                value = '"' + html.escape(value, quote=True) + '"'
            attrs.append("{}={}".format(name, value))
    if attrs:
        attrs_str = " " + " ".join(attrs)
    else:
        attrs_str = ""
    if not content:
        ret = "<{}{} />".format(tag, attrs_str)
    else:
        ret = "<{}{}>{}</{}>".format(tag, attrs_str, content, tag)
    if tag == "nowiki":
        if len(args) == 0:
            ret = MAGIC_NOWIKI_CHAR
        else:
            ret = nowiki_quote(content)
    return ret


def fullpagename_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the FULLPAGENAME magic word/parser function."""
    t = expander(args[0]) if args else ctx.title or "PAGENAME_ERROR"
    t = re.sub(r"\s+", " ", t)
    t = t.strip()
    ofs = t.find(":")
    if ofs == 0:
        # t = capitalizeFirstOnly(t[1:])
        t = t[1:]
    elif ofs > 0:
        ns = capitalizeFirstOnly(t[:ofs])
        # t = capitalizeFirstOnly(t[ofs + 1:])
        t = t[ofs + 1 :]
        t = ns + ":" + t
    # else:
    #    t = capitalizeFirstOnly(t)
    return t


def fullpagenamee_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the FULLPAGENAMEE magic word/parser function."""
    t = fullpagename_fn(ctx, fn_name, args, expander)
    return wikiurlencode(t)


def pagenamee_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the PAGENAMEE magic word/parser function."""
    t = pagename_fn(ctx, fn_name, args, expander)
    return wikiurlencode(t)


def rootpagenamee_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the ROOTPAGENAMEE magic word/parser function."""
    t = rootpagename_fn(ctx, fn_name, args, expander)
    return wikiurlencode(t)


def pagename_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the PAGENAME magic word/parser function."""
    t = expander(args[0]) if args else ctx.title or "PAGENAME_ERROR"
    t = re.sub(r"\s+", " ", t)
    t = t.strip()
    ofs = t.find(":")
    if ofs >= 0:
        # t = capitalizeFirstOnly(t[ofs + 1:])
        t = t[ofs + 1 :]
    # else:
    #    t = capitalizeFirstOnly(t)
    return t


def basepagename_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the BASEPAGENAME magic word/parser function."""
    t = expander(args[0]) if args else ctx.title or "PAGENAME_ERROR"
    t = re.sub(r"\s+", " ", t)
    t = t.strip()
    ofs = t.rfind("/")
    if ofs >= 0:
        t = t[:ofs]
    return pagename_fn(ctx, fn_name, [t], lambda x: x)


def rootpagename_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the ROOTPAGENAME magic word/parser function."""
    t = expander(args[0]) if args else ctx.title or "PAGENAME_ERROR"
    t = re.sub(r"\s+", " ", t)
    t = t.strip()
    ofs = t.find("/")
    if ofs >= 0:
        t = t[:ofs]
    return pagename_fn(ctx, fn_name, [t], lambda x: x)


def subpagename_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the SUBPAGENAME magic word/parser function."""
    t = expander(args[0]) if args else ctx.title or "PAGENAME_ERROR"
    t = re.sub(r"\s+", " ", t)
    t = t.strip()
    ofs = t.rfind("/")
    if ofs >= 0:
        return t[ofs + 1 :]
    else:
        return pagename_fn(ctx, fn_name, [t], lambda x: x)


def talkpagename_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the TALKPAGENAME magic word."""
    if ctx.title is not None:
        ofs = ctx.title.find(":")
    else:
        return "ERROR_PAGENAME"
    if ofs < 0:
        return ctx.NAMESPACE_DATA["Talk"]["name"] + ":" + ctx.title
    else:
        prefix = ctx.title[:ofs]
        if prefix not in ctx.NAMESPACE_DATA:
            return ctx.NAMESPACE_DATA["Talk"]["name"] + ":" + ctx.title
        return (
            ctx.NAMESPACE_DATA[prefix + " talk"]["name"]
            + ":"
            + ctx.title[ofs + 1 :]
        )


def namespacenumber_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the NAMESPACENUMBER magic word/parser function."""
    # XXX currently hard-coded to return the name space number for the Main
    # namespace
    return "0"


def namespace_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the NAMESPACE magic word/parser function."""
    t = expander(args[0]) if args else ctx.title or "ERROR_NAMESPACE"
    t = re.sub(r"\s+", " ", t)
    t = t.strip()
    ofs = t.find(":")
    if ofs >= 0:
        ns = capitalizeFirstOnly(t[:ofs])
        if ns == "Project":
            return ctx.NAMESPACE_DATA["Project"]["name"]
        return ns
    return ""


def subjectspace_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the SUBJECTSPACE magic word/parser function.  This
    implementation is very minimal."""
    t = expander(args[0]) if args else ctx.title or "ERROR_NAMESPACE"
    for prefix in ctx.NAMESPACE_DATA:
        if t.startswith(prefix + ":"):
            return prefix
    return ""


def talkspace_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the TALKSPACE magic word/parser function.  This
    implementation is very minimal."""
    t = expander(args[0]) if args else ctx.title or "ERROR_NAMESPACE"
    for prefix in ctx.NAMESPACE_DATA:
        if t.startswith(prefix + ":"):
            return ctx.NAMESPACE_DATA[prefix + " talk"]["name"]
    return ctx.NAMESPACE_DATA["Talk"]["name"]


def server_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the SERVER magic word."""
    return "//" + servername_fn(ctx, fn_name, args, expander)


def servername_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the SERVERNAME magic word."""
    return f"{ctx.lang_code}.{ctx.project}.org"


def currentyear_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the CURRENTYEAR magic word."""
    return str(datetime.now(timezone.utc).year)


def currentmonth_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the CURRENTMONTH magic word."""
    return datetime.now(timezone.utc).strftime("%m")


def currentmonth1_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the CURRENTMONTH1 magic word."""
    return str(datetime.now(timezone.utc).month)


def currentmonthname_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the CURRENTMONTHNAME magic word."""
    # XXX support for other languages?
    return datetime.now(timezone.utc).strftime("%B")


def currentmonthabbrev_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the CURRENTMONTHABBREV magic word."""
    # XXX support for other languages?
    return datetime.now(timezone.utc).strftime("%b")


def currentday_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the CURRENTDAY magic word."""
    return str(datetime.now(timezone.utc).day)


def currentday2_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the CURRENTDAY2 magic word."""
    return datetime.now(timezone.utc).strftime("%d")


def currentdow_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    return str(datetime.now(timezone.utc).isoweekday() % 7)


def currentdayname_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the CURRENTDAYNAME magic word."""
    return datetime.now(timezone.utc).strftime("%A")


def currenttime_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the CURRENTTIME magic word."""
    return datetime.now(timezone.utc).strftime("%H:%M")


def currenthour_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the CURRENTHOUR magic word."""
    return datetime.now(timezone.utc).strftime("%H")


def currentweek_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the CURRENTWEEK magic word."""
    return datetime.now(timezone.utc).strftime("%W")


def localweek_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the LOCALWEEK magic word."""
    return datetime.now(timezone.utc).astimezone().strftime("%W")


def local_timestamp_fn(
    wtp: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the LOCALTIMESTAMP magic word."""
    return (
        datetime.now(timezone.utc)
        .astimezone()
        .strftime(MEDIAWIKI_TIMESTAMP_FORMAT)
    )


def revisionid_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the REVISIONID magic word."""
    # We just return a dash, similar to "miser mode" in MediaWiki."""
    return "-"


def revisionuser_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the REVISIONUSER magic word."""
    # We always return AnonymousUser
    return "AnonymousUser"


def displaytitle_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the DISPLAYTITLE magic word/parser function."""
    # t = expander(args[0]) if args else ""
    # XXX this should at least remove html tags h1 h2 h3 h4 h5 h6 div blockquote
    # ol ul li hr table tr th td dl dd caption p ruby rb rt rtc rp br
    # Looks as if this should also set the display title for the page in ctx???
    # XXX I think this parser function exists for the side effect of
    # setting page title
    return ""


def defaultsort_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the DEFAULTSORT magic word/parser function."""
    # XXX apparently this should set the title by which this page is
    # sorted in category listings
    return ""


def lc_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the lc parser function (lowercase)."""
    return expander(args[0]).strip().lower() if args else ""


def lcfirst_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the lcfirst parser function (lowercase first character)."""
    t = expander(args[0]).strip() if args else ""
    if not t:
        return t
    return t[0].lower() + t[1:]


def uc_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the uc parser function (uppercase)."""
    t = expander(args[0]).strip() if args else ""
    return t.upper()


def ucfirst_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the ucfirst parser function (capitalize first character)."""
    t = expander(args[0]).strip() if args else ""
    return capitalizeFirstOnly(t)


def formatnum_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the formatnum parser function."""
    arg0 = expander(args[0]).strip() if args else ""
    arg1 = expander(args[1]).strip() if len(args) >= 2 else ""
    if arg1 == "R":
        # Reverse formatting
        # XXX this is a very simplified implementation, should handle more cases
        return arg0.replace(",", "")
    if arg1 == "NOSEP":
        sep = ""
    else:
        sep = ","
    comma = "."  # Really should depend on locale
    # XXX implement support for non-english locales for digits
    orig = arg0.split(".")
    first = orig[0]
    parts = []
    first = "".join(reversed(first))
    for i in range(0, len(first), 3):
        parts.append("".join(reversed(first[i : i + 3])))
    parts = [sep.join(reversed(parts))]
    if len(orig) > 1:
        parts.append(comma)
        parts.append(".".join(orig[1:]))
    return "".join(parts)


def dateformat_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the #dateformat (= #formatdate) parser function."""
    arg0 = expander(args[0]) if args else ""
    arg0x = arg0
    if not re.search(r"\d\d\d", arg0x):
        arg0x += " 3333"
    dt = dateparser.parse(arg0x)
    if not dt:
        # It seems this should return invalid dates as-is
        return arg0
    fmt = expander(args[1]) if len(args) > 1 else "ISO 8601"
    # This is supposed to format according to user preferences by default.
    if fmt in ("ISO 8601", "ISO8601") and dt.year == 0:
        fmt = "mdy"
    date_only = dt.hour == 0 and dt.minute == 0 and dt.second == 0
    if fmt == "mdy":
        if date_only:
            if dt.year == 3333:
                return dt.strftime("%b %d")
            return dt.strftime("%b %d, %Y")
        return dt.strftime("%b %d, %Y %H:%M:%S")
    elif fmt == "dmy":
        if date_only:
            if dt.year == 3333:
                return dt.strftime("%d %b")
            return dt.strftime("%d %b %Y")
        return dt.strftime("%d %b %Y %H:%M:%S")
    elif fmt == "ymd":
        if date_only:
            if dt.year == 3333:
                return dt.strftime("%b %d")
            return dt.strftime("%Y %b %d")
        return dt.strftime("%Y %b %d %H:%M:%S")
    # Otherwise format into ISO format
    if date_only:
        return dt.date().isoformat()
    return dt.isoformat()


def localurl_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the localurl parser function."""
    arg0 = expander(args[0]).strip() if args else ctx.title or "ERROR_URL"
    arg1 = expander(args[1]).strip() if len(args) >= 2 else ""
    # XXX handle interwiki prefixes in arg0
    if arg1:
        url = "/w/index.php?title={}&{}".format(
            urllib.parse.quote_plus(arg0), arg1
        )
    else:
        url = "/wiki/{}".format(wikiurlencode(arg0))
    return url


def fullurl_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """
    Implements the fullurl and fullurle parser function.
    https://www.mediawiki.org/wiki/Help:Magic_words#URL_data
    """
    page_name = expander(args[0]).strip() if args else ""
    url = f"//{ctx.lang_code}.{ctx.project}.org/wiki/$1"
    if ":" in page_name:
        quote_index = page_name.index(":")
        interwiki_prefix = page_name[:quote_index]
        interwiki_map = get_interwiki_map(ctx)
        if interwiki_prefix in interwiki_map:
            page_name = page_name[quote_index + 1 :]
            url = interwiki_map[interwiki_prefix]["url"]  # type: ignore

    url = url.replace(
        "$1", urllib.parse.quote(page_name.replace(" ", "_"), safe=":/")
    )
    if len(args) > 1:
        arg = expander(args[1]).strip()  # ignore rest arguments
        url += "?" + urllib.parse.quote(arg, safe="=")
    return url


def urlencode_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the urlencode parser function."""
    arg0 = expander(args[0]) if args else ""
    fmt = expander(args[1]) if len(args) > 1 else "QUERY"
    url = arg0.strip()
    if fmt == "PATH":
        return urllib.parse.quote(url, safe="")
    elif fmt == "QUERY":
        return urllib.parse.quote_plus(url)
    # All else in WIKI encoding
    return wikiurlencode(url)


def wikiurlencode(url: str) -> str:
    assert isinstance(url, str)
    url = re.sub(r"\s+", "_", url)
    return urllib.parse.quote(url, safe="/:")


def anchorencode_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the urlencode parser function."""
    anchor = expander(args[0]).strip() if args else ""
    anchor = re.sub(r"\s+", "_", anchor)

    # I am not sure how MediaWiki encodes these but HTML5 at least allows
    # any character except any type of space character.  However, we also
    # replace quotes and "<>", just in case these are used inside attributes.
    # XXX should really check from MediaWiki source code
    def repl_anchor(m):
        v = urllib.parse.quote(m.group(0))
        return v.replace("%", ".")

    anchor = re.sub(r"""['"<>]""", repl_anchor, anchor)
    return anchor


def ns_fn(
    wtp: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """
    Implements the ns parser function.
    https://www.mediawiki.org/wiki/Help:Magic_words#Namespaces_2
    """
    arg = expander(args[0]).strip() if args else ""
    if arg in ["0", ""]:
        return ""
    lc_arg = arg.lower()
    for key, ns in wtp.NAMESPACE_DATA.items():
        if arg.isdigit() and ns["id"] == int(arg):
            return ns["name"]
        if ns["name"].lower() == lc_arg or lc_arg == key.lower():
            return ns["name"]
        if lc_arg in [alias.lower() for alias in ns["aliases"]]:
            return ns["name"]
    template_ns_name = wtp.NAMESPACE_DATA["Template"]["name"]
    return f"[[:{template_ns_name}:ns:{arg}]]"


def titleparts_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the #titleparts parser function."""
    t = expander(args[0]).strip() if args else ""
    arg1 = expander(args[1]).strip() if len(args) >= 2 else ""
    arg2 = expander(args[2]).strip() if len(args) >= 3 else ""
    num_return = 0
    try:
        num_return = int(arg1)
    except ValueError:
        pass
    first = 0
    try:
        first = int(arg2)
    except ValueError:
        pass
    parts = re.split(r"([:/])", t)
    num_parts = (len(parts) + 1) // 2
    if first < 0:
        first = max(0, num_parts + first)
    elif first > num_parts:
        first = num_parts
    if num_return == 0:
        num_return = num_parts
    elif num_return < 0:
        num_return = max(0, num_parts + num_return)
    parts = parts[2 * first : 2 * (first + num_return) - 1]
    return "".join(parts)


BinaryCallable = Callable[
    [Union[int, float], Union[int, float]], Union[int, float, str]
]
UnaryCallable = Callable[[Union[int, float]], Union[int, float, str]]

# Supported unary functions for #expr
unary_fns: dict[str, UnaryCallable] = {
    "-": lambda x: -x,  # Kludge to have this here besides parse_unary
    "+": lambda x: x,  # Kludge to have this here besides parse_unary
    "not": lambda x: int(not x),
    "ceil": math.ceil,
    "trunc": math.trunc,
    "floor": math.floor,
    "abs": abs,
    "sqrt": lambda x: "sqrt of negative value" if x < 0 else math.sqrt(x),
    "exp": math.exp,
    "ln": math.log,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "acos": math.acos,
    "asin": math.asin,
    "atan": math.atan,
}


def binary_e_fn(
    x: Union[int, float], y: Union[int, float]
) -> Union[int, float]:
    if isinstance(x, int) and isinstance(y, int):
        if y >= 0:
            for i in range(y):
                x = x * 10
            return x
        while y < 0:
            if x % 10 == 0:
                x = x // 10
                y += 1
            else:
                return x * math.pow(10, y)
        return x
    return x * math.pow(10, y)


binary_e_fns: dict[str, BinaryCallable] = {
    "e": binary_e_fn,
}

binary_pow_fns: dict[str, BinaryCallable] = {
    "^": math.pow,
}

binary_mul_fns: dict[str, BinaryCallable] = {
    "*": lambda x, y: x * y,
    "/": lambda x, y: "Divide by zero" if y == 0 else x / y,
    "div": lambda x, y: "Divide by zero" if y == 0 else x / y,
    "mod": lambda x, y: "Divide by zero" if y == 0 else x % y,
}

binary_add_fns: dict[str, BinaryCallable] = {
    "+": lambda x, y: x + y,
    "-": lambda x, y: x - y,
}

binary_round_fns: dict[str, BinaryCallable] = {
    "round": round,  # type:ignore
}

binary_cmp_fns: dict[str, BinaryCallable] = {
    "=": lambda x, y: int(x == y),
    "!=": lambda x, y: int(x != y),
    "<>": lambda x, y: int(x != y),
    ">": lambda x, y: int(x > y),
    "<": lambda x, y: int(x < y),
    ">=": lambda x, y: int(x >= y),
    "<=": lambda x, y: int(x <= y),
}

binary_and_fns: dict[str, BinaryCallable] = {
    "and": lambda x, y: 1 if x and y else 0,
}

binary_or_fns: dict[str, BinaryCallable] = {
    "or": lambda x, y: 1 if x or y else 0,
}


def expr_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the #titleparts parser function."""
    full_expr = expander(args[0]).strip().lower() if args else ""
    full_expr = full_expr or ""
    tokens = list(
        m.group(0)
        for m in re.finditer(
            r"\d+(\.\d*)?|\.\d+|[a-z]+|" r"!=|<>|>=|<=|[^\s]", full_expr
        )
    )
    tokidx = 0

    def expr_error(tok: Optional[str]) -> str:
        if tok is None:
            tok = "&lt;end&gt;"
        # ctx.warning("#expr error near {} in {!r}"
        #            .format(tok, full_expr),
        #            sortid="parserfns/781")
        return '<strong class="error">Expression error near {}</strong>'.format(
            tok
        )

    def get_token() -> Optional[str]:
        nonlocal tokidx
        if tokidx >= len(tokens):
            return None
        tok = tokens[tokidx]
        tokidx += 1
        return tok

    def unget_token(tok: Optional[str]) -> None:
        nonlocal tokidx
        if tok is None:
            return
        assert tok == tokens[tokidx - 1]
        tokidx -= 1

    def parse_atom(tok: Optional[str]) -> Union[str, int, float]:
        if tok is None:
            return expr_error(tok)
        if tok == "(":
            tok = get_token()
            ret = parse_expr(tok)
            tok = get_token()
            if tok != ")":
                return expr_error(tok)
            return ret
        try:
            ret = int(tok)
            return ret
        except ValueError:
            pass
        try:
            ret = float(tok)
            return ret
        except ValueError:
            pass
        if tok == "e":
            return math.e
        if tok == "pi":
            return math.pi
        if tok == ".":
            return 0
        return expr_error(tok)

    def generic_binary(
        tok: Optional[str],
        parser: Callable,
        fns: dict[str, Callable],
        assoc="left",
    ) -> Union[int, float, str]:
        ret = parser(tok)
        if isinstance(ret, str):
            return ret
        while True:
            tok = get_token()
            if tok is None:
                return ret
            fn = fns.get(tok)
            if fn is None:
                break
            tok = get_token()
            ret2 = parser(tok)
            if isinstance(ret2, str):
                return ret2
            ret = fn(ret, ret2)
        unget_token(tok)
        return ret

    def parse_unary(tok: Optional[str]) -> Union[str, int, float]:
        if tok == "-":
            tok = get_token()
            ret: Union[str, int, float] = parse_unary(tok)  # type: ignore
            if isinstance(ret, str):
                return ret
            return -ret
        if tok == "+":
            tok = get_token()
            return parse_atom(tok)
        ret = parse_atom(tok)
        return ret

    def parse_binary_e(tok: Optional[str]) -> Union[str, int, float]:
        # binary "e" operator
        return generic_binary(tok, parse_unary, binary_e_fns)

    def parse_unary_fn(tok: Optional[str]) -> Union[str, int, float]:
        fn = unary_fns.get(tok)  # type: ignore[arg-type]
        if fn is None:
            return parse_binary_e(tok)
        tok = get_token()
        ret = parse_unary_fn(tok)
        if isinstance(ret, str):
            return ret
        return fn(ret)

    def parse_binary_pow(tok: Optional[str]) -> Union[str, int, float]:
        return generic_binary(tok, parse_unary_fn, binary_pow_fns)

    def parse_binary_mul(tok: Optional[str]) -> Union[str, int, float]:
        return generic_binary(tok, parse_binary_pow, binary_mul_fns)

    def parse_binary_add(tok: Optional[str]) -> Union[str, int, float]:
        return generic_binary(tok, parse_binary_mul, binary_add_fns)

    def parse_binary_round(tok: Optional[str]) -> Union[str, int, float]:
        return generic_binary(tok, parse_binary_add, binary_round_fns)

    def parse_binary_cmp(tok: Optional[str]) -> Union[str, int, float]:
        return generic_binary(tok, parse_binary_round, binary_cmp_fns)

    def parse_binary_and(tok: Optional[str]) -> Union[str, int, float]:
        return generic_binary(tok, parse_binary_cmp, binary_and_fns)

    def parse_binary_or(tok: Optional[str]) -> Union[str, int, float]:
        return generic_binary(tok, parse_binary_and, binary_or_fns)

    def parse_expr(tok: Optional[str]) -> Union[str, int, float]:
        return parse_binary_or(tok)

    tok = get_token()
    ret = parse_expr(tok)
    if isinstance(ret, str):
        return ret
    if isinstance(ret, float):
        if ret == math.floor(ret):
            return str(int(ret))
    return str(ret)


def padleft_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the padleft parser function."""
    v = expander(args[0]) if args else ""
    cntstr = expander(args[1]).strip() if len(args) >= 2 else "0"
    pad = expander(args[2]) if len(args) >= 3 and args[2] else "0"
    if not cntstr.isdigit():
        if cntstr.startswith("-") and cntstr[1:].isdigit():
            pass
        else:
            ctx.warning(
                "pad length is not integer: {!r}".format(cntstr),
                sortid="parserfns/916",
            )
        cnt = 0
    else:
        cnt = int(cntstr)
    if cnt - len(v) > len(pad):
        pad = pad * ((cnt - len(v)) // len(pad))
    if len(v) < cnt:
        v = pad[: cnt - len(v)] + v
    return v


def padright_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the padright parser function."""
    v = expander(args[0]) if args else ""
    cntstr = expander(args[1]).strip() if len(args) >= 2 else "0"
    arg2 = expander(args[2]) if len(args) >= 3 and args[2] else "0"
    pad = arg2 if len(args) >= 3 and arg2 else "0"
    if not cntstr.isdigit():
        cnt = 0
        if cntstr.startswith("-") and cntstr[1:].isdigit():
            pass
        else:
            ctx.warning(
                "pad length is not integer: {!r}".format(cnt),
                sortid="parserfns/940",
            )
    else:
        cnt = int(cntstr)
    if cnt - len(v) > len(pad):
        pad = pad * ((cnt - len(v)) // len(pad))
    if len(v) < cnt:
        v = v + pad[: cnt - len(v)]
    return v


def plural_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the #plural parser function."""
    expr = expander(args[0]).strip() if args else "0"
    v = expr_fn(ctx, fn_name, [expr], lambda x: x)
    # XXX for some language codes, this is more complex.  See {{plural:...}} in
    # https://www.mediawiki.org/wiki/Help:Magic_words
    if v == 1:
        return expander(args[1]).strip() if len(args) >= 2 else ""
    return expander(args[2]).strip() if len(args) >= 3 else ""


def month_num_days(ctx: "Wtp", t: datetime) -> int:
    mdays = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    v = mdays[t.month - 1]
    if t.month == 2:
        if t.year % 4 == 0 and (t.year % 100 != 0 or t.year % 400 == 0):
            v = 29
    return v


time_fmt_map: dict[
    str,
    Union[str, Callable[["Wtp", datetime], Union[int, float, str]]],
] = {
    "Y": "%Y",
    "y": "%y",
    "L": lambda ctx, t: 1
    if (t.year % 4 == 0 and (t.year % 100 != 0 or t.year % 400 == 0))
    else 0,
    "o": "%G",
    "n": lambda ctx, t: t.month,
    "m": "%m",
    "M": "%b",
    "F": "%B",
    "xg": "%B",  # Should be in genitive
    "j": lambda ctx, t: t.day,
    "d": "%d",
    "z": lambda ctx, t: (
        t - datetime(year=t.year, month=1, day=1, tzinfo=t.tzinfo)
    ).days,
    "W": "%V",
    "N": "%u",
    "w": "%w",
    "D": "%a",
    "l": "%A",
    "a": "%p",  # Should be lowercase
    "A": "%p",  # Should be uppercase
    "g": lambda ctx, t: t.hour % 12,
    "h": "%I",
    "G": lambda ctx, t: t.hour,
    "H": "%H",
    "i": "%M",
    "s": "%S",
    "U": lambda ctx, t: int(t.timestamp()),
    "e": "%Z",
    "I": lambda ctx, t: "1" if t.dst() and t.dst().seconds != 0 else "0",  # type: ignore[union-attr]
    "0": lambda ctx, t: t.strftime("%z")[:5],
    "P": lambda ctx, t: t.strftime("%z")[:3] + ":" + t.strftime("%z")[3:5],
    "T": "%Z",
    "Z": lambda ctx, t: 0 if t.utcoffset() is None else t.utcoffset().seconds,  # type: ignore[union-attr]
    "t": month_num_days,
    "c": lambda ctx, t: t.isoformat(),
    "r": lambda ctx, t: t.strftime("%a, %d %b %Y %H:%M:%S {}").format(
        t.strftime("%z")[:5]
    ),
    "%": "%%",  # in case there's a stray % in the original Wiki-side format
    # XXX non-gregorian calendar values
}


# This format is in Python datatime library's format
MEDIAWIKI_TIMESTAMP_FORMAT = "%Y%m%d%H%M%S"


def format_with_wiki_timeformat(ctx: "Wtp", t: datetime, fmt: str) -> str:
    def fmt_repl(m: re.Match) -> str:
        f = m.group(0)
        if len(f) > 1 and f.startswith('"') and f.endswith('"'):
            return f[1:-1]
        if f in time_fmt_map:
            v = time_fmt_map[f]
            if isinstance(v, str):
                return v
            assert callable(v)
            v2 = v(ctx, t)
            if not isinstance(v2, str):
                v2 = str(v2)
            return v2
        return f

    fmt = re.sub(r'(x[mijkot]?)?[^"]|"[^"]*"', fmt_repl, fmt)

    return t.strftime(fmt)


def parse_timestamp(
    ctx: "Wtp", fn_name: str, loc: str, dt: str
) -> Union[datetime, str]:
    orig_dt = dt
    dt = re.sub(r"\+", " in ", dt)
    if not dt:
        dt = "now"

    settings: dateparser._Settings = {"RETURN_AS_TIMEZONE_AWARE": True}
    if loc in ("", "0"):
        dt += " UTC"

    t: Optional[datetime]
    if dt.startswith("@"):
        try:
            return datetime.fromtimestamp(float(dt[1:]))
        except ValueError:
            ctx.warning(
                "bad time syntax in {}: {!r}".format(fn_name, orig_dt),
                sortid="parserfns/1032",
            )
            return '<strong class="error">Bad time syntax: {}</strong>'.format(
                html.escape(orig_dt)
            )
    else:
        # dateparser doesn't have the exact same behavior as
        # php's strtotime() (which is the original function used)
        # but we can handle special cases here and hope
        # people on wiktionary don't go crazy with weird formatting
        t = dateparser.parse(dt, settings=settings)
        if t is None:
            m = re.match(
                r"([^+]*)\s*(\+\s*\d+\s*(day|year|month)s?)\s*$", orig_dt
            )
            if m:
                main_date = dateparser.parse(m.group(1), settings=settings)
                add_time = dateparser.parse(m.group(2), settings=settings)
                now = dateparser.parse("now", settings=settings)
                if main_date and add_time is not None and now is not None:
                    # this is just a kludge: dateparser parses "+2 days" as
                    # "2 days AGO". The now-datetime object is used to check
                    # just in case which way the parsing goes (we're relying
                    # on the "+" in the original argument string).
                    # Couldn't figure out a way to get a delta value other
                    # than doing this; didn't even have to round anything,
                    # things seem to work out at these small timescales.
                    if add_time < now:
                        delta = now - add_time
                    else:
                        delta = add_time - now
                    t = main_date + delta
        if t is None and orig_dt.isdecimal() and len(orig_dt) == 14:
            # could be MediaWiki timestamp
            try:
                t = datetime.strptime(orig_dt, MEDIAWIKI_TIMESTAMP_FORMAT)
            except ValueError:
                pass
        if t is None:
            ctx.warning(
                "unrecognized time syntax in {}: {!r}".format(fn_name, orig_dt),
                sortid="parserfns/1040",
            )
            return (
                '<strong class="error">Bad time syntax: ' "{}</strong>".format(
                    html.escape(orig_dt)
                )
            )
    return t


def time_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the #time parser function."""
    fmt = expander(args[0]).strip() if args else ""
    dt = expander(args[1]).strip() if len(args) >= 2 else ""
    # unused `lang`?
    # lang = expander(args[2]).strip() if len(args) >= 3 else "en"
    loc = expander(args[3]).strip() if len(args) >= 4 else ""

    # XXX looks like we should not adjust the time
    # if t.utcoffset():
    #    t -= t.utcoffset()

    t = parse_timestamp(ctx, fn_name, loc, dt)
    if isinstance(t, str):
        # return error message
        return t
    ret = format_with_wiki_timeformat(ctx, t, fmt)

    return ret


def timel_fn(
    wtp: "Wtp",
    fn_name: str,
    args: Union[list[str], tuple[str, ...]],
    expander: Callable[[str], str],
) -> str:
    # `local` parameter set to true
    if isinstance(args, tuple):
        args = list(args)
    while len(args) < 3:
        args.append("")
    args.append("1")
    return time_fn(wtp, fn_name, args, expander)


def len_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the #len parser function."""
    v = expander(args[0]).strip() if args else ""
    return str(len(v))


def pos_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the #pos parser function."""
    arg0 = expander(args[0]).strip() if args else ""
    arg1 = expander(args[1]) or " " if len(args) >= 2 else " "
    offsetstr = expander(args[2]).strip() if len(args) >= 3 else ""
    if not offsetstr or not offsetstr.isdigit():
        offset = 0
    else:
        offset = int(offsetstr)
    idx = arg0.find(arg1, offset)
    if idx >= 0:
        return str(idx)
    return ""


def rpos_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the #rpos parser function."""
    arg0 = expander(args[0]).strip() if args else ""
    arg1 = expander(args[1]) or " " if len(args) >= 2 else " "
    offsetstr = expander(args[2]).strip() if len(args) >= 3 else ""
    if not offsetstr or not offsetstr.isdigit():
        offset = 0
    else:
        offset = int(offsetstr)
    idx = arg0.rfind(arg1, offset)
    if idx >= 0:
        return str(idx)
    return "-1"


def sub_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the #sub parser function."""
    arg0 = expander(args[0]).strip() if args else ""
    startstr = expander(args[1]).strip() if len(args) >= 2 else ""
    lengthstr = expander(args[2]).strip() if len(args) >= 3 else ""
    try:
        start = int(startstr)
    except ValueError:
        start = 0
    if start < 0:
        start = max(0, len(arg0) + start)
    start = min(start, len(arg0))
    try:
        length = int(lengthstr)
    except ValueError:
        length = 0
    if length == 0:
        length = max(0, len(arg0) - start)
    elif length < 0:
        length = max(0, len(arg0) - start + length)
    return arg0[start : start + length]


def pad_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the pad parser function."""
    v = expander(args[0]).strip() if args else ""
    cntstr = expander(args[1]).strip() if len(args) >= 2 else ""
    pad = expander(args[2]) if len(args) >= 3 and args[2] else "0"
    direction = expander(args[3]) if len(args) >= 4 else ""
    if not cntstr.isdigit():
        ctx.warning(
            "pad length is not integer: {!r}".format(cntstr),
            sortid="parserfns/1133",
        )
        cnt = 0
    else:
        cnt = int(cntstr)
    if cnt - len(v) > len(pad):
        pad = pad * ((cnt - len(v)) // len(pad) + 1)
    if len(v) < cnt:
        padlen = cnt - len(v)
        if direction == "right":
            v = v + pad[:padlen]
        elif direction == "center":
            v = pad[: padlen // 2] + v + pad[: padlen - padlen // 2]
        else:  # left
            v = pad[:padlen] + v
    return v


def replace_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the #replace parser function."""
    arg0 = expander(args[0]).strip() if args else ""
    arg1 = expander(args[1]) or " " if len(args) >= 2 else " "
    arg2 = expander(args[2]) if len(args) >= 3 else ""
    return arg0.replace(arg1, arg2)


def explode_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the #explode parser function."""
    arg0 = expander(args[0]).strip() if args else ""
    delim = expander(args[1]) or " " if len(args) >= 2 else " "
    posstr = expander(args[2]).strip() if len(args) >= 3 else ""
    limitstr = expander(args[3]).strip() if len(args) >= 4 else ""
    try:
        position = int(posstr)
    except ValueError:
        position = 0
    try:
        limit = int(limitstr)
    except ValueError:
        limit = 0
    parts = arg0.split(delim)
    if limit > 0 and len(parts) > limit:
        parts = parts[: limit - 1] + [delim.join(parts[limit - 1 :])]
    if position < 0:
        position = len(parts) + position
    if position < 0 or position >= len(parts):
        return ""
    return parts[position]


def urldecode_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the #urldecode parser function."""
    arg0 = expander(args[0]).strip() if args else ""
    ret = urllib.parse.unquote_plus(arg0)
    return ret


def shortdesc_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    # https://en.wikipedia.org/wiki/Wikipedia:Short_description
    return ""


def unimplemented_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    ctx.error(
        "unimplemented parserfn {}".format(fn_name), sortid="parserfns/1191"
    )
    return "{{" + fn_name + ":" + "|".join(map(str, args)) + "}}"


def statements_fn(
    wtp: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    # https://www.wikidata.org/wiki/Wikidata:How_to_use_data_on_Wikimedia_projects
    # XXX? This implementation doesn't implement the fancy things #statements
    # generates, like links or images
    return property_fn(wtp, fn_name, args, expander)


def property_fn(
    wtp: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    # #property is meant to be for pulling bare bones data, I guess.
    # Does not pull correct data, for example coordinates

    from .wikidata import statement_query

    prop = ""
    wikidata_item = ""
    if len(args) > 0:
        prop = expander(args[0])
    if len(args) > 1 and args[1].startswith("from="):
        wikidata_item = expander(args[1]).removeprefix("from=")
    return statement_query(wtp, prop, wikidata_item, wtp.lang_code)


def pagelanguage_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    return ctx.lang_code


def language_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    if len(args) > 0:
        from mediawiki_langcodes import code_to_name

        return code_to_name(args[0], ctx.lang_code)
    return ""


def current_timestamp_fn(
    wtp: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    return datetime.now().strftime(MEDIAWIKI_TIMESTAMP_FORMAT)


def coordinates_fn(
    wtp: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    # According to the GeoData (not Maps) #coordinate parser function source
    # code, #coordinates only returns an empty string or an error string.
    # https://github.com/wikimedia/
    # mediawiki-extensions-GeoData/blob/
    # c025f10fd88d1d72655bc43599071c4dddaab1f8/
    # includes/CoordinatesParserFunction.php#L42
    return ""


def pagesize_fn(
    wtp: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    # Return size of page in bytes. If "R" is given, format the number without
    # commas, otherwise format number with comma thousand separators
    if not args:
        return '<strong class="error">No arguments given to #pagesize</strong>'
    page_name = args[0]
    comma_formatting = args[1].strip() == "R" if len(args) >= 2 else False

    body = wtp.get_page_body(page_name, None)
    if body is None:
        return '<strong class="error">Page not found for PAGESIZE</strong>'
    body_length = len(body.encode("utf-8"))
    if comma_formatting:
        return f"{body_length:,}"
    else:
        return f"{body_length}"

    return "0"


def filepath_fn(
    wtp: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    # meaningless function in the context of parsing wikitext without
    # access to the whole Mediawiki server core thingies.
    # Return a dummy url in the form "//unimplemented/filepath.foo"

    # The Scribunto PHP code parser function seems to also return
    # an array [ $url, "nowiki" => true], but aren't all return values
    # meant to be strings here? Testing it in the sandbox (using the
    # 'nowiki' parameter) didn't give different results.
    if not args:
        return ""
    return rf"//unimplemented/{args[0]}"


def protectionlevel_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the PROTECTIONLEVEL magic word."""
    # Returns an empty string to indicate that the page is not protected."""
    return ""


def localyear_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the LOCALYEAR magic word."""
    utc_dt = datetime.now(timezone.utc)
    return str(utc_dt.astimezone().year)


def localmonth_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the LOCALMONTH magic word."""
    utc_dt = datetime.now(timezone.utc)
    return utc_dt.astimezone().strftime("%m")


def localmonthname_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%B")


def localmonthabbrev_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%b")


def localday_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the LOCALDAY magic word."""
    utc_dt = datetime.now(timezone.utc)
    return utc_dt.astimezone().strftime("%-d")


def localday2_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the LOCALDAY2 magic word, with a possible leading zero."""
    utc_dt = datetime.now(timezone.utc)
    return utc_dt.astimezone().strftime("%d")


def localdow_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    # Day of the week (unpadded number), 0 (for Sunday) through 6 (for Saturday)
    return str(datetime.now(timezone.utc).astimezone().isoweekday() % 7)


def localdayname_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%A")


def localtime_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the LOCALTIME magic word."""
    return datetime.now(timezone.utc).astimezone().strftime("%H:%M")


def localhour_fn(
    ctx: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    """Implements the LOCALHOUR magic word."""
    return datetime.now(timezone.utc).astimezone().strftime("%H")


def number_of_pages_fn(
    wtp: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    return str(wtp.saved_page_nums())


def number_of_articles_fn(
    wtp: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    return str(wtp.saved_page_nums([0], False))


def rel2abs_fn(
    wtp: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    # https://www.mediawiki.org/wiki/Help:Extension:ParserFunctions##rel2abs
    # https://github.com/wikimedia/mediawiki-extensions-ParserFunctions/blob/ea4d4d94ee0c55b6039e05650ccc322e106ae06b/includes/ParserFunctions.php#L319
    original_path_str = args[0].strip()
    path = Path(original_path_str.removeprefix("/"))
    base_path = Path("/" + (wtp.title or ""))
    if len(args) > 1:
        base_path = Path("/" + args[1].strip())
    # not relative path
    if (
        not original_path_str.startswith(("/", "./", "../"))
        and original_path_str != ".."
    ):
        base_path = Path("/")
    path = base_path / path
    return str(path.resolve()).removeprefix("/")


def int_fn(
    wtp: "Wtp", fn_name: str, args: list[str], expander: Callable[[str], str]
) -> str:
    # https://www.mediawiki.org/wiki/Help:Magic_words#Localization
    if wtp.project == "wiktionary" and len(args) > 0 and args[0] == "lang":
        return wtp.lang_code
    if len(args) > 0 and len(args[0]) > 0:
        return f"⧼{args[0]}⧽"
    return f"[[:{wtp.LOCAL_NS_NAME_BY_ID.get(10, '')}:int:]]"


# This list should include names of predefined parser functions and
# predefined variables (some of which can take arguments using the same
# syntax as parser functions and we treat them as parser functions).
# See https://en.wikipedia.org/wiki/Help:Magic_words#Parser_functions
PARSER_FUNCTIONS = {
    "FULLPAGENAME": fullpagename_fn,
    "PAGENAME": pagename_fn,
    "BASEPAGENAME": basepagename_fn,
    "ROOTPAGENAME": rootpagename_fn,
    "SUBPAGENAME": subpagename_fn,
    "ARTICLEPAGENAME": unimplemented_fn,
    "SUBJECTPAGENAME": unimplemented_fn,
    "TALKPAGENAME": talkpagename_fn,
    "NAMESPACENUMBER": namespacenumber_fn,
    "NAMESPACE": namespace_fn,
    "ARTICLESPACE": unimplemented_fn,
    "SUBJECTSPACE": subjectspace_fn,
    "TALKSPACE": talkspace_fn,
    "FULLPAGENAMEE": fullpagenamee_fn,
    "PAGENAMEE": pagenamee_fn,
    "BASEPAGENAMEE": unimplemented_fn,
    "ROOTPAGENAMEE": rootpagenamee_fn,
    "SUBPAGENAMEE": unimplemented_fn,
    "ARTICLEPAGENAMEE": unimplemented_fn,
    "SUBJECTPAGENAMEE": unimplemented_fn,
    "TALKPAGENAMEE": unimplemented_fn,
    "NAMESPACENUMBERE": unimplemented_fn,
    "NAMESPACEE": unimplemented_fn,
    "ARTICLESPACEE": unimplemented_fn,
    "SUBJECTSPACEE": unimplemented_fn,
    "TALKSPACEE": unimplemented_fn,
    "SHORTDESC": shortdesc_fn,
    "SITENAME": unimplemented_fn,
    "SERVER": server_fn,
    "SERVERNAME": servername_fn,
    "SCRIPTPATH": unimplemented_fn,
    "CURRENTVERSION": unimplemented_fn,
    "CURRENTYEAR": currentyear_fn,
    "CURRENTMONTH": currentmonth_fn,
    "CURRENTMONTH1": currentmonth1_fn,
    "CURRENTMONTHNAME": currentmonthname_fn,
    "CURRENTMONTHABBREV": currentmonthabbrev_fn,
    "CURRENTDAY": currentday_fn,
    "CURRENTDAY2": currentday2_fn,
    "CUEEWNTDOW": currentdow_fn,
    "CURRENTDAYNAME": currentdayname_fn,
    "CURRENTTIME": currenttime_fn,
    "CURRENTHOUR": currenthour_fn,
    "CURRENTWEEK": currentweek_fn,
    "CURRENTTIMESTAMP": current_timestamp_fn,
    "LOCALYEAR": localyear_fn,
    "LOCALMONTH": localmonth_fn,
    "LOCALMONTHNAME": localmonthname_fn,
    "LOCALMONTHABBREV": localmonthabbrev_fn,
    "LOCALDAY": localday_fn,
    "LOCALDAY2": localday2_fn,
    "LOCALDOW": localdow_fn,
    "LOCALDAYNAME": localdayname_fn,
    "LOCALTIME": localtime_fn,
    "LOCALHOUR": localhour_fn,
    "LOCALWEEK": localweek_fn,
    "LOCALTIMESTAMP": local_timestamp_fn,
    "REVISIONID": revisionid_fn,
    "REVISIONDAY": unimplemented_fn,
    "REVISIONDAY2": unimplemented_fn,
    "REVISIONMONTH": unimplemented_fn,
    "REVISIONYEAR": unimplemented_fn,
    "REVISIONTIMESTAMP": unimplemented_fn,
    "REVISIONUSER": revisionuser_fn,
    "NUMBEROFPAGES": number_of_pages_fn,
    "NUMBEROFARTICLES": number_of_articles_fn,
    "NUMBEROFFILES": unimplemented_fn,
    "NUMBEROFEDITS": unimplemented_fn,
    "NUMBEROFUSERS": unimplemented_fn,
    "NUMBEROFADMINS": unimplemented_fn,
    "NUMBEROFACTIVEUSERS": unimplemented_fn,
    "PAGEID": unimplemented_fn,
    "PAGESIZE": pagesize_fn,
    "PROTECTIONLEVEL": protectionlevel_fn,
    "PROTECTIONEXPIRY": unimplemented_fn,
    "PENDINGCHANGELEVEL": unimplemented_fn,
    "PAGESINCATEGORY": unimplemented_fn,
    "NUMBERINGROUP": unimplemented_fn,
    "DISPLAYTITLE": displaytitle_fn,
    "displaytitle": displaytitle_fn,
    "DEFAULTSORT": defaultsort_fn,
    "PAGELANGUAGE": pagelanguage_fn,
    "lc": lc_fn,
    "lcfirst": lcfirst_fn,
    "uc": uc_fn,
    "ucfirst": ucfirst_fn,
    "formatnum": formatnum_fn,
    "#dateformat": dateformat_fn,
    "#formatdate": dateformat_fn,
    "padleft": padleft_fn,
    "padright": padright_fn,
    "plural": plural_fn,
    "#time": time_fn,
    "#timel": timel_fn,
    "gender": unimplemented_fn,
    "#tag": tag_fn,
    "localurl": localurl_fn,
    "fullurl": fullurl_fn,
    "fullurle": fullurl_fn,
    "canonicalurl": unimplemented_fn,
    "filepath": filepath_fn,
    "urlencode": urlencode_fn,
    "anchorencode": anchorencode_fn,
    "ns": ns_fn,
    "nse": ns_fn,  # We don't have spaces in ns names
    "#rel2abs": rel2abs_fn,
    "#titleparts": titleparts_fn,
    "#expr": expr_fn,
    "#if": if_fn,
    "#ifeq": ifeq_fn,
    "#iferror": iferror_fn,
    "#ifexpr": ifexpr_fn,
    "#ifexist": ifexist_fn,
    "#switch": switch_fn,
    "#babel": unimplemented_fn,
    "#categorytree": (categorytree_fn, True),  # This takes kwargs
    "#coordinates": coordinates_fn,
    "#invoke": unimplemented_fn,
    "#lst": lst_fn,
    "#lsth": unimplemented_fn,
    "#lstx": unimplemented_fn,
    "#property": property_fn,
    "#related": unimplemented_fn,
    "#statements": statements_fn,
    "#target": unimplemented_fn,
    # From Help:Extension:ParserFunctions
    "#len": len_fn,
    "#pos": pos_fn,
    "#rpos": rpos_fn,
    "#sub": sub_fn,
    "#pad": pad_fn,
    "#replace": replace_fn,
    "#explode": explode_fn,
    "#urldecode": urldecode_fn,
    "#urlencode": urlencode_fn,
    # Additional language names for certain functions
    # See https://www.mediawiki.org/wiki/Extension:Labeled_Section_Transclusion
    "#section": lst_fn,  # English
    "#Abschnitt": lst_fn,  # German
    "#trecho": lst_fn,  # Portuguese
    "#קטע": lst_fn,  # Hebrew
    "#section-h": unimplemented_fn,
    "#Abschnitt-x": unimplemented_fn,
    "#trecho-x": unimplemented_fn,
    "#section-x": unimplemented_fn,
    "#language": language_fn,
    "int": int_fn,
}


def call_parser_function(
    ctx: "Wtp",
    fn_name: str,
    args: Union[dict[Union[int, str], str], Sequence[str]],
    expander: Callable[[str], str],
) -> str:
    """Calls the given parser function with the given arguments."""
    assert isinstance(fn_name, str)
    assert isinstance(args, (list, tuple, dict))
    assert callable(expander)
    if fn_name not in PARSER_FUNCTIONS:
        ctx.error(
            "unrecognized parser function {!r}".format(fn_name),
            sortid="parserfns/1354",
        )
        return ""
    fn = PARSER_FUNCTIONS[fn_name]
    accept_keyed_args = False
    if isinstance(fn, tuple):
        accept_keyed_args = fn[1]
        fn = fn[0]
    assert callable(fn)
    have_keyed_args = False
    if isinstance(args, dict) and not accept_keyed_args:
        # Convert from dict to vector, no keyed args allowed
        new_args = []
        for i in range(1, 1000):
            v = args.get(i, None)
            if v is None:
                break
            new_args.append(v)
        for i in range(1, len(new_args) + 1):
            del args[i]
        have_keyed_args = len(args) > 0
        args = new_args
    elif accept_keyed_args:
        # Convert from vector to keyed args
        ht = {}
        i = 1
        k: Union[str, int]
        for arg in args:
            arg = str(arg)
            ofs = arg.find("=")
            if ofs >= 0:
                k = arg[:ofs]
                if k.isdigit():
                    k = int(k)
                arg = arg[ofs + 1 :]
            else:
                k = i
            ht[k] = arg
        args = ht
    if have_keyed_args and not accept_keyed_args:
        ctx.error(
            "parser function {} does not (yet) support named "
            "arguments: {}".format(fn_name, args),
            sortid="parserfns/1393",
        )
        return ""

    return add_newline_to_expansion(fn(ctx, fn_name, args, expander))
    # return fn(ctx, fn_name, args, expander)
