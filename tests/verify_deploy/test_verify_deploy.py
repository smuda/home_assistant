"""Tests for tools/verify_deploy.py.

Fully offline: the HA fetch is injected or OPENER is patched. Stdlib
only.

Run from the repo root:

    python3 -m unittest discover -s tests/verify_deploy
"""

import contextlib
import http.client
import io
import json
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
import urllib.response
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import verify_deploy  # noqa: E402

TOKEN = "s3cr3t-token-value"


def write(root, rel, text):
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class CollectIdsTest(unittest.TestCase):
    def collect(self, files):
        with tempfile.TemporaryDirectory() as tmp:
            for rel, text in files.items():
                write(tmp, rel, text)
            return verify_deploy.collect_ids(Path(tmp))

    def test_quoting_variants(self):
        got = self.collect(
            {
                "automations/a.yaml": 'id: "1111111111111"\nalias: A\n',
                "automations/b.yaml": "id: '2222222222222'\nalias: B\n",
                "automations/c.yaml": "id: 3333333333333\nalias: C\n",
                "automations/d.yaml": "id: 4444444444444  # note\n",
                "automations/e.yaml": 'id: "5555555555555" # note\n',
            }
        )
        self.assertEqual(
            got,
            [
                ("1111111111111", "automations/a.yaml"),
                ("2222222222222", "automations/b.yaml"),
                ("3333333333333", "automations/c.yaml"),
                ("4444444444444", "automations/d.yaml"),
                ("5555555555555", "automations/e.yaml"),
            ],
        )

    def test_indented_trigger_id_ignored_before_top_level_id(self):
        text = (
            "alias: X\n"
            "triggers:\n"
            "  - trigger: state\n"
            "    id: trigger_one\n"
            "  - id: trigger_two\n"
            "id: '9999999999999'\n"
        )
        got = self.collect({"automations/x.yaml": text})
        self.assertEqual(got, [("9999999999999", "automations/x.yaml")])

    def test_only_indented_ids_means_skipped(self):
        text = "alias: X\ntriggers:\n  - id: trigger_one\n"
        self.assertEqual(
            self.collect({"automations/x.yaml": text}),
            [(None, "automations/x.yaml")],
        )

    def test_first_top_level_id_wins(self):
        text = "id: '1111111111111'\nid: '2222222222222'\n"
        got = self.collect({"automations/x.yaml": text})
        self.assertEqual(got, [("1111111111111", "automations/x.yaml")])

    def test_file_without_id_yields_none(self):
        got = self.collect(
            {
                "automations/noid.yaml": "alias: nothing\n",
                "automations/has.yaml": "id: '1234567890123'\n",
            }
        )
        self.assertEqual(
            got,
            [
                ("1234567890123", "automations/has.yaml"),
                (None, "automations/noid.yaml"),
            ],
        )

    def test_utf8_bom_before_id_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "automations" / "bom.yaml"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"\xef\xbb\xbfid: '1234567890123'\nalias: B\n")
            got = verify_deploy.collect_ids(Path(tmp))
        self.assertEqual(got, [("1234567890123", "automations/bom.yaml")])

    def test_non_yaml_ignored(self):
        got = self.collect(
            {
                "automations/README.md": "id: '1111111111111'\n",
                "automations/notes.txt": "id: '2222222222222'\n",
                "automations/real.yaml": "id: '3333333333333'\n",
            }
        )
        self.assertEqual(got, [("3333333333333", "automations/real.yaml")])

    def test_recursive_and_non_ascii_subdir(self):
        got = self.collect(
            {
                "automations/golvvärme/a.yaml": "id: '1111111111111'\n",
                "automations/deep/er/b.yaml": "id: '2222222222222'\n",
            }
        )
        self.assertEqual(
            sorted(got),
            [
                ("1111111111111", "automations/golvvärme/a.yaml"),
                ("2222222222222", "automations/deep/er/b.yaml"),
            ],
        )

    def test_only_automations_dir_is_scanned(self):
        got = self.collect(
            {
                "other/a.yaml": "id: '1111111111111'\n",
                "automations/b.yaml": "id: '2222222222222'\n",
            }
        )
        self.assertEqual(got, [("2222222222222", "automations/b.yaml")])

    def test_sorted_by_relative_posix_path(self):
        got = self.collect(
            {
                "automations/zaptec/Battery_hold.yaml": "id: '3'\n",
                "automations/belysning/z.yaml": "id: '2'\n",
                "automations/belysning/a.yaml": "id: '1'\n",
                "automations/avfuktare/m.yaml": "id: '0'\n",
            }
        )
        self.assertEqual(
            [rel for _, rel in got],
            [
                "automations/avfuktare/m.yaml",
                "automations/belysning/a.yaml",
                "automations/belysning/z.yaml",
                "automations/zaptec/Battery_hold.yaml",
            ],
        )
        self.assertEqual([i for i, _ in got], ["0", "1", "2", "3"])

    def test_real_repo_ids_are_13_digit_and_unique(self):
        got = verify_deploy.collect_ids(ROOT)
        self.assertTrue(got, "expected at least one automation id")
        ids = [i for i, _ in got]
        self.assertNotIn(None, ids)
        for i in ids:
            self.assertRegex(i, r"^\d{13}$")
        self.assertEqual(len(ids), len(set(ids)))


class TemplateTest(unittest.TestCase):
    def test_template_mentions_required_pieces(self):
        t = verify_deploy.TEMPLATE
        self.assertIsInstance(t, str)
        self.assertIn('attributes.get("id")', t)
        self.assertIn('integration_entities("template")', t)
        self.assertIn("to_json", t)


class FetchTest(unittest.TestCase):
    def test_request_shape(self):
        seen = {}

        class Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b'{"automations": [], "templates": []}'

        class FakeOpener:
            def open(self, req, *args, **kwargs):
                seen["req"] = req
                seen["kwargs"] = kwargs
                seen["args"] = args
                return Resp()

        with mock.patch.object(verify_deploy, "OPENER", FakeOpener()):
            out = verify_deploy.fetch("http://ha.local:8123/", TOKEN)
        req = seen["req"]
        self.assertEqual(req.full_url, "http://ha.local:8123/api/template")
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.get_header("Authorization"), f"Bearer {TOKEN}")
        self.assertEqual(
            json.loads(req.data), {"template": verify_deploy.TEMPLATE}
        )
        self.assertEqual(out, {"automations": [], "templates": []})
        self.assertEqual(seen["kwargs"].get("timeout"), 15)


class NoRedirectTest(unittest.TestCase):
    def test_redirect_request_returns_none(self):
        h = verify_deploy.NoRedirect()
        req = urllib.request.Request("http://ha.local:8123/api/template")
        got = h.redirect_request(
            req, None, 302, "Found", {}, "http://evil.example/"
        )
        self.assertIsNone(got)

    def test_302_is_not_followed(self):
        seen = []

        class Fake302(urllib.request.HTTPHandler):
            def http_open(self, req):
                seen.append(req.full_url)
                headers = http.client.HTTPMessage()
                headers["Location"] = "http://evil.example/"
                resp = urllib.response.addinfourl(
                    io.BytesIO(b""), headers, req.full_url, 302
                )
                resp.msg = "Found"
                return resp

        opener = urllib.request.build_opener(verify_deploy.NoRedirect, Fake302)
        with mock.patch.object(verify_deploy, "OPENER", opener):
            with self.assertRaises(urllib.error.HTTPError) as cm:
                verify_deploy.fetch("http://ha.local:8123", TOKEN)
        cm.exception.close()
        self.assertEqual(cm.exception.code, 302)
        self.assertEqual(seen, ["http://ha.local:8123/api/template"])


def auto(i, ent, state="on", changed="2026-11-18T10:00:00+00:00"):
    return {"id": i, "entity_id": ent, "state": state, "last_changed": changed}


def tmpl(ent, state, changed="2026-11-18T10:00:00+00:00"):
    return {"entity_id": ent, "state": state, "last_changed": changed}


class FormatReportTest(unittest.TestCase):
    def test_all_present_exact_output(self):
        repo = [
            ("1111111111111", "automations/a.yaml"),
            ("2222222222222", "automations/b.yaml"),
        ]
        data = {
            "automations": [
                auto("2222222222222", "automation.bb", "off", "T2"),
                auto("1111111111111", "automation.a_long_name", "on", "T1"),
            ],
            "templates": [],
        }
        lines, code = verify_deploy.format_report(repo, data)
        self.assertEqual(
            lines,
            [
                "Automations (2 in repo):",
                "  1111111111111  automation.a_long_name  on   T1",
                "  2222222222222  automation.bb           off  T2",
                "Template entities (0):",
                "OK: all 2 automation ids loaded",
            ],
        )
        self.assertEqual(code, 0)

    def test_id_column_aligned_to_longest_id(self):
        repo = [("1", "automations/a.yaml"), ("1234567", "automations/b.yaml")]
        data = {
            "automations": [
                auto("1", "automation.x", "on", "T"),
                auto("1234567", "automation.y", "on", "T"),
            ],
            "templates": [],
        }
        lines, _ = verify_deploy.format_report(repo, data)
        self.assertEqual(lines[1], "  1        automation.x  on  T")
        self.assertEqual(lines[2], "  1234567  automation.y  on  T")

    def test_missing_id_reports_relpath_and_fails(self):
        repo = [
            ("1111111111111", "automations/a.yaml"),
            ("2222222222222", "automations/zaptec/b.yaml"),
        ]
        data = {
            "automations": [auto("1111111111111", "automation.alpha", "on", "T1")],
            "templates": [],
        }
        lines, code = verify_deploy.format_report(repo, data)
        self.assertEqual(
            lines,
            [
                "Automations (2 in repo):",
                "  1111111111111  automation.alpha  on  T1",
                "  2222222222222  MISSING           automations/zaptec/b.yaml",
                "Template entities (0):",
                "FAIL: 1 of 2 automation(s) not OK "
                "(MISSING: 1, unavailable: 0, NO-ID: 0)",
            ],
        )
        self.assertEqual(code, 1)

    def test_ha_only_automation_not_listed(self):
        repo = [("1111111111111", "automations/a.yaml")]
        data = {
            "automations": [
                auto("1111111111111", "automation.alpha", "on", "T1"),
                auto("7777777777777", "automation.gui_only", "on", "T"),
                auto(None, "automation.no_id", "on", "T"),
            ],
            "templates": [],
        }
        lines, code = verify_deploy.format_report(repo, data)
        text = "\n".join(lines)
        self.assertNotIn("gui_only", text)
        self.assertNotIn("no_id", text)
        self.assertNotIn("7777777777777", text)
        self.assertEqual(lines[0], "Automations (1 in repo):")
        self.assertEqual(code, 0)

    def test_templates_sorted_and_aligned(self):
        data = {
            "automations": [],
            "templates": [
                tmpl("sensor.zeta", "1", "T3"),
                tmpl("binary_sensor.a", "unavailable", "T1"),
                tmpl("sensor.mid", "5", "T2"),
            ],
        }
        lines, code = verify_deploy.format_report([], data)
        self.assertEqual(
            lines,
            [
                "Automations (0 in repo):",
                "Template entities (3):",
                "  binary_sensor.a  unavailable  T1",
                "  sensor.mid       5            T2",
                "  sensor.zeta      1            T3",
                "FAIL: no automation files found under automations/",
            ],
        )
        self.assertEqual(code, 1)

    def test_no_trailing_whitespace(self):
        repo = [("1", "automations/a.yaml"), ("22", "automations/b.yaml")]
        data = {
            "automations": [auto("22", "automation.q", "on", "")],
            "templates": [tmpl("sensor.a", "x", ""), tmpl("sensor.bbb", "yy", "")],
        }
        lines, _ = verify_deploy.format_report(repo, data)
        for line in lines:
            self.assertEqual(line, line.rstrip(), repr(line))

    def test_multiple_missing_counted(self):
        repo = [("1", "automations/a.yaml"), ("2", "automations/b.yaml")]
        lines, code = verify_deploy.format_report(
            repo, {"automations": [], "templates": []}
        )
        self.assertEqual(
            lines[-1],
            "FAIL: 2 of 2 automation(s) not OK "
            "(MISSING: 2, unavailable: 0, NO-ID: 0)",
        )
        self.assertEqual(code, 1)

    def test_no_id_row_and_failure(self):
        repo = [
            ("1111111111111", "automations/a.yaml"),
            (None, "automations/noid.yaml"),
        ]
        data = {
            "automations": [auto("1111111111111", "automation.alpha", "on", "T1")],
            "templates": [],
        }
        lines, code = verify_deploy.format_report(repo, data)
        self.assertEqual(
            lines,
            [
                "Automations (2 in repo):",
                "  1111111111111  automation.alpha  on  T1",
                "  NO-ID          automations/noid.yaml",
                "Template entities (0):",
                "FAIL: 1 of 2 automation(s) not OK "
                "(MISSING: 0, unavailable: 0, NO-ID: 1)",
            ],
        )
        self.assertEqual(code, 1)

    def test_no_id_does_not_match_ha_automation_without_id(self):
        repo = [(None, "automations/noid.yaml")]
        data = {
            "automations": [auto(None, "automation.gui", "on", "T")],
            "templates": [],
        }
        lines, code = verify_deploy.format_report(repo, data)
        self.assertNotIn("automation.gui", "\n".join(lines))
        self.assertEqual(code, 1)

    def test_id_width_is_at_least_no_id_width(self):
        repo = [("1", "automations/a.yaml"), (None, "automations/b.yaml")]
        data = {"automations": [auto("1", "automation.x", "on", "T")], "templates": []}
        lines, _ = verify_deploy.format_report(repo, data)
        self.assertEqual(lines[1], "  1      automation.x  on  T")
        self.assertEqual(lines[2], "  NO-ID  automations/b.yaml")

    def test_unavailable_is_normal_row_but_failure(self):
        repo = [
            ("1111111111111", "automations/a.yaml"),
            ("2222222222222", "automations/b.yaml"),
        ]
        data = {
            "automations": [
                auto("1111111111111", "automation.alpha", "on", "T1"),
                auto("2222222222222", "automation.beta", "unavailable", "T2"),
            ],
            "templates": [],
        }
        lines, code = verify_deploy.format_report(repo, data)
        self.assertEqual(
            lines[2], "  2222222222222  automation.beta   unavailable  T2"
        )
        self.assertEqual(
            lines[-1],
            "FAIL: 1 of 2 automation(s) not OK "
            "(MISSING: 0, unavailable: 1, NO-ID: 0)",
        )
        self.assertEqual(code, 1)

    def test_mixed_failures_summed(self):
        repo = [
            ("1", "automations/a.yaml"),
            ("2", "automations/b.yaml"),
            (None, "automations/c.yaml"),
            ("4", "automations/d.yaml"),
        ]
        data = {
            "automations": [
                auto("1", "automation.a", "unavailable", "T"),
                auto("4", "automation.d", "on", "T"),
            ],
            "templates": [],
        }
        lines, code = verify_deploy.format_report(repo, data)
        self.assertEqual(lines[0], "Automations (4 in repo):")
        self.assertEqual(
            lines[-1],
            "FAIL: 3 of 4 automation(s) not OK "
            "(MISSING: 1, unavailable: 1, NO-ID: 1)",
        )
        self.assertEqual(code, 1)

    def test_empty_repo_fails(self):
        lines, code = verify_deploy.format_report(
            [], {"automations": [], "templates": []}
        )
        self.assertEqual(lines[0], "Automations (0 in repo):")
        self.assertEqual(
            lines[-1], "FAIL: no automation files found under automations/"
        )
        self.assertEqual(code, 1)


class MainTest(unittest.TestCase):
    def run_main(self, fetch, files=None, token_text=TOKEN + "\n", token=True):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            for rel, text in (files or {}).items():
                write(root, rel, text)
            root.mkdir(exist_ok=True)
            tok = Path(tmp) / "token"
            if token:
                tok.write_text(token_text, encoding="utf-8")
            argv = [
                "--url", "http://ha.local:8123",
                "--token-file", str(tok),
                "--root", str(root),
            ]
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = verify_deploy.main(argv, fetch=fetch)
            return code, out.getvalue(), err.getvalue(), str(tok)

    def test_happy_path_exit_0(self):
        calls = []

        def fake(url, token):
            calls.append((url, token))
            return {
                "automations": [auto("1111111111111", "automation.alpha")],
                "templates": [tmpl("sensor.t", "3")],
            }

        code, out, err, _ = self.run_main(
            fake, {"automations/a.yaml": "id: '1111111111111'\n"}
        )
        self.assertEqual(code, 0)
        self.assertEqual(calls, [("http://ha.local:8123", TOKEN)])
        self.assertIn("Automations (1 in repo):", out)
        self.assertIn("automation.alpha", out)
        self.assertIn("Template entities (1):", out)
        self.assertIn("OK: all 1 automation ids loaded", out)
        self.assertNotIn(TOKEN, out + err)

    def test_missing_propagates_exit_1(self):
        def fake(url, token):
            return {"automations": [], "templates": []}

        code, out, err, _ = self.run_main(
            fake, {"automations/a.yaml": "id: '1111111111111'\n"}
        )
        self.assertEqual(code, 1)
        self.assertIn("MISSING", out)
        self.assertIn("FAIL: 1 of 1 automation(s) not OK", out)
        self.assertIn("MISSING: 1", out)
        self.assertNotIn(TOKEN, out + err)

    def test_http_401_exit_2(self):
        def fake(url, token):
            raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)

        code, out, err, _ = self.run_main(fake)
        self.assertEqual(code, 2)
        self.assertIn("verify-deploy failed:", err)
        self.assertIn("401", err)
        self.assertNotIn(TOKEN, out + err)

    def test_url_error_exit_2(self):
        def fake(url, token):
            raise urllib.error.URLError("connection refused")

        code, out, err, _ = self.run_main(fake)
        self.assertEqual(code, 2)
        self.assertIn("verify-deploy failed:", err)
        self.assertIn("connection refused", err)
        self.assertNotIn(TOKEN, out + err)

    def test_timeout_exit_2(self):
        def fake(url, token):
            raise TimeoutError("timed out")

        code, out, err, _ = self.run_main(fake)
        self.assertEqual(code, 2)
        self.assertIn("verify-deploy failed:", err)
        self.assertNotIn(TOKEN, out + err)

    def test_bad_json_exit_2(self):
        def fake(url, token):
            raise json.JSONDecodeError("bad", "doc", 0)

        code, out, err, _ = self.run_main(fake)
        self.assertEqual(code, 2)
        self.assertIn("verify-deploy failed: ", err)
        self.assertIn("bad", err)
        self.assertNotIn(TOKEN, out + err)

    def test_value_error_generic_message(self):
        def fake(url, token):
            raise ValueError(f"bad header {token}")

        code, out, err, _ = self.run_main(fake)
        self.assertEqual(code, 2)
        self.assertEqual(
            err.strip(),
            "verify-deploy failed: invalid request (check URL and token)",
        )
        self.assertNotIn(TOKEN, out + err)
        self.assertNotIn("bad header", out + err)

    def test_unexpected_exception_names_type_only(self):
        def fake(url, token):
            raise TypeError(f"contains {token}")

        code, out, err, _ = self.run_main(fake)
        self.assertEqual(code, 2)
        self.assertEqual(err.strip(), "verify-deploy failed: unexpected TypeError")
        self.assertNotIn("contains", out + err)
        self.assertNotIn(TOKEN, out + err)

    def test_multiline_token_rejected(self):
        def fake(url, token):
            raise AssertionError("fetch must not be called")

        code, out, err, tok = self.run_main(fake, token_text="tokA\ntokB\n")
        self.assertEqual(code, 2)
        self.assertEqual(
            err.strip(),
            f"verify-deploy failed: token file {tok} does not hold a "
            "single-line token",
        )
        self.assertNotIn("tokA", out + err)
        self.assertNotIn("tokB", out + err)

    def test_empty_token_rejected(self):
        def fake(url, token):
            raise AssertionError("fetch must not be called")

        code, out, err, tok = self.run_main(fake, token_text=" \n\n")
        self.assertEqual(code, 2)
        self.assertIn("does not hold a single-line token", err)

    def test_token_with_inner_space_or_non_ascii_rejected(self):
        def fake(url, token):
            raise AssertionError("fetch must not be called")

        for text in ("tok en", "tok\ten", "tok\u00e5en", "tok\x7fen"):
            with self.subTest(text=text):
                code, out, err, _ = self.run_main(fake, token_text=text)
                self.assertEqual(code, 2)
                self.assertIn("does not hold a single-line token", err)

    def test_unreadable_automations_exit_2(self):
        def fake(url, token):
            raise AssertionError("fetch must not be called")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            bad = root / "automations" / "bad.yaml"
            bad.parent.mkdir(parents=True)
            bad.write_bytes(b"id: '1'\n\xff\xfe\x80\n")
            tok = Path(tmp) / "token"
            tok.write_text(TOKEN + "\n", encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = verify_deploy.main(
                    [
                        "--url", "http://ha.local:8123",
                        "--token-file", str(tok),
                        "--root", str(root),
                    ],
                    fetch=fake,
                )
        self.assertEqual(code, 2)
        self.assertTrue(
            err.getvalue().startswith(
                "verify-deploy failed: cannot read automations:"
            ),
            err.getvalue(),
        )
        self.assertEqual(out.getvalue(), "")
        self.assertNotIn(TOKEN, out.getvalue() + err.getvalue())

    def test_invalid_utf8_token_file(self):
        def fake(url, token):
            raise AssertionError("fetch must not be called")

        with tempfile.TemporaryDirectory() as tmp:
            tok = Path(tmp) / "token"
            tok.write_bytes(b"\xff\xfe\x80abc")
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = verify_deploy.main(
                    [
                        "--url", "http://ha.local:8123",
                        "--token-file", str(tok),
                        "--root", tmp,
                    ],
                    fetch=fake,
                )
        self.assertEqual(code, 2)
        self.assertEqual(
            err.getvalue().strip(),
            f"verify-deploy failed: cannot read token file {tok}",
        )

    def test_missing_key_exit_2(self):
        def fake(url, token):
            return {"automations": []}  # no "templates"

        code, out, err, _ = self.run_main(fake)
        self.assertEqual(code, 2)
        self.assertIn("verify-deploy failed:", err)
        self.assertNotIn(TOKEN, out + err)

    def test_unreadable_token_file_exit_2(self):
        def fake(url, token):
            raise AssertionError("fetch must not be called")

        code, out, err, tok = self.run_main(fake, token=False)
        self.assertEqual(code, 2)
        self.assertIn("verify-deploy failed: cannot read token file", err)
        self.assertIn(tok, err)

    def test_token_is_stripped(self):
        seen = []

        def fake(url, token):
            seen.append(token)
            return {"automations": [], "templates": []}

        self.run_main(fake, token_text="  " + TOKEN + " \n\n")
        self.assertEqual(seen, [TOKEN])


if __name__ == "__main__":
    unittest.main()
