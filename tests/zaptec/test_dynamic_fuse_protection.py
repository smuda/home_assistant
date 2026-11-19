"""Tests for the Zaptec fuse guard's optimiser-battery discount.

Loads the real automations/zaptec/Dynamic_fuse_protection.yaml and
templates/p1_sustained_overload.yaml, evaluates the automation's
`variables:` block in order the way Home Assistant does (each string
rendered as a Jinja template, output parsed back to a native type) with
mocked HA template functions, and checks the decision variables.

Run from the repo root:

    python3 -m unittest discover -s tests/zaptec

Needs jinja2 and pyyaml (not part of the repo's tooling).
"""

import datetime as dt
import unittest

from ha_harness import (
    CMD,
    EMS,
    NOW,
    P1_RAW,
    PAUSED,
    ROOT,
    SUSTAINED,
    Entity,
    load_yaml,
    make_env,
    render_variables,
    state_triggers,
)

AUTOMATION = ROOT / "automations" / "zaptec" / "Dynamic_fuse_protection.yaml"
OVERLOAD_TEMPLATE = ROOT / "templates" / "p1_sustained_overload.yaml"

BATT = "sensor.battery_charging_power"
MAX_ENTITY = "number.zag064494_max_laddstrom"
P1_FILT = [f"sensor.p1_fas_{n}_filtrerad" for n in (1, 2, 3)]
CAR = [f"sensor.zag064494_strom_fas_{n}" for n in (1, 2, 3)]


def build_entities(
    ems="3",
    cmd="170",
    sustained="off",
    batt_w=9660,
    p1=23.0,
    max_a=6,
    car=None,
    p1_age=5,
    secs_since=1000,
):
    """Entity table for one scenario; defaults are the optimiser charging at 9660 W.

    sustained=None means the entity does not exist.
    """
    car = max_a if car is None else car
    changed = NOW - dt.timedelta(seconds=secs_since)
    reported = NOW - dt.timedelta(seconds=5)
    p1_reported = NOW - dt.timedelta(seconds=p1_age)
    e = {}

    def put(eid, state, last_changed=changed, last_reported=reported):
        e[eid] = Entity(str(state), last_changed, last_reported)

    put(EMS, ems)
    put(CMD, cmd)
    if sustained is not None:
        put(SUSTAINED, sustained)
    put(BATT, batt_w)
    put(MAX_ENTITY, max_a, changed)
    put(PAUSED, "off", NOW - dt.timedelta(seconds=10000))
    put("sensor.zag064494_laddstatus", "connected_charging")
    for eid in P1_RAW:
        put(eid, p1, last_reported=p1_reported)
    for eid in P1_FILT:
        put(eid, p1)
    for eid in CAR:
        put(eid, car)
    return e


class Evaluator:
    def __init__(self, automation):
        self.variables = automation["variables"]

    def run(self, entities):
        return render_variables(make_env(entities), self.variables, {})


class FuseGuardTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.automation = load_yaml(AUTOMATION)
        cls.evaluator = Evaluator(cls.automation)

    def run_case(self, **kwargs):
        entities = build_entities(**kwargs)
        return self.evaluator.run(entities)


class TestFuseGuardBattery(FuseGuardTestBase):
    def test_optimiser_charging_discounted(self):
        v = self.run_case()
        self.assertAlmostEqual(v["batt_a"], 14.0)
        self.assertEqual(v["raw_target"], 16)
        self.assertIs(v["do_write"], True)
        self.assertIs(v["must_stop"], False)
        self.assertIs(v["emergency"], False)

    def test_other_ems_mode_no_discount(self):
        v = self.run_case(ems="2")
        self.assertEqual(v["batt_a"], 0)
        self.assertEqual(v["raw_target"], 6)
        self.assertIs(v["do_write"], False)
        self.assertIs(v["must_stop"], False)

    def test_other_charge_cmd_no_discount(self):
        v = self.run_case(cmd="204")
        self.assertEqual(v["batt_a"], 0)
        self.assertEqual(v["raw_target"], 6)

    def test_sustained_overload_no_discount(self):
        v = self.run_case(sustained="on")
        self.assertEqual(v["batt_a"], 0)
        self.assertEqual(v["raw_target"], 6)

    def test_sustained_unavailable_no_discount(self):
        v = self.run_case(sustained="unavailable")
        self.assertEqual(v["batt_a"], 0)
        self.assertEqual(v["raw_target"], 6)

    def test_sustained_unknown_no_discount(self):
        v = self.run_case(sustained="unknown")
        self.assertEqual(v["batt_a"], 0)
        self.assertEqual(v["raw_target"], 6)

    def test_sustained_missing_no_discount(self):
        v = self.run_case(sustained=None)
        self.assertEqual(v["batt_a"], 0)
        self.assertEqual(v["raw_target"], 6)

    def test_no_battery_household_load_unchanged(self):
        v = self.run_case(ems="0", batt_w=0, p1=22.0)
        self.assertEqual(v["raw_target"], 6)

    def test_dead_p1_failsafe_ignores_discount(self):
        v = self.run_case(p1_age=120)
        self.assertAlmostEqual(v["batt_a"], 14.0)
        for name in ("o1", "o2", "o3"):
            self.assertEqual(v[name], 18)
        self.assertEqual(v["raw_target"], 6)

    def test_dead_p1_failsafe_stop_values_unchanged(self):
        v = self.run_case(p1_age=120)
        for name in ("s1", "s2", "s3"):
            self.assertEqual(v[name], 18)

    def test_battery_reading_capped(self):
        v = self.run_case(batt_w=50000, p1=30.0)
        self.assertAlmostEqual(v["batt_a"], 10000 / 3 / 230)
        self.assertAlmostEqual(v["batt_a"], 14.49, places=2)
        self.assertEqual(v["raw_target"], 12)

    def test_negative_battery_power_clamped(self):
        v = self.run_case(batt_w=-2000)
        self.assertEqual(v["batt_a"], 0)

    def test_unavailable_battery_power_is_zero(self):
        v = self.run_case(batt_w="unavailable")
        self.assertEqual(v["batt_a"], 0)

    def test_must_stop_discounted_while_optimiser_yields(self):
        v = self.run_case(p1=35.0)
        self.assertIs(v["must_stop"], False)

    def test_must_stop_counts_battery_otherwise(self):
        v = self.run_case(p1=35.0, ems="2")
        self.assertIs(v["must_stop"], True)

    def test_emergency_still_cuts_with_discount(self):
        v = self.run_case(
            batt_w=2300, p1=39.333, max_a=16, secs_since=60
        )
        self.assertEqual(v["raw_target"], 6)
        self.assertIs(v["emergency"], True)
        self.assertIs(v["do_write"], True)


class TestTriggers(unittest.TestCase):
    def test_state_trigger_on_sustained_overload(self):
        automation = load_yaml(AUTOMATION)
        matches = [
            t
            for t in state_triggers(automation, SUSTAINED)
            if t.get("to") == "on"
        ]
        self.assertEqual(len(matches), 1, automation["triggers"])


class TestSustainedOverloadSensor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = load_yaml(OVERLOAD_TEMPLATE)
        cls.sensor = data[0]["binary_sensor"][0]

    def render_state(self, phases):
        entities = {
            eid: Entity(str(val), NOW, NOW) for eid, val in zip(P1_RAW, phases)
        }
        env = make_env(entities)
        return env.from_string(self.sensor["state"]).render()

    def test_threshold_on_at_27(self):
        self.assertIs(self.render_state([0.0, 27.0, 0.0]), True)

    def test_threshold_off_below_27(self):
        self.assertIs(self.render_state([26.9, 26.9, 26.9]), False)

    def test_uses_max_of_phases(self):
        for hot in range(3):
            phases = [5.0, 5.0, 5.0]
            phases[hot] = 30.0
            self.assertIs(self.render_state(phases), True)

    def test_unavailable_phases_read_zero(self):
        self.assertIs(
            self.render_state(["unavailable", "unknown", "unavailable"]),
            False,
        )

    def test_delays_debounce_on_and_hold_off(self):
        self.assertEqual(self.sensor["delay_on"], "00:01:00")
        self.assertEqual(self.sensor["delay_off"], "01:00:00")

    def test_unique_id_pinned(self):
        # The entity id binary_sensor.p1_sustained_overload is an
        # interface: the fuse guard's discount and the overload
        # notification read it by name. A changed or dropped unique_id
        # yields a duplicate ..._2 entity and silently breaks both.
        self.assertEqual(self.sensor["unique_id"], "p1_sustained_overload")


if __name__ == "__main__":
    unittest.main()
