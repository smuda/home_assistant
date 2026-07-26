# Battery steering: spot vs grid tariff (July 2026)

First data-driven check of whether the 1KOMMA5 optimiser loses money
by planning against raw Nord Pool spot while ignoring the grid
transfer fee (nataavgift) and the import/export price asymmetry.

Data source: VictoriaMetrics, `http://192.168.40.20:8428`. Scripts
that produced these numbers are in `scripts/`.

## The concern

Observed behaviour that prompted this: the battery seemed to sell to
the grid in the morning when the price was high, and to grid-charge in
the afternoon when the price was low. The worry was that the optimiser
does not account for the time-of-use grid transfer fee (rorligt
elnatspris) in its calculations.

## Window and totals

Window: 2026-07-15 15:15 -> 2026-07-26 07:00 (10.7 days, 15-min
resolution). Sign conventions were verified against SOC change and
export power before analysis.

| Post | kWh |
|---|---|
| Grid import | 225.0 |
| Grid export | 95.4 |
| Battery charged | 173.9 |
| Battery discharged | 164.2 |

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

Behaviour 1, grid-charging on the day. 78.6 kWh (45 % of all charging)
came from the grid, mean spot 0.236 kr. It happens in two clusters:
night 00-05 and afternoon 14-18. Only 9.5 kWh was charged at spot
above 0.5, with a small tail of about 5 kWh near spot 1.0 (max 1.06).

Behaviour 2, battery selling to the grid. 13.7 kWh (8 % of all
discharge) went straight out to the grid, concentrated in the early
morning 04-08 (about 10 kWh) at spot 0.5-0.78. This is exactly the
observed pattern.

## Why the summer data does not settle the concern

Grid-charging at low spot and discharging into the house in the
evening is textbook spot arbitrage. Because 92 % of discharge serves
own load rather than export, the tax + grid adder cancels out: you pay
the adder when charging, but you avoid it on the evening import you
would otherwise have made. Net benefit is the plain spot spread, about
0.95 - 0.24 minus round-trip losses, so roughly 0.5-0.6 kr/kWh. In the
summer data the grid-charging works in your favour, not against it.

The only thing the adder-blindness actually costs now is the 13.7 kWh
sold out instead of kept (about 0.72 kr/kWh, order of 10 kr) plus the
few kWh charged expensively. Real cost: a krona or two per day over 11
days. Small.

The key point: the time-of-use grid fee only varies Nov-Mar, working
days 06-22. April-October it is flat at 0.381. There is right now no
variable grid price to account for, so the behaviour can neither
confirm nor refute the hypothesis. Summer is the wrong measurement
period for that specific question.

## The real risk: winter

This is where the concern gets sharp. 66 % of the grid-charging (51.9
of 78.6 kWh) happened in hours 06-21, which is exactly the high-tariff
window in the winter half-year (0.956 vs 0.381, i.e. +0.575 kr/kWh). A
pure spot optimiser does not see that premium. If the same
"charge from the grid mid-day" pattern repeats on a winter working
day, those charges would carry about 30 kr extra grid fee that the AI
does not price in, and unlike summer there is no cheap PV as an
alternative then.

One cannot extrapolate the summer hours straight into winter, since
the spot and PV profile is entirely different. The conclusion is that
the feared effect is real and the mechanism exists, but it only
materialises in winter data.

## Hour-of-day profile (local time)

Positive grid is import, negative is export. Positive battery is
charging, negative is discharging.

```
hr | spot  | grid W  | batt W  | grid->batt kWh | batt->grid kWh
 0 |  0.78 |   +966  |  -1470  |      1.3       |      0.1
 1 |  0.66 |  +1436  |     -2  |      8.4       |      0.1
 2 |  0.59 |  +1081  |   -827  |      5.7       |      1.5
 3 |  0.58 |   +927  |   -552  |      2.8       |      0.7
 4 |  0.54 |   +549  |   -516  |      1.3       |      2.0
 5 |  0.54 |  +1130  |   +142  |      7.1       |      1.4
 6 |  0.63 |   +114  |   -315  |      0.0       |      0.8
 7 |  0.77 |   -546  |   -336  |      0.0       |      3.6
 8 |  0.78 |   -670  |    -21  |      0.0       |      1.7
 9 |  0.62 |   +493  |   +797  |      0.0       |      0.8
10 |  0.42 |   +495  |  +1185  |      0.4       |      0.0
11 |  0.31 |    +16  |  +1806  |      3.6       |      0.0
12 |  0.25 |   -770  |  +1249  |      0.1       |      0.0
13 |  0.22 |   -759  |  +1484  |      2.7       |      0.0
14 |  0.21 |   +941  |  +1336  |     10.8       |      0.0
15 |  0.24 |  +1090  |  +1596  |     10.8       |      0.0
16 |  0.27 |  +1427  |  +1402  |     11.5       |      0.0
17 |  0.40 |  +1540  |   -724  |      3.3       |      0.0
18 |  0.65 |   +924  |   +163  |      8.1       |      0.0
19 |  0.91 |   +315  |   -395  |      0.4       |      0.1
20 |  0.99 |   +220  |   -819  |      0.0       |      0.1
21 |  1.00 |   +108  |  -1301  |      0.0       |      0.7
22 |  0.94 |   +284  |   -944  |      0.0       |      0.1
23 |  0.91 |   +442  |  -1333  |      0.1       |      0.1
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
- The export-compensation sensor `sensor.elexport_ersattning` was
  created the same day as this analysis and has no history, so export
  pay was computed directly as spot + 0.104 rather than read from the
  sensor. The import price sensor existed but its formula may also have
  changed that day, so the analysis uses raw spot plus the documented
  adder constants throughout and does not depend on the historical
  values of the computed sensors.
- Entities used: `sensor.nord_pool_se3_aktuellt_pris` (spot),
  `sensor.battery_charging_power_signed` (+charge/-discharge),
  `sensor.p1_meter_effekt` (+import/-export),
  `sensor.battery_level` (SOC), `sensor.export_power`,
  `sensor.total_pv_generation`.

## Recommendation

1. Treat the concern as open until winter data exists. Re-run this
   analysis in Nov-Dec; then the high-tariff grid-charging can be
   measured in kronor.
2. To act now: check whether 1KOMMA5 can be fed the full import price
   (`sensor.nordpool_se3_inkl_skatt_o_nat`) and the export pay instead
   of raw spot. That is the only structural fix for the
   adder-blindness.
3. The small tail of grid-charging at spot near 1 kr is worth a quick
   look; it may be a forecast miss in the optimiser.
