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
from pathlib import Path

import yaml
from jinja2 import StrictUndefined
from jinja2.nativetypes import NativeEnvironment

ROOT = Path(__file__).resolve().parents[2]
AUTOMATION = ROOT / "automations" / "zaptec" / "Dynamic_fuse_protection.yaml"
OVERLOAD_TEMPLATE = ROOT / "templates" / "p1_sustained_overload.yaml"

NOW = dt.datetime(2026, 11, 18, 12, 0, 0, tzinfo=dt.timezone.utc)

EMS = "sensor.ems_mode_selection_raw"
CMD = "sensor.battery_forced_charge_discharge_cmd_raw"
SUSTAINED = "binary_sensor.p1_sustained_overload"
BATT = "sensor.battery_charging_power"
MAX_ENTITY = "number.zag064494_max_laddstrom"
PAUSED = "input_boolean.zaptec_fuse_paused"
P1_RAW = [f"sensor.p1_meter_strom_fas_{n}" for n in (1, 2, 3)]
P1_FILT = [f"sensor.p1_fas_{n}_filtrerad" for n in (1, 2, 3)]
CAR = [f"sensor.zag064494_strom_fas_{n}" for n in (1, 2, 3)]


class Entity:
    def __init__(self, state, last_changed, last_reported):
        self.state = state
        self.last_changed = last_changed
        self.last_reported = last_reported


class Domain:
    def __init__(self, domain, entities):
        self._domain = domain
        self._entities = entities

    def __getattr__(self, object_id):
        try:
            return self._entities[f"{self._domain}.{object_id}"]
        except KeyError:
            raise AttributeError(object_id)


class States:
    """`states('x')` and `states.<domain>.<object_id>` like HA."""

    def __init__(self, entities):
        self._entities = entities

    def __call__(self, entity_id):
        entity = self._entities.get(entity_id)
        return "unknown" if entity is None else entity.state

    def __getattr__(self, domain):
        if domain.startswith("_"):
            raise AttributeError(domain)
        return Domain(domain, self._entities)


def make_env(entities):
    env = NativeEnvironment(undefined=StrictUndefined)
    env.globals["states"] = States(entities)
    env.globals["is_state"] = lambda eid, value: (
        eid in entities and entities[eid].state == value
    )
    env.globals["now"] = lambda: NOW
    return env


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
    """Entity table for one scenario; defaults are the spec's case A.

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
        env = make_env(entities)
        scope = {}
        for name, value in self.variables.items():
            if isinstance(value, str):
                value = env.from_string(value).render(**scope)
            scope[name] = value
        return scope


def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)


class FuseGuardTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.automation = load_yaml(AUTOMATION)
        cls.evaluator = Evaluator(cls.automation)

    def run_case(self, **kwargs):
        entities = build_entities(**kwargs)
        return self.evaluator.run(entities)


class TestTemplateSemantics(unittest.TestCase):
    """The Jinja builtins stand in for HA's filters; check the inputs used."""

    def render(self, source, **ctx):
        return NativeEnvironment().from_string(source).render(**ctx)

    def test_float_default_on_non_numeric(self):
        for bad in ("unknown", "unavailable", "none", ""):
            self.assertEqual(self.render("{{ v|float(0) }}", v=bad), 0)

    def test_int_default_and_decimal_string(self):
        self.assertEqual(self.render("{{ v|int(0) }}", v="unknown"), 0)
        self.assertEqual(self.render("{{ v|int(0) }}", v="12.49"), 12)
        self.assertEqual(self.render("{{ v|int(0) }}", v=12.49), 12)

    def test_min_max_abs_on_lists(self):
        self.assertEqual(self.render("{{ [3, 1.5, 2]|min }}"), 1.5)
        self.assertEqual(self.render("{{ [3, 1.5, 2]|max }}"), 3)
        self.assertEqual(self.render("{{ (-4)|abs }}"), 4)


class TestFuseGuardBattery(FuseGuardTestBase):
    def test_a_optimiser_charging_discounted(self):
        v = self.run_case()
        self.assertAlmostEqual(v["batt"], 14.0)
        self.assertEqual(v["raw_target"], 16)
        self.assertIs(v["do_write"], True)
        self.assertIs(v["must_stop"], False)
        self.assertIs(v["emergency"], False)

    def test_b_other_ems_mode_no_discount(self):
        v = self.run_case(ems="2")
        self.assertEqual(v["batt"], 0)
        self.assertEqual(v["raw_target"], 6)
        self.assertIs(v["do_write"], False)
        self.assertIs(v["must_stop"], False)

    def test_b2_other_charge_cmd_no_discount(self):
        v = self.run_case(cmd="204")
        self.assertEqual(v["batt"], 0)
        self.assertEqual(v["raw_target"], 6)

    def test_c_sustained_overload_no_discount(self):
        v = self.run_case(sustained="on")
        self.assertEqual(v["batt"], 0)
        self.assertEqual(v["raw_target"], 6)

    def test_d_sustained_unavailable_no_discount(self):
        v = self.run_case(sustained="unavailable")
        self.assertEqual(v["batt"], 0)
        self.assertEqual(v["raw_target"], 6)

    def test_d_sustained_unknown_no_discount(self):
        v = self.run_case(sustained="unknown")
        self.assertEqual(v["batt"], 0)
        self.assertEqual(v["raw_target"], 6)

    def test_d_sustained_missing_no_discount(self):
        v = self.run_case(sustained=None)
        self.assertEqual(v["batt"], 0)
        self.assertEqual(v["raw_target"], 6)

    def test_e_no_battery_household_load_unchanged(self):
        v = self.run_case(ems="0", batt_w=0, p1=22.0)
        self.assertEqual(v["raw_target"], 6)

    def test_f_dead_p1_failsafe_ignores_discount(self):
        v = self.run_case(p1_age=120)
        self.assertAlmostEqual(v["batt"], 14.0)
        for name in ("o1", "o2", "o3"):
            self.assertEqual(v[name], 18)
        self.assertEqual(v["raw_target"], 6)

    def test_f_dead_p1_failsafe_stop_values_unchanged(self):
        v = self.run_case(p1_age=120)
        for name in ("s1", "s2", "s3"):
            self.assertEqual(v[name], 18)

    def test_g_battery_reading_capped(self):
        v = self.run_case(batt_w=50000, p1=30.0)
        self.assertAlmostEqual(v["batt"], 10000 / 3 / 230)
        self.assertAlmostEqual(v["batt"], 14.49, places=2)
        self.assertEqual(v["raw_target"], 12)

    def test_g2_negative_battery_power_clamped(self):
        v = self.run_case(batt_w=-2000)
        self.assertEqual(v["batt"], 0)

    def test_g3_unavailable_battery_power_is_zero(self):
        v = self.run_case(batt_w="unavailable")
        self.assertEqual(v["batt"], 0)

    def test_h_must_stop_discounted_while_optimiser_yields(self):
        v = self.run_case(p1=35.0)
        self.assertIs(v["must_stop"], False)

    def test_h2_must_stop_counts_battery_otherwise(self):
        v = self.run_case(p1=35.0, ems="2")
        self.assertIs(v["must_stop"], True)

    def test_i_emergency_still_cuts_with_discount(self):
        v = self.run_case(
            batt_w=2300, p1=39.333, max_a=16, secs_since=60
        )
        self.assertEqual(v["raw_target"], 6)
        self.assertIs(v["emergency"], True)
        self.assertIs(v["do_write"], True)


class TestTriggers(unittest.TestCase):
    def test_j_state_trigger_on_sustained_overload(self):
        triggers = load_yaml(AUTOMATION)["triggers"]
        matches = [
            t
            for t in triggers
            if t.get("trigger") == "state"
            and t.get("entity_id") == SUSTAINED
            and t.get("to") == "on"
        ]
        self.assertEqual(len(matches), 1, triggers)


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

    def test_k_threshold_on_at_27(self):
        self.assertIs(self.render_state([0.0, 27.0, 0.0]), True)

    def test_k_threshold_off_below_27(self):
        self.assertIs(self.render_state([26.9, 26.9, 26.9]), False)

    def test_k_uses_max_of_phases(self):
        for hot in range(3):
            phases = [5.0, 5.0, 5.0]
            phases[hot] = 30.0
            self.assertIs(self.render_state(phases), True)

    def test_k_unavailable_phases_read_zero(self):
        self.assertIs(
            self.render_state(["unavailable", "unknown", "unavailable"]),
            False,
        )

    def test_k_metadata(self):
        self.assertEqual(self.sensor["delay_on"], "00:01:00")
        self.assertEqual(self.sensor["delay_off"], "01:00:00")
        self.assertEqual(self.sensor["unique_id"], "p1_sustained_overload")
        self.assertEqual(self.sensor["name"], "P1 sustained overload")
        self.assertEqual(self.sensor["device_class"], "problem")


if __name__ == "__main__":
    unittest.main()
