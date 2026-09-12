"""Pull the same series as pull.py, but from Home Assistant's recorder.

VictoriaMetrics is the normal source; this is the fallback for windows
VM missed. HA's recorder keeps only `purge_keep_days` (10 by default),
so it can only rescue the recent past -- run it while the gap is fresh.

Output goes to ../data/<name>.csv in the repo, committed, so a window
recovered once is never lost again. Same columns as pull.py, so
analyze.py reads either without changes.

The long-lived token is read from the path below and never printed.
"""
import csv, json, os, subprocess, sys
from urllib.parse import quote
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Stockholm")
BASE = "http://homeassistant.local:8123/api/history/period"
TOKEN = os.path.expanduser(
    "~/Projects/smuda/home_assistant/metrics/vmconfig/homeassistant-token")
STEP = 900

START = datetime(2026, 9, 2, 4, 15, tzinfo=TZ)
END   = datetime(2026, 9, 12, 0, 0, tzinfo=TZ)
OUT   = "../data/2026-09.csv"

# column -> entity, matching pull.py
ENTS = {
    "spot":   "sensor.nord_pool_se3_aktuellt_pris",
    "imp_px": "sensor.nordpool_se3_inkl_skatt_o_nat",
    "exp_px": "sensor.elexport_ersattning",
    "batt":   "sensor.battery_charging_power_signed",
    "grid":   "sensor.p1_meter_effekt",
    "soc":    "sensor.battery_level",
    "expw":   "sensor.export_power",
    "pvgen":  "sensor.total_pv_generation",
    "direct": "sensor.total_direct_energy_consumption",
    "pvbatt": "sensor.total_battery_charge_from_pv",
    "pvexp":  "sensor.total_exported_energy_from_pv",
    "loadw":  "sensor.load_power",
    "ev":     "sensor.zag064494_laddeffekt",
}

def fetch_day(day_start, day_end, entities):
    """All entities for one day. Returns {entity: [(epoch, float)]}."""
    # "+02:00" must be encoded; a bare + in a query string means space.
    url = "%s/%s?filter_entity_id=%s&end_time=%s&minimal_response" % (
        BASE, quote(day_start.isoformat()), ",".join(entities),
        quote(day_end.isoformat()))
    raw = subprocess.check_output([
        "curl", "-s", "-m", "120", "-H",
        "Authorization: Bearer %s" % open(TOKEN).read().strip(), url,
    ], timeout=180)
    data = json.loads(raw)
    if not isinstance(data, list):
        raise SystemExit("Home Assistant returned: %s" % data)
    out = {}
    for series in data:
        if not series:
            continue
        ent = series[0].get("entity_id")
        pts = []
        for st in series:
            v = st.get("state")
            try:
                pts.append((datetime.fromisoformat(
                    st.get("last_changed") or st["last_updated"]).timestamp(), float(v)))
            except (TypeError, ValueError):
                continue      # unavailable / unknown / non-numeric
        out[ent] = pts
    return out

# HA caps how much one request returns, so walk a day at a time.
series = {e: [] for e in ENTS.values()}
day = START
while day < END:
    nxt = min(day + timedelta(days=1), END)
    got = fetch_day(day, nxt, list(ENTS.values()))
    for e, pts in got.items():
        series[e].extend(pts)
    print("  %s: %s" % (day.date(),
          " ".join("%s=%d" % (k, len(got.get(v, []))) for k, v in ENTS.items())))
    day = nxt

# Resample: the value at each boundary is the last state at or before it,
# the same semantics as a VictoriaMetrics query_range step.
for e in series:
    series[e].sort()

def at(pts, t, idx):
    while idx[0] + 1 < len(pts) and pts[idx[0] + 1][0] <= t:
        idx[0] += 1
    if not pts or pts[idx[0]][0] > t:
        return None
    return pts[idx[0]][1]

cursors = {e: [0] for e in series}
t0 = int(START.timestamp()); t1 = int(END.timestamp())
rows = []
for t in range(t0 - t0 % STEP, t1, STEP):
    if t < t0:
        continue
    rows.append([t] + [at(series[ENTS[c]], t, cursors[ENTS[c]]) for c in ENTS])

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["t"] + list(ENTS))
    w.writerows(rows)
print("wrote %s  %d rows  %s -> %s" % (OUT, len(rows), START, END))
