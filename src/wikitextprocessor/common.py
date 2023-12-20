# Some definitions used for both Wikitext expansion and parsing
#
# Copyright (c) 2020-2022 Tatu Ylonen.  See file LICENSE and https://ylonen.org

import re
from typing import Iterator

# Character range used for marking magic sequences.  This package
# assumes that these characters do not occur on Wikitext pages.  These
# characters are in the Unicode private use area U+100000..U+10FFFF.
MAGIC_NUMBER: int = 0x0010203D
# Instead of doing `MAGIC_NUMBER + 1` manually
# 100 is a convenient upper bound
mnum: Iterator[int] = iter(range(MAGIC_NUMBER, MAGIC_NUMBER + 100))

MAGIC_NOWIKI: int = next(mnum)  # Used for <nowiki />
MAGIC_NOWIKI_CHAR: str = chr(MAGIC_NOWIKI)

# Used to replace single quotes inside HTML double-quoted attributes:
# <tag attr="something with 'single quotes', like this" />
MAGIC_SINGLE_QUOTE: int = next(mnum)
MAGIC_SQUOTE_CHAR: str = chr(MAGIC_SINGLE_QUOTE)

# Magic characters used to store templates and other expandable
# text while the stuff around them are being parsed.
MAGIC_FIRST: int = next(mnum)
MAGIC_LAST: int = 0x0010FFF0
MAX_MAGICS = MAGIC_LAST - MAGIC_FIRST + 1

# Mappings performed for text inside <nowiki>...</nowiki>
_nowiki_map: dict[str, str] = {
    # ";": "&semi;",
    # "&": "&amp;",
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
    "_": "&#95;",  # wikitext __MAGIC_WORDS__
}
_nowiki_re: re.Pattern[str] = re.compile(
    "|".join(re.escape(x) for x in _nowiki_map.keys())
)


def nowiki_quote(text: str) -> str:
    """Quote text inside <nowiki>...</nowiki> by escaping certain characters."""

    def _nowiki_repl(m: re.Match[str]) -> str:
        return _nowiki_map[m.group(0)]

    return re.sub(_nowiki_re, _nowiki_repl, text)


def add_newline_to_expansion(text: str) -> str:
    """https://meta.wikimedia.org/wiki/Help:Newlines_and_spaces#Automatic_newline
    When templates (and parserfunctions) are expanded, we should check for
    these special characters at the start and insert a newline if detected."""
    if isinstance(text, str) and text.startswith(("*", ";", ":", "#", "{|")):
        return "\n" + text
    return text
