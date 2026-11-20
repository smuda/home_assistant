"""Tests for vmq.py, on canned VictoriaMetrics responses. No network.

Run from the repo root:

    python3 -m unittest discover -s metrics/scripts
"""
import io
import re
import unittest
import urllib.error
import urllib.parse
from unittest import mock

import vmq

T0 = 1795072800  # 2026-11-19T07:20:00Z, a multiple of 60
ENTITY = "sensor.p1_meter_effekt"


def response(*results):
    return {"status": "success",
            "data": {"resultType": "matrix", "result": list(results)}}


def result(name, entity, values, **labels):
    metric = dict(labels, __name__=name, entity=entity)
    return {"metric": metric, "values": [[t, v] for t, v in values]}


def params(url):
    return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))


class QueryTest(unittest.TestCase):
    def test_url_carries_range_and_selector(self):
        url = vmq.query_url("http://vm:8428/", ENTITY, T0, T0 + 600, 60)
        self.assertTrue(url.startswith("http://vm:8428/api/v1/query_range?"))
        self.assertEqual(params(url), {
            "query": vmq.selector(ENTITY),
            "start": str(T0), "end": str(T0 + 600), "step": "60s"})

    def test_selector_matches_entity_label(self):
        self.assertIn('entity="sensor.p1_meter_effekt"', vmq.selector(ENTITY))

    def test_selector_excludes_sibling_series(self):
        m = re.search(r'__name__!~"([^"]+)"', vmq.selector(ENTITY))
        exclude = re.compile(m.group(1))
        for name in ("homeassistant_state_change_total",
                     "homeassistant_state_change_created",
                     "homeassistant_entity_available",
                     "homeassistant_last_updated_time_seconds",
                     "homeassistant_sensor_attr_foo",
                     "homeassistant_sensor_info"):
            self.assertTrue(exclude.fullmatch(name), name)
        for name in ("homeassistant_sensor_power_w",
                     "homeassistant_sensor_energy_kwh",
                     "homeassistant_sensor_state",
                     "homeassistant_binary_sensor_state",
                     "homeassistant_climate_current_temperature_celsius"):
            self.assertIsNone(exclude.fullmatch(name), name)

    def test_selector_escapes_quotes(self):
        self.assertIn(r'entity="a\"b"', vmq.selector('a"b'))

    def test_parse_time(self):
        self.assertEqual(vmq.parse_time("2026-11-19T07:20:00Z"), T0)
        self.assertEqual(vmq.parse_time("2026-11-19T07:20"), T0)
        self.assertEqual(vmq.parse_time("2026-11-19T08:20:00+01:00"), T0)
        self.assertEqual(vmq.format_time(T0), "2026-11-19T07:20:00Z")


class ProxyTest(unittest.TestCase):
    URL = "http://192.168.40.20:8428/api/v1/query_range?query=x"
    NO_PROXY = {"no_proxy": "localhost,192.168.0.0/16",
                "NO_PROXY": "localhost,192.168.0.0/16"}

    def test_proxy_used_even_when_no_proxy_covers_host(self):
        env = dict(self.NO_PROXY, http_proxy="http://proxy.internal:3128")
        self.assertEqual(vmq.proxy_for(self.URL, env),
                         "http://proxy.internal:3128")
        with mock.patch.dict("os.environ", env, clear=True):
            req = vmq.build_request(self.URL, env)
        self.assertEqual(req.host, "proxy.internal:3128")
        self.assertEqual(req.full_url, self.URL)

    def test_upper_case_variable(self):
        env = dict(self.NO_PROXY, HTTP_PROXY="proxy.internal:3128")
        req = vmq.build_request(self.URL, env)
        self.assertEqual(req.host, "proxy.internal:3128")

    def test_proxy_credentials(self):
        env = {"http_proxy": "http://u%40x:p@proxy.internal:3128"}
        req = vmq.build_request(self.URL, env)
        self.assertEqual(req.host, "proxy.internal:3128")
        self.assertEqual(req.get_header("Proxy-authorization"),
                         "Basic dUB4OnA=")

    def test_no_proxy_set_connects_directly(self):
        self.assertIsNone(vmq.proxy_for(self.URL, self.NO_PROXY))
        req = vmq.build_request(self.URL, self.NO_PROXY)
        self.assertEqual(req.host, "192.168.40.20:8428")
        self.assertFalse(req.has_proxy())

    def connect_host(self, env):
        """The host fetch() opens a connection to, with env as os.environ."""
        hosts = []

        class Refused(OSError):
            pass

        def connection(host, **kwargs):
            hosts.append(host)
            conn = mock.Mock()
            conn.request.side_effect = Refused
            return conn

        with mock.patch.dict("os.environ", env, clear=True), \
                mock.patch("http.client.HTTPConnection", connection), \
                self.assertRaises(vmq.urllib.error.URLError):
            vmq.fetch(self.URL)
        return hosts

    def test_fetch_goes_through_proxy_despite_no_proxy(self):
        env = dict(self.NO_PROXY, http_proxy="http://proxy.internal:3128")
        self.assertEqual(self.connect_host(env), ["proxy.internal:3128"])

    def test_fetch_connects_directly_without_proxy(self):
        self.assertEqual(self.connect_host(dict(self.NO_PROXY)),
                         ["192.168.40.20:8428"])


class ReshapeTest(unittest.TestCase):
    def run_main(self, argv, responses):
        calls = []

        def fetch(url):
            calls.append(url)
            return responses[params(url)["query"]]

        out, err = io.StringIO(), io.StringIO()
        vmq.main(argv, fetch=fetch, out=out, err=err)
        return out.getvalue(), err.getvalue(), calls

    def argv(self, *entities, end=180, extra=()):
        return list(entities) + [
            "--start", vmq.format_time(T0),
            "--end", vmq.format_time(T0 + end), "--csv"] + list(extra)

    def test_columns_in_argument_order_with_gaps(self):
        a, b = "sensor.a", "binary_sensor.b"
        responses = {
            vmq.selector(a): response(result(
                "homeassistant_sensor_power_w", a,
                [(T0, "100"), (T0 + 120, "250.5")])),
            vmq.selector(b): response(result(
                "homeassistant_binary_sensor_state", b,
                [(T0 + 60, "1"), (T0 + 120, "0")])),
        }
        out, err, calls = self.run_main(self.argv(b, a), responses)
        self.assertEqual(out.splitlines(), [
            "time,binary_sensor.b,sensor.a",
            "2026-11-19T07:20:00Z,,100",
            "2026-11-19T07:21:00Z,1,",
            "2026-11-19T07:22:00Z,0,250.5",
            "2026-11-19T07:23:00Z,,",
        ])
        self.assertEqual(err, "")
        self.assertEqual([params(u)["query"] for u in calls],
                         [vmq.selector(b), vmq.selector(a)])

    def test_entity_without_series_is_an_empty_column(self):
        responses = {vmq.selector("sensor.gone"): response()}
        out, err, _ = self.run_main(self.argv("sensor.gone", end=60),
                                    responses)
        self.assertEqual(out.splitlines(), [
            "time,sensor.gone",
            "2026-11-19T07:20:00Z,", "2026-11-19T07:21:00Z,"])
        self.assertIn("sensor.gone: no value series", err)

    def test_non_numeric_values_kept(self):
        e = "sensor.mode"
        responses = {vmq.selector(e): response(result(
            "homeassistant_sensor_state", e,
            [(T0, "NaN"), (T0 + 60, "+Inf")]))}
        out, _, _ = self.run_main(self.argv(e, end=60), responses)
        self.assertEqual(out.splitlines()[1:], [
            "2026-11-19T07:20:00Z,NaN", "2026-11-19T07:21:00Z,+Inf"])

    def test_multiple_series_get_a_column_each_and_a_note(self):
        e = "sensor.ev"
        responses = {vmq.selector(e): response(
            result("homeassistant_sensor_power_w", e, [(T0, "7000")]),
            result("homeassistant_sensor_power_kw", e, [(T0 + 60, "7.1")]))}
        out, err, _ = self.run_main(self.argv(e, end=60), responses)
        self.assertEqual(out.splitlines(), [
            "time,sensor.ev#1,sensor.ev#2",
            "2026-11-19T07:20:00Z,7000,",
            "2026-11-19T07:21:00Z,,7.1"])
        self.assertIn("sensor.ev: 2 value series", err)
        self.assertIn('sensor.ev#1 = homeassistant_sensor_power_w'
                      '{entity="sensor.ev"}', err)
        self.assertIn("sensor.ev#2 = homeassistant_sensor_power_kw", err)

    def test_changes_only(self):
        a, b = "sensor.a", "sensor.b"
        responses = {
            vmq.selector(a): response(result(
                "homeassistant_sensor_current_a", a,
                [(T0 + 60 * i, v) for i, v in
                 enumerate(["6", "6", "10", "10", "", "10"])
                 if v])),
            vmq.selector(b): response(result(
                "homeassistant_sensor_power_w", b,
                [(T0 + 60 * i, str(i)) for i in range(6)])),
        }
        out, _, _ = self.run_main(
            self.argv(a, b, end=300, extra=["--changes", a]), responses)
        self.assertEqual(out.splitlines(), [
            "time,sensor.a,sensor.b",
            "2026-11-19T07:20:00Z,6,0",
            "2026-11-19T07:22:00Z,10,2",
            "2026-11-19T07:24:00Z,,4",
            "2026-11-19T07:25:00Z,10,5",
        ])

    def test_start_aligned_to_step(self):
        e = "sensor.a"
        responses = {vmq.selector(e): response(result(
            "homeassistant_sensor_power_w", e, [(T0, "1")]))}
        argv = [e, "--start", vmq.format_time(T0 + 30),
                "--end", vmq.format_time(T0 + 60), "--csv"]
        out, _, calls = self.run_main(argv, responses)
        self.assertEqual(params(calls[0])["start"], str(T0))
        self.assertEqual(out.splitlines()[1:], [
            "2026-11-19T07:20:00Z,1", "2026-11-19T07:21:00Z,"])

    def test_text_output_is_aligned(self):
        e = "sensor.a"
        responses = {vmq.selector(e): response(result(
            "homeassistant_sensor_power_w", e, [(T0, "12345678901234")]))}
        argv = [e, "--start", vmq.format_time(T0),
                "--end", vmq.format_time(T0)]
        out, _, _ = self.run_main(argv, responses)
        self.assertEqual(out.splitlines(), [
            "time                  sensor.a",
            "2026-11-19T07:20:00Z  12345678901234"])

    def test_error_response_raises(self):
        with self.assertRaises(RuntimeError):
            vmq.series({"status": "error", "error": "bad query"})

    def test_http_error_body_is_returned(self):
        body = io.BytesIO(b'{"status":"error","error":"too many points"}')
        error = urllib.error.HTTPError(
            "http://vm:8428/", 422, "Unprocessable Entity", {}, body)
        with mock.patch.object(vmq.OPENER, "open", side_effect=error):
            response = vmq.fetch("http://vm:8428/x", env={})
        with self.assertRaisesRegex(RuntimeError, "too many points"):
            vmq.series(response)

    def test_http_error_without_json_body_raises(self):
        error = urllib.error.HTTPError(
            "http://vm:8428/", 502, "Bad Gateway", {}, io.BytesIO(b"<html>"))
        with mock.patch.object(vmq.OPENER, "open", side_effect=error), \
                self.assertRaises(urllib.error.HTTPError):
            vmq.fetch("http://vm:8428/x", env={})


if __name__ == "__main__":
    unittest.main()
