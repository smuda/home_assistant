"""Pull battery / grid / price series from VictoriaMetrics into data.csv.

VM is read-only at http://192.168.40.20:8428 (no auth). We shell out
to curl because the sandbox blocks Python's own socket layer but
allows curl.

Sign conventions (verified against SOC change and export power):
  grid (sensor.p1_meter_effekt):            + = import, - = export
  batt (sensor.battery_charging_power_signed): + = charging, - = discharging
"""
import json, subprocess

BASE = "http://192.168.40.20:8428/api/v1/query_range"
STEP = "900"          # 15 min
RANGE_DAYS = 14

series = {
    "spot":   'homeassistant_sensor_unit_sek_per_kwh{entity="sensor.nord_pool_se3_aktuellt_pris"}',
    "imp_px": 'homeassistant_sensor_unit_sek_per_kwh{entity="sensor.nordpool_se3_inkl_skatt_o_nat"}',
    "exp_px": 'homeassistant_sensor_unit_sek_per_kwh{entity="sensor.elexport_ersattning"}',
    "batt":   'homeassistant_sensor_power_w{entity="sensor.battery_charging_power_signed"}',
    "grid":   'homeassistant_sensor_power_w{entity="sensor.p1_meter_effekt"}',
    "soc":    'homeassistant_sensor_battery_percent{entity="sensor.battery_level"}',
    "expw":   'homeassistant_sensor_power_w{entity="sensor.export_power"}',
    "pvgen":  'homeassistant_sensor_energy_kwh{entity="sensor.total_pv_generation"}',
}

def fetch(q):
    out = subprocess.check_output([
        "curl", "-s", BASE,
        "--data-urlencode", "query=%s" % q,
        "--data-urlencode", "start=now-%dd" % RANGE_DAYS,
        "--data-urlencode", "end=now",
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

ts = sorted(cols["grid"].keys())
import csv
with open("data.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["t"] + list(cols.keys()))
    for t in ts:
        w.writerow([t] + [cols[k].get(t) for k in cols])
print("wrote data.csv", len(ts), "rows")
