# Some definitions used for both Wikitext expansion and parsing
#
# Copyright (c) 2020-2022 Tatu Ylonen.  See file LICENSE and https://ylonen.org

import re


# Character range used for marking magic sequences.  This package
# assumes that these characters do not occur on Wikitext pages.  These
# characters are in the Unicode private use area U+100000..U+10FFFF.
MAGIC_NUMBER = 0x0010203d
# Instead of doing `MAGIC_NUMBER + 1` manually
mnum = iter(range(MAGIC_NUMBER, MAGIC_NUMBER + 100)) # 100 is a convenient
                                                     # upper bound

MAGIC_NOWIKI = next(mnum)  # Used for <nowiki />
MAGIC_NOWIKI_CHAR = chr(MAGIC_NOWIKI)

# Used to replace single quotes inside HTML double-quoted attributes:
# <tag attr="something with 'single quotes', like this" />
MAGIC_SINGLE_QUOTE = next(mnum) 
MAGIC_SQUOTE_CHAR = chr(MAGIC_SINGLE_QUOTE)

# replace `-{}-` in Chinese Wiktionary template `ja-romanization of` to fix
# encode template bug
MAGIC_ZH_PLACEHOLDER = next(mnum) 
MAGIC_ZH_PLACEHOLDER_CHAR = chr(MAGIC_ZH_PLACEHOLDER)

# Magic characters used to store templates and other expandable
# text while the stuff around them are being parsed.
MAGIC_FIRST = next(mnum) 
MAGIC_LAST = 0x0010fff0
MAX_MAGICS = MAGIC_LAST - MAGIC_FIRST + 1

# Mappings performed for text inside <nowiki>...</nowiki>
_nowiki_map = {
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
_nowiki_re = re.compile("|".join(re.escape(x) for x in _nowiki_map.keys()))

def nowiki_quote(text):
    """Quote text inside <nowiki>...</nowiki> by escaping certain characters."""
    def _nowiki_repl(m):
        return _nowiki_map[m.group(0)]

    text = re.sub(_nowiki_re, _nowiki_repl, text)
    return text
