"""Tests for automations/zaptec/Eco_mode_nudge.yaml.

Renders the automation's `variables:` block against a mocked
`sensor.elpris_serie_se3` price series and the two input_number
helpers, then evaluates the notify condition and the notification
message the way Home Assistant would. The series is a list of
[epoch_ms, SEK/kWh] entries at 15-minute resolution, built relative to
the harness NOW (treated as both UTC and "local"; see ha_harness).

Run from the repo root with `make test`, or directly:

    python3 -m unittest discover -s tests/zaptec

Needs jinja2 and pyyaml; `make test` installs them into .venv from
requirements-dev.txt.
"""

import unittest

from ha_harness import (
    NOW,
    ROOT,
    Entity,
    as_list,
    load_yaml,
    make_env,
    render_variables,
    state_triggers,
)

NUDGE = ROOT / "automations" / "zaptec" / "Eco_mode_nudge.yaml"
CAR = "sensor.zag064494_laddstatus"
SERIES = "sensor.elpris_serie_se3"
WINDOW_H = "input_number.elbil_laddfonster_timmar"
GAP = "input_number.elbil_laddpris_gap"
TARGET = "notify.parents"
QUARTER_MS = 900_000

# Current quarter-hour in epoch ms, the same flooring the automation
# does. NOW is aligned to noon, so it is its own quarter.
NOW_MS = int(NOW.timestamp() // 900 * 900_000)
# Next 06:00 is tomorrow 06:00 (NOW is noon): 18 h = 72 quarters ahead.
DEADLINE_INDEX = 72


def series_from_now(prices, first_index=0):
    """Build [epoch_ms, price] entries starting `first_index` quarters
    after the current quarter-hour."""
    return [
        [NOW_MS + (first_index + i) * QUARTER_MS, p]
        for i, p in enumerate(prices)
    ]


def entities(prices=None, n_hours="3", gap="0.50", today=None, tomorrow=None):
    if today is None:
        today = series_from_now(prices or [])
    if tomorrow is None:
        tomorrow = []
    return {
        WINDOW_H: Entity(n_hours, NOW, NOW),
        GAP: Entity(gap, NOW, NOW),
        SERIES: Entity(
            "100", NOW, NOW, attributes={"today": today, "tomorrow": tomorrow}
        ),
    }


class RenderMixin:
    @classmethod
    def setUpClass(cls):
        cls.automation = load_yaml(NUDGE)

    def scope(self, ents):
        env = make_env(ents)
        return env, render_variables(env, self.automation["variables"], {})

    def condition(self, ents):
        env, scope = self.scope(ents)
        (cond,) = as_list(self.automation["conditions"])
        return bool(env.from_string(cond["value_template"]).render(**scope))

    def notifies(self, ents):
        return self.condition(ents)


class TestEcoModeNudgeCondition(RenderMixin, unittest.TestCase):
    def test_gap_below_threshold_notifies(self):
        # Now 0.89, a window just 0.05 cheaper -> gap under 0.50.
        prices = [0.89] + [0.84] * 40
        self.assertTrue(self.notifies(entities(prices)))

    def test_gap_above_threshold_does_not_notify(self):
        # Now 1.50, a long cheap stretch far below it -> gap over 0.50.
        prices = [1.50] + [0.50] * 40
        self.assertFalse(self.notifies(entities(prices)))

    def test_negative_gap_notifies(self):
        # Now is the single cheapest quarter; every window is dearer, so
        # the gap is negative and it still notifies.
        prices = [0.50] + [0.90] * 40
        env, scope = self.scope(entities(prices))
        self.assertLess(scope["gap"], 0)
        self.assertTrue(self.notifies(entities(prices)))

    def test_missing_price_now_does_not_notify(self):
        # Series starts one quarter in the future: no entry for now.
        today = series_from_now([0.80] * 40, first_index=1)
        self.assertFalse(self.notifies(entities(today=today)))

    def test_too_few_entries_before_deadline_does_not_notify(self):
        # Empty tomorrow and only 8 forward entries: no full 3 h window.
        self.assertFalse(self.notifies(entities([0.50] * 8)))

    def test_short_window_still_too_few(self):
        env, scope = self.scope(entities([0.50] * 8))
        self.assertIsNone(scope["best"])
        self.assertFalse(scope["can_notify"])


class TestEcoModeNudgeWindow(RenderMixin, unittest.TestCase):
    def test_window_crossing_midnight_uses_tomorrow(self):
        # today runs to index 47 (23:45); tomorrow starts at index 48
        # (00:00). A 0.50 block spans indices 44..55, crossing midnight.
        prices = [0.90] * 44 + [0.50] * 12 + [0.90] * 20
        full = series_from_now(prices)
        today = [e for e in full if e[0] < NOW_MS + 48 * QUARTER_MS]
        tomorrow = [e for e in full if e[0] >= NOW_MS + 48 * QUARTER_MS]
        env, scope = self.scope(entities(today=today, tomorrow=tomorrow))
        # best is 0.50 only if the window drew its tail from tomorrow.
        self.assertAlmostEqual(scope["best"], 0.50)
        self.assertEqual(scope["best_start_ms"], NOW_MS + 44 * QUARTER_MS)
        # The start is a today entry; the window reaches into tomorrow.
        self.assertLess(scope["best_start_ms"], tomorrow[0][0])

    def test_window_ending_after_deadline_is_excluded(self):
        # 0.90 up to the deadline, a 0.10 block only from 06:00 (index
        # 72) onward. No valid window reaches it, so best stays 0.90.
        prices = [0.90] * DEADLINE_INDEX + [0.10] * 20
        env, scope = self.scope(entities(prices))
        self.assertAlmostEqual(scope["best"], 0.90)

    def test_window_ending_exactly_at_deadline_is_included(self):
        # The 0.10 block sits at indices 60..71; the window 60..71 ends
        # exactly at 06:00 and is allowed, so best is 0.10.
        prices = [0.90] * 60 + [0.10] * 12
        env, scope = self.scope(entities(prices))
        self.assertAlmostEqual(scope["best"], 0.10)
        self.assertEqual(scope["best_start_ms"], NOW_MS + 60 * QUARTER_MS)

    def test_window_length_changes_best(self):
        # A one-hour 0.50 dip. N=1 fits inside it (best 0.50); N=3 spans
        # dearer quarters either side, so its best is higher.
        prices = [0.89] * 4 + [0.50] * 4 + [0.90] * 40
        _, short = self.scope(entities(prices, n_hours="1"))
        _, long = self.scope(entities(prices, n_hours="3"))
        self.assertAlmostEqual(short["best"], 0.50)
        self.assertLess(short["best"], long["best"])


class TestEcoModeNudgeMessage(RenderMixin, unittest.TestCase):
    def message(self, ents):
        env, scope = self.scope(ents)
        (action,) = as_list(self.automation["actions"])
        return env.from_string(action["data"]["message"]).render(**scope)

    def clean_case(self):
        # Now 1.00; a 0.80 stretch from the next quarter (12:15) on.
        # Cheapest 3 h window is 0.80, starting at 12:15. gap 0.20.
        prices = [1.00] + [0.80] * 40
        return entities(prices)

    def test_message_names_price_now_best_time_and_gap(self):
        message = self.message(self.clean_case())
        self.assertIn("1,00 kr/kWh", message)
        self.assertIn("0,80", message)
        self.assertIn("kl 12:15", message)
        self.assertIn("20", message)

    def test_message_suggests_and_never_claims_a_start(self):
        message = self.message(self.clean_case())
        self.assertIn("om du vill ladda nu", message)
        self.assertIn("Zaptec", message)

    def test_action_carries_the_zaptec_uri(self):
        (action,) = as_list(self.automation["actions"])
        uris = [
            a.get("uri")
            for a in action["data"]["data"]["actions"]
            if a.get("action") == "URI"
        ]
        self.assertEqual(uris, ["https://portal.zaptec.com/app/config/x"])


class TestEcoModeNudgeShape(RenderMixin, unittest.TestCase):
    def test_only_trigger_is_connected_requesting_for_two_minutes(self):
        triggers = as_list(self.automation["triggers"])
        self.assertEqual(len(triggers), 1, triggers)
        matches = [
            t
            for t in state_triggers(self.automation, CAR)
            if t.get("to") == "connected_requesting"
            and t.get("for") == "00:02:00"
        ]
        self.assertEqual(len(matches), 1, triggers)

    def test_single_notify_action_to_parents(self):
        actions = as_list(self.automation["actions"])
        self.assertEqual(len(actions), 1, actions)
        self.assertEqual(actions[0]["action"], TARGET)

    def test_no_action_targets_the_charger(self):
        # Watch-only: nothing in the actions may touch a zag064494
        # entity (the whole point of this automation vs #2).
        import yaml

        dumped = yaml.safe_dump(self.automation["actions"])
        self.assertNotIn("zag064494", dumped)


class TestEcoModeNudgeId(unittest.TestCase):
    def test_id_present_and_numeric_string(self):
        auto_id = load_yaml(NUDGE)["id"]
        self.assertIsInstance(auto_id, str)
        self.assertTrue(auto_id.isdigit(), auto_id)

    def test_id_unique_among_automations(self):
        own = load_yaml(NUDGE)["id"]
        owners = []
        for path in sorted((ROOT / "automations").rglob("*.yaml")):
            data = load_yaml(path)
            for item in as_list(data):
                if isinstance(item, dict) and str(item.get("id")) == own:
                    owners.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(owners, ["automations/zaptec/Eco_mode_nudge.yaml"])


if __name__ == "__main__":
    unittest.main()
