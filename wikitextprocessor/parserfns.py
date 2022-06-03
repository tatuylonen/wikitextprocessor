# Definitions for various parser functions supported in WikiText
#
# Copyright (c) 2020-2022 Tatu Ylonen.  See file LICENSE and https://ylonen.org

import re
import html
import math
import datetime
import urllib.parse
import dateparser
from .wikihtml import ALLOWED_HTML_TAGS
from .common import nowiki_quote

# Suppress some warnings that are out of our control
import warnings
warnings.filterwarnings("ignore",
                        r".*The localize method is no longer necessary.*")


# Name of the WikiMedia for which we are generating content
PROJECT_NAME = "Wiktionary"

# The host to which generated URLs will point
SERVER_NAME = "dummy.host"

namespace_prefixes = set([
    "Appendix",
    "Category",
    "Citations",
    "Concordance",
    "File",
    "Help",
    "Image",
    "Index",
    "Media",
    "MediaWiki",
    "Module",
    "Project",
    "Reconstruction",
    "Rhymes",
    "Sign gloss",
    "Summary",
    "Talk",
    "Template",
    "Thesaurus",
    "Thread",
    "User",
    "Wiktionary",
])

def capitalizeFirstOnly(s):
    if s:
        s = s[0].upper() + s[1:]
    return s


def if_fn(ctx, fn_name, args, expander):
    """Implements #if parser function."""
    arg0 = args[0] if args else ""
    arg1 = args[1] if len(args) >= 2 else ""
    arg2 = args[2] if len(args) >= 3 else ""
    v = expander(arg0).strip()
    if v:
        return expander(arg1).strip()
    return expander(arg2).strip()


def ifeq_fn(ctx, fn_name, args, expander):
    """Implements #ifeq parser function."""
    arg0 = args[0] if args else ""
    arg1 = args[1] if len(args) >= 2 else ""
    arg2 = args[2] if len(args) >= 3 else ""
    arg3 = args[3] if len(args) >= 4 else ""
    if expander(arg0).strip() == expander(arg1).strip():
        return expander(arg2).strip()
    return expander(arg3).strip()


def iferror_fn(ctx, fn_name, args, expander):
    """Implements the #iferror parser function."""
    arg0 = expander(args[0]) if args else ""
    arg1 = args[1] if len(args) >= 2 else None
    arg2 = args[2] if len(args) >= 3 else None
    if re.search(r'<[^>]*?\sclass="error"', arg0):
        if arg1 is None:
            return ""
        return expander(arg1).strip()
    if arg2 is None:
        return arg0
    return expander(arg2).strip()


def ifexpr_fn(ctx, fn_name, args, expander):
    """Implements #ifexpr parser function."""
    arg0 = args[0] if args else "0"
    arg1 = args[1] if len(args) >= 2 else ""
    arg2 = args[2] if len(args) >= 3 else ""
    cond = expr_fn(ctx, fn_name, [arg0], expander)
    try:
        ret = int(cond)
    except ValueError:
        ret = 0
    if ret:
        return expander(arg1).strip()
    return expander(arg2).strip()

def ifexist_fn(ctx, fn_name, args, expander):
    """Implements #ifexist parser function."""
    arg0 = args[0] if args else ""
    arg1 = args[1] if len(args) >= 2 else ""
    arg2 = args[2] if len(args) >= 3 else ""
    exists = ctx.page_exists(expander(arg0).strip())
    if exists:
        return expander(arg1).strip()
    return expander(arg2).strip()

def switch_fn(ctx, fn_name, args, expander):
    """Implements #switch parser function."""
    val = expander(args[0]).strip() if args else ""
    match_next = False
    defval = None
    last = None
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


def categorytree_fn(ctx, fn_name, args, expander):
    """Implements the #categorytree parser function.  This function accepts
    keyed arguments."""
    assert isinstance(args, dict)
    # We don't currently really implement categorytree.  It is just recognized
    # and silently ignored.
    return ""


def lst_fn(ctx, fn_name, args, expander):
    """Implements the #lst (alias #section etc) parser function."""
    pagetitle = expander(args[0]).strip() if args else ""
    chapter = expander(args[1]).strip() if len(args) >= 2 else ""
    text = ctx.read_by_title(pagetitle)
    if text is None:
        ctx.warning("{} trying to transclude chapter {!r} from non-existent "
                    "page {!r}"
                    .format(fn_name, chapter, pagetitle))
        return ""

    parts = []
    for m in re.finditer(r"(?si)<\s*section\s+begin={}\s*/\s*>(.*?)"
                         r"<\s*section\s+end={}\s*/\s*>"
                         .format(re.escape(chapter),
                                 re.escape(chapter)),
                         text):
        parts.append(m.group(1))
    if not parts:
        ctx.warning("{} could not find chapter {!r} on page {!r}"
                    .format(fn_name, chapter, pagetitle))
    return "".join(parts)


def tag_fn(ctx, fn_name, args, expander):
    """Implements #tag parser function."""
    tag = expander(args[0]).lower() if args else ""
    if tag not in ALLOWED_HTML_TAGS and tag != "nowiki":
        ctx.warning("#tag creating non-allowed tag <{}> - omitted"
                    .format(tag))
        return "{{" + fn_name + ":" + "|".join(args) + "}}"
    content = expander(args[1]) if len(args) >= 2 else ""
    attrs = []
    if len(args) > 2:
        for x in args[2:]:
            x = expander(x)
            m = re.match(r"""(?s)^([^=<>'"]+)=(.*)$""", x)
            if not m:
                ctx.warning("invalid attribute format {!r} missing name"
                            .format(x))
                continue
            name, value = m.groups()
            if not value.startswith('"') and not value.startswith("'"):
                value = '"' + html.escape(value, quote=True) + '"'
            attrs.append('{}={}'.format(name, value))
    if attrs:
        attrs = " " + " ".join(attrs)
    else:
        attrs = ""
    if not content:
        ret = "<{}{} />".format(tag, attrs)
    else:
        ret = "<{}{}>{}</{}>".format(tag, attrs, content, tag)
    if tag == "nowiki":
        if len(args) == 0:
            ret = MAGIC_NOWIKI_CHAR
        else:
            ret = nowiki_quote(content)
    return ret


def fullpagename_fn(ctx, fn_name, args, expander):
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


def fullpagenamee_fn(ctx, fn_name, args, expander):
    """Implements the FULLPAGENAMEE magic word/parser function."""
    t = fullpagename_fn(ctx, fn_name, args, expander)
    return wikiurlencode(t)


def pagenamee_fn(ctx, fn_name, args, expander):
    """Implements the PAGENAMEE magic word/parser function."""
    t = pagename_fn(ctx, fn_name, args, expander)
    return wikiurlencode(t)


def rootpagenamee_fn(ctx, fn_name, args, expander):
    """Implements the ROOTPAGENAMEE magic word/parser function."""
    t = rootpagename_fn(ctx, fn_name, args, expander)
    return wikiurlencode(t)


def pagename_fn(ctx, fn_name, args, expander):
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


def basepagename_fn(ctx, fn_name, args, expander):
    """Implements the BASEPAGENAME magic word/parser function."""
    t = expander(args[0]) if args else ctx.title
    t = re.sub(r"\s+", " ", t)
    t = t.strip()
    ofs = t.rfind("/")
    if ofs >= 0:
        t = t[:ofs]
    return pagename_fn(ctx, fn_name, [t], lambda x: x)


def rootpagename_fn(ctx, fn_name, args, expander):
    """Implements the ROOTPAGENAME magic word/parser function."""
    t = expander(args[0]) if args else ctx.title
    t = re.sub(r"\s+", " ", t)
    t = t.strip()
    ofs = t.find("/")
    if ofs >= 0:
        t = t[:ofs]
    return pagename_fn(ctx, fn_name, [t], lambda x: x)


def subpagename_fn(ctx, fn_name, args, expander):
    """Implements the SUBPAGENAME magic word/parser function."""
    t = expander(args[0]) if args else ctx.title
    t = re.sub(r"\s+", " ", t)
    t = t.strip()
    ofs = t.rfind("/")
    if ofs >= 0:
        return t[ofs + 1:]
    else:
        return pagename_fn(ctx, fn_name, [t], lambda x: x)


def talkpagename_fn(ctx, fn_name, args, expander):
    """Implements the TALKPAGENAME magic word."""
    ofs = ctx.title.find(":")
    if ofs < 0:
        return "Talk:" + ctx.title
    if ofs >= 0:
        prefix = ctx.title[:ofs]
        if prefix not in namespace_prefixes:
            return "Talk:" + ctx.title
        return prefix + "_talk:" + ctx.title[ofs + 1:]


def namespacenumber_fn(ctx, fn_name, args, expander):
    """Implements the NAMESPACENUMBER magic word/parser function."""
    # XXX currently hard-coded to return the name space number for the Main
    # namespace
    return 0


def namespace_fn(ctx, fn_name, args, expander):
    """Implements the NAMESPACE magic word/parser function."""
    t = expander(args[0]) if args else ctx.title
    t = re.sub(r"\s+", " ", t)
    t = t.strip()
    ofs = t.find(":")
    if ofs >= 0:
        ns = capitalizeFirstOnly(t[:ofs])
        if ns == "Project":
            return PROJECT_NAME
        return ns
    return ""


def subjectspace_fn(ctx, fn_name, args, expander):
    """Implements the SUBJECTSPACE magic word/parser function.  This
    implementation is very minimal."""
    t = expander(args[0]) if args else ctx.title
    for prefix in namespace_prefixes:
        if t.startswith(prefix + ":"):
            return prefix
    return ""


def talkspace_fn(ctx, fn_name, args, expander):
    """Implements the TALKSPACE magic word/parser function.  This
    implementation is very minimal."""
    t = expander(args[0]) if args else ctx.title
    for prefix in namespace_prefixes:
        if t.startswith(prefix + ":"):
            return prefix + "_talk"
    return "Talk"


def server_fn(ctx, fn_name, args, expander):
    """Implements the SERVER magic word."""
    return "//{}".format(SERVER_NAME)


def servername_fn(ctx, fn_name, args, expander):
    """Implements the SERVERNAME magic word."""
    return SERVER_NAME


def currentyear_fn(ctx, fn_name, args, expander):
    """Implements the CURRENTYEAR magic word."""
    return str(datetime.datetime.utcnow().year)


def currentmonth_fn(ctx, fn_name, args, expander):
    """Implements the CURRENTMONTH magic word."""
    return "{:02d}".format(datetime.datetime.utcnow().month)


def currentmonth1_fn(ctx, fn_name, args, expander):
    """Implements the CURRENTMONTH1 magic word."""
    return "{:d}".format(datetime.datetime.utcnow().month)


def currentmonthname_fn(ctx, fn_name, args, expander):
    """Implements the CURRENTMONTHNAME magic word."""
    # XXX support for other languages?
    month = datetime.datetime.utcnow().month
    return ("", "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November",
            "December")[month]


def currentmonthabbrev_fn(ctx, fn_name, args, expander):
    """Implements the CURRENTMONTHABBREV magic word."""
    # XXX support for other languages?
    month = datetime.datetime.utcnow().month
    return ("", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")[month]


def currentday_fn(ctx, fn_name, args, expander):
    """Implements the CURRENTDAY magic word."""
    return "{:d}".format(datetime.datetime.utcnow().day)


def currentday2_fn(ctx, fn_name, args, expander):
    """Implements the CURRENTDAY2 magic word."""
    return "{:02d}".format(datetime.datetime.utcnow().day)


def currentdow_fn(ctx, fn_name, args, expander):
    """Implements the CURRENTDOW magic word."""
    return "{:d}".format(datetime.datetime.utcnow().weekday())


def revisionid_fn(ctx, fn_name, args, expander):
    """Implements the REVISIONID magic word."""
    # We just return a dash, similar to "miser mode" in MediaWiki."""
    return "-"


def revisionuser_fn(ctx, fn_name, args, expander):
    """Implements the REVISIONUSER magic word."""
    # We always return AnonymousUser
    return "AnonymousUser"


def displaytitle_fn(ctx, fn_name, args, expander):
    """Implements the DISPLAYTITLE magic word/parser function."""
    t = expander(args[0]) if args else ""
    # XXX this should at least remove html tags h1 h2 h3 h4 h5 h6 div blockquote
    # ol ul li hr table tr th td dl dd caption p ruby rb rt rtc rp br
    # Looks as if this should also set the display title for the page in ctx???
    # XXX I think this parser function exists for the side effect of
    # setting page title
    return ""

def defaultsort_fn(ctx, fn_nae, args, expander):
    """Implements the DEFAULTSORT magic word/parser function."""
    # XXX apparently this should set the title by which this page is
    # sorted in category listings
    return ""

def lc_fn(ctx, fn_name, args, expander):
    """Implements the lc parser function (lowercase)."""
    return expander(args[0]).strip().lower() if args else ""


def lcfirst_fn(ctx, fn_name, args, expander):
    """Implements the lcfirst parser function (lowercase first character)."""
    t = expander(args[0]).strip() if args else ""
    if not t:
        return t
    return t[0].lower() + t[1:]


def uc_fn(ctx, fn_name, args, expander):
    """Implements the uc parser function (uppercase)."""
    t = expander(args[0]).strip() if args else ""
    return t.upper()


def ucfirst_fn(ctx, fn_name, args, expander):
    """Implements the ucfirst parser function (capitalize first character)."""
    t = expander(args[0]).strip() if args else ""
    return capitalizeFirstOnly(t)


def formatnum_fn(ctx, fn_name, args, expander):
    """Implements the formatnum parser function."""
    arg0 = expander(args[0]).strip() if args else ""
    arg1 = expander(args[1]).strip() if len(args) >= 2 else ""
    if arg1 == "R":
        # Reverse formatting
        # XXX this is a very simplified implementation, should handle more cases
        return re.sub(r",", "", arg0)
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


def dateformat_fn(ctx, fn_name, args, expander):
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


def localurl_fn(ctx, fn_name, args, expander):
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


def fullurl_fn(ctx, fn_name, args, expander):
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


def urlencode_fn(ctx, fn_name, args, expander):
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


def wikiurlencode(url):
    assert isinstance(url, str)
    url = re.sub(r"\s+", "_", url)
    return urllib.parse.quote(url, safe="/:")


def anchorencode_fn(ctx, fn_name, args, expander):
    """Implements the urlencode parser function."""
    anchor = expander(args[0]).strip() if args else ""
    anchor = re.sub(r"\s+", "_", anchor)
    # I am not sure how MediaWiki encodes these but HTML5 at least allows
    # any character except any type of space character.  However, we also
    # replace quotes and "<>", just in case these are used inside attributes.
    # XXX should really check from MediaWiki source code
    def repl_anchor(m):
        v = urllib.parse.quote(m.group(0))
        return re.sub(r"%", ".", v)

    anchor = re.sub(r"""['"<>]""", repl_anchor, anchor)
    return anchor


class Namespace(object):
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

    def __init__(self, aliases=[], canonicalName="",
                 defaultContentModel="wikitext", hasGenderDistinction=True,
                 id=None, isCapitalized=False, isContent=False,
                 isIncludable=False,
                 isMovable=False, isSubject=False, isTalk=False,
                 name="", subject=None, talk=None):
        assert name
        assert id is not None
        self.aliases = aliases
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

# These duplicate definitions in lua/mw_site.lua
media_ns = Namespace(id=-2, name="Media", isSubject=True)
special_ns = Namespace(id=-1, name="Special", isSubject=True)
main_ns = Namespace(id=0, name="Main", isContent=True, isSubject=True)
talk_ns = Namespace(id=1, name="Talk", isTalk=True, subject=main_ns)
user_ns = Namespace(id=2, name="User", isSubject=True)
user_talk_ns = Namespace(id=3, name="User_talk", isTalk=True,
                         subject=user_ns)
project_ns = Namespace(id=4, name="Project", isSubject=True)
project_talk_ns = Namespace(id=5, name="Project_talk", isTalk=True,
                            subject=project_ns)
image_ns = Namespace(id=6, name="File", aliases=["Image"],
                     isSubject=True)
image_talk_ns = Namespace(id=7, name="File_talk",
                          aliases=["Image_talk"],
                          isTalk=True, subject=image_ns)
mediawiki_ns = Namespace(id=8, name="MediaWiki", isSubject=True)
mediawiki_talk_ns = Namespace(id=9, name="MediaWiki_talk",
                              isTalk=True, subject=mediawiki_ns)
template_ns = Namespace(id=10, name="Template", isSubject=True)
template_talk_ns = Namespace(id=11, name="Template_talk", isTalk=True,
                             subject=template_ns)
help_ns = Namespace(id=12, name="Help", isSubject=True)
help_talk_ns = Namespace(id=13, name="Help_talk", isTalk=True,
                         subject=help_ns)
category_ns = Namespace(id=14, name="Category", isSubject=True)
category_talk_ns = Namespace(id=15, name="Category_talk", isTalk=True,
                             subject=category_ns)
module_ns = Namespace(id=828, name="Module", isIncludable=True,
                      isSubject=True)
module_talk_ns = Namespace(id=829, name="Module_talk", isTalk=True,
                           subject=module_ns)
main_ns.talk = talk_ns
user_ns.talk = user_talk_ns
project_ns.talk = project_talk_ns
mediawiki_ns.talk = mediawiki_talk_ns
template_ns.talk = template_talk_ns
help_ns.talk = help_talk_ns
category_ns.talk = category_talk_ns
module_ns.talk = module_talk_ns

namespaces = {}

def add_ns(t, ns):
   t[ns.id] = ns

add_ns(namespaces, media_ns)
add_ns(namespaces, special_ns)
add_ns(namespaces, main_ns)
add_ns(namespaces, talk_ns)
add_ns(namespaces, user_ns)
add_ns(namespaces, user_talk_ns)
add_ns(namespaces, project_ns)
add_ns(namespaces, project_talk_ns)
add_ns(namespaces, image_ns)
add_ns(namespaces, image_talk_ns)
add_ns(namespaces, mediawiki_ns)
add_ns(namespaces, mediawiki_talk_ns)
add_ns(namespaces, template_ns)
add_ns(namespaces, template_talk_ns)
add_ns(namespaces, help_ns)
add_ns(namespaces, help_talk_ns)
add_ns(namespaces, category_ns)
add_ns(namespaces, category_talk_ns)
add_ns(namespaces, module_ns)
add_ns(namespaces, module_talk_ns)


def ns_fn(ctx, fn_name, args, expander):
    """Implements the ns parser function."""
    t = expander(args[0]).strip().upper() if args else ""
    if t and t.isdigit():
        t = int(t)
        ns = namespaces.get(t)
    else:
        for ns in namespaces.values():
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


def titleparts_fn(ctx, fn_name, args, expander):
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


# Supported unary functions for #expr
unary_fns = {
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

def binary_e_fn(x, y):
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

binary_e_fns = {
    "e": binary_e_fn,
}

binary_pow_fns = {
    "^": math.pow,
}

binary_mul_fns = {
    "*": lambda x, y: x * y,
    "/": lambda x, y: "Divide by zero" if y == 0 else x / y,
    "div": lambda x, y: "Divide by zero" if y == 0 else x / y,
    "mod": lambda x, y: "Divide by zero" if y == 0 else x % y,
}

binary_add_fns = {
    "+": lambda x, y: x + y,
    "-": lambda x, y: x - y,
}

binary_round_fns = {
    "round": round,
}

binary_cmp_fns = {
    "=": lambda x, y: int(x == y),
    "!=": lambda x, y: int(x != y),
    "<>": lambda x, y: int(x != y),
    ">": lambda x, y: int(x > y),
    "<": lambda x, y: int(x < y),
    ">=": lambda x, y: int(x >= y),
    "<=": lambda x, y: int(x <= y),
}

binary_and_fns = {
    "and": lambda x, y: 1 if x and y else 0,
}

binary_or_fns = {
    "or": lambda x, y: 1 if x or y else 0,
}

def expr_fn(ctx, fn_name, args, expander):
    """Implements the #titleparts parser function."""
    full_expr = expander(args[0]).strip().lower() if args else ""
    full_expr = full_expr or ""
    tokens = list(m.group(0) for m in
                  re.finditer(r"\d+(\.\d*)?|\.\d+|[a-z]+|"
                              r"!=|<>|>=|<=|[^\s]", full_expr))
    tokidx = 0

    def expr_error(tok):
        if tok is None:
            tok = "&lt;end&gt;"
        #ctx.warning("#expr error near {} in {!r}"
        #            .format(tok, full_expr))
        return ('<strong class="error">Expression error near {}</strong>'
                .format(tok))

    def get_token():
        nonlocal tokidx
        if tokidx >= len(tokens):
            return None
        tok = tokens[tokidx]
        tokidx += 1
        return tok

    def unget_token(tok):
        nonlocal tokidx
        if tok is None:
            return
        assert tok == tokens[tokidx - 1]
        tokidx -= 1

    def parse_atom(tok):
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

    def generic_binary(tok, parser, fns, assoc="left"):
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

    def parse_unary(tok):
        if tok == "-":
            tok = get_token()
            ret = parse_unary(tok)
            if isinstance(ret, str):
                return ret
            return -ret
        if tok == "+":
            tok = get_token()
            return parse_atom(tok)
        ret = parse_atom(tok)
        return ret

    def parse_binary_e(tok):
        # binary "e" operator
        return generic_binary(tok, parse_unary, binary_e_fns)

    def parse_unary_fn(tok):
        fn = unary_fns.get(tok)
        if fn is None:
            return parse_binary_e(tok)
        tok = get_token()
        ret = parse_unary_fn(tok)
        if isinstance(ret, str):
            return ret
        return fn(ret)

    def parse_binary_pow(tok):
        return generic_binary(tok, parse_unary_fn, binary_pow_fns)

    def parse_binary_mul(tok):
        return generic_binary(tok, parse_binary_pow, binary_mul_fns)

    def parse_binary_add(tok):
        return generic_binary(tok, parse_binary_mul, binary_add_fns)

    def parse_binary_round(tok):
        return generic_binary(tok, parse_binary_add, binary_round_fns)

    def parse_binary_cmp(tok):
        return generic_binary(tok, parse_binary_round, binary_cmp_fns)

    def parse_binary_and(tok):
        return generic_binary(tok, parse_binary_cmp, binary_and_fns)

    def parse_binary_or(tok):
        return generic_binary(tok, parse_binary_and, binary_or_fns)

    def parse_expr(tok):
        return parse_binary_or(tok)

    tok = get_token()
    ret = parse_expr(tok)
    if isinstance(ret, str):
        return ret
    if isinstance(ret, float):
        if ret == math.floor(ret):
            return str(int(ret))
    return str(ret)


def padleft_fn(ctx, fn_name, args, expander):
    """Implements the padleft parser function."""
    v = expander(args[0]) if args else ""
    cnt = expander(args[1]).strip() if len(args) >= 2 else "0"
    pad = expander(args[2]) if len(args) >= 3 and args[2] else "0"
    if not cnt.isdigit():
        ctx.warning("pad length is not integer: {!r}".format(cnt))
        cnt = 0
    else:
        cnt = int(cnt)
    if cnt - len(v) > len(pad):
        pad = (pad * ((cnt - len(v)) // len(pad)))
    if len(v) < cnt:
        v = pad[:cnt - len(v)] + v
    return v


def padright_fn(ctx, fn_name, args, expander):
    """Implements the padright parser function."""
    v = expander(args[0]) if args else ""
    cnt = expander(args[1]).strip() if len(args) >= 2 else "0"
    arg2 = expander(args[2]) if len(args) >= 3 and args[2] else "0"
    pad = arg2 if len(args) >= 3 and arg2 else "0"
    if not cnt.isdigit():
        ctx.warning("pad length is not integer: {!r}".format(cnt))
        cnt = 0
    else:
        cnt = int(cnt)
    if cnt - len(v) > len(pad):
        pad = (pad * ((cnt - len(v)) // len(pad)))
    if len(v) < cnt:
        v = v + pad[:cnt - len(v)]
    return v


def plural_fn(ctx, fn_name, args, expander):
    """Implements the #plural parser function."""
    expr = expander(args[0]).strip() if args else "0"
    v = expr_fn(ctx, fn_name, [expr], lambda x: x)
    # XXX for some language codes, this is more complex.  See {{plural:...}} in
    # https://www.mediawiki.org/wiki/Help:Magic_words
    if v == 1:
        return expander(args[1]).strip() if len(args) >= 2 else ""
    return expander(args[2]).strip() if len(args) >= 3 else ""


def month_num_days(ctx, t):
    mdays = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    v = mdays[t.month - 1]
    if t.month == 2:
        if t.year % 4 == 0 and (t.year % 100 != 0 or t.year % 400 == 0):
            v = 29
    return v


time_fmt_map = {
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
    "I": lambda ctx, t: "1" if t.dst() and t.dst().seconds != 0 else "0",
    "0": lambda ctx, t: t.strftime("%z")[:5],
    "P": lambda ctx, t: t.strftime("%z")[:3] + ":" + t.strftime("%z")[3:5],
    "T": "%Z",
    "Z": lambda ctx, t: 0 if t.utcoffset() == None else t.utcoffset().seconds,
    "t": month_num_days,
    "c": lambda ctx, t: t.isoformat(),
    "r": lambda ctx, t: t.strftime("%a, %d %b %Y %H:%M:%S {}").format(
        t.strftime("%z")[:5]),
    # XXX non-gregorian calendar values
}


def time_fn(ctx, fn_name, args, expander):
    """Implements the #time parser function."""
    fmt = expander(args[0]).strip() if args else ""
    dt = expander(args[1]).strip() if len(args) >= 2 else ""
    lang = expander(args[2]).strip() if len(args) >= 3 else "en"
    loc = expander(args[3]).strip() if len(args) >= 4 else ""

    orig_dt = dt
    dt = re.sub(r"\+", " in ", dt)
    if not dt:
        dt = "now"

    settings = { "RETURN_AS_TIMEZONE_AWARE": True}
    if loc in ("", "0"):
        dt += " UTC"

    if dt.startswith("@"):
        try:
            t = datetime.datetime.fromtimestamp(float(dt[1:]))
        except ValueError:
            ctx.warning("bad time syntax in {}: {!r}"
                        .format(fn_name, orig_dt))
            return ('<strong class="error">Bad time syntax: {}</strong>'
                    .format(html.escape(orig_dt)))
    else:
        t = dateparser.parse(dt, settings=settings)
        if t is None:
            ctx.warning("unrecognized time syntax in {}: {!r}"
                        .format(fn_name, orig_dt))
            return ('<strong class="error">Bad time syntax: {}</strong>'
                    .format(html.escape(orig_dt)))

    # XXX looks like we should not adjust the time
    #if t.utcoffset():
    #    t -= t.utcoffset()

    def fmt_repl(m):
        f = m.group(0)
        if len(f) > 1 and f.startswith('"') and f.endswith('"'):
            return f[1:-1]
        if f in time_fmt_map:
            v = time_fmt_map[f]
            if isinstance(v, str):
                return v
            assert callable(v)
            v = v(ctx, t)
            if not isinstance(v, str):
                v = str(v)
            return v
        return f

    fmt = re.sub(r'(x[mijkot]?)?[^"]|"[^"]*"', fmt_repl, fmt)
    return t.strftime(fmt)


def len_fn(ctx, fn_name, args, expander):
    """Implements the #len parser function."""
    v = expander(args[0]).strip() if args else ""
    return str(len(v))


def pos_fn(ctx, fn_name, args, expander):
    """Implements the #pos parser function."""
    arg0 = expander(args[0]).strip() if args else ""
    arg1 = expander(args[1]) or " " if len(args) >= 2 else " "
    offset = expander(args[2]).strip() if len(args) >= 3 else ""
    if not offset or not offset.isdigit():
        offset = "0"
    offset = int(offset)
    idx = arg0.find(arg1, offset)
    if idx >= 0:
        return str(idx)
    return ""


def rpos_fn(ctx, fn_name, args, expander):
    """Implements the #rpos parser function."""
    arg0 = expander(args[0]).strip() if args else ""
    arg1 = expander(args[1]) or " " if len(args) >= 2 else " "
    offset = expander(args[2]).strip() if len(args) >= 3 else ""
    if not offset or not offset.isdigit():
        offset = "0"
    offset = int(offset)
    idx = arg0.rfind(arg1, offset)
    if idx >= 0:
        return str(idx)
    return "-1"


def sub_fn(ctx, fn_name, args, expander):
    """Implements the #sub parser function."""
    arg0 = expander(args[0]).strip() if args else ""
    start = expander(args[1]).strip() if len(args) >= 2 else ""
    length = expander(args[2]).strip() if len(args) >= 3 else ""
    try:
        start = int(start)
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


def pad_fn(ctx, fn_name, args, expander):
    """Implements the pad parser function."""
    v = expander(args[0]).strip() if args else ""
    cnt = expander(args[1]).strip() if len(args) >= 2 else ""
    pad = expander(args[2]) if len(args) >= 3 and args[2] else "0"
    direction = expander(args[3]) if len(args) >= 4 else ""
    if not cnt.isdigit():
        ctx.warning("pad length is not integer: {!r}".format(cnt))
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


def replace_fn(ctx, fn_name, args, expander):
    """Implements the #replace parser function."""
    arg0 = expander(args[0]).strip() if args else ""
    arg1 = expander(args[1]) or " " if len(args) >= 2 else " "
    arg2 = expander(args[2]) if len(args) >= 3 else ""
    return arg0.replace(arg1, arg2)


def explode_fn(ctx, fn_name, args, expander):
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


def urldecode_fn(ctx, fn_name, args, expander):
    """Implements the #urldecode parser function."""
    arg0 = expander(args[0]).strip() if args else ""
    ret = urllib.parse.unquote_plus(arg0)
    return ret


def unimplemented_fn(ctx, fn_name, args, expander):
    ctx.error("unimplemented parserfn {}".format(fn_name))
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
    "SHORTDESC": unimplemented_fn,
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


def call_parser_function(ctx, fn_name, args, expander):
    """Calls the given parser function with the given arguments."""
    assert isinstance(fn_name, str)
    assert isinstance(args, (list, tuple, dict))
    assert callable(expander)
    if fn_name not in PARSER_FUNCTIONS:
        ctx.error("unrecognized parser function {!r}".format(fn_name))
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
                  .format(fn_name, args))
        return ""
    return fn(ctx, fn_name, args, expander)
