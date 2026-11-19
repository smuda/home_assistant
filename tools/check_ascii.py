"""Reject non-ASCII punctuation and symbols in the given files.

The repo CLAUDE.md asks for ASCII in Markdown: `->` not an arrow, `--`
not an em-dash, straight quotes not curly ones. Accented letters (the
Swedish terms) are tolerated, so Latin-script letters and combining
marks pass and every other non-ASCII character -- punctuation,
symbols, separators such as NBSP, control/format characters, numbers,
and letters of other scripts or modifier letters -- is reported.
Stdlib only.

Run via `make lint`, or:
  python3 -I tools/check_ascii.py FILE...
"""

import os
import sys
import unicodedata


def is_allowed(ch: str) -> bool:
    """True for ASCII, Latin-script letters and combining marks."""
    if ord(ch) < 128:
        return True
    category = unicodedata.category(ch)[0]
    if category == "L":
        return unicodedata.name(ch, "").startswith("LATIN ")
    return category == "M"


def check_text(text: str) -> list[tuple[int, int, str]]:
    found = []
    for lineno, line in enumerate(text.split("\n"), start=1):
        for col, ch in enumerate(line, start=1):
            if not is_allowed(ch):
                found.append((lineno, col, ch))
    return found


def check_file(path: str | os.PathLike[str]) -> list[str]:
    try:
        with open(path, encoding="utf-8", newline="") as f:
            text = f.read()
    except UnicodeDecodeError:
        return [f"{path}: not valid UTF-8"]
    return [
        f"{path}:{line}:{col}: U+{ord(ch):04X} "
        f"{unicodedata.name(ch, 'UNKNOWN')}"
        for line, col, ch in check_text(text)
    ]


def main(argv: list[str]) -> int:
    messages = []
    for path in argv:
        messages.extend(check_file(path))
    for message in messages:
        print(message)
    return 1 if messages else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
