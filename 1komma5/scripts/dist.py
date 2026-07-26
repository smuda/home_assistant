import csv, statistics
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import defaultdict
TZ = ZoneInfo("Europe/Stockholm"); H = 0.25

rows=[]
with open("data.csv") as f:
    for r in csv.DictReader(f):
        d={"t":int(r["t"])}
        for k in ["spot","imp_px","batt","grid"]:
            d[k]=float(r[k]) if r[k] not in ("","None") else None
        rows.append(d)
R=[r for r in rows if r["batt"] is not None and r["grid"] is not None and r["spot"] is not None]

# grid-charge energy by spot bucket and by hour; sold-to-grid by hour
spot_buckets=defaultdict(float)
gch_by_hour=defaultdict(float); sold_by_hour=defaultdict(float)
gch_high_spot=0.0  # grid-charged while spot>0.5
maxspot_charge=0.0
for r in R:
    batt=r["batt"]; grid=r["grid"]; spot=r["spot"]
    ch=max(batt,0); imp=max(grid,0); dis=max(-batt,0); exp=max(-grid,0)
    g=min(ch,imp)/1000*H   # grid->batt kWh
    s=min(dis,exp)/1000*H   # batt->grid kWh
    h=datetime.fromtimestamp(r["t"],TZ).hour
    if g>0:
        gch_by_hour[h]+=g
        b=round(spot*2)/2  # 0.5 kr buckets
        spot_buckets[b]+=g
        if spot>0.5: gch_high_spot+=g
        maxspot_charge=max(maxspot_charge, spot)
    if s>0: sold_by_hour[h]+=s

print("=== grid-charge energy by spot level (kr/kWh bucket) ===")
for b in sorted(spot_buckets):
    print("  spot ~%.1f : %5.1f kWh" % (b, spot_buckets[b]))
print("  grid-charged while spot>0.5 kr: %.1f kWh" % gch_high_spot)
print("  highest spot at which it grid-charged: %.3f kr" % maxspot_charge)

print("\n=== grid-charge (kWh) by hour  |  battery-sold-to-grid (kWh) by hour ===")
print("hr | grid->batt | batt->grid")
for h in range(24):
    print("%2d |   %5.1f    |   %5.1f" % (h, gch_by_hour.get(h,0), sold_by_hour.get(h,0)))

# winter what-if: hours 6-21 = high nat tariff on workdays Nov-Mar
gch_winter_window=sum(v for h,v in gch_by_hour.items() if 6<=h<22)
gch_total=sum(gch_by_hour.values())
print("\n=== WINTER WHAT-IF ===")
print("grid-charge in hours 06-21 (would be HIGH nat in winter): %.1f of %.1f kWh (%.0f%%)"
      % (gch_winter_window, gch_total, 100*gch_winter_window/max(gch_total,1e-9)))
print("extra nat cost IF this happened on a winter workday: %.1f kWh x 0.575 kr = %.0f kr"
      % (gch_winter_window, gch_winter_window*0.575))
