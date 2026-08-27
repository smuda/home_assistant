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

## Where the adder-blindness does bite

The morning selling is the behaviour to watch, and it can be costed
exactly: energy the battery sold before 12:00 that the house then had
to re-import after 16:00 the same day, valued at the difference
between the import price paid and the export pay received.

Over the whole window that comes to 6.7 kr, and 6.1 kr of it is one
day.

2026-08-17 is the case in full:

- 08:15-09:15, the battery dumps 7.5 kW to the grid, SOC 76 % -> 38 %,
  earning spot 1.33 plus 0.104. The house was already exporting PV at
  the time, so this was on top of a surplus.
- 09:30-14:00, the battery sits at 37 % for four and a half hours
  while 3-4 kW of PV goes out to the grid.
- 14:00-16:15, it charges from PV back to 79 %.
- 16:30-18:15, it discharges 15.8 kWh into a heavy house load and
  empties to 11 %.
- 18:30-23:45, the house imports 8-14 kW at 2.08-2.38 kr/kWh, and at
  22:15 the optimiser starts grid-charging the battery again at 2.06-
  2.31 kr/kWh.

So it sold at 1.43 and bought back at 2.2-2.3 about ten hours later.
On raw spot alone that round trip is only mildly bad (1.33 out, 1.49
in). The 0.73 kr/kWh asymmetry between import and export is what turns
it into a real loss, and that asymmetry is exactly what a spot-only
plan cannot see.

The idle midday is the larger miss on that day, though it is a
forecast question rather than a pricing one: the battery had room and
the evening needed 40 kWh.

On every other day with morning selling the loss is a rounding error,
because the battery refilled from PV surplus and the evening import
was essentially zero. Selling a kWh that PV was about to replace for
free costs nothing.

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
  `sensor.total_pv_generation`.

## Recommendation

1. The summer verdict holds and strengthens: the optimiser is net
   positive, about 10 kr/day, and the adder-blindness costs single
   kronor per month while PV surplus covers the evening.
2. Feed 1KOMMA5 the full import price
   (`sensor.nordpool_se3_inkl_skatt_o_nat`) and the export pay
   (`sensor.elexport_ersattning`) instead of raw spot, if the
   integration allows it. That is the structural fix, and it is the
   one that matters in winter.
3. Watch for repeats of the 2026-08-17 shape: a heavy evening load on
   a day the battery sold down in the morning. One such day cost 6 kr;
   a winter one would cost more, and the midday idle on that day
   suggests the load forecast, not just the price model, missed.
4. Re-run in Nov-Dec, when the high-tariff window is live and the
   grid-charging in hours 06-21 can be priced for real.
