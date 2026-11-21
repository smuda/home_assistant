"""Tests for the fuse guard clearing a pause after a resume from outside HA.

While input_boolean.zaptec_fuse_paused is on, the stop and current-write
branches are off, so a charge resumed in the Zaptec app would leave the
guard blind. The `resumed_outside` variable (paused, charging, and
laddstatus changed after the flag) drives a second `choose` branch that
only turns the flag off. See README.md, "Resumed outside HA".

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

from ha_harness import NOW, PAUSED, Entity, load_yaml
from test_dynamic_fuse_protection import AUTOMATION
from test_fuse_stop_confirm import (
    PAUSE_ON,
    PENDING_ON,
    PRESS_STOP,
    SET_MAX,
    Guard,
    entities,
)

PAUSE_OFF = ("input_boolean.turn_off", PAUSED)
PRESS_RESUME = ("button.press", "button.zag064494_ateruppta_laddning")
STATUS = "sensor.zag064494_laddstatus"

OUTSIDE_RESUME_BRANCH = "{{ resumed_outside }}"

# Even 6 A will not fit: phase total 25.4 A with the car at 5.9 A, so
# the others draw 19.5 A and 19.5 + 6 >= 25.
MUST_STOP = {"p1": 25.4, "max_a": 6, "car": 5.9, "ems": "2"}
# Plenty of room to resume: others at 8 A, car off.
LOW_LOAD = {"p1": 8.0, "car": 0}


def ago(secs):
    return NOW - dt.timedelta(seconds=secs)


def paused_entities(
    flag_age, status="connected_charging", status_age=None, **kw
):
    """Entity table with the pause flag on for flag_age seconds.

    status_age is how long ago laddstatus last changed; None puts it
    just after the flag (flag_age - 1 s ago, floored at 0).
    """
    if status_age is None:
        status_age = max(flag_age - 1, 0)
    e = entities(status=status, **kw)
    e[PAUSED] = Entity("on", ago(flag_age), NOW)
    e[STATUS].last_changed = ago(status_age)
    return e


class OutsideResumeBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.automation = load_yaml(AUTOMATION)

    def guard(self, entity_table):
        return Guard(self.automation, entity_table)

    def branches(self):
        for step in self.automation["actions"]:
            if "choose" in step:
                return step["choose"]
        self.fail("no choose step in actions")

    def true_branches(self, guard):
        """Indices of the choose branches whose conditions hold."""
        return [
            i
            for i, b in enumerate(self.branches())
            if guard.truthy(b["conditions"])
        ]

    def branch_index(self, template):
        """Index of the branch with one template condition."""
        found = [
            i
            for i, b in enumerate(self.branches())
            if [c.get("value_template", "").strip() for c in b["conditions"]]
            == [template]
        ]
        self.assertEqual(len(found), 1, template)
        return found[0]

    def unplug_index(self):
        return self.branch_index("{{ is_paused and status == 'disconnected' }}")

    def resume_index(self):
        # Substring, not exact: the loader keeps the newline and indent
        # of this branch's multi-line template, so an exact match would
        # break on any reflow.
        found = [
            i
            for i, b in enumerate(self.branches())
            if "can_resume" in b["conditions"][0]["value_template"]
        ]
        self.assertEqual(len(found), 1)
        return found[0]


class TestResumedOutside(OutsideResumeBase):
    def test_0414_regression_clears_flag_only(self):
        g = self.guard(
            paused_entities(660, status_age=60, **MUST_STOP)
        )
        self.assertIs(g.scope["is_paused"], True)
        self.assertIs(g.scope["charging"], True)
        self.assertIs(g.scope["must_stop"], True)
        self.assertIs(g.scope["can_resume"], False)
        self.assertIs(g.scope["resumed_outside"], True)
        outside = self.branch_index(OUTSIDE_RESUME_BRANCH)
        self.assertEqual(self.true_branches(g), [outside])
        calls = g.run()
        self.assertEqual(calls, [PAUSE_OFF])
        for forbidden in (PRESS_STOP, PRESS_RESUME, SET_MAX):
            self.assertNotIn(forbidden, calls)

    def test_outside_resume_branch_sits_between_unplug_and_resume(self):
        self.assertEqual(
            self.unplug_index() + 1, self.branch_index(OUTSIDE_RESUME_BRANCH)
        )
        self.assertEqual(
            self.branch_index(OUTSIDE_RESUME_BRANCH) + 1, self.resume_index()
        )

    def test_cloud_lag_after_own_stop_does_not_clear(self):
        # laddstatus still reads connected_charging from before our
        # stop: it changed 120 s ago, the flag only 5 s ago.
        g = self.guard(
            paused_entities(5, status_age=120, **MUST_STOP)
        )
        self.assertIs(g.scope["is_paused"], True)
        self.assertIs(g.scope["charging"], True)
        self.assertIs(g.scope["resumed_outside"], False)
        self.assertEqual(self.true_branches(g), [])
        self.assertNotIn(PAUSE_OFF, g.run())

    def test_equal_timestamps_do_not_count(self):
        g = self.guard(
            paused_entities(100, status_age=100, **MUST_STOP)
        )
        self.assertIs(g.scope["resumed_outside"], False)
        self.assertEqual(self.true_branches(g), [])
        self.assertNotIn(PAUSE_OFF, g.run())

    def test_status_change_after_flag_by_a_hair_counts(self):
        g = self.guard(
            paused_entities(100, status_age=99.9, **MUST_STOP)
        )
        self.assertIs(g.scope["resumed_outside"], True)

    def test_not_charging_does_not_clear(self):
        g = self.guard(
            paused_entities(
                100, status="connected_finished", status_age=10,
                **MUST_STOP,
            )
        )
        self.assertIs(g.scope["charging"], False)
        self.assertIs(g.scope["resumed_outside"], False)
        self.assertNotIn(PAUSE_OFF, g.run())

    def test_not_paused_is_not_resumed_outside(self):
        e = entities(**MUST_STOP)
        e[PAUSED] = Entity("off", ago(1000), NOW)
        e[STATUS].last_changed = ago(10)
        g = self.guard(e)
        self.assertIs(g.scope["is_paused"], False)
        self.assertIs(g.scope["charging"], True)
        self.assertIs(g.scope["resumed_outside"], False)


class TestUnchangedBranches(OutsideResumeBase):
    """Regression guards for the branches next to the outside-resume one."""

    def test_unplug_still_clears_the_flag(self):
        g = self.guard(
            paused_entities(
                100, status="disconnected", status_age=10, **MUST_STOP
            )
        )
        self.assertIs(g.scope["resumed_outside"], False)
        self.assertEqual(self.true_branches(g), [self.unplug_index()])
        self.assertEqual(g.run(), [PAUSE_OFF])

    def test_resume_after_a_quiet_stop(self):
        g = self.guard(
            paused_entities(
                400, status="connected_finished", status_age=399,
                **LOW_LOAD,
            )
        )
        self.assertIs(g.scope["can_resume"], True)
        self.assertEqual(self.true_branches(g), [self.resume_index()])
        self.assertEqual(g.run(), [PRESS_RESUME, PAUSE_OFF])

    def test_resume_min_hold_still_applies(self):
        for age, resumes in ((299, False), (300, True)):
            with self.subTest(age=age):
                g = self.guard(
                    paused_entities(
                        age, status="connected_finished",
                        status_age=age - 1, **LOW_LOAD,
                    )
                )
                self.assertEqual(g.run() == [PRESS_RESUME, PAUSE_OFF], resumes)
                if not resumes:
                    self.assertEqual(g.calls, [])

    def test_resume_during_cloud_lag_with_low_load(self):
        # Charging per a stale laddstatus from before the flag: the new
        # branch stays off and the old resume branch still fires.
        g = self.guard(
            paused_entities(400, status_age=500, **LOW_LOAD)
        )
        self.assertIs(g.scope["charging"], True)
        self.assertIs(g.scope["resumed_outside"], False)
        self.assertEqual(self.true_branches(g), [self.resume_index()])
        self.assertEqual(g.run(), [PRESS_RESUME, PAUSE_OFF])


class TestFollowUpAfterClear(OutsideResumeBase):
    def test_restop_lockout_counts_from_the_clear(self):
        # The flag is off now, changed N s ago by the clear; must_stop
        # held and the 20 s confirmation has run out.
        for age, stops in ((29, False), (30, True)):
            with self.subTest(age=age):
                g = self.guard(
                    entities(
                        pending="on", pending_age=20, pause_age=age,
                        **MUST_STOP,
                    )
                )
                self.assertIs(g.scope["must_stop"], True)
                self.assertIs(g.scope["is_paused"], False)
                calls = g.run()
                self.assertEqual(PRESS_STOP in calls, stops)
                if stops:
                    self.assertIn(PAUSE_ON, calls)
                else:
                    self.assertNotIn(PAUSE_ON, calls)
                self.assertNotIn(PENDING_ON, calls)


if __name__ == "__main__":
    unittest.main()
