# Some definitions used for both Wikitext expansion and parsing
#
# Copyright (c) 2020 Tatu Ylonen.  See file LICENSE and https://ylonen.org

# Character range used for marking magic sequences.  This package
# assumes that these characters do not occur on Wikitext pages.  These
# characters are in the Unicode private use area U+100000..U+10FFFF.
MAGIC_NOWIKI = 0x0010203d  # Used for <nowiki />
MAGIC_NOWIKI_CHAR = chr(MAGIC_NOWIKI)
MAGIC_FIRST = 0x0010203e
MAGIC_LAST = 0x0010fff0
MAX_MAGICS = MAGIC_LAST - MAGIC_FIRST + 1
