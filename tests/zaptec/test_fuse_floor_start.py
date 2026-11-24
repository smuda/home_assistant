"""Tests for the fuse guard's floor start (issue #48).

Once laddstatus has been `disconnected` for floor_start_delay (60 s) the
guard sets number.zag064494_max_laddstrom to ev_min (6 A), so every
session starts at the floor and the first current write is a ramp from
there. It never writes while the car is merely requesting or finished,
because that would suspend Eco Mode.

See README.md, "Do not disturb Eco Mode".

Uses the interpreter from test_fuse_stop_confirm: the real automation
YAML, a mocked entity table, and the service calls recorded instead of
executed. Each scenario is one run of the guard.

Run from the repo root with `make test`, or directly:

    python3 -m unittest discover -s tests/zaptec

Needs jinja2 and pyyaml; `make test` installs them into .venv from
requirements-dev.txt.
"""

import datetime as dt
import unittest

from ha_harness import NOW, PAUSED, RAMPING, Entity, load_yaml
from test_dynamic_fuse_protection import AUTOMATION
from test_fuse_stop_confirm import (
    MAX_ENTITY,
    PENDING_OFF,
    SET_MAX,
    Guard,
    entities,
)

PAUSE_OFF = ("input_boolean.turn_off", PAUSED)
RAMP_OFF = ("input_boolean.turn_off", RAMPING)
STATUS = "sensor.zag064494_laddstatus"

# Low household load, car off: nothing but the floor start can fire.
LOW_LOAD = {"p1": 8.0, "car": 0, "ems": "2"}


def ago(secs):
    return NOW - dt.timedelta(seconds=secs)


def table(status="disconnected", status_age=3600, max_a=16, paused=False,
          **kw):
    """Entity table with laddstatus at status for status_age seconds."""
    e = entities(status=status, max_a=max_a, **LOW_LOAD, **kw)
    e[STATUS].last_changed = ago(status_age)
    if paused:
        e[PAUSED] = Entity("on", ago(10000), NOW)
    return e


class FloorStartBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.automation = load_yaml(AUTOMATION)

    def guard(self, entity_table):
        return Guard(self.automation, entity_table)

    @staticmethod
    def written(g):
        # The harness renders native types, so a value may be int 6.
        return [str(w) for w in g.writes]


class TestFloorStartWrites(FloorStartBase):
    def test_writes_ev_min_after_the_delay(self):
        for age in (60, 61, 3600):
            with self.subTest(age=age):
                g = self.guard(table(status_age=age))
                self.assertTrue(g.passes())
                self.assertEqual(g.run(), [SET_MAX])
                self.assertEqual(self.written(g), [str(g.scope["ev_min"])])

    def test_no_write_before_the_delay(self):
        for age in (0, 5, 59):
            with self.subTest(age=age):
                g = self.guard(table(status_age=age))
                self.assertNotIn(SET_MAX, g.run())
                self.assertEqual(g.writes, [])

    def test_no_write_when_already_at_the_floor(self):
        g = self.guard(table(max_a=6))
        self.assertFalse(g.passes())
        self.assertNotIn(SET_MAX, g.run())
        self.assertEqual(g.writes, [])

    def test_floor_start_does_not_need_load_headroom(self):
        # Even with the house heavily loaded the floor is 6 A, never
        # more, so the write is the same.
        e = entities(status="disconnected", max_a=16, p1=22.0, car=0,
                     ems="2")
        e[STATUS].last_changed = ago(3600)
        g = self.guard(e)
        self.assertEqual(g.run(), [SET_MAX])
        self.assertEqual(self.written(g), ["6"])


class TestFloorStartWhilePaused(FloorStartBase):
    def test_paused_and_just_unplugged_only_clears_the_pause(self):
        g = self.guard(table(status_age=30, paused=True))
        self.assertTrue(g.passes())
        self.assertEqual(g.run(), [PAUSE_OFF])
        self.assertEqual(g.writes, [])

    def test_paused_and_unplugged_long_clears_then_floors(self):
        for age in (60, 3600):
            with self.subTest(age=age):
                g = self.guard(table(status_age=age, paused=True))
                self.assertTrue(g.passes())
                self.assertEqual(g.run(), [PAUSE_OFF, SET_MAX])
                self.assertEqual(self.written(g), [str(g.scope["ev_min"])])

    def test_paused_unplugged_long_at_the_floor_only_clears_pause(self):
        g = self.guard(table(status_age=3600, max_a=6, paused=True))
        self.assertTrue(g.passes())
        self.assertEqual(g.run(), [PAUSE_OFF])
        self.assertEqual(g.writes, [])


class TestFloorStartNeedsReadableMax(FloorStartBase):
    """An unreadable max current must not be overwritten blindly."""

    def test_unavailable_or_unknown_max_is_not_written(self):
        for state in ("unavailable", "unknown"):
            with self.subTest(state=state):
                e = table()
                e[MAX_ENTITY].state = state
                g = self.guard(e)
                self.assertFalse(g.passes())
                self.assertNotIn(SET_MAX, g.run())
                self.assertEqual(g.writes, [])

    def test_paused_with_unavailable_max_only_clears_the_pause(self):
        e = table(paused=True)
        e[MAX_ENTITY].state = "unavailable"
        g = self.guard(e)
        self.assertEqual(g.run(), [PAUSE_OFF])
        self.assertEqual(g.writes, [])


class TestMissingStatusEntity(FloorStartBase):
    def test_missing_laddstatus_does_nothing(self):
        e = table()
        del e[STATUS]
        g = self.guard(e)
        self.assertFalse(g.passes())
        self.assertNotIn(SET_MAX, g.run())
        self.assertEqual(g.writes, [])


class TestNeverWritesOutsideDisconnected(FloorStartBase):
    """Regression guards: Eco Mode must not be disturbed."""

    def test_requesting_finished_and_unknown_states_are_left_alone(self):
        for status in (
            "connected_requesting",
            "connected_finished",
            "unknown",
            "unavailable",
        ):
            with self.subTest(status=status):
                g = self.guard(table(status=status, status_age=3600))
                self.assertFalse(g.passes())
                self.assertNotIn(SET_MAX, g.run())
                self.assertEqual(g.writes, [])


class TestHelpersClearedOnFloorStart(FloorStartBase):
    def test_stop_pending_is_cleared_and_the_floor_still_written(self):
        g = self.guard(table(pending="on", pending_age=100))
        self.assertTrue(g.passes())
        calls = g.run()
        self.assertIn(PENDING_OFF, calls)
        self.assertIn(SET_MAX, calls)
        self.assertEqual(self.written(g), ["6"])

    def test_ramping_flag_is_cleared_and_the_floor_still_written(self):
        e = table()
        e[RAMPING] = Entity("on", ago(500), NOW)
        g = self.guard(e)
        self.assertTrue(g.passes())
        calls = g.run()
        self.assertIn(RAMP_OFF, calls)
        self.assertIn(SET_MAX, calls)
        self.assertEqual(self.written(g), ["6"])


if __name__ == "__main__":
    unittest.main()
