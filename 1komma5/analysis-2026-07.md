# Battery steering: spot vs grid tariff (July 2026)

Data-driven check of whether the 1KOMMA5 optimiser loses money by
planning against raw Nord Pool spot while ignoring the grid transfer
fee (nataavgift) and the import/export price asymmetry.

Data source: VictoriaMetrics, `http://192.168.40.20:8428`. Scripts
that produced these numbers are in `scripts/`.

## The concern

Observed behaviour that prompted this: the battery seemed to sell to
the grid in the morning when the price was high, and to grid-charge in
the afternoon when the price was low. The worry was that the optimiser
does not account for the time-of-use grid transfer fee (rörligt
elnätspris) in its calculations.

## Window and totals

Window: 2026-07-15 15:15 -> 2026-08-01 00:00 (16.4 days, 15-min
resolution). Sign conventions were verified against SOC change and
export power before analysis.

| Post | kWh |
|---|---|
| Grid import | 316.5 |
| Grid export | 171.9 |
| Battery charged | 253.9 |
| Battery discharged | 226.7 |

Price model, from the repo's own template sensors:

- Import cost = spot + 0.45 (energy tax) + grid fee. Grid fee is
  0.381 low, 0.956 high. Summer is always low, so import is about
  spot + 0.83 kr/kWh.
- Export pay = spot + 0.104 kr/kWh.
- The gap between keeping a kWh (avoids spot + 0.83) and selling it
  (earns spot + 0.104) is about 0.72 kr/kWh. A spot-only optimiser
  does not see that gap.

## The two behaviours, confirmed

Both behaviours are real and visible in the data.

Behaviour 1, grid-charging. 107.3 kWh (42 % of all charging) came
from the grid, mean spot 0.199 kr. It happens in two clusters: night
00-06 and afternoon 13-18. Only 9.6 kWh was charged at spot above
0.5, with a tail of about 5.4 kWh near spot 1.0 (max 1.06).

Behaviour 2, battery selling to the grid. 16.3 kWh (7 % of all
discharge) went straight out to the grid, mean spot 0.877 kr,
concentrated in the early morning 02-09 (about 14 kWh). This is
exactly the observed pattern.

The two substantial episodes:

- 2026-07-17 06:00-09:00, 3.9 kWh sold out, SOC 43 % -> 19 %, spot
  1.03-1.09 kr.
- 2026-07-18 00:00-07:00, 6.4 kWh sold out, SOC 83 % -> 19 %, spot
  0.72-0.92 kr.

Both fall in high-spot hours, which is what a spot optimiser is
supposed to sell into.

Costed properly, that is cheaper than it looks. Valuing the sold kWh
at the import they would have avoided in the same hour overstates the
loss, because the house was usually exporting at the time -- there was
no import in that hour to avoid. The honest measure is energy sold
before noon that the house had to re-import after 16:00 the same day:

| Day | sold | at | re-imported | at | loss |
|---|---|---|---|---|---|
| 2026-07-17 | 3.9 | 1.17 | 3.1 | 1.98 | 2.5 kr |
| 2026-07-18 | 6.4 | 0.91 | 13.7 | 1.11 | 1.3 kr |
| 2026-07-24 | 1.1 | 1.13 | 1.2 | 1.78 | 0.7 kr |
| 2026-07-29 | 1.8 | 0.73 | 2.5 | 0.97 | 0.4 kr |

Total 5.0 kr over 16 days, well under a krona a day. Neither of the
two large episodes involved EV charging: the first charging session in
this window starts 2026-07-19 14:15, two days after the 07-17 sale.
These sales are price decisions, not a response to house load.

## What the battery earned

Pricing each kWh marginally -- charging costs whatever it was
otherwise worth, discharging is worth the import it avoids or the
export it earns -- gives the whole picture. Round-trip losses fall out
of the arithmetic, since discharge is smaller than charge.

| Flow | kWh | kr | kr/kWh |
|---|---|---|---|
| Charged from grid | 107.3 | -119.1 | 1.11 paid |
| Charged from PV | 146.6 | -67.1 | 0.46 export forgone |
| Discharged to house | 210.5 | +317.1 | 1.51 import avoided |
| Discharged to grid | 16.3 | +15.9 | 0.98 earned |

Net: +147 kr over 16.4 days, about 9 kr/day. The optimiser is making
money; the 5 kr of adder-blindness above is noise against it.

## Why the summer data does not settle the concern

Grid-charging at low spot and discharging into the house in the
evening is textbook spot arbitrage. Because 93 % of discharge serves
own load rather than export, the tax + grid adder cancels out: you pay
the adder when charging, but you avoid it on the evening import you
would otherwise have made. Net benefit is the plain spot spread,
roughly 0.5-0.6 kr/kWh after round-trip losses. In the summer data the
grid-charging works in your favour, not against it.

The key point: the time-of-use grid fee only varies Nov-Mar, working
days 06-22. April-October it is flat at 0.381. There is right now no
variable grid price to account for, so the behaviour can neither
confirm nor refute the hypothesis. Summer is the wrong measurement
period for that specific question.

## The real risk: winter

This is where the concern gets sharp. 60 % of the grid-charging (64.0
of 107.3 kWh) happened in hours 06-21, which is exactly the
high-tariff window in the winter half-year (0.956 vs 0.381, i.e.
+0.575 kr/kWh). A pure spot optimiser does not see that premium. If
the same "charge from the grid mid-day" pattern repeats on winter
working days, those charges would carry about 37 kr extra grid fee
over a comparable 16-day stretch that the AI does not price in, and
unlike summer there is no cheap PV as an alternative then.

One cannot extrapolate the summer hours straight into winter, since
the spot and PV profile is entirely different. The conclusion is that
the feared effect is real and the mechanism exists, but it only
materialises in winter data.

## Hour-of-day profile (local time)

Positive grid is import, negative is export. Positive battery is
charging, negative is discharging.

```
hr | spot  | grid W  | batt W  | grid->batt kWh | batt->grid kWh
 0 |  0.60 |  +1363  |  -1002  |      2.6       |      0.2
 1 |  0.51 |  +1579  |   -169  |      9.6       |      0.1
 2 |  0.46 |  +1434  |   -514  |      7.2       |      1.5
 3 |  0.45 |  +1215  |   -516  |      4.6       |      0.7
 4 |  0.42 |  +1213  |    +56  |      7.9       |      2.0
 5 |  0.44 |  +1199  |   +183  |     10.8       |      1.4
 6 |  0.53 |   +131  |   -292  |      0.4       |      0.8
 7 |  0.60 |   -445  |   -110  |      0.0       |      3.6
 8 |  0.59 |   -703  |    +79  |      0.1       |      3.5
 9 |  0.45 |    -43  |   +755  |      0.1       |      0.8
10 |  0.31 |    +83  |   +704  |      0.4       |      0.0
11 |  0.23 |   -364  |  +1875  |      3.6       |      0.0
12 |  0.19 |  -1022  |   +603  |      0.4       |      0.0
13 |  0.17 |   -582  |  +1167  |      4.2       |      0.0
14 |  0.16 |   +360  |  +1366  |     16.4       |      0.0
15 |  0.18 |   +280  |  +1083  |     12.6       |      0.0
16 |  0.22 |   +582  |  +1145  |     13.7       |      0.0
17 |  0.33 |   +828  |   -246  |      3.6       |      0.4
18 |  0.58 |   +568  |    +54  |      8.1       |      0.0
19 |  0.81 |   +188  |   -381  |      0.4       |      0.1
20 |  0.88 |   +145  |   -786  |      0.0       |      0.1
21 |  0.88 |    +66  |  -1263  |      0.0       |      0.8
22 |  0.80 |   +246  |   -863  |      0.0       |      0.1
23 |  0.70 |   +488  |  -1056  |      0.5       |      0.1
```

## Method notes and caveats

- Grid-to-battery per bucket is estimated as
  min(charge power, import power); battery-to-grid as
  min(discharge power, export power). By energy conservation at the
  point of common coupling these overlaps are exact when the P1 grid
  meter and the inverter battery sensor are consistent and
  synchronous. At 15-min averages, brief opposite-sign excursions
  inside a bucket can bias the figure slightly. Treat totals as good
  estimates, not to the last kWh.
- The export-compensation sensor `sensor.elexport_ersattning` has no
  history for most of this window, so export pay was computed directly
  as spot + 0.104 rather than read from the sensor. The import price
  sensor existed but its formula may also have changed during the
  window, so the analysis uses raw spot plus the documented adder
  constants throughout and does not depend on the historical values of
  the computed sensors.
- Entities used: `sensor.nord_pool_se3_aktuellt_pris` (spot),
  `sensor.battery_charging_power_signed` (+charge/-discharge),
  `sensor.p1_meter_effekt` (+import/-export),
  `sensor.battery_level` (SOC), `sensor.export_power`,
  `sensor.total_pv_generation`,
  `sensor.zag064494_laddeffekt` (EV charger power; per-bucket EV energy
  must come from the power series, not the session energy counter,
  which reports in delayed batches).
- The P&L is marginal, not a bill. It prices each kWh at what it was
  otherwise worth at that moment, and says nothing about whether the
  battery pays for its own capital cost.

## Recommendation

1. Treat the concern as open until winter data exists. Re-run this
   analysis in Nov-Dec; then the high-tariff grid-charging can be
   measured in kronor.
2. To act now: check whether 1KOMMA5 can be fed the full import price
   (`sensor.nordpool_se3_inkl_skatt_o_nat`) and the export pay instead
   of raw spot. That is the only structural fix for the
   adder-blindness.
3. The tail of grid-charging at spot near 1 kr (5.4 kWh) is worth a
   quick look; it may be a forecast miss in the optimiser.
4. House load, not price, is the other variable worth watching. See
   `analysis-2026-08.md` for a day where an unforecastable EV charge,
   not the price model, drove the outcome.
