# Battery steering: spot vs grid tariff (August 2026)

Preliminary check of whether the 1KOMMA5 optimiser loses money by
planning against raw Nord Pool spot while ignoring the grid transfer
fee (nataavgift) and the import/export price asymmetry.

Data source: VictoriaMetrics, `http://192.168.40.20:8428`. Scripts
that produced these numbers are in `scripts/`.

## Window and totals

Window: 2026-08-01 00:00 -> 2026-08-27 00:00 (26.0 days, 15-min
resolution). Battery charged and discharged the same 322.8 kWh over
the window, so the start and end SOC match and the totals below need
no boundary correction.

| Post | kWh |
|---|---|
| Grid import | 259.6 |
| Grid export | 345.7 |
| Battery charged | 322.8 |
| Battery discharged | 322.8 |
| EV charged (Zaptec) | 159.7 |

The house was a net exporter this month: 86 kWh more went out than
came in. That changes the question from July. When PV is in surplus
most of the day, the alternative to storing a kWh is exporting it, not
importing later.

Unlike the July window, both computed price sensors have full history
here, so the analysis reads them directly instead of applying the
documented constants. They agree with the model: import minus spot is
0.8313 on average (model 0.83125) and export minus spot is 0.1038
(model 0.104).

## The two behaviours

Behaviour 1, grid-charging. 68.3 kWh (21 % of all charging) came from
the grid at a mean import price of 1.77 kr/kWh. This is far more
expensive charging than July, and it is concentrated: 39.3 kWh of it
went in at spot above 1.2 kr, on 2026-08-17 through 2026-08-19 and
2026-08-24, during the mid-month price spike.

Behaviour 2, battery selling to the grid. 69.7 kWh (22 % of all
discharge) went straight out to the grid at a mean export pay of 1.36
kr/kWh, overwhelmingly in hours 07-09 (55.2 of 69.7 kWh). Three times
the July share, and the same morning-sale pattern.

## What it actually earned

The honest way to price the battery is marginally: charging costs
whatever the kWh was otherwise worth (grid-sourced at the import
price, PV-sourced at the export price it gives up), and discharging is
worth the import it avoids or the export it earns. Round-trip losses
fall out of the arithmetic, since discharge is smaller than charge.

| Flow | kWh | kr | kr/kWh |
|---|---|---|---|
| Charged from grid | 68.3 | -120.8 | 1.77 paid |
| Charged from PV | 254.5 | -142.1 | 0.56 export forgone |
| Discharged to house | 253.1 | +426.1 | 1.68 import avoided |
| Discharged to grid | 69.7 | +94.8 | 1.36 earned |

Net: +258 kr over 26 days, about 10 kr/day. The battery is making
money, and the expensive grid-charging during the spike is part of
why: on 2026-08-18 and 2026-08-19 it bought at 2.03-2.45 kr/kWh in
the afternoon and displaced evening import at 2.87-3.04 kr/kWh. That
is a 0.7-0.9 kr/kWh spread that survives the adder. Buying at 2.4 kr
looks alarming in isolation and is correct in context.

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

6.7 kr over 26 days, and 6.1 kr of it is the 17th.

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

68 % of the grid-charging (46.6 of 68.3 kWh) happened in hours 06-21,
which is the high-tariff window in the winter half-year (0.956 vs
0.381, i.e. +0.575 kr/kWh). A pure spot optimiser does not see that
premium. Repeated on winter working days, a comparable 26-day stretch
would carry about 27 kr of extra grid fee that the AI does not price
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
 0 |  0.60 |   +200  |   -575  |      0.1       |      0.8
 1 |  0.53 |   +407  |   -437  |      1.4       |      0.2
 2 |  0.51 |  +1014  |   -512  |      1.3       |      0.1
 3 |  0.51 |  +1311  |   -860  |      1.0       |      0.1
 4 |  0.53 |  +1065  |   -524  |      7.6       |      0.1
 5 |  0.58 |   +745  |   -335  |      6.3       |      0.1
 6 |  0.72 |   +196  |   -124  |      2.5       |      0.1
 7 |  0.84 |   -846  |   -621  |      0.1       |     13.6
 8 |  0.83 |  -2052  |  -1111  |      0.5       |     29.7
 9 |  0.71 |  -1935  |   -267  |      0.1       |     11.9
10 |  0.57 |  -1844  |   +387  |      0.2       |      1.6
11 |  0.50 |  -1470  |   +275  |      1.3       |      1.5
12 |  0.44 |  -1049  |  +1214  |      1.4       |      0.0
13 |  0.41 |   -148  |  +2111  |      3.3       |      0.0
14 |  0.40 |   +102  |  +2681  |     11.4       |      0.0
15 |  0.44 |   -277  |  +1696  |     10.6       |      0.0
16 |  0.51 |   -202  |   +977  |      9.5       |      1.6
17 |  0.69 |   -140  |   +190  |      5.4       |      0.3
18 |  0.94 |   +143  |   -162  |      0.0       |      0.4
19 |  1.12 |   +570  |   -611  |      0.0       |      3.0
20 |  1.14 |   +190  |   -943  |      0.2       |      2.4
21 |  1.03 |   +263  |   -876  |      0.1       |      0.6
22 |  0.86 |   +189  |   -949  |      0.8       |      0.8
23 |  0.70 |   +253  |   -616  |      3.2       |      0.5
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
  `sensor.total_pv_generation`,
  `sensor.zag064494_laddeffekt` (EV charger power; per-bucket EV energy
  must come from the power series, not the session energy counter,
  which reports in delayed batches).
- Battery size is taken from the data, not a datasheet: discharge runs
  give about 0.198 kWh delivered per SOC point and charge runs about
  0.237 kWh in, so roughly 19-20 kWh usable with a 17 % round trip.

## Recommendation

1. The summer verdict holds and strengthens: the optimiser is net
   positive, about 10 kr/day, and the adder-blindness costs single
   kronor per month while PV surplus covers the evening.
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
   grid-charging in hours 06-21 can be priced for real.
