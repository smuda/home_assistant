"""Tests for automations/zaptec/Battery_hold.yaml.

The automation is driven by its action sequence, so this runs a minimal
interpreter over the subset it uses: `variables:`, then `actions:` with
`repeat: {count, sequence}`, `if:`/`then:`/`else:`, `action:` (recorded,
not executed), `continue_on_error` and `delay` (a no-op that ends the
iteration). Mocked states can change between iterations and in response
to a recorded call, to model the inverter.

Run from the repo root with `make test`, or directly:

    python3 -m unittest discover -s tests/zaptec

Needs jinja2 and pyyaml; `make test` installs them into .venv from
requirements-dev.txt.
"""

import datetime as dt
import unittest

from ha_harness import (
    CMD,
    EMS,
    NOW,
    PAUSED,
    ROOT,
    Entity,
    as_list,
    load_yaml,
    make_env,
    render_variables,
    state_triggers,
)

HOLD = ROOT / "automations" / "zaptec" / "Battery_hold.yaml"
CAR = "sensor.zag064494_laddstatus"
STOP = ("select.select_option", "select.battery_forced_charge_discharge", "Stop (default)")
FORCED = ("select.select_option", "select.ems_mode", "Forced mode")
SELF = ("select.select_option", "select.ems_mode", "Self-consumption mode (default)")


class Runner:
    """Walks an action sequence against mutable mocked entities.

    calls: list of (iteration, (service, entity_id, option)).
    on_iteration(i, entities) runs at the start of each repeat iteration
    (i from 0); on_call(call, entities) runs after each recorded call.
    """

    def __init__(self, automation, entities, on_iteration=None, on_call=None):
        self.automation = automation
        self.entities = entities
        self.on_iteration = on_iteration
        self.on_call = on_call
        self.calls = []
        self.iteration = None

    def template(self, text):
        return make_env(self.entities).from_string(text).render(**self.scope)

    def run(self):
        self.scope = render_variables(
            make_env(self.entities),
            self.automation.get("variables", {}),
            {},
        )
        self.walk(self.automation["actions"])
        return self.calls

    def truthy(self, cond):
        if isinstance(cond, list):
            return all(self.truthy(c) for c in cond)
        if isinstance(cond, str):
            return bool(self.template(cond))
        raise NotImplementedError(cond)

    def walk(self, steps):
        for step in as_list(steps):
            if "repeat" in step:
                rep = step["repeat"]
                for i in range(rep["count"]):
                    self.iteration = i
                    if self.on_iteration:
                        self.on_iteration(i, self.entities)
                    self.walk(rep["sequence"])
                self.iteration = None
            elif "if" in step:
                if self.truthy(step["if"]):
                    self.walk(step.get("then", []))
                else:
                    self.walk(step.get("else", []))
            elif "action" in step:
                target = step["target"]["entity_id"]
                call = (step["action"], target, step["data"]["option"])
                self.calls.append((self.iteration, call))
                if self.on_call:
                    self.on_call(call, self.entities)
            elif "delay" in step:
                pass
            else:
                raise NotImplementedError(step)


def entities(car="connected_charging", ems="0", cmd="170", pause_age=100000):
    e = {}
    for eid, state, changed in (
        (CAR, car, NOW - dt.timedelta(seconds=1000)),
        (PAUSED, "off", NOW - dt.timedelta(seconds=pause_age)),
        (EMS, ems, NOW - dt.timedelta(seconds=1000)),
        (CMD, cmd, NOW - dt.timedelta(seconds=1000)),
    ):
        e[eid] = Entity(state, changed, changed)
    return e


def stop_sets_204(call, ents):
    if call == STOP:
        ents[CMD].state = "204"


class TestBatteryHold(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.automation = load_yaml(HOLD)

    def run_case(self, ents, **hooks):
        return Runner(self.automation, ents, **hooks).run()

    def by_iteration(self, calls):
        out = {}
        for i, call in calls:
            out.setdefault(i, []).append(call)
        return out

    def test_hold_in_self_consumption_window_writes_each_iteration(self):
        calls = self.run_case(entities(ems="0"), on_call=stop_sets_204)
        self.assertEqual(
            self.by_iteration(calls),
            {0: [STOP, FORCED], 1: [STOP, FORCED], 2: [STOP, FORCED]},
        )

    def test_optimiser_in_control_blocks_hold(self):
        calls = self.run_case(entities(ems="3", cmd="204"))
        self.assertEqual(calls, [])

    def test_takeover_mid_charge_stops_further_writes(self):
        def switch(i, ents):
            ents[EMS].state = "0" if i == 0 else "3"

        calls = self.run_case(
            entities(ems="0"), on_iteration=switch, on_call=stop_sets_204
        )
        self.assertEqual(self.by_iteration(calls), {0: [STOP, FORCED]})

    def test_release_skipped_while_optimiser_in_control(self):
        calls = self.run_case(entities(car="disconnected", ems="3"))
        self.assertEqual(calls, [])

    def test_release_writes_self_consumption(self):
        calls = self.run_case(entities(car="disconnected", ems="2"))
        self.assertEqual(
            self.by_iteration(calls), {0: [SELF], 1: [SELF], 2: [SELF]}
        )

    def test_unavailable_ems_sensor_still_holds(self):
        calls = self.run_case(
            entities(ems="unavailable", cmd="204"), on_call=stop_sets_204
        )
        self.assertEqual(
            self.by_iteration(calls),
            {0: [STOP, FORCED], 1: [STOP, FORCED], 2: [STOP, FORCED]},
        )

    def test_refused_stop_does_not_write_forced_mode(self):
        calls = self.run_case(entities(ems="0", cmd="170"))
        self.assertEqual(
            self.by_iteration(calls), {0: [STOP], 1: [STOP], 2: [STOP]}
        )
        self.assertNotIn(FORCED, [c for _, c in calls])

    def test_trigger_on_optimiser_window_end(self):
        matches = [
            t
            for t in state_triggers(self.automation, EMS)
            if str(t.get("to")) == "0" and t.get("for") == "00:00:30"
        ]
        self.assertEqual(len(matches), 1, self.automation["triggers"])


if __name__ == "__main__":
    unittest.main()
