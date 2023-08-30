# Definitions for various parser functions supported in WikiText
#
# Copyright (c) 2020-2022 Tatu Ylonen.  See file LICENSE and https://ylonen.org

import re
import html
import math
import datetime
import urllib.parse
import dateparser

from typing import (
    Dict,
    List,
    Optional,
    TYPE_CHECKING,
    Union,
)

from collections.abc import Callable

from .wikihtml import ALLOWED_HTML_TAGS
from .common import nowiki_quote, MAGIC_NOWIKI_CHAR

if TYPE_CHECKING:
    # Reached only by mypy or other type-checker
    from .core import Wtp

# Suppress some warnings that are out of our control
import warnings
warnings.filterwarnings("ignore",
                        r".*The localize method is no longer necessary.*")

# The host to which generated URLs will point
SERVER_NAME: str = "dummy.host"


def capitalizeFirstOnly(s: str) -> str:
    if s:
        s = s[0].upper() + s[1:]
    return s


def if_fn(ctx: "Wtp", fn_name: str,
          args: List[str],
          expander: Callable[[str], str]
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


def ifeq_fn(ctx: "Wtp", fn_name: str,
            args: List[str],
            expander: Callable[[str], str]
            ) -> str:
    """Implements #ifeq parser function."""
    arg0: str = args[0] if args else ""
    arg1: str = args[1] if len(args) >= 2 else ""
    arg2: str = args[2] if len(args) >= 3 else ""
    arg3: str = args[3] if len(args) >= 4 else ""
    if expander(arg0).strip() == expander(arg1).strip():
        return expander(arg2).strip()
    return expander(arg3).strip()


def iferror_fn(ctx: "Wtp", fn_name: str,
            args: List[str],
            expander: Callable[[str], str]
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


def ifexpr_fn(ctx: "Wtp", fn_name: str,
              args: List[str],
              expander: Callable[[str], str]
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


def ifexist_fn(ctx: "Wtp", fn_name: str,
               args: List[str],
               expander: Callable[[str], str]
               ) -> str:
    """Implements #ifexist parser function."""
    arg0 = args[0] if args else ""
    arg1 = args[1] if len(args) >= 2 else ""
    arg2 = args[2] if len(args) >= 3 else ""
    if ctx.get_page(expander(arg0).strip()) is not None:
        return expander(arg1).strip()
    return expander(arg2).strip()


def switch_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
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
        if k == "#default":
            defval = v
        last = None
    if defval is not None:
        return expander(defval).strip()
    return last or ""


def categorytree_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable
) -> str:
    """Implements the #categorytree parser function.  This function accepts
    keyed arguments."""
    assert isinstance(args, dict)
    # We don't currently really implement categorytree.  It is just recognized
    # and silently ignored.
    return ""


def lst_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the #lst (alias #section etc) parser function."""
    pagetitle = expander(args[0]).strip() if args else ""
    chapter = expander(args[1]).strip() if len(args) >= 2 else ""
    text: Optional[str] = ctx.read_by_title(pagetitle)
    if text is None:
        ctx.warning("{} trying to transclude chapter {!r} from non-existent "
                    "page {!r}"
                    .format(fn_name, chapter, pagetitle),
                    sortid="parserfns/132")
        return ""

    parts: List[str] = []
    for m in re.finditer(r"(?si)<\s*section\s+begin={}\s*/\s*>(.*?)"
                         r"<\s*section\s+end={}\s*/\s*>"
                         .format(re.escape(chapter),
                                 re.escape(chapter)),
                         text):
        parts.append(m.group(1))
    if not parts:
        ctx.warning("{} could not find chapter {!r} on page {!r}"
                    .format(fn_name, chapter, pagetitle),
                    sortid="parserfns/146")
    return "".join(parts)


def tag_fn(
    ctx: "Wtp",
   fn_name: str,
   args: List[str],
   expander: Callable[[str], str]
) -> str:
    """Implements #tag parser function."""
    tag = expander(args[0]).lower() if args else ""
    if tag not in ALLOWED_HTML_TAGS and tag != "nowiki":
        ctx.warning("#tag creating non-allowed tag <{}> - omitted"
                    .format(tag),
                    sortid="parserfns/156")
        return "{{" + fn_name + ":" + "|".join(args) + "}}"
    content = expander(args[1]) if len(args) >= 2 else ""
    attrs = []
    if len(args) > 2:
        for x in args[2:]:
            x = expander(x)
            m = re.match(r"""(?s)^([^=<>'"]+)=(.*)$""", x)
            if not m:
                ctx.warning("invalid attribute format {!r} missing name"
                            .format(x),
                            sortid="parserfns/167")
                continue
            name, value = m.groups()
            if not value.startswith('"') and not value.startswith("'"):
                value = '"' + html.escape(value, quote=True) + '"'
            attrs.append('{}={}'.format(name, value))
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
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the FULLPAGENAME magic word/parser function."""
    t = expander(args[0]) if args else ctx.title
    t = re.sub(r"\s+", " ", t)
    t = t.strip()
    ofs = t.find(":")
    if ofs == 0:
        # t = capitalizeFirstOnly(t[1:])
        t = t[1:]
    elif ofs > 0:
        ns = capitalizeFirstOnly(t[:ofs])
        # t = capitalizeFirstOnly(t[ofs + 1:])
        t = t[ofs + 1:]
        t = ns + ":" + t
    #else:
    #    t = capitalizeFirstOnly(t)
    return t


def fullpagenamee_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the FULLPAGENAMEE magic word/parser function."""
    t = fullpagename_fn(ctx, fn_name, args, expander)
    return wikiurlencode(t)


def pagenamee_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the PAGENAMEE magic word/parser function."""
    t = pagename_fn(ctx, fn_name, args, expander)
    return wikiurlencode(t)


def rootpagenamee_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the ROOTPAGENAMEE magic word/parser function."""
    t = rootpagename_fn(ctx, fn_name, args, expander)
    return wikiurlencode(t)


def pagename_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the PAGENAME magic word/parser function."""
    t = expander(args[0]) if args else ctx.title
    t = re.sub(r"\s+", " ", t)
    t = t.strip()
    ofs = t.find(":")
    if ofs >= 0:
        # t = capitalizeFirstOnly(t[ofs + 1:])
        t = t[ofs + 1:]
    #else:
    #    t = capitalizeFirstOnly(t)
    return t


def basepagename_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the BASEPAGENAME magic word/parser function."""
    t = expander(args[0]) if args else ctx.title
    t = re.sub(r"\s+", " ", t)
    t = t.strip()
    ofs = t.rfind("/")
    if ofs >= 0:
        t = t[:ofs]
    return pagename_fn(ctx, fn_name, [t], lambda x: x)


def rootpagename_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the ROOTPAGENAME magic word/parser function."""
    t = expander(args[0]) if args else ctx.title
    t = re.sub(r"\s+", " ", t)
    t = t.strip()
    ofs = t.find("/")
    if ofs >= 0:
        t = t[:ofs]
    return pagename_fn(ctx, fn_name, [t], lambda x: x)


def subpagename_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the SUBPAGENAME magic word/parser function."""
    t = expander(args[0]) if args else ctx.title
    t = re.sub(r"\s+", " ", t)
    t = t.strip()
    ofs = t.rfind("/")
    if ofs >= 0:
        return t[ofs + 1:]
    else:
        return pagename_fn(ctx, fn_name, [t], lambda x: x)


def talkpagename_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the TALKPAGENAME magic word."""
    ofs = ctx.title.find(":")
    if ofs < 0:
        return ctx.NAMESPACE_DATA["Talk"]["name"] + ":" + ctx.title
    else:
        prefix = ctx.title[:ofs]
        if prefix not in ctx.NAMESPACE_DATA:
            return ctx.NAMESPACE_DATA["Talk"]["name"] + ":" + ctx.title
        return ctx.NAMESPACE_DATA[prefix + " talk"]["name"] + ":" + ctx.title[ofs + 1:]


def namespacenumber_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the NAMESPACENUMBER magic word/parser function."""
    # XXX currently hard-coded to return the name space number for the Main
    # namespace
    return "0"


def namespace_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the NAMESPACE magic word/parser function."""
    t = expander(args[0]) if args else ctx.title
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
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the SUBJECTSPACE magic word/parser function.  This
    implementation is very minimal."""
    t = expander(args[0]) if args else ctx.title
    for prefix in ctx.NAMESPACE_DATA:
        if t.startswith(prefix + ":"):
            return prefix
    return ""


def talkspace_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the TALKSPACE magic word/parser function.  This
    implementation is very minimal."""
    t = expander(args[0]) if args else ctx.title
    for prefix in ctx.NAMESPACE_DATA:
        if t.startswith(prefix + ":"):
            return ctx.NAMESPACE_DATA[prefix + " talk"]["name"]
    return ctx.NAMESPACE_DATA["Talk"]["name"]


def server_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the SERVER magic word."""
    return "//{}".format(SERVER_NAME)


def servername_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the SERVERNAME magic word."""
    return SERVER_NAME


def currentyear_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the CURRENTYEAR magic word."""
    return str(datetime.datetime.utcnow().year)


def currentmonth_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the CURRENTMONTH magic word."""
    return "{:02d}".format(datetime.datetime.utcnow().month)


def currentmonth1_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the CURRENTMONTH1 magic word."""
    return "{:d}".format(datetime.datetime.utcnow().month)


def currentmonthname_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the CURRENTMONTHNAME magic word."""
    # XXX support for other languages?
    month = datetime.datetime.utcnow().month
    return ("", "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November",
            "December")[month]


def currentmonthabbrev_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the CURRENTMONTHABBREV magic word."""
    # XXX support for other languages?
    month = datetime.datetime.utcnow().month
    return ("", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")[month]


def currentday_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the CURRENTDAY magic word."""
    return "{:d}".format(datetime.datetime.utcnow().day)


def currentday2_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the CURRENTDAY2 magic word."""
    return "{:02d}".format(datetime.datetime.utcnow().day)


def currentdow_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the CURRENTDOW magic word."""
    return "{:d}".format(datetime.datetime.utcnow().weekday())


def revisionid_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the REVISIONID magic word."""
    # We just return a dash, similar to "miser mode" in MediaWiki."""
    return "-"


def revisionuser_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the REVISIONUSER magic word."""
    # We always return AnonymousUser
    return "AnonymousUser"


def displaytitle_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the DISPLAYTITLE magic word/parser function."""
    t = expander(args[0]) if args else ""
    # XXX this should at least remove html tags h1 h2 h3 h4 h5 h6 div blockquote
    # ol ul li hr table tr th td dl dd caption p ruby rb rt rtc rp br
    # Looks as if this should also set the display title for the page in ctx???
    # XXX I think this parser function exists for the side effect of
    # setting page title
    return ""


def defaultsort_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:

    """Implements the DEFAULTSORT magic word/parser function."""
    # XXX apparently this should set the title by which this page is
    # sorted in category listings
    return ""


def lc_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the lc parser function (lowercase)."""
    return expander(args[0]).strip().lower() if args else ""


def lcfirst_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the lcfirst parser function (lowercase first character)."""
    t = expander(args[0]).strip() if args else ""
    if not t:
        return t
    return t[0].lower() + t[1:]


def uc_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the uc parser function (uppercase)."""
    t = expander(args[0]).strip() if args else ""
    return t.upper()


def ucfirst_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the ucfirst parser function (capitalize first character)."""
    t = expander(args[0]).strip() if args else ""
    return capitalizeFirstOnly(t)


def formatnum_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
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
        parts.append("".join(reversed(first[i: i + 3])))
    parts = [sep.join(reversed(parts))]
    if len(orig) > 1:
        parts.append(comma)
        parts.append(".".join(orig[1:]))
    return "".join(parts)


def dateformat_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
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
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the localurl parser function."""
    arg0 = expander(args[0]).strip() if args else ctx.title
    arg1 = expander(args[1]).strip() if len(args) >= 2 else ""
    # XXX handle interwiki prefixes in arg0
    if arg1:
        url = "/w/index.php?title={}&{}".format(
            urllib.parse.quote_plus(arg0), arg1)
    else:
        url = "/wiki/{}".format(wikiurlencode(arg0))
    return url


def fullurl_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the fullurl parser function."""
    arg0 = expander(args[0]).strip() if args else ""
    # XXX handle interwiki prefixes in arg0
    url = "//{}/index.php?title={}".format(
        SERVER_NAME, urllib.parse.quote_plus(arg0))
    if len(args) > 1:
        for arg in args[1:]:
            arg = expander(arg).strip()
            m = re.match(r"^([^=]+)=(.*)$", arg)
            if not m:
                url += "&" + urllib.parse.quote_plus(arg)
            else:
                url += ("&" + urllib.parse.quote_plus(m.group(1)) + "=" +
                        urllib.parse.quote_plus(m.group(2)))
    return url


def urlencode_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
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
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
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


class Namespace:
    __slots__ = (
        "aliases",
        "canonicalName",
        "defaultContentModel",
        "hasGenderDistinction",
        "id",
        "isCapitalized",
        "isContent",
        "isIncludable",
        "isMovable",
        "isSubject",
        "isTalk",
        "name",
        "subject",
        "talk",
    )

    def __init__(
        self,
        aliases: Optional[List[str]]=None,
        canonicalName="",
        defaultContentModel="wikitext",
        hasGenderDistinction=True,
        id: Optional[int]=None,
        isCapitalized=False,
        isContent=False,
        isIncludable=False,
        isMovable=False,
        isSubject=False,
        isTalk=False,
        name="",
        subject: Optional["Namespace"]=None,
        talk: Optional["Namespace"]=None
    ) -> None:
        assert name
        assert id is not None
        if aliases is None:
            aliases = []
        self.aliases: List[str] = aliases
        self.canonicalName = canonicalName
        self.defaultContentModel = defaultContentModel
        self.hasGenderDistinction = hasGenderDistinction
        self.id = id
        self.isCapitalized = isCapitalized
        self.isContent = isContent
        self.isIncludable = isIncludable
        self.isMovable = isMovable
        self.isSubject = isSubject
        self.isTalk = isTalk
        self.name = name
        self.subject = subject
        self.talk = talk


def init_namespaces(ctx: "Wtp") -> None:
    # These duplicate definitions in lua/mw_site.lua
    for ns_can_name, ns_data in ctx.NAMESPACE_DATA.items():
        ctx.namespaces[ns_data["id"]] = Namespace(
            id=ns_data["id"],
            name=ns_data["name"],
            isSubject=ns_data["issubject"],
            isContent=ns_data["content"],
            isTalk=ns_data["istalk"],
            aliases=ns_data["aliases"],
            canonicalName=ns_can_name
        )
    for ns in ctx.namespaces.values():
        if ns.isContent and ns.id >= 0:
            ns.talk = ctx.namespaces[ns.id + 1]
        elif ns.isTalk:
            ns.subject = ctx.namespaces[ns.id - 1]


def ns_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the ns parser function."""
    t = expander(args[0]).strip().upper() if args else ""
    if t and t.isdigit():
        ns = ctx.namespaces.get(int(t))
    else:
        for ns in ctx.namespaces.values():
            # print("checking", ns.name)
            if ns.name and t == ns.name.upper():
                break
            if ns.canonicalName and t == ns.canonicalName.upper():
                break
            for a in ns.aliases:
                if t == a.upper():
                    break
            else:
                continue
            break
        else:
            ns = None
    if ns is None:
        return ""
    return ns.name


def titleparts_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
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
    parts = parts[2 * first: 2 * (first + num_return) - 1]
    return "".join(parts)

BinaryCallable = Callable[[Union[int, float], Union[int,float]],
                           Union[int, float, str]]
UnaryCallable = Callable[[Union[int, float]], Union[int, float, str]]

# Supported unary functions for #expr
unary_fns: Dict[str, UnaryCallable] = {
    "-": lambda x: -x,  # Kludge to have this here besides parse_unary
    "+": lambda x: x,   # Kludge to have this here besides parse_unary
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


def binary_e_fn(x: Union[int, float], y: Union[int, float]
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


binary_e_fns: Dict[str, BinaryCallable] = {
    "e": binary_e_fn,
}

binary_pow_fns: Dict[str, BinaryCallable] = {
    "^": math.pow,
}

binary_mul_fns:  Dict[str, BinaryCallable] = {
    "*": lambda x, y: x * y,
    "/": lambda x, y: "Divide by zero" if y == 0 else x / y,
    "div": lambda x, y: "Divide by zero" if y == 0 else x / y,
    "mod": lambda x, y: "Divide by zero" if y == 0 else x % y,
}

binary_add_fns: Dict[str, BinaryCallable] = {
    "+": lambda x, y: x + y,
    "-": lambda x, y: x - y,
}

binary_round_fns: Dict[str, BinaryCallable] = {
    "round": round, # type:ignore
}

binary_cmp_fns: Dict[str, BinaryCallable] = {
    "=": lambda x, y: int(x == y),
    "!=": lambda x, y: int(x != y),
    "<>": lambda x, y: int(x != y),
    ">": lambda x, y: int(x > y),
    "<": lambda x, y: int(x < y),
    ">=": lambda x, y: int(x >= y),
    "<=": lambda x, y: int(x <= y),
}

binary_and_fns: Dict[str, BinaryCallable] = {
    "and": lambda x, y: 1 if x and y else 0,
}

binary_or_fns: Dict[str, BinaryCallable] = {
    "or": lambda x, y: 1 if x or y else 0,
}


def expr_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the #titleparts parser function."""
    full_expr = expander(args[0]).strip().lower() if args else ""
    full_expr = full_expr or ""
    tokens = list(m.group(0) for m in
                  re.finditer(r"\d+(\.\d*)?|\.\d+|[a-z]+|"
                              r"!=|<>|>=|<=|[^\s]", full_expr))
    tokidx = 0

    def expr_error(tok: Optional[str]) -> str:
        if tok is None:
            tok = "&lt;end&gt;"
        #ctx.warning("#expr error near {} in {!r}"
        #            .format(tok, full_expr),
        #            sortid="parserfns/781")
        return ('<strong class="error">Expression error near {}</strong>'
                .format(tok))

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
        fns: Dict[str, Callable],
        assoc="left"
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
            ret: Union[str, int, float] = parse_unary(tok) # type: ignore
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
        fn = unary_fns.get(tok) # type: ignore[arg-type]
        if fn is None:
            return parse_binary_e(tok)
        tok = get_token()
        ret = parse_unary_fn(tok)
        if isinstance(ret, str):
            return ret
        return fn(ret)

    def parse_binary_pow(tok: Optional[str]
    ) -> Union[str, int, float]:
        return generic_binary(tok, parse_unary_fn, binary_pow_fns)

    def parse_binary_mul(tok: Optional[str]
    ) -> Union[str, int, float]:
        return generic_binary(tok, parse_binary_pow, binary_mul_fns)

    def parse_binary_add(tok: Optional[str]
    ) -> Union[str, int, float]:
        return generic_binary(tok, parse_binary_mul, binary_add_fns)

    def parse_binary_round(tok: Optional[str]
    ) -> Union[str, int, float]:
        return generic_binary(tok, parse_binary_add, binary_round_fns)

    def parse_binary_cmp(tok: Optional[str]
    ) -> Union[str, int, float]:
        return generic_binary(tok, parse_binary_round, binary_cmp_fns)

    def parse_binary_and(tok: Optional[str]
    ) -> Union[str, int, float]:
        return generic_binary(tok, parse_binary_cmp, binary_and_fns)

    def parse_binary_or(tok: Optional[str]
    ) -> Union[str, int, float]:
        return generic_binary(tok, parse_binary_and, binary_or_fns)

    def parse_expr(tok: Optional[str]
    ) -> Union[str, int, float]:
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
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the padleft parser function."""
    v = expander(args[0]) if args else ""
    cntstr = expander(args[1]).strip() if len(args) >= 2 else "0"
    pad = expander(args[2]) if len(args) >= 3 and args[2] else "0"
    if not cntstr.isdigit():
        if cntstr.startswith("-") and cntstr[1:].isdigit():
            pass
        else:
            ctx.warning("pad length is not integer: {!r}".format(cntstr),
                        sortid="parserfns/916")
        cnt = 0
    else:
        cnt = int(cntstr)
    if cnt - len(v) > len(pad):
        pad = (pad * ((cnt - len(v)) // len(pad)))
    if len(v) < cnt:
        v = pad[:cnt - len(v)] + v
    return v


def padright_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
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
            ctx.warning("pad length is not integer: {!r}".format(cnt),
                        sortid="parserfns/940")
    else:
        cnt = int(cntstr)
    if cnt - len(v) > len(pad):
        pad = (pad * ((cnt - len(v)) // len(pad)))
    if len(v) < cnt:
        v = v + pad[:cnt - len(v)]
    return v


def plural_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the #plural parser function."""
    expr = expander(args[0]).strip() if args else "0"
    v = expr_fn(ctx, fn_name, [expr], lambda x: x)
    # XXX for some language codes, this is more complex.  See {{plural:...}} in
    # https://www.mediawiki.org/wiki/Help:Magic_words
    if v == 1:
        return expander(args[1]).strip() if len(args) >= 2 else ""
    return expander(args[2]).strip() if len(args) >= 3 else ""


def month_num_days(ctx: "Wtp", t: datetime.datetime) -> int:
    mdays = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    v = mdays[t.month - 1]
    if t.month == 2:
        if t.year % 4 == 0 and (t.year % 100 != 0 or t.year % 400 == 0):
            v = 29
    return v


time_fmt_map: Dict[str,
                   Union[
                    str,
                    Callable[
                        ["Wtp", datetime.datetime],
                        Union[int, float, str]]]
                ] = {
    "Y": "%Y",
    "y": "%y",
    "L": lambda ctx, t: 1 if (t.year % 4 == 0 and
                              (t.year % 100 != 0 or
                               t.year % 400 == 0)) else 0,
    "o": "%G",
    "n": lambda ctx, t: t.month,
    "m": "%m",
    "M": "%b",
    "F": "%B",
    "xg": "%B",  # Should be in genitive
    "j": lambda ctx, t: t.day,
    "d": "%d",
    "z": lambda ctx, t:
        (t - datetime.datetime(year=t.year, month=1, day=1,
                               tzinfo=t.tzinfo)).days,
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
        t.strftime("%z")[:5]),
    # XXX non-gregorian calendar values
}


def time_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the #time parser function."""
    fmt = expander(args[0]).strip() if args else ""
    dt = expander(args[1]).strip() if len(args) >= 2 else ""
    # unused `lang`?
    # lang = expander(args[2]).strip() if len(args) >= 3 else "en"
    loc = expander(args[3]).strip() if len(args) >= 4 else ""

    orig_dt = dt
    dt = re.sub(r"\+", " in ", dt)
    if not dt:
        dt = "now"

    settings: dateparser._Settings = {"RETURN_AS_TIMEZONE_AWARE": True}
    if loc in ("", "0"):
        dt += " UTC"

    t: Optional[datetime.datetime]
    if dt.startswith("@"):
        try:
            t = datetime.datetime.fromtimestamp(float(dt[1:]))
        except ValueError:
            ctx.warning("bad time syntax in {}: {!r}"
                        .format(fn_name, orig_dt),
                        sortid="parserfns/1032")
            return ('<strong class="error">Bad time syntax: {}</strong>'
                    .format(html.escape(orig_dt)))
    else:
        # dateparser doesn't have the exact same behavior as
        # php's strtotime() (which is the original function used)
        # but we can handle special cases here and hope
        # people on wiktionary don't go crazy with weird formatting
        t = dateparser.parse(dt, settings=settings)
        if t is None:
            m = re.match(r"([^+]*)\s*(\+\s*\d+\s*(day|year|month)s?)\s*$",
                         orig_dt)
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
        if t is None:
            ctx.warning("unrecognized time syntax in {}: {!r}"
                        .format(fn_name, orig_dt),
                        sortid="parserfns/1040")
            return ('<strong class="error">Bad time syntax: '
                    '{}</strong>'
                    .format(html.escape(orig_dt)))

    # XXX looks like we should not adjust the time
    #if t.utcoffset():
    #    t -= t.utcoffset()

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


def len_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the #len parser function."""
    v = expander(args[0]).strip() if args else ""
    return str(len(v))


def pos_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
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
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
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
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the #sub parser function."""
    arg0 = expander(args[0]).strip() if args else ""
    startstr = expander(args[1]).strip() if len(args) >= 2 else ""
    length = expander(args[2]).strip() if len(args) >= 3 else ""
    try:
        start = int(startstr)
    except ValueError:
        start = 0
    if start < 0:
        start = max(0, len(arg0) + start)
    start = min(start, len(arg0))
    try:
        length = int(length)
    except ValueError:
        length = 0
    if length == 0:
        length = max(0, len(arg0) - start)
    elif length < 0:
        length = max(0, len(arg0) - start + length)
    return arg0[start : start + length]


def pad_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the pad parser function."""
    v = expander(args[0]).strip() if args else ""
    cnt = expander(args[1]).strip() if len(args) >= 2 else ""
    pad = expander(args[2]) if len(args) >= 3 and args[2] else "0"
    direction = expander(args[3]) if len(args) >= 4 else ""
    if not cnt.isdigit():
        ctx.warning("pad length is not integer: {!r}".format(cnt),
                    sortid="parserfns/1133")
        cnt = 0
    else:
        cnt = int(cnt)
    if cnt - len(v) > len(pad):
        pad = (pad * ((cnt - len(v)) // len(pad) + 1))
    if len(v) < cnt:
        padlen = cnt - len(v)
        if direction == "right":
            v = v + pad[:padlen]
        elif direction == "center":
            v = pad[:padlen // 2] + v + pad[:padlen - padlen // 2]
        else:  # left
            v = pad[:padlen] + v
    return v


def replace_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the #replace parser function."""
    arg0 = expander(args[0]).strip() if args else ""
    arg1 = expander(args[1]) or " " if len(args) >= 2 else " "
    arg2 = expander(args[2]) if len(args) >= 3 else ""
    return arg0.replace(arg1, arg2)


def explode_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the #explode parser function."""
    arg0 = expander(args[0]).strip() if args else ""
    delim = expander(args[1]) or " " if len(args) >= 2 else " "
    position = expander(args[2]).strip() if len(args) >= 3 else ""
    limit = expander(args[3]).strip() if len(args) >= 4 else ""
    try:
        position = int(position)
    except ValueError:
        position = 0
    try:
        limit = int(limit)
    except ValueError:
        limit = 0
    parts = arg0.split(delim)
    if limit > 0 and len(parts) > limit:
        parts = parts[:limit - 1] + [delim.join(parts[limit - 1:])]
    if position < 0:
        position = len(parts) + position
    if position < 0 or position >= len(parts):
        return ""
    return parts[position]


def urldecode_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Implements the #urldecode parser function."""
    arg0 = expander(args[0]).strip() if args else ""
    ret = urllib.parse.unquote_plus(arg0)
    return ret


def shortdesc_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    # https://en.wikipedia.org/wiki/Wikipedia:Short_description
    return ""


def unimplemented_fn(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    ctx.error("unimplemented parserfn {}".format(fn_name),
              sortid="parserfns/1191")
    return "{{" + fn_name + ":" + "|".join(map(str, args)) + "}}"


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
    "CURRENTDAYNAME": unimplemented_fn,
    "CURRENTTIME": unimplemented_fn,
    "CURRENTHOUR": unimplemented_fn,
    "CURRENTWEEK": unimplemented_fn,
    "CURRENTTIMESTAMP": unimplemented_fn,
    "LOCALYEAR": unimplemented_fn,
    "LOCALMONTH": unimplemented_fn,
    "LOCALMONTHNAME": unimplemented_fn,
    "LOCALMONTHABBREV": unimplemented_fn,
    "LOCALDAY": unimplemented_fn,
    "LOCALDAY2": unimplemented_fn,
    "LOCALDOW": unimplemented_fn,
    "LOCALDAYNAME": unimplemented_fn,
    "LOCALTIME": unimplemented_fn,
    "LOCALHOUR": unimplemented_fn,
    "LOCALWEEK": unimplemented_fn,
    "LOCALTIMESTAMP": unimplemented_fn,
    "REVISIONID": revisionid_fn,
    "REVISIONDAY": unimplemented_fn,
    "REVISIONDAY2": unimplemented_fn,
    "REVISIONMONTH": unimplemented_fn,
    "REVISIONYEAR": unimplemented_fn,
    "REVISIONTIMESTAMP": unimplemented_fn,
    "REVISIONUSER": revisionuser_fn,
    "NUMBEROFPAGES": unimplemented_fn,
    "NUMBEROFARTICLES": unimplemented_fn,
    "NUMBEROFFILES": unimplemented_fn,
    "NUMBEROFEDITS": unimplemented_fn,
    "NUMBEROFUSERS": unimplemented_fn,
    "NUMBEROFADMINS": unimplemented_fn,
    "NUMBEROFACTIVEUSERS": unimplemented_fn,
    "PAGEID": unimplemented_fn,
    "PAGESIZE": unimplemented_fn,
    "PROTECTIONLEVEL": unimplemented_fn,
    "PROTECTIONEXPIRY": unimplemented_fn,
    "PENDINGCHANGELEVEL": unimplemented_fn,
    "PAGESINCATEGORY": unimplemented_fn,
    "NUMBERINGROUP": unimplemented_fn,
    "DISPLAYTITLE": displaytitle_fn,
    "displaytitle": displaytitle_fn,
    "DEFAULTSORT": defaultsort_fn,
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
    "#timel": unimplemented_fn,
    "gender": unimplemented_fn,
    "#tag": tag_fn,
    "localurl": localurl_fn,
    "fullurl": fullurl_fn,
    "canonicalurl": unimplemented_fn,
    "filepath": unimplemented_fn,
    "urlencode": urlencode_fn,
    "anchorencode": anchorencode_fn,
    "ns": ns_fn,
    "nse": ns_fn,  # We don't have spaces in ns names
    "#rel2abs": unimplemented_fn,
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
    "#coordinates": unimplemented_fn,
    "#invoke": unimplemented_fn,
    "#language": unimplemented_fn,
    "#lst": lst_fn,
    "#lsth": unimplemented_fn,
    "#lstx": unimplemented_fn,
    "#property": unimplemented_fn,
    "#related": unimplemented_fn,
    "#statements": unimplemented_fn,
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
    "#section": lst_fn,    # English
    "#Abschnitt": lst_fn,  # German
    "#trecho": lst_fn,     # Portuguese
    "#קטע": lst_fn,        # Hebrew
    "#section-h": unimplemented_fn,
    "#Abschnitt-x": unimplemented_fn,
    "#trecho-x": unimplemented_fn,
    "#section-x": unimplemented_fn,
}


def call_parser_function(
    ctx: "Wtp",
    fn_name: str,
    args: List[str],
    expander: Callable[[str], str]
) -> str:
    """Calls the given parser function with the given arguments."""
    assert isinstance(fn_name, str)
    assert isinstance(args, (list, tuple, dict))
    assert callable(expander)
    if fn_name not in PARSER_FUNCTIONS:
        ctx.error("unrecognized parser function {!r}".format(fn_name),
                  sortid="parserfns/1354")
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
        for arg in args:
            arg = str(arg)
            ofs = arg.find("=")
            if ofs >= 0:
                k = arg[:ofs]
                if k.isdigit():
                    k = int(k)
                arg = arg[ofs + 1:]
            else:
                k = i
            ht[k] = arg
        args = ht
    if have_keyed_args and not accept_keyed_args:
        ctx.error("parser function {} does not (yet) support named "
                  "arguments: {}"
                  .format(fn_name, args),
                  sortid="parserfns/1393")
        return ""
    return fn(ctx, fn_name, args, expander)
