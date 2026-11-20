#!/usr/bin/env python3
"""Print a per-step table of Home Assistant entity values from VictoriaMetrics.

One row per step: the UTC timestamp, then one column per entity in
argument order. A step with no value prints an empty cell. Values are
printed as VictoriaMetrics returns them, so non-numeric ones such as
"NaN" pass through unchanged.

    python3 metrics/scripts/vmq.py \\
        sensor.p1_meter_effekt sensor.zag064494_laddeffekt \\
        --start 2026-11-19T14:00:00Z --end 2026-11-19T16:00:00Z

Python 3 standard library only. See "Querying from the command line"
in metrics/README.md.
"""

import argparse
import base64
import csv
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

DEFAULT_BASE = "http://192.168.40.20:8428"

# The sibling series HA exports under the same entity label (availability,
# last_updated, state_change counters, attributes, info). Excluding them
# rather than listing the value gauges keeps every domain and unit.
EXCLUDE = ".*(available|last_updated|state_change|_attr_|created|info).*"


def selector(entity):
    """The series selector for an entity's value series."""
    esc = entity.replace("\\", "\\\\").replace('"', '\\"')
    return '{entity="%s",__name__!~"%s"}' % (esc, EXCLUDE)


def parse_time(text):
    """ISO 8601 to epoch seconds. A time without an offset is UTC."""
    t = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return int(t.timestamp())


def format_time(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def align(start, step):
    """VictoriaMetrics aligns the range start down to a step multiple."""
    return start - start % step


def query_url(base, entity, start, end, step):
    params = urllib.parse.urlencode({
        "query": selector(entity),
        "start": start,
        "end": end,
        "step": "%ds" % step,
    })
    return "%s/api/v1/query_range?%s" % (base.rstrip("/"), params)


def proxy_for(url, env):
    """The proxy to use for url, or None for a direct connection.

    Behaves like `curl --noproxy ''`: no_proxy is ignored, so a
    configured proxy is used even for a LAN address it lists.
    """
    scheme = urllib.parse.urlsplit(url).scheme
    for name in ("%s_proxy" % scheme, ("%s_proxy" % scheme).upper()):
        value = env.get(name, "").strip()
        if value:
            return value
    return None


def build_request(url, env):
    req = urllib.request.Request(url)
    proxy = proxy_for(url, env)
    if proxy:
        if "://" not in proxy:
            proxy = "http://" + proxy
        parts = urllib.parse.urlsplit(proxy)
        if parts.username is not None:
            creds = "%s:%s" % (urllib.parse.unquote(parts.username),
                               urllib.parse.unquote(parts.password or ""))
            req.add_header("Proxy-Authorization", "Basic " + base64.b64encode(
                creds.encode()).decode("ascii"))
        hostport = parts.hostname
        if parts.port:
            hostport = "%s:%d" % (hostport, parts.port)
        req.set_proxy(hostport, req.type)
    return req


# ProxyHandler({}) stops urllib from choosing a proxy itself; its own
# choice honours no_proxy. build_request sets the proxy instead.
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def fetch(url, env=None):
    req = build_request(url, os.environ if env is None else env)
    with OPENER.open(req, timeout=60) as resp:
        return json.load(resp)


def series(response):
    """[(labels, {epoch: value})] from a query_range response."""
    if response.get("status") != "success":
        raise RuntimeError("VictoriaMetrics: %s" % response.get(
            "error", response.get("status")))
    out = []
    for item in response["data"]["result"]:
        values = {int(float(t)): v for t, v in item.get("values", [])}
        out.append((item.get("metric", {}), values))
    return out


def columns(entity, found):
    """(name, values) per column for one entity, plus notes for stderr.

    An entity with no series gets one empty column. One with several
    gets a column each, numbered, and a note naming every series.
    """
    if not found:
        return [(entity, {})], ["%s: no value series" % entity]
    if len(found) == 1:
        return [(entity, found[0][1])], []
    cols, notes = [], ["%s: %d value series, one column each:" % (
        entity, len(found))]
    for n, (labels, values) in enumerate(found, 1):
        name = "%s#%d" % (entity, n)
        cols.append((name, values))
        notes.append("  %s = %s" % (name, labels_text(labels)))
    return cols, notes


def labels_text(labels):
    rest = ",".join('%s="%s"' % (k, labels[k])
                    for k in sorted(labels) if k != "__name__")
    return "%s{%s}" % (labels.get("__name__", ""), rest)


def table(cols, start, end, step, changes=None):
    """Header and rows: every step from start to end, gaps empty.

    changes is a list of column indexes; when set, only the first row
    and rows where one of those columns differs from the row before
    are kept.
    """
    stamps = set(range(align(start, step), end + 1, step))
    for _, values in cols:
        stamps.update(values)
    header = ["time"] + [name for name, _ in cols]
    rows, prev = [], None
    for t in sorted(stamps):
        cells = [values.get(t, "") for _, values in cols]
        key = [cells[i] for i in changes] if changes else None
        if not changes or prev is None or key != prev:
            rows.append([format_time(t)] + cells)
        prev = key
    return header, rows


def write_text(header, rows, out):
    widths = [max(len(r[i]) for r in [header] + rows)
              for i in range(len(header))]
    for r in [header] + rows:
        out.write("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip()
                  + "\n")


def parse_args(argv):
    p = argparse.ArgumentParser(
        description="Per-step table of HA entity values from "
                    "VictoriaMetrics.")
    p.add_argument("entities", nargs="+", metavar="ENTITY",
                   help="entity id, e.g. sensor.p1_meter_effekt")
    p.add_argument("--start", required=True, type=parse_time,
                   help="range start, ISO 8601, UTC unless an offset "
                        "is given")
    p.add_argument("--end", required=True, type=parse_time,
                   help="range end, inclusive, same format")
    p.add_argument("--step", type=int, default=60,
                   help="seconds between rows (default 60)")
    p.add_argument("--changes", metavar="ENTITY",
                   help="print only rows where this entity's value "
                        "changed from the previous row")
    p.add_argument("--csv", action="store_true",
                   help="write CSV instead of aligned columns")
    p.add_argument("--url", default=DEFAULT_BASE,
                   help="VictoriaMetrics base URL (default %s)"
                        % DEFAULT_BASE)
    args = p.parse_args(argv)
    if args.step <= 0:
        p.error("--step must be positive")
    if args.end < args.start:
        p.error("--end is before --start")
    if args.changes and args.changes not in args.entities:
        p.error("--changes must be one of the entities")
    return args


def main(argv=None, fetch=fetch, out=sys.stdout, err=sys.stderr):
    args = parse_args(argv)
    start = align(args.start, args.step)
    cols, owner = [], []
    for entity in args.entities:
        url = query_url(args.url, entity, start, args.end, args.step)
        entity_cols, notes = columns(entity, series(fetch(url)))
        for note in notes:
            err.write(note + "\n")
        cols.extend(entity_cols)
        owner.extend([entity] * len(entity_cols))
    changes = None
    if args.changes:
        changes = [i for i, e in enumerate(owner) if e == args.changes]
    header, rows = table(cols, start, args.end, args.step, changes)
    if args.csv:
        csv.writer(out, lineterminator="\n").writerows([header] + rows)
    else:
        write_text(header, rows, out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
