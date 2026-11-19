"""Tests for automations/zaptec/Overload_notify.yaml.

Loads the real automation, checks its trigger/action shape, renders the
notification title and message with mocked HA template functions, and
checks that its id is unique across automations/.

Run from the repo root with `make test`, or directly:

    python3 -m unittest discover -s tests/zaptec

Needs jinja2 and pyyaml; `make test` installs them into .venv from
requirements-dev.txt.
"""

import unittest

from ha_harness import (
    NOW,
    P1_RAW,
    ROOT,
    SUSTAINED,
    Entity,
    as_list,
    load_yaml,
    make_env,
    state_triggers,
)

NOTIFY = ROOT / "automations" / "zaptec" / "Overload_notify.yaml"
TARGET = "notify.mobile_app_johns_iphone_13"


def mock_entities(phases=(20.0, 31.4, 18.0), others=None):
    values = {
        "sensor.battery_power": "9660",
        "sensor.ems_mode_selection_raw": "3",
        "sensor.battery_forced_charge_discharge_cmd_raw": "170",
        "sensor.zag064494_laddstatus": "connected_charging",
        "number.zag064494_max_laddstrom": "16",
        SUSTAINED: "on",
    }
    values.update(zip(P1_RAW, phases))
    values.update(others or {})
    return {eid: Entity(str(v), NOW, NOW) for eid, v in values.items()}


class TestOverloadNotify(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.automation = load_yaml(NOTIFY)

    def action(self):
        return as_list(self.automation["actions"])

    def render(self, text, entities):
        return make_env(entities).from_string(text).render()

    def notify_data(self):
        (action,) = self.action()
        return action["data"]

    def test_state_trigger_on_sustained_overload(self):
        triggers = as_list(self.automation["triggers"])
        matches = [
            t
            for t in state_triggers(self.automation, SUSTAINED)
            if str(t.get("to")) == "on"
        ]
        self.assertEqual(len(matches), 1, triggers)
        self.assertEqual(len(triggers), 1, triggers)

    def test_no_conditions(self):
        self.assertFalse(self.automation.get("conditions"))

    def test_single_notify_action(self):
        actions = self.action()
        self.assertEqual(len(actions), 1, actions)
        self.assertEqual(actions[0]["action"], TARGET)

    def test_message_renders_with_max_phase(self):
        message = self.render(self.notify_data()["message"], mock_entities())
        self.assertTrue(message.strip())
        self.assertIn("31.4", message)

    def test_max_phase_follows_the_hot_phase(self):
        for hot in range(3):
            phases = [10.0, 10.0, 10.0]
            phases[hot] = 33.7
            message = self.render(
                self.notify_data()["message"], mock_entities(phases)
            )
            self.assertIn("33.7", message)

    def test_message_renders_with_unavailable_entities(self):
        entities = mock_entities(
            others={
                "sensor.battery_power": "unavailable",
                "sensor.ems_mode_selection_raw": "unavailable",
                "sensor.battery_forced_charge_discharge_cmd_raw": "unknown",
                "sensor.zag064494_laddstatus": "unavailable",
                "number.zag064494_max_laddstrom": "unavailable",
            }
        )
        message = self.render(self.notify_data()["message"], entities)
        self.assertTrue(message.strip())
        self.assertIn("31.4", message)

    def test_message_renders_with_unavailable_phase(self):
        message = self.render(
            self.notify_data()["message"],
            mock_entities(phases=("unavailable", 29.5, "unknown")),
        )
        self.assertIn("29.5", message)

    def test_message_has_one_fact_per_line(self):
        message = self.render(self.notify_data()["message"], mock_entities())
        lines = [ln for ln in message.splitlines() if ln.strip()]
        self.assertGreaterEqual(len(lines), 5, message)

    def test_message_shows_battery_ems_and_car_values(self):
        message = self.render(self.notify_data()["message"], mock_entities())
        for expected in ("9660", "170", "connected_charging"):
            self.assertIn(expected, message)

    def test_message_ends_with_guard_counts_battery_line(self):
        message = self.render(self.notify_data()["message"], mock_entities())
        last = [ln for ln in message.splitlines() if ln.strip()][-1]
        self.assertIn("tills överlastgivaren slår av", last)
        self.assertNotIn("60 min", message)

    def test_title_renders(self):
        title = self.render(self.notify_data()["title"], mock_entities())
        self.assertEqual(title.strip(), "Säkringsvakt: överlast")


class TestOverloadNotifyId(unittest.TestCase):
    def test_id_present_and_numeric_string(self):
        auto_id = load_yaml(NOTIFY)["id"]
        self.assertIsInstance(auto_id, str)
        self.assertTrue(auto_id.isdigit(), auto_id)

    def test_id_unique_among_automations(self):
        own = load_yaml(NOTIFY)["id"]
        owners = []
        for path in sorted((ROOT / "automations").rglob("*.yaml")):
            data = load_yaml(path)
            for item in as_list(data):
                if isinstance(item, dict) and str(item.get("id")) == own:
                    owners.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(owners, ["automations/zaptec/Overload_notify.yaml"])


if __name__ == "__main__":
    unittest.main()
