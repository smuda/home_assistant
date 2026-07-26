import csv, statistics
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Stockholm")
H = 0.25  # hours per bucket (15 min)

rows = []
with open("data.csv") as f:
    for r in csv.DictReader(f):
        d = {"t": int(r["t"])}
        for k in ["spot", "imp_px", "batt", "grid", "soc", "expw", "pvgen"]:
            d[k] = float(r[k]) if r[k] not in ("", "None") else None
        rows.append(d)

# keep rows where we have battery + grid + spot
R = [r for r in rows if r["batt"] is not None and r["grid"] is not None and r["spot"] is not None]
print("usable rows: %d (%.1f days)" % (len(R), len(R)*H/24))
t0 = datetime.fromtimestamp(R[0]["t"], TZ)
t1 = datetime.fromtimestamp(R[-1]["t"], TZ)
print("window: %s -> %s\n" % (t0.strftime("%Y-%m-%d %H:%M"), t1.strftime("%Y-%m-%d %H:%M")))

def expprice(spot):   # export compensation = spot + 0.104
    return spot + 0.104

# ---- 1. Battery -> grid (discharge while exporting) ----
sold_kwh = 0.0; sold_val = 0.0; sold_spotw = 0.0
# ---- 2. Grid -> battery (charge while importing) ----
gch_kwh = 0.0; gch_cost = 0.0; gch_spotw = 0.0
# reference totals
imp_kwh = 0.0; exp_kwh = 0.0
batt_ch_kwh = 0.0; batt_dis_kwh = 0.0

sold_events = []; gch_events = []

for r in R:
    batt = r["batt"]; grid = r["grid"]; spot = r["spot"]
    imp = r["imp_px"] if r["imp_px"] is not None else spot + 0.83
    imp_w = max(grid, 0.0); exp_w = max(-grid, 0.0)
    ch_w = max(batt, 0.0); dis_w = max(-batt, 0.0)
    imp_kwh += imp_w/1000*H; exp_kwh += exp_w/1000*H
    batt_ch_kwh += ch_w/1000*H; batt_dis_kwh += dis_w/1000*H

    # battery energy reaching the grid
    s = min(dis_w, exp_w)/1000*H
    if s > 0:
        sold_kwh += s; sold_val += s*expprice(spot); sold_spotw += s*spot
        if min(dis_w, exp_w) > 300:
            sold_events.append((r["t"], min(dis_w, exp_w), spot, r["expw"]))
    # grid energy reaching the battery
    g = min(ch_w, imp_w)/1000*H
    if g > 0:
        gch_kwh += g; gch_cost += g*imp; gch_spotw += g*spot
        if min(ch_w, imp_w) > 300:
            gch_events.append((r["t"], min(ch_w, imp_w), spot, imp))

print("=== TOTALS over window ===")
print("grid import:        %7.1f kWh" % imp_kwh)
print("grid export:        %7.1f kWh" % exp_kwh)
print("battery charged:    %7.1f kWh" % batt_ch_kwh)
print("battery discharged: %7.1f kWh" % batt_dis_kwh)

print("\n=== PATTERN 1: battery discharged straight to grid ===")
print("energy sold from battery: %.1f kWh (%.0f%% of all discharge)" %
      (sold_kwh, 100*sold_kwh/max(batt_dis_kwh,1e-9)))
if sold_kwh>0:
    print("  avg spot when selling:   %.3f kr/kWh" % (sold_spotw/sold_kwh))
    print("  paid as export comp:     %.1f kr  (spot+0.104)" % sold_val)

print("\n=== PATTERN 2: battery charged from the grid ===")
print("energy grid-charged:      %.1f kWh (%.0f%% of all charge)" %
      (gch_kwh, 100*gch_kwh/max(batt_ch_kwh,1e-9)))
if gch_kwh>0:
    print("  avg spot when grid-chg:  %.3f kr/kWh" % (gch_spotw/gch_kwh))
    print("  full import cost paid:   %.1f kr  (spot+skatt+nat)" % gch_cost)

# ---- hour-of-day profile ----
print("\n=== HOUR-OF-DAY PROFILE (local time) ===")
print("hr | spot  | grid kW (+imp/-exp) | batt kW (+chg/-dis) | n")
from collections import defaultdict
byh = defaultdict(lambda: {"spot":[], "grid":[], "batt":[]})
for r in R:
    h = datetime.fromtimestamp(r["t"], TZ).hour
    byh[h]["spot"].append(r["spot"])
    byh[h]["grid"].append(r["grid"])
    byh[h]["batt"].append(r["batt"])
for h in range(24):
    b = byh[h]
    if not b["spot"]: continue
    print("%2d | %5.2f | %+6.0f              | %+6.0f              | %d" % (
        h, statistics.mean(b["spot"]),
        statistics.mean(b["grid"]), statistics.mean(b["batt"]), len(b["spot"])))
