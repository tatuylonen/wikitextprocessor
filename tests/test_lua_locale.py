import locale
import string
from contextlib import contextmanager
from unittest import TestCase

import lupa.lua51 as lupa

from wikitextprocessor import Wtp
from wikitextprocessor.luaexec import initialize_lua

# Locales in which some C libraries count bytes above 0x7F as spaces or
# letters, or change their case: macOS in any UTF-8 locale (0xA0 is a space,
# 0xE0 a letter), and single-byte Latin-1 locales (like Windows code pages).
CANDIDATE_LOCALES = [
    "C.UTF-8",
    "en_US.UTF-8",
    "en_US.ISO8859-1",
    "en_US.ISO-8859-1",
    "en_US.iso88591",
    "de_DE.ISO8859-1",
    "de_DE.ISO-8859-1",
    "fr_FR.ISO8859-1",
]

LOCALE_PROBE = r"""
(string.find("\160", "%s") or string.find("\224", "%a")
 or string.lower("\201") ~= "\201") and true or false
"""


@contextmanager
def misclassifying_locale():
    """Switches LC_CTYPE to a locale in which plain Lua classifies bytes
    above 0x7F, if this system has one; yields its name or None."""
    saved = locale.setlocale(locale.LC_CTYPE)
    try:
        for name in CANDIDATE_LOCALES:
            try:
                locale.setlocale(locale.LC_CTYPE, name)
            except locale.Error:
                continue
            if lupa.LuaRuntime().eval(LOCALE_PROBE):
                yield name
                return
        locale.setlocale(locale.LC_CTYPE, saved)
        yield None
    finally:
        locale.setlocale(locale.LC_CTYPE, saved)


# The members of each class in the C locale.
ASCII_CLASSES = {
    "a": set(string.ascii_letters),
    "c": {chr(b) for b in range(32)} | {"\x7f"},
    "d": set(string.digits),
    "l": set(string.ascii_lowercase),
    "p": set(string.punctuation),
    "s": set(" \t\n\v\f\r"),
    "u": set(string.ascii_uppercase),
    "w": set(string.ascii_letters + string.digits),
    "x": set(string.hexdigits),
}

CLASS_HITS = r"""
function(pattern)
  local hits = {}
  for b = 0, 255 do
    hits[#hits + 1] = string.find(string.char(b), pattern) and "1" or "0"
  end
  return table.concat(hits)
end
"""

CASE_OF_ALL_BYTES = r"""
function(fn)
  local all = {}
  for b = 0, 255 do all[#all + 1] = string.char(b) end
  local changed = {}
  for b, c in ipairs({string.byte(string[fn](table.concat(all)), 1, -1)}) do
    if c ~= b - 1 then changed[#changed + 1] = string.char(b - 1, c) end
  end
  return table.concat(changed)
end
"""


class TestLuaLocale(TestCase):
    def setUp(self):
        self.wtp = Wtp()

    def tearDown(self):
        self.wtp.close_db_conn()

    def check_c_locale_classes(self):
        initialize_lua(self.wtp)
        class_hits = self.wtp.lua.eval(CLASS_HITS)
        for letter, members in ASCII_CLASSES.items():
            expected = "".join(
                "1" if chr(b) in members else "0" for b in range(256)
            )
            complement = expected.translate(str.maketrans("01", "10"))
            for pattern, want in [
                (f"%{letter}", expected),
                (f"[%{letter}]", expected),
                (f"[^%{letter}]", complement),
                (f"%{letter.upper()}", complement),
                (f"[%{letter.upper()}]", complement),
                (f"[^%{letter.upper()}]", expected),
            ]:
                with self.subTest(pattern=pattern):
                    self.assertEqual(class_hits(pattern), want)
        case_changes = self.wtp.lua.eval(CASE_OF_ALL_BYTES)
        self.assertEqual(
            case_changes("lower"),
            "".join(c + c.lower() for c in string.ascii_uppercase),
        )
        self.assertEqual(
            case_changes("upper"),
            "".join(c + c.upper() for c in string.ascii_lowercase),
        )

    def test_c_locale_classes(self):
        self.check_c_locale_classes()

    def test_c_locale_classes_in_misclassifying_locale(self):
        with misclassifying_locale() as name:
            if name is None:
                self.skipTest("no locale here classifies bytes above 0x7F")
            self.check_c_locale_classes()

    def test_utf8_survives_trim_and_lower(self):
        # "à" is C3 A0 and "ム" is E3 83 A0: on macOS in a UTF-8 locale,
        # `%s` took the A0 byte and mw.text.trim() then failed with
        # "string is not UTF-8" (also wikitextprocessor issue #301).
        self.wtp.add_page(
            "Module:test",
            828,
            """
            local export = {}
            function export.trim(frame)
              local s = frame.args[1]:gsub("^%s+", ""):gsub("%s+$", "")
              return mw.text.trim(s)
            end
            function export.lower(frame)
              return mw.text.trim(frame.args[1]:lower())
            end
            function export.upper(frame)
              return mw.text.trim(frame.args[1]:upper())
            end
            function export.words(frame)
              local words = {}
              for w in frame.args[1]:gmatch("%a+") do
                words[#words + 1] = w
              end
              return table.concat(words, "|")
            end
            return export
            """,
            model="Scribunto",
        )
        with misclassifying_locale():
            self.wtp.start_page("umanità")
            for call, expected in [
                ("trim| umanità ", "umanità"),
                ("trim|ム", "ム"),
                ("lower|ÉGALITÉ À", "ÉgalitÉ À"),
                ("upper|città é", "CITTà é"),
                ("words|città à ma", "citt|ma"),
            ]:
                with self.subTest(call=call):
                    self.assertEqual(
                        self.wtp.expand("{{#invoke:test|" + call + "}}"),
                        expected,
                    )

    def test_pattern_rewrite_keeps_other_syntax(self):
        initialize_lua(self.wtp)
        find = self.wtp.lua.eval(
            "function(s, p) return table.concat({string.find(s, p)}, ',') end"
        )
        for subject, pattern, expected in [
            ("a-b", "[%a-]+", "1,3"),  # "-" after a class stays literal
            ("x(a b)y", "%b()", "2,6"),
            ("ab cd", "%f[%a]%a+$", "4,5"),
            ("1]x", "[]%d]+", "1,2"),
            ("a%b", "%%", "2,2"),
            ("aa", "(%a)%1", "1,2,a"),
            ("a.b", "a.b", "1,3"),
            ("x\t\n", "%s+$", "2,3"),
        ]:
            with self.subTest(pattern=pattern):
                self.assertEqual(find(subject, pattern), expected)
        self.assertEqual(
            self.wtp.lua.eval('(string.find("a%sb", "%s", 1, true))'), 2
        )
        with self.assertRaisesRegex(lupa.LuaError, "malformed pattern"):
            self.wtp.lua.eval('string.find("a", "[%a")')
