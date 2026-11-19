"""Tests for tools/check_ascii.py.

Fully offline: files are written to temp dirs. Stdlib only. Non-ASCII
characters are spelled as \\u escapes so this file stays ASCII.

Run from the repo root:

    python3 -m unittest discover -s tests/check_ascii
"""

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import check_ascii  # noqa: E402


def write_bytes(root, name, data):
    path = Path(root) / name
    path.write_bytes(data)
    return path


def write(root, name, text):
    return write_bytes(root, name, text.encode("utf-8"))


class IsAllowedTest(unittest.TestCase):
    def test_rejected_punctuation_and_symbols(self):
        cases = {
            "em dash": "\u2014",
            "en dash": "\u2013",
            "rightwards arrow": "\u2192",
            "left double quote": "\u201c",
            "right double quote": "\u201d",
            "left single quote": "\u2018",
            "right single quote": "\u2019",
            "nbsp": "\u00a0",
            "degree": "\u00b0",
            "ellipsis": "\u2026",
            "superscript two": "\u00b2",
            "modifier letter apostrophe": "\u02bc",
            "hangul filler": "\u3164",
            "greek alpha": "\u03b1",
            "cyrillic a": "\u0430",
        }
        for name, ch in cases.items():
            with self.subTest(name):
                self.assertFalse(check_ascii.is_allowed(ch))

    def test_allowed_letters(self):
        cases = {
            "a ring": "\u00e5",
            "a diaeresis": "\u00e4",
            "o diaeresis": "\u00f6",
            "A ring": "\u00c5",
            "e acute": "\u00e9",
            "sharp s": "\u00df",
        }
        for name, ch in cases.items():
            with self.subTest(name):
                self.assertTrue(check_ascii.is_allowed(ch))

    def test_combining_mark_allowed(self):
        self.assertTrue(check_ascii.is_allowed("\u0308"))

    def test_ascii_allowed(self):
        for ch in ("a", "Z", "0", " ", "\n", "\t", "-", "'", '"', "`", "~"):
            with self.subTest(repr(ch)):
                self.assertTrue(check_ascii.is_allowed(ch))


class CheckTextTest(unittest.TestCase):
    def test_plain_ascii_no_findings(self):
        text = "# Title\n\n- item -- with `code` and 'quotes'\n"
        self.assertEqual(check_ascii.check_text(text), [])

    def test_empty_text(self):
        self.assertEqual(check_ascii.check_text(""), [])

    def test_allowed_non_ascii_no_findings(self):
        text = "Sol\u00e5ngd \u00c5re \u00e4r h\u00f6g, caf\u00e9 a\u0308\n"
        self.assertEqual(check_ascii.check_text(text), [])

    def test_each_rejected_char_found(self):
        for ch in "\u2014\u2013\u2192\u201c\u201d\u2018\u2019\u00a0\u00b0\u2026":
            with self.subTest(hex(ord(ch))):
                self.assertEqual(check_ascii.check_text("a" + ch + "b"), [(1, 2, ch)])

    def test_line_and_column_are_one_based(self):
        text = "ok\nab\u2014cd\nplain\n\u2192x \u00b0y\n"
        self.assertEqual(
            check_ascii.check_text(text),
            [
                (2, 3, "\u2014"),
                (4, 1, "\u2192"),
                (4, 4, "\u00b0"),
            ],
        )

    def test_modifier_letter_apostrophe_position(self):
        self.assertEqual(
            check_ascii.check_text("ab\nc\u02bcd\n"), [(2, 2, "\u02bc")]
        )

    def test_non_latin_letters_found(self):
        for ch in "\u3164\u03b1\u0430":
            with self.subTest(hex(ord(ch))):
                self.assertEqual(check_ascii.check_text("a" + ch), [(1, 2, ch)])

    def test_first_char_first_line(self):
        self.assertEqual(check_ascii.check_text("\u2014"), [(1, 1, "\u2014")])

    def test_column_counts_characters_not_bytes(self):
        # a-ring is 2 bytes in UTF-8 but 1 character.
        text = "\u00e5\u00e4\u00f6 \u2014"
        self.assertEqual(check_ascii.check_text(text), [(1, 5, "\u2014")])

    def test_combining_mark_counts_as_a_column(self):
        text = "a\u0308\u2014"
        self.assertEqual(check_ascii.check_text(text), [(1, 3, "\u2014")])

    def test_crlf_line_numbers(self):
        text = "a\r\nb \u2014\r\n"
        self.assertEqual(check_ascii.check_text(text), [(2, 3, "\u2014")])


class CheckFileTest(unittest.TestCase):
    def test_message_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "README.md", "ab\nxy \u2014 z\n")
            self.assertEqual(
                check_ascii.check_file(path),
                [f"{path}:2:4: U+2014 EM DASH"],
            )

    def test_message_uses_path_as_given(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.md", "\u2192\n")
            self.assertEqual(
                check_ascii.check_file(str(path)),
                [f"{path}:1:1: U+2192 RIGHTWARDS ARROW"],
            )

    def test_multiple_messages_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.md", "\u00b0\nx\u2013\n")
            self.assertEqual(
                check_ascii.check_file(path),
                [
                    f"{path}:1:1: U+00B0 DEGREE SIGN",
                    f"{path}:2:2: U+2013 EN DASH",
                ],
            )

    def test_clean_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.md", "plain \u00e5\u00e4\u00f6\n")
            self.assertEqual(check_ascii.check_file(path), [])

    def test_invalid_utf8(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_bytes(tmp, "bad.md", b"ok\n\xff\xfe broken\n")
            self.assertEqual(
                check_ascii.check_file(path),
                [f"{path}: not valid UTF-8"],
            )


class MainTest(unittest.TestCase):
    def run_main(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = check_ascii.main(argv)
        return code, out.getvalue()

    def test_no_paths(self):
        self.assertEqual(self.run_main([]), (0, ""))

    def test_clean_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.md", "all ascii\n")
            self.assertEqual(self.run_main([str(path)]), (0, ""))

    def test_finding_returns_one_and_prints(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.md", "x \u2014\n")
            code, out = self.run_main([str(path)])
        self.assertEqual(code, 1)
        self.assertEqual(out, f"{path}:1:3: U+2014 EM DASH\n")

    def test_messages_in_file_then_position_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = write(tmp, "a.md", "\u2014 \u2013\nx \u2192\n")
            clean = write(tmp, "clean.md", "fine\n")
            b = write(tmp, "b.md", "\u00b0\n")
            code, out = self.run_main([str(a), str(clean), str(b)])
        self.assertEqual(code, 1)
        self.assertEqual(
            out.splitlines(),
            [
                f"{a}:1:1: U+2014 EM DASH",
                f"{a}:1:3: U+2013 EN DASH",
                f"{a}:2:3: U+2192 RIGHTWARDS ARROW",
                f"{b}:1:1: U+00B0 DEGREE SIGN",
            ],
        )

    def test_one_bad_file_among_clean_still_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = write(tmp, "good.md", "fine\n")
            bad = write(tmp, "bad.md", "\u201cquoted\u201d\n")
            code, out = self.run_main([str(good), str(bad)])
        self.assertEqual(code, 1)
        self.assertEqual(len(out.splitlines()), 2)

    def test_invalid_utf8_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = write_bytes(tmp, "bad.md", b"\xff\n")
            code, out = self.run_main([str(bad)])
        self.assertEqual(code, 1)
        self.assertEqual(out, f"{bad}: not valid UTF-8\n")


if __name__ == "__main__":
    unittest.main()
