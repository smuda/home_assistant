"""Property test: the fuse guard does nothing on one degraded input (#54).

From a resting state, where the guard must make no service call, each
entity the automation reads is degraded one at a time -- `unavailable`,
`unknown`, or missing from the entity table -- and the run must still
make no service call. The entity ids are collected from the
automation's YAML text, so a new input is covered without editing this
test. See CODING_STANDARDS.md, "A write's condition stays false on a
degraded input".

Uses the interpreter from test_fuse_stop_confirm: the real automation
YAML, a mocked entity table, and the service calls recorded instead of
executed. Each case is one run of the guard.

Run from the repo root with `make test`, or directly:

    python3 -m unittest discover -s tests/zaptec

Needs jinja2 and pyyaml; `make test` installs them into .venv from
requirements-dev.txt.
"""

import datetime as dt
import re
import unittest

from ha_harness import NOW, PAUSED, RAMPING, Entity, load_yaml
from test_dynamic_fuse_protection import AUTOMATION
from test_fuse_floor_start import STATUS, table
from test_fuse_stop_confirm import MAX_ENTITY, Guard

ID = r"[a-z_]+\.[a-z0-9_]+"
# states('<id>') and is_state('<id>', ...)
CALL_READ = re.compile(rf"\b(?:states|is_state)\(\s*'({ID})'")
# states.<domain>.<object_id>
ATTR_READ = re.compile(r"\bstates\.([a-z_]+)\.([a-z0-9_]+)")

DEGRADATIONS = ("unavailable", "unknown", "missing")

# Degradations allowed to raise a template error instead of rendering.
# A missing helper or charger entity is a broken config, and in Home
# Assistant a template error in `variables:` aborts the run, so nothing
# is written: failing without a write is already the safe outcome.
EXCLUDED = {
    # secs_since_pause reads .last_changed on the missing helper.
    (PAUSED, "missing"),
    # secs_since reads .last_changed on the missing charger number.
    (MAX_ENTITY, "missing"),
}


def read_entity_ids(text):
    """Every entity id a template in the automation text reads."""
    ids = set(CALL_READ.findall(text))
    ids.update(f"{d}.{o}" for d, o in ATTR_READ.findall(text))
    return ids


def resting(status, max_a):
    """A table where the guard must do nothing, helpers all present."""
    e = table(status=status, max_a=max_a, pending="off")
    e[RAMPING] = Entity("off", NOW - dt.timedelta(seconds=10000), NOW)
    return e


# name -> builder for a fresh entity table
SCENARIOS = {
    # Unplugged long enough for the Floor start, already at ev_min.
    "unplugged_at_ev_min": lambda: resting("disconnected", 6),
    # Eco Mode waiting at 16 A: the guard must not touch the charger.
    "connected_requesting": lambda: resting("connected_requesting", 16),
}


def degrade(entities, entity_id, how):
    if how == "missing":
        del entities[entity_id]
    else:
        entities[entity_id].state = how


class DegradedInputsBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.automation = load_yaml(AUTOMATION)
        cls.read_ids = read_entity_ids(AUTOMATION.read_text())

    def run_guard(self, entities):
        """Service calls of one run: condition, then the actions.

        Raises if the variables block (or a condition) fails to render.
        """
        g = Guard(self.automation, entities)
        return g.run() if g.passes() else []


class TestCollectedEntities(DegradedInputsBase):
    def test_collection_is_not_vacuous(self):
        self.assertGreaterEqual(len(self.read_ids), 15, self.read_ids)
        for eid in (MAX_ENTITY, STATUS, PAUSED, RAMPING):
            self.assertIn(eid, self.read_ids)

    def test_resting_tables_hold_every_read_entity(self):
        # So "missing" is a deliberate degradation, not the default.
        for name, build in SCENARIOS.items():
            with self.subTest(scenario=name):
                self.assertEqual(self.read_ids - set(build()), set())

    def test_exclusions_are_read_entities(self):
        for eid, how in EXCLUDED:
            self.assertIn(eid, self.read_ids)
            self.assertIn(how, DEGRADATIONS)


class TestRestingBaselines(DegradedInputsBase):
    def test_baselines_make_no_service_call(self):
        for name, build in SCENARIOS.items():
            with self.subTest(scenario=name):
                self.assertEqual(self.run_guard(build()), [])


class TestOneDegradedInput(DegradedInputsBase):
    def test_no_service_call_on_any_single_degraded_input(self):
        for name, build in SCENARIOS.items():
            for eid in sorted(self.read_ids):
                for how in DEGRADATIONS:
                    with self.subTest(scenario=name, entity=eid, how=how):
                        self.check(build, eid, how)

    def check(self, build, eid, how):
        entities = build()
        degrade(entities, eid, how)
        try:
            calls = self.run_guard(entities)
        except Exception as err:
            if (eid, how) in EXCLUDED:
                return
            self.fail(f"template error: {type(err).__name__}: {err}")
        if (eid, how) in EXCLUDED:
            self.fail("stale exclusion: renders cleanly now, drop it")
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
