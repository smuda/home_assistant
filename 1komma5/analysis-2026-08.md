# Battery steering: spot vs grid tariff (August 2026)

Full-month check of whether the 1KOMMA5 optimiser loses money by
planning against raw Nord Pool spot while ignoring the grid transfer
fee (nataavgift) and the import/export price asymmetry.

Data source: VictoriaMetrics, `http://192.168.40.20:8428`. Scripts
that produced these numbers are in `scripts/`.

## Window and totals

Window: 2026-08-01 00:00 -> 2026-09-01 00:00 (31.0 days, 15-min
resolution), the whole month. SOC ran 82 % to 77 %, so the battery
ends marginally emptier than it started and charge exceeds discharge
by 12 kWh.

| Post | kWh |
|---|---|
| Grid import | 456.1 |
| Grid export | 370.4 |
| Battery charged | 400.0 |
| Battery discharged | 387.9 |
| EV charged (Zaptec) | 249.9 |

The house was a net importer over the month, by 86 kWh. That is the
opposite of what the first three weeks suggested, and the last five
days are why: 2026-08-27 to 08-31 alone drew 196.8 kWh of import, of
which 90.2 kWh went into the car. PV was also falling away by then.
For most of the month the alternative to storing a kWh was exporting
it; by the end of the month it was importing later.

Both computed price sensors have history for most of the window, so
the analysis reads them directly instead of applying the documented
constants. They agree with the model: import minus spot is 0.8313 on
average (model 0.83125) and export minus spot is 0.1038 (model 0.104).

## The two behaviours

Behaviour 1, grid-charging. 120.5 kWh (30 % of all charging) came from
the grid at a mean import price of 1.59 kr/kWh. This is far more
expensive charging than July, and part of it is concentrated: 45.4 kWh
went in at spot above 1.2 kr, at a mean import price of 2.21, during
the mid-month price spike. The rest is cheap night charging, 25.9 kWh
of it in hours 04-05 alone.

Behaviour 2, battery selling to the grid. 84.7 kWh (22 % of all
discharge) went straight out to the grid at a mean export pay of 1.37
kr/kWh, overwhelmingly in hours 07-09 (69.2 of 84.7 kWh). Three times
the July share, and the same morning-sale pattern.

## What it actually earned

The honest way to price the battery is marginally: charging costs
whatever the kWh was otherwise worth (grid-sourced at the import
price, PV-sourced at the export price it gives up), and discharging is
worth the import it avoids or the export it earns. Round-trip losses
fall out of the arithmetic, since discharge is smaller than charge.

| Flow | kWh | kr | kr/kWh |
|---|---|---|---|
| Charged from grid | 120.5 | -191.4 | 1.59 paid |
| Charged from PV | 279.5 | -157.5 | 0.56 export forgone |
| Discharged to house | 303.2 | +512.4 | 1.69 import avoided |
| Discharged to grid | 84.7 | +115.9 | 1.37 earned |

Net: +280 kr over 31 days, about 9 kr/day, level with July's 9. The
battery is making money, and the expensive grid-charging during the
spike is part of why: on 2026-08-18 and 2026-08-19 it bought at
2.03-2.45 kr/kWh in the afternoon and displaced evening import at
2.87-3.04 kr/kWh. That is a 0.7-0.9 kr/kWh spread that survives the
adder. Buying at 2.4 kr looks alarming in isolation and is correct in
context.

## What the solar was worth

Priced at the moment each kWh was consumed rather than when it was
generated. That is the point of pairing panels with a battery: solar
made at midday, when a kWh is cheap, is spent in the evening when it
is dear.

| Where it went | kWh | kr | kr/kWh |
|---|---|---|---|
| Used as it was generated | 324.1 | 489.3 | 1.51 avoided |
| Stored, used later by the house | 205.8 | 322.9 | 1.57 avoided |
| Stored, later sold to the grid | 65.5 | 93.9 | 1.43 earned |
| Exported as it was generated | 285.8 | 168.4 | 0.59 earned |
| Total | 881.2 | 1074 | |

1074 kr over 31.0 days, about 35 kr/day, against July's 33.

The battery is what lifts the middle rows. Solar that went into it had
no house load to serve at the time, so its alternative was export at
0.59 kr/kWh. It came back out at 1.57. That spread, 0.98 kr/kWh over
205.8 kWh, is about 202 kr of the 1074 -- and it is the same value the
battery P&L above counts as the battery's, seen from the other side.
Do not add the two together.

Note how much better the stored kWh did this month than in July: 1.57
against 1.53 on the way out is barely changed, but the export
alternative rose from 0.45 to 0.59 while twice as much solar went
through the battery. The mid-month price spike is why the evenings
were worth so much.

Generation is metered on the DC side while prices apply on the AC
side, so the totals are scaled by the window's own DC-to-AC ratio,
0.920 here (889.4 kWh AC from 966.6 kWh DC). A further 8.2 kWh of
solar was still sitting in the battery when the window closed and is
not valued.

## 2026-08-17: an EV charge, not a pricing error

The one day in the window that looks bad has a load explanation, not a
price one.

`sensor.zag064494_laddeffekt` shows a single EV session on the 17th:
16:30 to 22:45, 10.6 kW flat for most of it, 44.3 kWh. That session is
the whole of the evening import.

The day in sequence:

- 08:15-09:15, the battery exports 7.5 kW to the grid, SOC 76 % ->
  38 %, earning spot 1.33 plus 0.104. The house was already exporting
  PV, so this was on top of a surplus.
- 09:30-13:45, the battery sits at 37 % while PV exports.
- 13:45-16:15, it charges 7.9 kWh from PV back to 79 %.
- 16:30, the car plugs in at 10.6 kW. The battery empties into it,
  15.7 kWh, and reaches 3 % by 18:30.
- 18:30-23:45, the house imports 39.4 kWh at a mean 2.25 kr/kWh, and
  from 22:15 the optimiser grid-charges the battery again at
  2.06-2.31 kr/kWh.

The morning sale did not cost the battery anything by itself: SOC was
76 % at 08:00 and back to 79 % by 16:15, so PV fully replaced what was
sold. On any normal evening that is free money -- evening import in
this window is otherwise about 0.1 kWh a day.

Nor was the session forecastable. August charging starts at 16:30,
13:15, 02:15, 11:15, 18:15, 02:15, 16:00 and 02:15. There is a
recurring 02:15 night charge; the 16:30 plug-in has no precedent in
the data to learn from.

The midday idle is not a miss either. PV charging costs the export it
forgoes, and that was about 1.03 kr/kWh at 14:00 against 1.40 at
10:00. Waiting for the cheapest PV was the right call, given a normal
load forecast.

What the sale did cost is bounded by battery headroom. At 16:30 the
battery was at 82 % against a 99 % ceiling, so at most 17 SOC points
-- about 3.4 kWh at the measured 0.198 kWh per point -- of the 7.5 kWh
sold could have been retained. Those 3.4 kWh would have displaced
evening import at 2.25 kr/kWh, worth 7.6 kr, against 4.9 kr of sale
revenue given up. That is a net cost of about 3 kr.

Against a 44.3 kWh charge and a battery that delivers roughly 19 kWh
from full, some 25 kWh had to come from the grid whatever the
optimiser did. Perfect price foresight would have saved 3 kr of an
88 kr evening.

## What adder-blindness costs across the window

Measured as energy the battery sold before 12:00 that the house had to
re-import after 16:00 the same day, valued at the difference between
the import price paid and the export pay received:

8.9 kr over 31 days, and 6.1 kr of it is the 17th. The month's other
notable days are 08-27 at 1.2 kr and 08-31 at 1.1 kr, both the same
shape as the 17th and both far smaller.

Treat that as an upper bound. It ignores headroom -- it credits the
counterfactual with keeping every sold kWh, when the battery could
only have held part of it. The headroom-capped figure for the 17th is
about 3 kr, roughly half.

On every other day with morning selling the loss is a rounding error,
because the battery refilled from PV surplus and the evening import
was essentially zero. Selling a kWh that PV was about to replace for
free costs nothing.

Where the adder does matter is the direction of the error. The sale
earned spot plus 0.104 and the buy-back cost spot plus 0.83, so a
round trip that is only mildly bad on spot alone (1.33 out, 1.49 in)
becomes a real loss. That asymmetry is precisely what a spot-only plan
cannot see. On the 17th it is the second-order term; the EV is the
first.

## The winter risk

61 % of the grid-charging (73.5 of 120.5 kWh) happened in hours 06-21,
which is the high-tariff window in the winter half-year (0.956 vs
0.381, i.e. +0.575 kr/kWh). A pure spot optimiser does not see that
premium. Repeated on winter working days, a comparable 26-day stretch
would carry about 42 kr of extra grid fee that the AI does not price
in.

This is still the open question. The time-of-use grid fee only varies
Nov-Mar, working days 06-22; April-October it is flat at 0.381, so
August data can neither confirm nor refute it. What August does add is
that the optimiser will happily grid-charge at 2.4 kr/kWh when the
spread justifies it. In winter the same decision carries an extra
0.575 kr/kWh that never enters its arithmetic, and it would take a
spread that much wider to stay profitable.

## Hour-of-day profile (local time)

Positive grid is import, negative is export. Positive battery is
charging, negative is discharging.

```
hr | spot  | grid W  | batt W  | grid->batt kWh | batt->grid kWh
 0 |  0.58 |   +537  |   -412  |      3.6       |      0.8
 1 |  0.52 |   +647  |   -366  |      1.4       |      0.2
 2 |  0.50 |  +1533  |   -430  |      1.3       |      0.1
 3 |  0.51 |  +1590  |   -656  |      3.5       |      0.1
 4 |  0.52 |  +1380  |   -307  |     12.5       |      0.2
 5 |  0.57 |  +1316  |    -97  |     13.4       |      0.1
 6 |  0.72 |   +607  |   -124  |      3.4       |      0.1
 7 |  0.85 |   -676  |   -638  |      0.1       |     15.7
 8 |  0.84 |  -1801  |  -1118  |      0.5       |     34.7
 9 |  0.72 |  -1748  |   -315  |      3.1       |     18.8
10 |  0.56 |  -1571  |   +413  |      0.2       |      1.8
11 |  0.49 |   -872  |   +416  |      5.4       |      1.5
12 |  0.44 |   -585  |  +1262  |      5.4       |      0.0
13 |  0.40 |   +181  |  +1907  |      5.6       |      0.0
14 |  0.40 |   +226  |  +2388  |     13.4       |      0.0
15 |  0.43 |    -37  |  +1574  |     11.6       |      0.0
16 |  0.51 |    -89  |   +943  |     11.5       |      1.6
17 |  0.70 |     +5  |   +188  |      7.8       |      0.3
18 |  0.96 |   +210  |   -268  |      2.3       |      0.7
19 |  1.13 |   +609  |   -681  |      3.0       |      3.0
20 |  1.13 |   +195  |  -1053  |      0.2       |      2.4
21 |  1.01 |   +245  |   -986  |      0.1       |      1.0
22 |  0.83 |   +267  |   -917  |      0.8       |      0.8
23 |  0.68 |   +591  |   -327  |     10.4       |      0.5
```

## Method notes and caveats

- Grid-to-battery per bucket is estimated as
  min(charge power, import power); battery-to-grid as
  min(discharge power, export power); the remainder of charging is
  taken as PV-sourced and the remainder of discharge as serving the
  house. By energy conservation at the point of common coupling these
  overlaps are exact when the P1 grid meter and the inverter battery
  sensor are consistent and synchronous. At 15-min averages, brief
  opposite-sign excursions inside a bucket can bias the figure
  slightly. Treat totals as good estimates, not to the last kWh.
- The P&L is marginal, not a bill. It prices each kWh at what it was
  otherwise worth at that moment. It says nothing about whether the
  battery pays for its own capital cost.
- Do not read a single day's net in isolation. A day that ends with a
  fuller battery than it started shows a loss it will book the next
  morning; 2026-08-19 is such a day.
- Entities used: `sensor.nord_pool_se3_aktuellt_pris` (spot),
  `sensor.nordpool_se3_inkl_skatt_o_nat` (import price),
  `sensor.elexport_ersattning` (export pay),
  `sensor.battery_charging_power_signed` (+charge/-discharge),
  `sensor.p1_meter_effekt` (+import/-export),
  `sensor.battery_level` (SOC), `sensor.export_power`,
  `sensor.total_pv_generation`, `sensor.load_power`,
  `sensor.zag064494_laddeffekt` (EV charger power; per-bucket EV energy
  must come from the power series, not the session energy counter,
  which reports in delayed batches).
- The solar split is economic, not physical. A kWh that charged the
  battery while the house was importing did not reduce the bill, so it
  counts as grid-sourced whatever the DC wiring did. Sungrow's own
  `total_battery_charge_from_pv` answers the physical question instead
  and gives a different, larger PV share; it is not the right basis for
  costing.
- Solar into the battery is traced back out with a mixing model: each
  discharge draws the battery's current mix of PV- and grid-sourced
  energy. Conversion losses are not charged against stored solar, since
  charge and discharge are measured at the same plane.
- Counter lag makes some buckets show more solar going to store and
  export than that bucket generated, so direct use goes slightly
  negative there. It nets out across the window.
- No microproduction tax reduction is applied; it has been withdrawn.
  Export earns spot + 0.104 only.
- The counterfactual holds house load and battery behaviour fixed. EV
  charging reacts to Nord Pool prices only and knows nothing about the
  panels or the battery, so it is unaffected by their presence.
- The Nord Pool integration dropped out over the last days of the
  month: spot was missing for 20, 24, 38 and 95 of the 96 buckets on
  08-28, 08-29, 08-30 and 08-31. Those 178 buckets are backfilled from
  elprisetjustnu.se, the same SE3 day-ahead series at the same 15-min
  resolution. Calibrated against 2026-08-27, which has full local
  coverage: the Home Assistant sensor lags the published series by
  exactly one bucket, and at that offset the two agree to a mean
  absolute difference of 0.014 kr/kWh. The import and export prices for
  those buckets come from the documented constants rather than their
  sensors, which were missing too.
- The metrics history begins mid-window on 2026-07-15 with the
  generation counter already at 261.1 kWh, so the install date cannot
  be recovered from it. These are window figures, not lifetime ones.
- Battery size is taken from the data, not a datasheet: discharge runs
  give about 0.198 kWh delivered per SOC point and charge runs about
  0.237 kWh in, so roughly 19-20 kWh usable with a 17 % round trip.

## Recommendation

1. The summer verdict holds: the optimiser is net positive, about
   9 kr/day, and adder-blindness costs 9 kr across the whole month
   while PV surplus covers the evening. The solar itself is worth four
   times what the battery adds, 35 kr/day against 9.
2. Feed 1KOMMA5 the full import price
   (`sensor.nordpool_se3_inkl_skatt_o_nat`) and the export pay
   (`sensor.elexport_ersattning`) instead of raw spot, if the
   integration allows it. That is the structural fix, and it is the
   one that matters in winter.
3. The 2026-08-17 shape is a load-forecast problem, not a price one,
   and it cost about 3 kr. If it recurs often enough to matter, the fix
   is telling the optimiser about a planned EV charge, not changing its
   price inputs. In winter the same day would cost more, since PV
   cannot refill what was sold.
4. Re-run in Nov-Dec, when the high-tariff window is live and the
   grid-charging in hours 06-21 can be priced for real. The last five
   days of August already show the turn: PV falling, import rising,
   and the house a net importer for the month despite three weeks of
   surplus.
5. Watch the Nord Pool integration. It went missing for the last days
   of the month and the gap had to be backfilled from a public source;
   while it is down the repo's own price templates have nothing to
   work from.
