"""Offline tests for vmq.py, on canned VictoriaMetrics responses.

Run from this directory: python3 -m unittest test_vmq
No network: only query construction and response reshaping are tested.
"""
import unittest

import vmq


def resp(*series):
    """A query_range JSON body from (name, [(ts, val), ...]) pairs."""
    return {"status": "success", "data": {"resultType": "matrix", "result": [
        {"metric": {"__name__": name, "entity": "e"}, "values": vals}
        for name, vals in series]}}


class BuildQuery(unittest.TestCase):
    def test_selects_entity_and_excludes_siblings(self):
        q = vmq.build_query("sensor.p1_meter_effekt")
        self.assertIn('entity="sensor.p1_meter_effekt"', q)
        self.assertIn("__name__!~", q)
        for sib in ("state_change", "created", "available", "_attr_",
                    "last_updated", "info"):
            self.assertIn(sib, q)


class ParseResponse(unittest.TestCase):
    def test_values_and_single_name(self):
        values, names = vmq.parse_response(
            resp(("homeassistant_sensor_power_w", [[1000, "12.5"], [1060, "13"]])))
        self.assertEqual(values, {1000: "12.5", 1060: "13"})
        self.assertEqual(names, ["homeassistant_sensor_power_w"])

    def test_empty_result(self):
        values, names = vmq.parse_response(resp())
        self.assertEqual(values, {})
        self.assertEqual(names, [])

    def test_multiple_series_are_reported_not_collapsed(self):
        _, names = vmq.parse_response(resp(
            ("homeassistant_sensor_state", [[1000, "1"]]),
            ("homeassistant_sensor_power_w", [[1000, "2"]])))
        self.assertEqual(len(names), 2)

    def test_non_numeric_value_kept_as_string(self):
        values, _ = vmq.parse_response(
            resp(("homeassistant_sensor_state", [[1000, "NaN"], [1060, "charging"]])))
        self.assertEqual(values[1000], "NaN")
        self.assertEqual(values[1060], "charging")

    def test_float_timestamp_is_coerced_to_int(self):
        values, _ = vmq.parse_response(
            resp(("homeassistant_sensor_power_w", [[1000.0, "1"]])))
        self.assertEqual(list(values), [1000])


class Reshape(unittest.TestCase):
    def test_gaps_become_empty_cells(self):
        cols = {"a": {1000: "1", 1060: "2"}, "b": {1060: "9"}}
        rows = vmq.reshape(cols, ["a", "b"])
        self.assertEqual(rows, [[1000, "1", None], [1060, "2", "9"]])

    def test_column_order_follows_entities(self):
        cols = {"a": {1000: "1"}, "b": {1000: "9"}}
        self.assertEqual(vmq.reshape(cols, ["b", "a"]), [[1000, "9", "1"]])

    def test_missing_entity_all_empty(self):
        rows = vmq.reshape({"a": {1000: "1"}}, ["a", "b"])
        self.assertEqual(rows, [[1000, "1", None]])


class ChangedOnly(unittest.TestCase):
    def test_keeps_first_and_changes(self):
        rows = [[0, "1"], [60, "1"], [120, "2"], [180, "2"], [240, "3"]]
        self.assertEqual(vmq.changed_only(rows, 1),
                         [[0, "1"], [120, "2"], [240, "3"]])

    def test_empty_cell_counts_as_a_change(self):
        rows = [[0, "1"], [60, None], [120, "1"]]
        self.assertEqual(vmq.changed_only(rows, 1), rows)


class Render(unittest.TestCase):
    def test_header_and_utc_timestamp(self):
        out = vmq.render([[1795046400, "12.5", None]], ["a", "b"])
        header, row = out.splitlines()
        self.assertEqual(header, "time\ta\tb")
        self.assertEqual(row, "2026-11-19T00:00:00Z\t12.5\t")


if __name__ == "__main__":
    unittest.main()
