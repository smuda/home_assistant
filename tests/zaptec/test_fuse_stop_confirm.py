"""Tests for the fuse guard's 20 s stop confirmation.

Loads the real automations/zaptec/Dynamic_fuse_protection.yaml and
helpers/input_boolean/zaptec_fuse_stop_pending.yaml. A minimal
interpreter evaluates the automation's `variables:` block, its
automation-level condition, and walks the `actions:` (`if`/`then` and
`choose` over template conditions), recording the service calls instead
of executing them. Each scenario is one run of the guard against a
mocked entity table; the timer is the helper's `last_changed`.

Run from the repo root with `make test`, or directly:

    python3 -m unittest discover -s tests/zaptec

Needs jinja2 and pyyaml; `make test` installs them into .venv from
requirements-dev.txt.
"""

import datetime as dt
import unittest

from ha_harness import (
    NOW,
    PAUSED,
    ROOT,
    STOP_PENDING,
    Entity,
    as_list,
    load_yaml,
    make_env,
    render_variables,
    state_triggers,
)
from test_dynamic_fuse_protection import AUTOMATION, build_entities

HELPER = ROOT / "helpers" / "input_boolean" / "zaptec_fuse_stop_pending.yaml"

STOP_BUTTON = "button.zag064494_stoppa_laddning"
MAX_ENTITY = "number.zag064494_max_laddstrom"

PENDING_ON = ("input_boolean.turn_on", STOP_PENDING)
PENDING_OFF = ("input_boolean.turn_off", STOP_PENDING)
PRESS_STOP = ("button.press", STOP_BUTTON)
PAUSE_ON = ("input_boolean.turn_on", PAUSED)
SET_MAX = ("number.set_value", MAX_ENTITY)

# A phase total of 35 A with the optimiser not yielding: even 6 A will
# not fit, and the 24 A emergency threshold is crossed too, but the
# commanded max is already 6 A, so there is nothing to cut.
STOP_CASE = {"p1": 35.0, "ems": "2"}


def entities(pending=None, pending_age=0, pause_age=10000, status=None, **kw):
    """Entity table for one run.

    pending is "on"/"off", or None for a missing helper entity;
    pending_age is how long it has held that state; pause_age is the
    time since the pause helper last changed.
    """
    e = build_entities(**kw)
    e[PAUSED] = Entity("off", NOW - dt.timedelta(seconds=pause_age), NOW)
    if pending is not None:
        e[STOP_PENDING] = Entity(
            pending, NOW - dt.timedelta(seconds=pending_age), NOW
        )
    if status is not None:
        e["sensor.zag064494_laddstatus"].state = status
    return e


class Guard:
    """One run of the guard: variables, condition, then the actions."""

    def __init__(self, automation, entities, trigger=None):
        # trigger None leaves it undefined, like a manual run; else it
        # is {"id": trigger}.
        self.automation = automation
        self.env = make_env(entities)
        context = {} if trigger is None else {"trigger": {"id": trigger}}
        self.scope = render_variables(
            self.env, automation["variables"], context
        )
        self.calls = []
        # Rendered data.value of each number.set_value, in order.
        self.writes = []

    def render(self, text):
        return self.env.from_string(text).render(**self.scope)

    def passes(self):
        return all(
            self.render(c["value_template"])
            for c in as_list(self.automation["conditions"])
        )

    def truthy(self, cond):
        if isinstance(cond, list):
            return all(self.truthy(c) for c in cond)
        if isinstance(cond, str):
            return bool(self.render(cond))
        if cond.get("condition") == "template":
            return bool(self.render(cond["value_template"]))
        raise NotImplementedError(cond)

    def run(self):
        self.walk(self.automation["actions"])
        return self.calls

    def walk(self, steps):
        for step in as_list(steps):
            if "if" in step:
                if self.truthy(step["if"]):
                    self.walk(step["then"])
            elif "choose" in step:
                for branch in step["choose"]:
                    if self.truthy(branch["conditions"]):
                        self.walk(branch["sequence"])
                        break
            elif "action" in step:
                target = step["target"]["entity_id"]
                self.calls.append((step["action"], target))
                if "value" in step.get("data", {}):
                    self.writes.append(self.render(step["data"]["value"]))
            else:
                raise NotImplementedError(step)


def seconds(hms):
    h, m, s = (int(x) for x in hms.split(":"))
    return h * 3600 + m * 60 + s


class StopConfirmBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.automation = load_yaml(AUTOMATION)

    def guard(self, trigger=None, **kw):
        return Guard(self.automation, entities(**kw), trigger)

    def calls(self, **kw):
        return self.guard(**kw).run()

    def assertNoStop(self, calls):
        self.assertNotIn(PRESS_STOP, calls)
        self.assertNotIn(PAUSE_ON, calls)


class TestStopConfirmation(StopConfirmBase):
    def test_must_stop_starts_the_timer(self):
        g = self.guard(pending="off", pending_age=500, **STOP_CASE)
        self.assertIs(g.scope["must_stop"], True)
        self.assertIs(g.scope["stop_wanted"], True)
        calls = g.run()
        self.assertIn(PENDING_ON, calls)
        self.assertNotIn(PENDING_OFF, calls)
        self.assertNoStop(calls)

    def test_missing_helper_reads_as_not_pending(self):
        g = self.guard(pending=None, **STOP_CASE)
        self.assertIs(g.scope["stop_pending"], False)
        self.assertEqual(g.scope["secs_pending"], 0)
        calls = g.run()
        self.assertIn(PENDING_ON, calls)
        self.assertNoStop(calls)

    def test_no_stop_before_confirmation(self):
        for age in (0, 4, 7, 10, 19, 19.9):
            with self.subTest(age=age):
                g = self.guard(pending="on", pending_age=age, **STOP_CASE)
                self.assertAlmostEqual(g.scope["secs_pending"], age)
                calls = g.run()
                self.assertNoStop(calls)
                self.assertNotIn(PENDING_ON, calls)
                self.assertNotIn(PENDING_OFF, calls)

    def test_stop_once_confirmed(self):
        for age in (20, 21, 300):
            with self.subTest(age=age):
                calls = self.calls(pending="on", pending_age=age, **STOP_CASE)
                self.assertEqual(calls[0], PRESS_STOP)
                self.assertIn(PENDING_OFF, calls)
                self.assertIn(PAUSE_ON, calls)
                self.assertNotIn(PENDING_ON, calls)
                self.assertNotIn(SET_MAX, calls)

    def test_must_stop_false_clears_pending(self):
        for age in (5, 25, 600):
            with self.subTest(age=age):
                g = self.guard(pending="on", pending_age=age)
                self.assertIs(g.scope["must_stop"], False)
                calls = g.run()
                self.assertIn(PENDING_OFF, calls)
                self.assertNotIn(PENDING_ON, calls)
                self.assertNoStop(calls)

    def test_timer_restarts_after_a_clear(self):
        # Run 1: a dip -- must_stop false -- while the timer is at 5 s.
        calls = self.calls(pending="on", pending_age=5)
        self.assertIn(PENDING_OFF, calls)
        # Run 2: must_stop true again, helper now off since the clear.
        g = self.guard(pending="off", pending_age=3, **STOP_CASE)
        self.assertIn(PENDING_ON, g.run())
        # Run 3: the helper turned on just now; the new last_changed
        # counts, not the 5 s of the first attempt.
        g = self.guard(pending="on", pending_age=1, **STOP_CASE)
        self.assertAlmostEqual(g.scope["secs_pending"], 1)
        self.assertNoStop(g.run())

    def test_restop_lockout_still_applies(self):
        for pause_age, stops in ((29, False), (30, True)):
            with self.subTest(pause_age=pause_age):
                calls = self.calls(
                    pending="on",
                    pending_age=20,
                    pause_age=pause_age,
                    **STOP_CASE,
                )
                self.assertEqual(PRESS_STOP in calls, stops)

    def test_no_stop_without_charging(self):
        g = self.guard(
            pending="on", pending_age=60, status="connected_requesting",
            **STOP_CASE,
        )
        self.assertIs(g.scope["stop_wanted"], False)
        calls = g.run()
        self.assertNoStop(calls)
        self.assertIn(PENDING_OFF, calls)

    def test_no_stop_while_already_paused(self):
        entities_ = entities(pending="on", pending_age=60, **STOP_CASE)
        entities_[PAUSED] = Entity("on", NOW - dt.timedelta(seconds=100), NOW)
        g = Guard(self.automation, entities_)
        self.assertIs(g.scope["stop_wanted"], False)
        calls = g.run()
        self.assertNotIn(PRESS_STOP, calls)
        self.assertIn(PENDING_OFF, calls)


class TestStopConfirmTrigger(StopConfirmBase):
    """The `for:` trigger and now() use different clocks, so its run
    can read just under 20 s; that run counts as confirmed."""

    AGE = 19.99

    def test_confirm_trigger_stops_just_under_20s(self):
        g = self.guard(
            trigger="stop_confirm", pending="on", pending_age=self.AGE,
            **STOP_CASE,
        )
        self.assertIs(g.scope["must_stop"], True)
        self.assertLess(g.scope["secs_pending"], 20)
        calls = g.run()
        self.assertEqual(calls[0], PRESS_STOP)
        self.assertIn(PENDING_OFF, calls)
        self.assertIn(PAUSE_ON, calls)

    def test_other_trigger_does_not_stop_under_20s(self):
        for trigger in ("minute_tick", "p1_change", ""):
            with self.subTest(trigger=trigger):
                g = self.guard(
                    trigger=trigger, pending="on", pending_age=self.AGE,
                    **STOP_CASE,
                )
                self.assertNoStop(g.run())

    def test_confirm_trigger_with_pending_off_does_not_stop(self):
        g = self.guard(
            trigger="stop_confirm", pending="off", pending_age=500,
            **STOP_CASE,
        )
        calls = g.run()
        self.assertNoStop(calls)
        self.assertIn(PENDING_ON, calls)

    def test_confirm_trigger_without_stop_wanted_does_not_stop(self):
        g = self.guard(
            trigger="stop_confirm", pending="on", pending_age=self.AGE,
            status="connected_requesting", **STOP_CASE,
        )
        self.assertIs(g.scope["stop_wanted"], False)
        calls = g.run()
        self.assertNoStop(calls)
        self.assertIn(PENDING_OFF, calls)

    def test_confirm_trigger_respects_restop_lockout(self):
        calls = self.calls(
            trigger="stop_confirm", pending="on", pending_age=self.AGE,
            pause_age=29, **STOP_CASE,
        )
        self.assertNotIn(PRESS_STOP, calls)

    def test_manual_run_without_trigger(self):
        for age, stops in ((0, False), (19.99, False), (20, True)):
            with self.subTest(age=age):
                g = self.guard(pending="on", pending_age=age, **STOP_CASE)
                self.assertNotIn("trigger", g.scope)
                self.assertEqual(PRESS_STOP in g.run(), stops)


class TestEmergencyCut(StopConfirmBase):
    CASE = {"p1": 39.0, "ems": "2", "max_a": 16, "secs_since": 60}

    def test_cut_is_immediate_with_timer_off(self):
        g = self.guard(pending="off", pending_age=500, **self.CASE)
        self.assertIs(g.scope["must_stop"], True)
        self.assertIs(g.scope["emergency"], True)
        self.assertIs(g.scope["do_write"], True)
        calls = g.run()
        self.assertIn(SET_MAX, calls)
        self.assertNoStop(calls)

    def test_cut_is_immediate_with_timer_just_started(self):
        g = self.guard(pending="on", pending_age=1, **self.CASE)
        self.assertIs(g.scope["emergency"], True)
        self.assertIs(g.scope["do_write"], True)
        calls = g.run()
        self.assertIn(SET_MAX, calls)
        self.assertNoStop(calls)


class TestWiring(StopConfirmBase):
    def test_trigger_matches_stop_confirm(self):
        matches = [
            t
            for t in state_triggers(self.automation, STOP_PENDING)
            if t.get("to") == "on"
        ]
        self.assertEqual(len(matches), 1, self.automation["triggers"])
        self.assertEqual(seconds(matches[0]["for"]), 20)
        self.assertEqual(matches[0].get("id"), "stop_confirm")
        self.assertEqual(self.automation["variables"]["stop_confirm"], 20)
        self.assertEqual(
            seconds(matches[0]["for"]),
            self.automation["variables"]["stop_confirm"],
        )

    def test_condition_passes_on_pending_alone(self):
        # Charging ended and no pause: only a pending timer should let
        # the run through, so it can clear the timer.
        for pending, expected in (("on", True), ("off", False)):
            with self.subTest(pending=pending):
                g = self.guard(
                    pending=pending, status="disconnected"
                )
                self.assertIs(g.scope["charging"], False)
                self.assertIs(g.scope["is_paused"], False)
                self.assertIs(g.passes(), expected)

    def test_run_after_charging_ended_clears_timer(self):
        calls = self.calls(
            pending="on", pending_age=30, status="disconnected"
        )
        self.assertIn(PENDING_OFF, calls)
        self.assertNoStop(calls)

    def test_condition_still_passes_while_charging(self):
        self.assertIs(self.guard(pending="off").passes(), True)


class TestHelper(unittest.TestCase):
    def test_starts_off_after_restart(self):
        # A pending stop from before a restart must not count toward
        # the 20 s, so the helper must not restore its last state.
        helper = load_yaml(HELPER)
        self.assertIs(helper["initial"], False)
        self.assertEqual(helper["name"], "zaptec_fuse_stop_pending")


if __name__ == "__main__":
    unittest.main()
