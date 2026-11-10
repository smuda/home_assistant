"""Pull the series the battery simulation needs into sim.csv and prices.csv.

Both files are written next to this script, whatever the working
directory.

VM is read-only at http://192.168.40.20:8428 (no auth). We shell out
to curl rather than using Python's socket layer. `--noproxy ''` is
needed or the sandbox routes the LAN address through its proxy.

Unlike pull.py this uses last_over_time on the HA entity label, so
one query shape works for every entity whatever its unit, and the
window is the whole local days 2026-10-10 .. 2026-11-09. END is
exclusive.

Sign conventions (see pull.py):
  grid (sensor.p1_meter_effekt):            + = import, - = export
  batt (sensor.battery_charging_power_signed): + = charging, - = discharging
"""
import csv
import json
import os
import subprocess
from datetime import datetime, timezone

BASE = "http://192.168.40.20:8428/api/v1/query_range"
START = "2026-10-09T22:00:00Z"   # 2026-10-10 00:00 local (CEST)
END = "2026-11-09T23:00:00Z"     # 2026-11-10 00:00 local (CET)
# Rows at or after END are dropped: the query end is inclusive.
END_EPOCH = int(datetime.strptime(END, "%Y-%m-%dT%H:%M:%SZ")
                .replace(tzinfo=timezone.utc).timestamp())

HERE = os.path.dirname(os.path.abspath(__file__))

X = "_afc12081_4304_4878_97df_a160569e3faf"

SIM = {
    "spot": "sensor.nord_pool_se3_aktuellt_pris",
    "imp_px": "sensor.nordpool_se3_inkl_skatt_o_nat",
    "exp_px": "sensor.elexport_ersattning",
    "batt": "sensor.battery_charging_power_signed",
    "grid": "sensor.p1_meter_effekt",
    "soc": "sensor.battery_level",
    "loadw": "sensor.load_power",
    "ev": "sensor.zag064494_laddeffekt",
    "dec": "sensor.heartbeat_batteribeslut",
    "ems": "sensor.ems_mode_selection_raw",
    "cmd": "sensor.battery_forced_charge_discharge_cmd_raw",
    "minsoc": "sensor.battery_min_soc",
    "maxdis": "sensor.battery_max_discharge_power",
    "nodis": "binary_sensor.sh10_0rt_20_battery_no_discharge_active" + X,
    "pvw": "sensor.total_dc_power",
}

PRICES = {
    "spot": "sensor.nord_pool_se3_aktuellt_pris",
    "imp": "sensor.nordpool_se3_inkl_skatt_o_nat",
    "nat": "sensor.elnatsavgift_aktuell",
}
for _k in ("electricity_price", "spot_price", "heartbeat_price",
           "comparison_price", "grid_costs"):
    PRICES["k_" + _k] = "sensor.heartbeat_john_allberg_" + _k + X


def fetch(entity, step, lookback):
    # Filter out the sibling series (availability, attributes, ...) that
    # share the entity label so res[0] is the state series.
    q = ('last_over_time({entity="%s",__name__!~".*(available|last_updated'
         '|state_change|_attr_|created|info).*"}[%s])' % (entity, lookback))
    out = subprocess.check_output([
        "curl", "--noproxy", "", "-s", "-G", BASE,
        "--data-urlencode", "query=" + q,
        "--data-urlencode", "start=" + START,
        "--data-urlencode", "end=" + END,
        "--data-urlencode", "step=" + step,
    ], timeout=120)
    res = json.loads(out)["data"]["result"]
    if not res:
        return {}
    return {int(t): float(v) for t, v in res[0]["values"]
            if int(t) < END_EPOCH}


def pull(entities, step, lookback, path):
    cols = {}
    for k, e in entities.items():
        cols[k] = fetch(e, step, lookback)
        print("%-20s %d points" % (k, len(cols[k])))
    ts = sorted(cols["spot"] if step == "900" else cols["grid"])
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t"] + list(cols))
        for t in ts:
            w.writerow([t] + [cols[k].get(t) for k in cols])
    print("wrote %s (%d rows)" % (path, len(ts)))


if __name__ == "__main__":
    pull(SIM, "300", "10m", os.path.join(HERE, "sim.csv"))
    pull(PRICES, "900", "15m", os.path.join(HERE, "prices.csv"))
