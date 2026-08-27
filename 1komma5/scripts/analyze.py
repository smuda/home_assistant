import csv, statistics
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Stockholm")
H = 0.25  # hours per bucket (15 min)

rows = []
with open("data.csv") as f:
    for r in csv.DictReader(f):
        d = {"t": int(r["t"])}
        for k in ["spot", "imp_px", "exp_px", "batt", "grid", "soc", "expw", "pvgen", "ev"]:
            d[k] = float(r[k]) if r[k] not in ("", "None") else None
        rows.append(d)

# keep rows where we have battery + grid + spot
R = [r for r in rows if r["batt"] is not None and r["grid"] is not None and r["spot"] is not None]
print("usable rows: %d (%.1f days)" % (len(R), len(R)*H/24))
t0 = datetime.fromtimestamp(R[0]["t"], TZ)
t1 = datetime.fromtimestamp(R[-1]["t"], TZ)
print("window: %s -> %s\n" % (t0.strftime("%Y-%m-%d %H:%M"), t1.strftime("%Y-%m-%d %H:%M")))

def expprice(r):      # export compensation, sensor if present else spot + 0.104
    return r["exp_px"] if r["exp_px"] is not None else r["spot"] + 0.104

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
        sold_kwh += s; sold_val += s*expprice(r); sold_spotw += s*spot
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

# ---- battery P&L, marginal accounting ----
# Charging costs what the kWh would otherwise have been worth: grid-sourced
# at the import price, PV-sourced at the export price it forgoes. Discharge
# is worth the import it avoids, or the export it earns. Round-trip losses
# fall out of the arithmetic.
pl = {"gch":0.0, "gcost":0.0, "pvch":0.0, "pvcost":0.0,
      "house":0.0, "hval":0.0, "sold2":0.0, "srev":0.0}
for r in R:
    spot = r["spot"]
    imp = r["imp_px"] if r["imp_px"] is not None else spot + 0.83125
    exp = expprice(r)
    ch = max(r["batt"], 0.0); dis = max(-r["batt"], 0.0)
    imp_w = max(r["grid"], 0.0); exp_w = max(-r["grid"], 0.0)
    g = min(ch, imp_w)/1000*H;  pv = (ch - min(ch, imp_w))/1000*H
    s = min(dis, exp_w)/1000*H; ho = (dis - min(dis, exp_w))/1000*H
    pl["gch"] += g;     pl["gcost"] += g*imp
    pl["pvch"] += pv;   pl["pvcost"] += pv*exp
    pl["house"] += ho;  pl["hval"] += ho*imp
    pl["sold2"] += s;   pl["srev"] += s*exp

def rate(v, q):
    return v/q if q > 1e-9 else 0.0

print("\n=== BATTERY P&L over window ===")
print("charged from grid:   %6.1f kWh, cost %7.1f kr (%.2f/kWh)"
      % (pl["gch"], pl["gcost"], rate(pl["gcost"], pl["gch"])))
print("charged from PV:     %6.1f kWh, export forgone %.1f kr (%.2f/kWh)"
      % (pl["pvch"], pl["pvcost"], rate(pl["pvcost"], pl["pvch"])))
print("discharged to house: %6.1f kWh, import avoided %.1f kr (%.2f/kWh)"
      % (pl["house"], pl["hval"], rate(pl["hval"], pl["house"])))
print("discharged to grid:  %6.1f kWh, revenue %7.1f kr (%.2f/kWh)"
      % (pl["sold2"], pl["srev"], rate(pl["srev"], pl["sold2"])))
net = pl["hval"] + pl["srev"] - pl["gcost"] - pl["pvcost"]
print("NET: %+.1f kr over %.1f days (%+.1f kr/day)"
      % (net, len(R)*H/24, net/(len(R)*H/24)))

# ---- sold in the morning, bought back the same evening ----
# The direct cost of adder-blindness: battery energy exported before noon
# that the house had to re-import after 16:00 the same day. Upper bound --
# it ignores that the battery may not have had room to keep all of it.
byday = defaultdict(lambda: {"sold": 0.0, "srev": 0.0, "imp": 0.0, "icost": 0.0})
for r in R:
    d = datetime.fromtimestamp(r["t"], TZ)
    imp = r["imp_px"] if r["imp_px"] is not None else r["spot"] + 0.83125
    D = byday[d.date()]
    if d.hour < 12:
        s = min(max(-r["batt"], 0), max(-r["grid"], 0))/1000*H
        D["sold"] += s; D["srev"] += s*expprice(r)
    if d.hour >= 16:
        i = max(r["grid"], 0)/1000*H
        D["imp"] += i; D["icost"] += i*imp

print("\n=== SOLD BEFORE NOON, RE-IMPORTED AFTER 16:00 ===")
print("day         sold  @kr   re-imported  @kr    overlap  loss kr")
rt = 0.0
for k in sorted(byday):
    D = byday[k]
    if D["sold"] < 0.5: continue
    pe = D["srev"]/D["sold"]
    pi = D["icost"]/D["imp"] if D["imp"] > 1e-9 else 0.0
    ov = min(D["sold"], D["imp"])
    l = ov*(pi - pe) if pi > pe else 0.0
    rt += l
    print("%s %5.1f  %5.2f  %10.1f  %5.2f  %6.1f  %6.1f" % (k, D["sold"], pe, D["imp"], pi, ov, l))
print("total: %.1f kr" % rt)

# ---- EV charging sessions ----
E = [r for r in R if r["ev"] is not None]
if E:
    ON, GAP = 500.0, 4          # W, and buckets of idle that end a session
    sess = []; cur = None; idle = 0
    for i, r in enumerate(E):
        if r["ev"] > ON:
            if cur is None: cur = [i, i]
            cur[1] = i; idle = 0
        elif cur is not None:
            idle += 1
            if idle > GAP: sess.append(tuple(cur)); cur = None
    if cur: sess.append(tuple(cur))
    print("\n=== EV CHARGING SESSIONS ===")
    print("start             end      kWh   peak kW")
    for a, b in sess:
        kwh = sum(E[i]["ev"] for i in range(a, b + 1))/1000*H
        if kwh < 1.0: continue
        print("%s  %s  %5.1f  %6.1f" % (
            datetime.fromtimestamp(E[a]["t"], TZ).strftime("%Y-%m-%d %H:%M"),
            datetime.fromtimestamp(E[b]["t"], TZ).strftime("%H:%M"),
            kwh, max(E[i]["ev"] for i in range(a, b + 1))/1000))

# ---- hour-of-day profile ----
print("\n=== HOUR-OF-DAY PROFILE (local time) ===")
print("hr | spot  | grid kW (+imp/-exp) | batt kW (+chg/-dis) | n")
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
