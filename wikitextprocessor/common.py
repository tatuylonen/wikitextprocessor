# Some definitions used for both Wikitext expansion and parsing
#
# Copyright (c) 2020 Tatu Ylonen.  See file LICENSE and https://ylonen.org

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


def _nowiki_repl(m):
    return _nowiki_map[m.group(0)]


def _nowiki_sub_fn(m):
    """This function escapes the contents of a <nowiki> ... </nowiki> pair."""
    text = m.group(1)
    text = re.sub(_nowiki_re, _nowiki_repl, text)
    text = re.sub(r"\s+", " ", text)
    return text


def preprocess_text(text):
    """Preprocess the text by handling <nowiki> and comments."""
    assert isinstance(text, str)
    text = re.sub(r"(?si)<\s*nowiki\s*>(.*?)<\s*/\s*nowiki\s*>",
                  _nowiki_sub_fn, text)
    text = re.sub(r"(?si)<\s*nowiki\s*/\s*>", MAGIC_NOWIKI_CHAR, text)
    text = re.sub(r"(?s)<!\s*--.*?--\s*>", "", text)
    return text
