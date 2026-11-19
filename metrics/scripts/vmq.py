#!/usr/bin/env python3
"""Print a per-step table of Home Assistant entity values from VictoriaMetrics.

VictoriaMetrics is read-only at http://192.168.40.20:8428 (no auth). A
naive selector such as {__name__=~"homeassistant_.*", entity=~"..."}
also matches the sibling series that share the `entity` label
(availability, attributes, the state_change counters and _created
timestamps, _info, _last_updated), so the result shows counters and
timestamps instead of values. We select on the `entity` label plus an
exclusion regex on __name__ that drops those siblings, leaving the one
value gauge per entity. The regex is the same one pull_sim.py uses; it
is kept here as a constant so this script stays standard-library only.

Example:

    python3 vmq.py \\
        sensor.zag064494_laddeffekt sensor.p1_meter_effekt \\
        --start 2026-11-19T06:00:00Z --end 2026-11-19T09:00:00Z

    python3 vmq.py sensor.battery_level sensor.load_power \\
        --start 2026-11-19T06:00:00Z --end 2026-11-19T09:00:00Z \\
        --step 300 --changes sensor.battery_level

Only the Python 3 standard library is used, so it runs without the
1KOMMA5 venv. The proxy is bypassed for the request the same way the
curl-based scripts use `--noproxy ''`, because the LAN address must be
reached directly.
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

DEFAULT_URL = "http://192.168.40.20:8428"

# Drop the sibling series that share the `entity` label but are not the
# value gauge. Identical to the filter in 1komma5/scripts/pull_sim.py.
EXCLUDE = r".*(available|last_updated|state_change|_attr_|created|info).*"


def build_query(entity):
    """PromQL selector for one entity's value gauge."""
    return '{entity="%s",__name__!~"%s"}' % (entity, EXCLUDE)


def parse_response(obj):
    """Reshape one query_range response for a single entity.

    Returns (values, names) where `values` maps int epoch second to the
    raw string value, and `names` is the sorted list of distinct metric
    names the entity matched. More than one name means the exclusion
    regex did not narrow the entity to a single value series; the caller
    decides what to do rather than this picking one silently.
    """
    result = obj.get("data", {}).get("result", [])
    values = {}
    names = set()
    for series in result:
        names.add(series.get("metric", {}).get("__name__", ""))
        for ts, val in series.get("values", []):
            # Keep the raw string: enum / non-numeric state series (e.g.
            # homeassistant_sensor_state) must survive without a float()
            # cast, and numeric values print fine as-is.
            values[int(float(ts))] = val
    return values, sorted(n for n in names if n)


def reshape(columns, entities):
    """Build table rows from per-entity {epoch: value} maps.

    One row per step that any entity has a value for, ordered by time,
    with the columns in `entities` order. A step an entity has no value
    for gets None (an empty cell), rather than dropping the row.
    """
    stamps = sorted({t for e in entities for t in columns.get(e, {})})
    rows = []
    for t in stamps:
        rows.append([t] + [columns.get(e, {}).get(t) for e in entities])
    return rows


def changed_only(rows, column_index):
    """Keep only rows where `column_index` differs from the prior row."""
    out = []
    prev = object()  # sentinel so the first row is always kept
    for row in rows:
        cur = row[column_index]
        if cur != prev:
            out.append(row)
            prev = cur
    return out


def fetch(base_url, entity, start, end, step):
    """Query VictoriaMetrics for one entity. Returns the parsed JSON."""
    params = urllib.parse.urlencode({
        "query": build_query(entity),
        "start": start,
        "end": end,
        "step": step,
    })
    url = base_url.rstrip("/") + "/api/v1/query_range?" + params
    # Bypass any proxy: the VM host is on the LAN and must be reached
    # directly, the same as `curl --noproxy ''` in the sibling scripts.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fmt_cell(value):
    return "" if value is None else str(value)


def fmt_time(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def render(rows, entities):
    lines = ["\t".join(["time"] + entities)]
    for row in rows:
        lines.append("\t".join(
            [fmt_time(row[0])] + [fmt_cell(c) for c in row[1:]]))
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Per-step table of HA entity values from VictoriaMetrics.")
    p.add_argument("entities", nargs="+", help="entity ids, e.g. sensor.foo")
    p.add_argument("--start", required=True,
                   help="window start, UTC ISO 8601 (2026-11-19T06:00:00Z)")
    p.add_argument("--end", required=True,
                   help="window end, UTC ISO 8601")
    p.add_argument("--step", default="60",
                   help="step in seconds (default 60)")
    p.add_argument("--changes", metavar="ENTITY",
                   help="print only rows where this entity's value changed")
    p.add_argument("--url", default=DEFAULT_URL,
                   help="VictoriaMetrics base URL (default %s)" % DEFAULT_URL)
    args = p.parse_args(argv)

    if args.changes and args.changes not in args.entities:
        p.error("--changes %s is not one of the queried entities" %
                args.changes)

    columns = {}
    for entity in args.entities:
        values, names = parse_response(
            fetch(args.url, entity, args.start, args.end, args.step))
        if len(names) > 1:
            p.exit(2, "%s matched %d value series: %s\n"
                   "Narrow it with an explicit __name__, or check the entity.\n"
                   % (entity, len(names), ", ".join(names)))
        columns[entity] = values

    rows = reshape(columns, args.entities)
    if args.changes:
        rows = changed_only(rows, 1 + args.entities.index(args.changes))

    print(render(rows, args.entities))
    return 0


if __name__ == "__main__":
    sys.exit(main())
