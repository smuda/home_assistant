"""Tests for the fuse guard's ramp (issue #47).

Loads the real automations/zaptec/Dynamic_fuse_protection.yaml and
helpers/input_boolean/zaptec_fuse_ramping.yaml. Reuses the Guard
interpreter from test_fuse_stop_confirm.py: each scenario is one run
against a mocked entity table, and Guard.writes holds the values
written to the charger's max current.

Run from the repo root with `make test`, or directly:

    python3 -m unittest discover -s tests/zaptec

Needs jinja2 and pyyaml; `make test` installs them into .venv from
requirements-dev.txt.
"""

import datetime as dt
import unittest

from ha_harness import NOW, PAUSED, RAMPING, ROOT, Entity, load_yaml
from test_dynamic_fuse_protection import CAR, MAX_ENTITY
from test_fuse_stop_confirm import (
    PAUSE_ON,
    PENDING_OFF,
    PRESS_STOP,
    SET_MAX,
    STOP_CASE,
    Guard,
    StopConfirmBase,
    entities,
)

HELPER = ROOT / "helpers" / "input_boolean" / "zaptec_fuse_ramping.yaml"
STATUS = "sensor.zag064494_laddstatus"

RAMP_ON = ("input_boolean.turn_on", RAMPING)
RAMP_OFF = ("input_boolean.turn_off", RAMPING)


def ago(seconds):
    return NOW - dt.timedelta(seconds=seconds)


def ramp_entities(
    ramp="on", ramp_age=100, status_age=5000, car_reported_age=None, **kw
):
    """Entity table for one ramp run.

    ramp is "on"/"off", or None for a missing helper entity; ramp_age
    is how long it has held that state; status_age is the time since
    laddstatus last changed (older than the flag for a live ramp).
    car_reported_age, if given, is the age of the charger phase sensors'
    last report.
    """
    e = entities(**kw)
    if ramp is not None:
        e[RAMPING] = Entity(ramp, ago(ramp_age), NOW)
    e[STATUS].last_changed = ago(status_age)
    if car_reported_age is not None:
        for eid in CAR:
            e[eid].last_reported = ago(car_reported_age)
    return e


class RampBase(StopConfirmBase):
    def ramp_guard(self, **kw):
        return Guard(self.automation, ramp_entities(**kw))

    def ramp_run(self, **kw):
        g = self.ramp_guard(**kw)
        calls = g.run()
        return g, calls


def scenario(raw, max_a, **kw):
    """Keyword arguments for a run with raw_target == raw at max_a.

    The optimiser discount is off (ems "2"), so other load is
    p1 - car. A phase headroom of 22 - other gives the target; keep the
    car current equal to max_a.
    """
    if raw >= 16:
        other = 3.0
    else:
        other = 22.0 - raw
    return dict(ems="2", batt_w=0, p1=other + max_a, max_a=max_a, **kw)


class TestScenarioHelper(RampBase):
    def test_scenario_gives_the_intended_target(self):
        for raw in (6, 9, 12, 14, 16):
            for max_a in (6, 10, 14, 16):
                with self.subTest(raw=raw, max_a=max_a):
                    g = self.ramp_guard(**scenario(raw, max_a))
                    self.assertEqual(g.scope["raw_target"], raw)
                    self.assertEqual(g.scope["current_max"], max_a)


class TestRampStart(RampBase):
    def test_big_raise_writes_one_step_and_starts_ramp(self):
        g, calls = self.ramp_run(
            ramp="off", ramp_age=500, max_a=6, secs_since=1000
        )
        self.assertEqual(g.scope["raw_target"], 16)
        self.assertEqual(g.writes, [10])
        self.assertIn(RAMP_ON, calls)
        self.assertNotIn(RAMP_OFF, calls)

    def test_regression_2026_11_21_optimiser_grid_charging(self):
        # 01:00:58: car at 6 A, optimiser grid-charging (defaults),
        # target 16. One jump to 16 A put P1 phase 2 at 37.8 A.
        g, calls = self.ramp_run(ramp="off", max_a=6, secs_since=1000)
        self.assertIs(g.scope["optimiser_charging"], True)
        self.assertEqual(g.scope["raw_target"], 16)
        self.assertEqual(g.writes, [10])
        self.assertNotIn(16, g.writes)

    def test_missing_helper_reads_as_not_ramping(self):
        g, calls = self.ramp_run(ramp=None, max_a=6, secs_since=1000)
        self.assertIs(g.scope["ramping"], False)
        self.assertEqual(g.writes, [10])
        self.assertIn(RAMP_ON, calls)

    def test_big_raise_before_min_interval_waits(self):
        g, calls = self.ramp_run(ramp="off", max_a=6, secs_since=600)
        self.assertEqual(g.writes, [])
        self.assertNotIn(RAMP_ON, calls)


class TestSmallRaises(RampBase):
    def test_raise_within_ramp_step_written_directly(self):
        for rise in (3, 4):
            with self.subTest(rise=rise):
                g, calls = self.ramp_run(
                    ramp="off", **scenario(10 + rise, 10, secs_since=1000)
                )
                self.assertEqual(g.scope["delta"], rise)
                self.assertEqual(g.writes, [10 + rise])
                self.assertNotIn(RAMP_ON, calls)

    def test_raise_under_deadband_not_written(self):
        g, calls = self.ramp_run(
            ramp="off", **scenario(12, 10, secs_since=1000)
        )
        self.assertEqual(g.scope["delta"], 2)
        self.assertEqual(g.writes, [])
        self.assertNotIn(SET_MAX, calls)
        self.assertNotIn(RAMP_ON, calls)


class TestRampSteps(RampBase):
    def test_next_step_after_ramp_interval(self):
        g, calls = self.ramp_run(**scenario(16, 10, secs_since=115))
        self.assertIs(g.scope["ramp_live"], True)
        self.assertEqual(g.writes, [14])
        self.assertNotIn(RAMP_OFF, calls)

    def test_no_step_before_ramp_interval(self):
        for secs in (0, 60, 114):
            with self.subTest(secs_since=secs):
                g, calls = self.ramp_run(**scenario(16, 10, secs_since=secs))
                self.assertEqual(g.writes, [])
                self.assertNotIn(SET_MAX, calls)

    def test_final_step_under_deadband_is_written(self):
        g, calls = self.ramp_run(**scenario(16, 14, secs_since=115))
        self.assertEqual(g.scope["delta"], 2)
        self.assertEqual(g.writes, [16])

    def test_final_step_of_one_amp_is_written(self):
        g, calls = self.ramp_run(**scenario(16, 15, secs_since=115))
        self.assertEqual(g.writes, [16])

    def test_whole_ramp_6_to_16(self):
        # Walk the ramp: each run's write becomes the next run's max.
        # Phase sensors are fresh each time (reported after the write).
        max_a, written = 6, []
        g, calls = self.ramp_run(
            ramp="off", **scenario(16, max_a, secs_since=1000)
        )
        self.assertIn(RAMP_ON, calls)
        for _ in range(5):
            if not g.writes:
                break
            max_a = g.writes[-1]
            written.append(max_a)
            g, calls = self.ramp_run(**scenario(16, max_a, secs_since=115))
        self.assertEqual(written, [10, 14, 16])


class TestWriteCap(RampBase):
    def test_no_write_exceeds_target_or_ev_max(self):
        cases = [
            (16, 6, 1000, "off"),
            (16, 10, 115, "on"),
            (16, 14, 115, "on"),
            (16, 12, 115, "on"),
            (14, 6, 1000, "off"),
            (12, 6, 1000, "off"),
            (10, 6, 1000, "off"),
            (16, 13, 1000, "off"),
            (16, 15, 115, "on"),
        ]
        for raw, max_a, secs, ramp in cases:
            with self.subTest(
                raw=raw, max_a=max_a, secs_since=secs, ramp=ramp
            ):
                g, _ = self.ramp_run(
                    ramp=ramp, **scenario(raw, max_a, secs_since=secs)
                )
                self.assertEqual(g.scope["raw_target"], raw)
                for value in g.writes:
                    self.assertGreaterEqual(value, 6)
                    self.assertLessEqual(value, raw)
                    self.assertLessEqual(value, 16)
                    self.assertLessEqual(value - max_a, 4)

    def test_cap_with_battery_discount_scenario(self):
        g, _ = self.ramp_run(ramp="on", max_a=14, secs_since=115)
        self.assertEqual(g.scope["raw_target"], 16)
        self.assertEqual(g.writes, [16])


class TestMissingEntities(RampBase):
    def test_missing_phase_sensor_counts_as_fresh_and_ends_ramp(self):
        # raw_target == current_max == 6 holds with any sensor gone.
        for eid in CAR:
            with self.subTest(missing=eid):
                e = ramp_entities(**scenario(6, 6, secs_since=100))
                del e[eid]
                g = Guard(self.automation, e)
                calls = g.run()
                self.assertIs(g.scope["ramp_live"], True)
                self.assertIs(g.scope["car_fresh"], True)
                self.assertEqual(g.scope["delta"], 0)
                self.assertEqual(g.writes, [])
                self.assertIn(RAMP_OFF, calls)

    def test_missing_phase_sensor_with_flag_off_renders(self):
        for eid in CAR:
            with self.subTest(missing=eid):
                e = ramp_entities(ramp="off", **scenario(6, 6, secs_since=100))
                del e[eid]
                g = Guard(self.automation, e)
                g.run()
                self.assertIs(g.scope["ramp_live"], False)
                self.assertIs(g.scope["car_fresh"], False)

    def test_missing_status_entity_is_not_a_live_ramp(self):
        e = ramp_entities(**scenario(16, 10, secs_since=115))
        e[PAUSED] = Entity("on", ago(100), NOW)
        del e[STATUS]
        g = Guard(self.automation, e)
        self.assertIs(g.scope["ramping"], True)
        self.assertIs(g.scope["ramp_live"], False)
        self.assertIs(g.scope["car_fresh"], False)
        self.assertTrue(g.passes())
        g.run()


class TestNeverBelowEvMin(RampBase):
    def test_unknown_max_writes_one_step_above_ev_min(self):
        # Maintainer rule: "we should never write a number below 6A per
        # phase". The charger's max reads unknown, so current_max is 0.
        e = ramp_entities(ramp="off", **scenario(13, 0, secs_since=1000))
        e[MAX_ENTITY].state = "unknown"
        g = Guard(self.automation, e)
        calls = g.run()
        self.assertEqual(g.scope["current_max"], 0)
        self.assertEqual(g.scope["raw_target"], 13)
        self.assertEqual(g.writes, [10])
        self.assertIn(RAMP_ON, calls)

    def test_unknown_max_with_small_target_writes_ev_min(self):
        e = ramp_entities(ramp="off", **scenario(6, 0, secs_since=1000))
        e[MAX_ENTITY].state = "unknown"
        g = Guard(self.automation, e)
        g.run()
        self.assertEqual(g.scope["current_max"], 0)
        for value in g.writes:
            self.assertGreaterEqual(value, 6)


class TestRampEnd(RampBase):
    def test_target_reached_with_stale_sensors_keeps_flag(self):
        g, calls = self.ramp_run(
            car_reported_age=200, **scenario(16, 16, secs_since=100)
        )
        self.assertIs(g.scope["ramp_live"], True)
        self.assertIs(g.scope["car_fresh"], False)
        self.assertEqual(g.writes, [])
        self.assertNotIn(RAMP_OFF, calls)

    def test_target_reached_with_fresh_sensors_ends_ramp(self):
        g, calls = self.ramp_run(
            car_reported_age=5, **scenario(16, 16, secs_since=100)
        )
        self.assertIs(g.scope["car_fresh"], True)
        self.assertEqual(g.writes, [])
        self.assertIn(RAMP_OFF, calls)

    def test_emergency_cut_written_at_once_and_ends_ramp(self):
        g, calls = self.ramp_run(
            p1=39.0, ems="2", max_a=16, secs_since=60
        )
        self.assertIs(g.scope["emergency"], True)
        self.assertEqual(len(g.writes), 1)
        self.assertLess(g.writes[0], 16)
        self.assertIn(RAMP_OFF, calls)

    def test_normal_cut_ends_ramp(self):
        g, calls = self.ramp_run(**scenario(8, 14, secs_since=1000))
        self.assertEqual(g.writes, [8])
        self.assertIn(RAMP_OFF, calls)

    def test_last_resort_stop_ends_ramp(self):
        g, calls = self.ramp_run(
            pending="on", pending_age=20, **STOP_CASE
        )
        self.assertIn(PRESS_STOP, calls)
        self.assertIn(PAUSE_ON, calls)
        self.assertIn(PENDING_OFF, calls)
        self.assertIn(RAMP_OFF, calls)
        self.assertNotIn(SET_MAX, calls)

    def test_pause_ends_ramp(self):
        e = ramp_entities(**scenario(16, 10, secs_since=115))
        e[PAUSED] = Entity("on", ago(100), NOW)
        g = Guard(self.automation, e)
        calls = g.run()
        self.assertIn(RAMP_OFF, calls)
        self.assertEqual(g.writes, [])

    def test_not_charging_ends_ramp(self):
        g, calls = self.ramp_run(
            pending="on", pending_age=30, status="disconnected"
        )
        self.assertIn(RAMP_OFF, calls)
        self.assertEqual(g.writes, [])

    def test_no_turn_off_when_flag_is_off(self):
        for kw in (
            scenario(16, 16, secs_since=100),
            scenario(8, 14, secs_since=1000),
        ):
            with self.subTest(**kw):
                g, calls = self.ramp_run(ramp="off", **kw)
                self.assertNotIn(RAMP_OFF, calls)


class TestStaleFlag(RampBase):
    # The flag is older than laddstatus's last_changed: an earlier
    # session, or interrupted by a status change.
    STALE = {"ramp_age": 600, "status_age": 100}

    def test_stale_flag_is_not_live(self):
        g = self.ramp_guard(**self.STALE, **scenario(16, 10, secs_since=200))
        self.assertIs(g.scope["ramping"], True)
        self.assertIs(g.scope["ramp_live"], False)

    def test_small_raise_not_written_and_flag_cleared(self):
        g, calls = self.ramp_run(
            **self.STALE, **scenario(12, 10, secs_since=200)
        )
        self.assertEqual(g.writes, [])
        self.assertIn(RAMP_OFF, calls)

    def test_big_raise_before_min_interval_not_written_and_flag_cleared(self):
        g, calls = self.ramp_run(
            **self.STALE, **scenario(16, 6, secs_since=200)
        )
        self.assertEqual(g.scope["delta"], 10)
        self.assertEqual(g.writes, [])
        self.assertIn(RAMP_OFF, calls)
        self.assertNotIn(RAMP_ON, calls)

    def test_big_raise_after_min_interval_restarts_ramp(self):
        g, calls = self.ramp_run(
            **self.STALE, **scenario(16, 6, secs_since=1000)
        )
        self.assertEqual(g.writes, [10])
        self.assertIn(RAMP_OFF, calls)
        self.assertIn(RAMP_ON, calls)
        self.assertLess(calls.index(RAMP_OFF), calls.index(RAMP_ON))


class TestHelperAndConfig(unittest.TestCase):
    def test_helper_starts_off_after_restart(self):
        # A ramp never survives a restart; the name pins the entity id.
        helper = load_yaml(HELPER)
        self.assertIs(helper["initial"], False)
        self.assertEqual(helper["name"], "zaptec_fuse_ramping")

    def test_config_variables(self):
        variables = load_yaml(
            ROOT / "automations" / "zaptec" / "Dynamic_fuse_protection.yaml"
        )["variables"]
        self.assertEqual(variables["ramp_step"], 4)
        self.assertEqual(variables["ramp_interval"], 115)


if __name__ == "__main__":
    unittest.main()
