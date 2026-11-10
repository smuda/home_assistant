"""Check how 1KOMMA5 prices the tariff, from prices.csv (pull_sim.py).

Compares the heartbeat sensors' prices with the Nord Pool spot and the
house's own tariff sensors: the spot multiplier, the flat add-on to
the electricity price, and the grid-cost component by period.
"""
import csv
import statistics
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Stockholm")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "prices.csv"
    with open(path) as f:
        rows = [{k: (float(v) if v not in ("", "None") else None)
                 for k, v in r.items()} for r in csv.DictReader(f)]
    rows = [r for r in rows if r["k_electricity_price"] is not None]
    fmt = "%Y-%m-%d %H:%M"
    print("rows with k_electricity_price: %d, %s -> %s" % (
        len(rows),
        datetime.fromtimestamp(rows[0]["t"], TZ).strftime(fmt),
        datetime.fromtimestamp(rows[-1]["t"], TZ).strftime(fmt)))

    ratios = [r["k_spot_price"] / r["spot"] for r in rows
              if r["spot"] > 0.2 and r["k_spot_price"] is not None]
    near = sum(1 for x in ratios if abs(x / 1.25 - 1) < 0.01)
    print("k_spot_price/spot (spot > 0.2): n %d, median %.4f, "
          "%d (%.0f %%) within 1 %% of 1.25"
          % (len(ratios), statistics.median(ratios), near,
             100 * near / len(ratios)))

    diff = [r["k_electricity_price"] - r["k_spot_price"] for r in rows
            if r["k_spot_price"] is not None]
    print("k_electricity_price - k_spot_price: %.4f .. %.4f"
          % (min(diff), max(diff)))

    groups = {"October": [], "November, high tariff": [],
              "November, low tariff": []}
    for r in rows:
        if r["k_grid_costs"] is None:
            continue
        month = datetime.fromtimestamp(r["t"], TZ).month
        if month == 10:
            groups["October"].append(r["k_grid_costs"])
        elif month == 11 and r["nat"] is not None:
            key = ("November, high tariff" if r["nat"] > 0.5
                   else "November, low tariff")
            groups[key].append(r["k_grid_costs"])
    for name, vals in groups.items():
        if vals:
            print("k_grid_costs %-22s values %s, min %.4f, max %.4f"
                  % (name, sorted(set(vals)), min(vals), max(vals)))
        else:
            print("k_grid_costs %-22s no data" % name)


if __name__ == "__main__":
    main()
