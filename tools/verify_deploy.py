"""Show which repo automations are loaded in HA and when they changed.

After `make deploy`, a repo automation that failed to load is a silent
failure. This asks HA (POST /api/template) for every automation and
template-integration entity, matches the repo's automation ids against
them and exits non-zero if any is missing. Stdlib only: HA YAML has
custom tags, so the repo files are scanned for their top-level id
rather than parsed.

Run via `make verify-deploy`, or:
  python3 -I tools/verify_deploy.py --url http://HOST:8123 \
      --token-file PATH
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ID_RE = re.compile(r"^id:\s*([\"']?)([^\"'\s#]+)\1\s*(#.*)?$")

# Automations are looked up by attributes.id, not entity id: entity ids
# are fixed at first registration and are not derived from the current
# alias. Template entities use integration_entities("template") because
# templates cannot look up by unique_id; this also lists GUI-created
# template helpers, which is accepted.
TEMPLATE = """\
{%- set ns = namespace(a=[], t=[]) -%}
{%- for s in states.automation -%}
{%- set ns.a = ns.a + [{"id": s.attributes.get("id"), "entity_id": s.entity_id, "state": s.state, "last_changed": s.last_changed.isoformat()}] -%}
{%- endfor -%}
{%- set te = integration_entities("template") -%}
{%- for s in states | selectattr("entity_id", "in", te) -%}
{%- set ns.t = ns.t + [{"entity_id": s.entity_id, "state": s.state, "last_changed": s.last_changed.isoformat()}] -%}
{%- endfor -%}
{{ {"automations": ns.a, "templates": ns.t} | to_json }}"""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    # urllib's default handler forwards the Authorization header to the
    # redirect target; the curl reload targets do not follow redirects.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def collect_ids(root: Path) -> list[tuple[str | None, str]]:
    found = []
    for path in (root / "automations").rglob("*.yaml"):
        rel = path.relative_to(root).as_posix()
        auto_id = None
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            m = ID_RE.match(line)
            if m:
                auto_id = m.group(2)
                break
        found.append((auto_id, rel))
    return sorted(found, key=lambda t: t[1])


def fetch(url: str, token: str) -> dict:
    req = urllib.request.Request(
        url.rstrip("/") + "/api/template",
        data=json.dumps({"template": TEMPLATE}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with OPENER.open(req, timeout=15) as resp:
        return json.loads(resp.read())


def format_report(
    repo_ids: list[tuple[str | None, str]], data: dict
) -> tuple[list[str], int]:
    by_id = {a["id"]: a for a in data["automations"]}
    rows = [(i, rel, by_id.get(i) if i is not None else None) for i, rel in repo_ids]
    present = [a for _, _, a in rows if a is not None]
    id_w = max([len(i) for i, _ in repo_ids if i is not None] + [len("NO-ID")])
    ent_w = max([len(a["entity_id"]) for a in present] + [len("MISSING")])
    st_w = max((len(a["state"]) for a in present), default=0)

    lines = [f"Automations ({len(repo_ids)} in repo):"]
    missing = unavailable = no_id = 0
    for i, rel, a in rows:
        if i is None:
            no_id += 1
            lines.append(f"  {'NO-ID'.ljust(id_w)}  {rel}".rstrip())
        elif a is None:
            missing += 1
            lines.append(f"  {i.ljust(id_w)}  {'MISSING'.ljust(ent_w)}  {rel}".rstrip())
        else:
            if a["state"] == "unavailable":
                unavailable += 1
            lines.append(
                f"  {i.ljust(id_w)}  {a['entity_id'].ljust(ent_w)}"
                f"  {a['state'].ljust(st_w)}  {a['last_changed']}".rstrip()
            )

    templates = sorted(data["templates"], key=lambda t: t["entity_id"])
    lines.append(f"Template entities ({len(templates)}):")
    te_w = max((len(t["entity_id"]) for t in templates), default=0)
    ts_w = max((len(t["state"]) for t in templates), default=0)
    for t in templates:
        lines.append(
            f"  {t['entity_id'].ljust(te_w)}  {t['state'].ljust(ts_w)}"
            f"  {t['last_changed']}".rstrip()
        )

    failed = missing + unavailable + no_id
    if not repo_ids:
        lines.append("FAIL: no automation files found under automations/")
        return lines, 1
    if failed:
        lines.append(
            f"FAIL: {failed} of {len(repo_ids)} automation(s) not OK "
            f"(MISSING: {missing}, unavailable: {unavailable}, NO-ID: {no_id})"
        )
        return lines, 1
    lines.append(f"OK: all {len(repo_ids)} automation ids loaded")
    return lines, 0


def main(argv: list[str] | None = None, fetch=fetch) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", required=True)
    ap.add_argument("--token-file", required=True)
    ap.add_argument("--root", type=Path, default=ROOT)
    args = ap.parse_args(argv)

    try:
        token = Path(args.token_file).read_text().strip()
    except (OSError, UnicodeDecodeError):
        print(
            f"verify-deploy failed: cannot read token file {args.token_file}",
            file=sys.stderr,
        )
        return 2
    if not token or any(not 33 <= ord(c) <= 126 for c in token):
        print(
            f"verify-deploy failed: token file {args.token_file} does not "
            "hold a single-line token",
            file=sys.stderr,
        )
        return 2

    try:
        repo_ids = collect_ids(args.root)
    except (OSError, UnicodeDecodeError) as e:
        print(f"verify-deploy failed: cannot read automations: {e}", file=sys.stderr)
        return 2

    try:
        data = fetch(args.url, token)
        lines, code = format_report(repo_ids, data)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as e:
        print(f"verify-deploy failed: {e}", file=sys.stderr)
        return 2
    except ValueError:
        print(
            "verify-deploy failed: invalid request (check URL and token)",
            file=sys.stderr,
        )
        return 2
    except Exception as e:
        print(f"verify-deploy failed: unexpected {type(e).__name__}", file=sys.stderr)
        return 2
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main())
