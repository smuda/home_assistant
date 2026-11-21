"""Tests for the held EMS values the fuse guard reads.

Loads the real templates/sungrow_ems_held.yaml and
automations/zaptec/Dynamic_fuse_protection.yaml. A small simulator
plays raw Sungrow polls and battery readings on a timeline: it fires
the trigger-based templates' state and `for:` triggers the way Home
Assistant does, renders them with `this` and `trigger`, and runs the
guard's `variables:` block at chosen times.

Run from the repo root with `make test`, or directly:

    python3 -m unittest discover -s tests/zaptec
"""

import datetime as dt
import types
import unittest

from ha_harness import (
    CMD,
    CMD_HELD,
    EMS,
    EMS_HELD,
    NOW,
    P1_RAW,
    ROOT,
    Entity,
    as_list,
    load_yaml,
    make_env,
    render_variables,
)
from test_dynamic_fuse_protection import AUTOMATION, build_entities

TEMPLATE = ROOT / "templates" / "sungrow_ems_held.yaml"

FAILED = ("unavailable", "unknown")


def seconds(hms):
    h, m, s = (int(x) for x in hms.split(":"))
    return h * 3600 + m * 60 + s


def as_state(value):
    return "None" if value is None else str(value).strip()


def held_block(blocks, raw):
    for block in blocks:
        if "trigger" in block and block["trigger"][0].get("entity_id") == raw:
            return block
    raise KeyError(raw)


class World:
    """Entities on a timeline, with the hold templates wired in.

    Time t is seconds after NOW. Starts with the optimiser charging
    (3/170, battery 9660 W) and P1 at 35 A per phase, which needs the
    battery discount to avoid a stop.
    """

    def __init__(self, blocks, guard_vars, batt_w=9660, p1=35.0):
        self.blocks = blocks
        self.guard_vars = guard_vars
        self.t = 0.0
        self.timers = []  # (time, raw entity id, trigger id)
        self.warnings = []  # (time, message)
        self.e = build_entities(batt_w=batt_w, p1=p1)
        for raw in (EMS, CMD):
            self.e[raw] = Entity("unknown", self.now(), self.now())
        self.set_raw(EMS, "3")
        self.set_raw(CMD, "170")

    def now(self):
        return NOW + dt.timedelta(seconds=self.t)

    def env(self):
        return make_env(self.e, now=self.now())

    def advance(self, t):
        while self.timers and min(self.timers)[0] <= t:
            self.timers.sort()
            when, raw, trig_id = self.timers.pop(0)
            self.t = when
            self.fire_held(raw, trig_id)
        self.t = t

    def at(self, t, eid, state):
        self.advance(t)
        if eid in (EMS, CMD):
            self.set_raw(eid, state)
        else:
            self.e[eid].state = str(state)

    def set_raw(self, raw, state):
        state = str(state)
        if self.e[raw].state == state:
            return
        self.e[raw] = Entity(state, self.now(), self.now())
        self.timers = [x for x in self.timers if x[1] != raw]
        block = held_block(self.blocks, raw)
        for trig in block["trigger"]:
            if trig.get("trigger") == "state" and "for" in trig:
                if state in as_list(trig["to"]):
                    when = self.t + seconds(trig["for"])
                    self.timers.append((when, raw, trig["id"]))
        self.fire_held(raw, "change")

    def run_actions(self, block, trig_id):
        for step in block.get("action", []):
            if all(
                c["condition"] == "trigger" and c["id"] == trig_id
                for c in step["if"]
            ):
                for act in step["then"]:
                    if act["action"] == "system_log.write":
                        self.warnings.append((self.t, act["data"]))

    def fire_held(self, raw, trig_id):
        block = held_block(self.blocks, raw)
        self.run_actions(block, trig_id)
        held = EMS_HELD if raw == EMS else CMD_HELD
        cfg = block["sensor"][0]
        old = self.e.get(held) or Entity("unknown", self.now(), self.now())
        ctx = {"this": old, "trigger": types.SimpleNamespace(id=trig_id)}
        env = self.env()
        if env.from_string(cfg["availability"]).render(**ctx):
            new = as_state(env.from_string(cfg["state"]).render(**ctx))
        else:
            new = "unavailable"
        self.e[held] = Entity(new, self.now(), self.now())

    def guard(self, t):
        self.advance(t)
        for eid in P1_RAW:
            self.e[eid].last_reported = self.now() - dt.timedelta(seconds=2)
        return render_variables(self.env(), self.guard_vars, {})


class WorldTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blocks = load_yaml(TEMPLATE)
        cls.guard_vars = load_yaml(AUTOMATION)["variables"]

    def world(self, **kwargs):
        return World(self.blocks, self.guard_vars, **kwargs)

    def assertDiscounted(self, v, watts=9660):
        self.assertAlmostEqual(v["batt_a"], watts / 3 / 230)
        self.assertIs(v["must_stop"], False)

    def assertNotDiscounted(self, v):
        self.assertEqual(v["batt_a"], 0)
        self.assertIs(v["must_stop"], True)


def fail_polls(world, raw, misses, start=10):
    """`misses` failed polls of `raw` from `start`, then a good read."""
    good = world.e[raw].state
    world.at(start, raw, "unavailable")
    world.at(start + 10 * misses, raw, good)


class TestHold(WorldTestBase):
    def test_one_failed_poll_held(self):
        for raw, held in ((EMS, EMS_HELD), (CMD, CMD_HELD)):
            with self.subTest(raw=raw):
                w = self.world()
                w.at(10, raw, "unavailable")
                v = w.guard(15)
                self.assertNotIn(w.e[held].state, FAILED)
                self.assertIs(v["optimiser_charging"], True)
                self.assertDiscounted(v)
                w.at(20, raw, w.e[held].state)
                self.assertDiscounted(w.guard(21))
                self.assertEqual(w.warnings, [])

    def test_two_failed_polls_held_and_warn_once(self):
        for raw, held in ((EMS, EMS_HELD), (CMD, CMD_HELD)):
            with self.subTest(raw=raw):
                w = self.world()
                fail_polls(w, raw, 2)
                v = w.guard(29)
                self.assertIs(v["optimiser_charging"], True)
                self.assertDiscounted(v)
                w2 = self.world()
                w2.at(10, raw, "unavailable")
                for t in (15, 19, 24, 29):
                    v = w2.guard(t)
                    self.assertIs(v["optimiser_charging"], True, t)
                    self.assertDiscounted(v)
                self.assertEqual(len(w2.warnings), 1)
                when, data = w2.warnings[0]
                self.assertEqual(when, 25)
                self.assertEqual(data["level"], "warning")
                self.assertIn(raw, data["message"])

    def test_third_failed_poll_fails_safe(self):
        for raw, held in ((EMS, EMS_HELD), (CMD, CMD_HELD)):
            with self.subTest(raw=raw):
                w = self.world()
                w.at(10, raw, "unavailable")
                self.assertDiscounted(w.guard(34))
                v = w.guard(35)
                self.assertEqual(w.e[held].state, "unavailable")
                self.assertIs(v["optimiser_charging"], False)
                self.assertNotDiscounted(v)
                self.assertNotDiscounted(w.guard(60))
                self.assertEqual(len(w.warnings), 1)

    def test_recovers_after_expiry(self):
        w = self.world()
        fail_polls(w, CMD, 4)
        self.assertEqual(w.e[CMD_HELD].state, "170")
        self.assertDiscounted(w.guard(51))

    def test_unknown_is_held_like_unavailable(self):
        w = self.world()
        w.at(10, CMD, "unknown")
        self.assertEqual(w.e[CMD_HELD].state, "170")
        self.assertDiscounted(w.guard(15))

    def test_real_values_pass_through(self):
        w = self.world()
        w.at(10, CMD, "204")
        self.assertEqual(w.e[CMD_HELD].state, "204")
        w.at(20, EMS, "0")
        self.assertEqual(w.e[EMS_HELD].state, "0")

    def test_real_change_ends_discount_at_once(self):
        # The hold covers failed reads only; a real 204 or mode change
        # is believed, with no grace period for the battery to ramp down.
        for raw, value in ((CMD, "204"), (EMS, "0")):
            with self.subTest(raw=raw):
                w = self.world()
                w.at(10, raw, value)
                v = w.guard(10.5)
                self.assertIs(v["optimiser_charging"], False)
                self.assertEqual(v["batt_a"], 0)

    def test_value_after_failure_is_new_value(self):
        w = self.world()
        w.at(10, CMD, "unavailable")
        w.at(20, CMD, "204")
        self.assertEqual(w.e[CMD_HELD].state, "204")

    def test_start_without_good_read_is_unavailable(self):
        block = held_block(self.blocks, CMD)
        cfg = block["sensor"][0]
        e = {CMD: Entity("unknown", NOW, NOW)}
        ctx = {
            "this": Entity("170", NOW, NOW),
            "trigger": types.SimpleNamespace(id="start"),
        }
        self.assertIs(
            make_env(e).from_string(cfg["availability"]).render(**ctx), False
        )

    def test_start_with_good_read_is_value(self):
        block = held_block(self.blocks, CMD)
        cfg = block["sensor"][0]
        e = {CMD: Entity("204", NOW, NOW)}
        ctx = {
            "this": Entity("170", NOW, NOW),
            "trigger": types.SimpleNamespace(id="start"),
        }
        env = make_env(e)
        self.assertIs(env.from_string(cfg["availability"]).render(**ctx), True)
        self.assertEqual(
            as_state(env.from_string(cfg["state"]).render(**ctx)), "204"
        )

    def test_start_triggers(self):
        for raw in (EMS, CMD):
            ids = {
                t.get("event") or t.get("event_type"): t["id"]
                for t in held_block(self.blocks, raw)["trigger"]
                if t["trigger"] in ("homeassistant", "event")
            }
            self.assertEqual(
                ids, {"start": "start", "event_template_reloaded": "start"}
            )

    def test_unique_ids_pinned(self):
        # The fuse guard reads these entities by id. A changed or
        # dropped unique_id yields a duplicate ..._2 entity, and the
        # guard silently loses its discount.
        self.assertEqual(
            held_block(self.blocks, EMS)["sensor"][0]["unique_id"],
            "ems_mode_selection_raw_held",
        )
        self.assertEqual(
            held_block(self.blocks, CMD)["sensor"][0]["unique_id"],
            "battery_forced_charge_discharge_cmd_raw_held",
        )


if __name__ == "__main__":
    unittest.main()
