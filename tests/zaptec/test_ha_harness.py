"""Tests for the filters the harness adds to its Jinja environment.

The harness mirrors the Home Assistant filters the automations use, so
a wrong mirror makes every other test lie. Each case renders through
make_env({}), a NativeEnvironment, so results come back as native
Python values.

Run from the repo root with `make test`, or directly:

    python3 -m unittest discover -s tests/zaptec

Needs jinja2 and pyyaml; `make test` installs them into .venv from
requirements-dev.txt.
"""

import datetime as dt
import unittest

from ha_harness import make_env


def render(source, **context):
    return make_env({}).from_string(source).render(**context)


class BoolFilterTest(unittest.TestCase):
    def test_truthy_strings(self):
        for value in ("true", "On", " yes ", "1", "enable"):
            with self.subTest(value=value):
                self.assertIs(render("{{ v | bool }}", v=value), True)

    def test_falsy_strings(self):
        for value in ("false", "off", "no", "0", "disable"):
            with self.subTest(value=value):
                self.assertIs(render("{{ v | bool }}", v=value), False)

    def test_bool_passthrough(self):
        self.assertIs(render("{{ v | bool }}", v=True), True)
        self.assertIs(render("{{ v | bool }}", v=False), False)

    def test_numbers_are_true_unless_zero(self):
        for value in (2, 0.5):
            with self.subTest(value=value):
                self.assertIs(render("{{ v | bool }}", v=value), True)
        for value in (0, 0.0):
            with self.subTest(value=value):
                self.assertIs(render("{{ v | bool }}", v=value), False)

    def test_unrecognised_without_default_raises(self):
        for value in ("maybe", None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    render("{{ v | bool }}", v=value)

    def test_default_used_when_not_convertible(self):
        self.assertIs(render("{{ 'maybe' | bool(false) }}"), False)
        self.assertEqual(render("{{ 'unavailable' | bool('x') }}"), "x")

    def test_default_ignored_when_convertible(self):
        self.assertIs(render("{{ 'on' | bool(false) }}"), True)


class AsLocalFilterTest(unittest.TestCase):
    def test_naive_gets_utc_with_same_wall_time(self):
        naive = dt.datetime(2026, 11, 18, 12, 30, 0)
        result = render("{{ v | as_local }}", v=naive)
        self.assertEqual(result.replace(tzinfo=None), naive)
        self.assertEqual(result.tzinfo, dt.timezone.utc)

    def test_aware_is_converted_to_utc(self):
        plus2 = dt.timezone(dt.timedelta(hours=2))
        aware = dt.datetime(2026, 11, 18, 12, 0, 0, tzinfo=plus2)
        result = render("{{ v | as_local }}", v=aware)
        self.assertEqual(result.tzinfo, dt.timezone.utc)
        self.assertEqual(result.hour, 10)
        self.assertEqual(result, aware)


if __name__ == "__main__":
    unittest.main()
