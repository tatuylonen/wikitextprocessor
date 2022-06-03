# Some definitions used for both Wikitext expansion and parsing
#
# Copyright (c) 2020-2022 Tatu Ylonen.  See file LICENSE and https://ylonen.org

import re
import html


# Character range used for marking magic sequences.  This package
# assumes that these characters do not occur on Wikitext pages.  These
# characters are in the Unicode private use area U+100000..U+10FFFF.
MAGIC_NOWIKI = 0x0010203d  # Used for <nowiki />
MAGIC_NOWIKI_CHAR = chr(MAGIC_NOWIKI)
MAGIC_FIRST = 0x0010203e
MAGIC_LAST = 0x0010fff0
MAX_MAGICS = MAGIC_LAST - MAGIC_FIRST + 1

# Mappings performed for text inside <nowiki>...</nowiki>
_nowiki_map = {
    ";": "&semi;",
    "&": "&amp;",
    "=": "&equals;",
    "<": "&lt;",
    ">": "&gt;",
    "*": "&ast;",
    "#": "&num;",
    ":": "&colon;",
    "!": "&excl;",
    "|": "&vert;",
    "[": "&lsqb;",
    "]": "&rsqb;",
    "{": "&lbrace;",
    "}": "&rbrace;",
    '"': "&quot;",
    "'": "&apos;",
}
_nowiki_re = re.compile("|".join(re.escape(x) for x in _nowiki_map.keys()))

def nowiki_quote(text):
    """Quote text inside <nowiki>...</nowiki> by escaping certain characters."""
    def _nowiki_repl(m):
        return _nowiki_map[m.group(0)]

    text = re.sub(_nowiki_re, _nowiki_repl, text)
    return text
