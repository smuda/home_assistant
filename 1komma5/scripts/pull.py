"""Pull battery / grid / price series from VictoriaMetrics into data.csv.

VM is read-only at http://192.168.40.20:8428 (no auth). We shell out
to curl rather than using Python's socket layer.

Sign conventions (verified against SOC change and export power):
  grid (sensor.p1_meter_effekt):            + = import, - = export
  batt (sensor.battery_charging_power_signed): + = charging, - = discharging
"""
import json, subprocess
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Stockholm")

BASE = "http://192.168.40.20:8428/api/v1/query_range"
STEP = "900"          # 15 min
# Absolute window, Europe/Stockholm (CEST = UTC+2 in July).
START = "2026-07-31T22:00:00Z"   # 2026-08-01 00:00 local
END   = "2026-08-31T22:00:00Z"   # 2026-09-01 00:00 local

series = {
    "spot":   'homeassistant_sensor_unit_sek_per_kwh{entity="sensor.nord_pool_se3_aktuellt_pris"}',
    "imp_px": 'homeassistant_sensor_unit_sek_per_kwh{entity="sensor.nordpool_se3_inkl_skatt_o_nat"}',
    "exp_px": 'homeassistant_sensor_unit_sek_per_kwh{entity="sensor.elexport_ersattning"}',
    "batt":   'homeassistant_sensor_power_w{entity="sensor.battery_charging_power_signed"}',
    "grid":   'homeassistant_sensor_power_w{entity="sensor.p1_meter_effekt"}',
    "soc":    'homeassistant_sensor_battery_percent{entity="sensor.battery_level"}',
    "expw":   'homeassistant_sensor_power_w{entity="sensor.export_power"}',
    "pvgen":  'homeassistant_sensor_energy_kwh{entity="sensor.total_pv_generation"}',
    # Sungrow's own PV split, metered on the DC side. These are cumulative
    # counters: difference consecutive samples for per-bucket energy. They
    # close exactly, pvgen == direct + pvbatt + pvexp over any window.
    "direct": 'homeassistant_sensor_energy_kwh{entity="sensor.total_direct_energy_consumption"}',
    "pvbatt": 'homeassistant_sensor_energy_kwh{entity="sensor.total_battery_charge_from_pv"}',
    "pvexp":  'homeassistant_sensor_energy_kwh{entity="sensor.total_exported_energy_from_pv"}',
    "loadw":  'homeassistant_sensor_power_w{entity="sensor.load_power"}',
    # EV charger power. Per-bucket EV energy must come from this, not from
    # the session energy counter, which reports in delayed batches.
    "ev":     'homeassistant_sensor_power_w{entity="sensor.zag064494_laddeffekt"}',
}

def fetch(q):
    out = subprocess.check_output([
        "curl", "-s", BASE,
        "--data-urlencode", "query=%s" % q,
        "--data-urlencode", "start=%s" % START,
        "--data-urlencode", "end=%s" % END,
        "--data-urlencode", "step=%s" % STEP,
    ], timeout=90)
    j = json.loads(out)
    res = j["data"]["result"]
    if not res:
        return {}
    return {int(t): float(v) for t, v in res[0]["values"]}

cols = {k: fetch(q) for k, q in series.items()}
for k, v in cols.items():
    print("fetched", k, len(v), "points")

# The Nord Pool integration dropped out for the last days of August, so
# spot is backfilled from elprisetjustnu.se, which serves the same SE3
# day-ahead series at the same 15-min resolution. Calibrated against a
# fully-covered day: the HA sensor lags the published series by exactly
# one bucket (mean |diff| 0.014 kr/kWh at that offset), hence the shift.
# Only spot is filled; analyze.py already derives the import and export
# prices from the documented constants when those sensors are missing.
def backfill_spot(cols, ts):
    missing = [t for t in ts if t not in cols["spot"]]
    if not missing:
        return 0
    days = sorted({datetime.fromtimestamp(t, TZ).date() for t in missing})
    api = {}
    for d in days:
        url = ("https://www.elprisetjustnu.se/api/v1/prices/"
               "%d/%02d-%02d_SE3.json" % (d.year, d.month, d.day))
        try:
            raw = subprocess.check_output(["curl", "-s", "-m", "30", url], timeout=60)
            for e in json.loads(raw):
                api[int(datetime.fromisoformat(e["time_start"]).timestamp())] = e["SEK_per_kWh"]
        except Exception as exc:
            print("  backfill: %s failed (%s)" % (d, exc))
    n = 0
    for t in missing:
        v = api.get(t - 900)
        if v is not None:
            cols["spot"][t] = v; n += 1
    print("backfilled spot for %d of %d missing buckets across %s"
          % (n, len(missing), ", ".join(str(d) for d in days)))
    return n

ts = sorted(cols["grid"].keys())
backfill_spot(cols, ts)
import csv
with open("data.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["t"] + list(cols.keys()))
    for t in ts:
        w.writerow([t] + [cols[k].get(t) for k in cols])
print("wrote data.csv", len(ts), "rows")
