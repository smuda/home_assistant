# Battery steering: November 2026, first ten days (preliminary)

The first ten days with the winter grid tariff live. October, on the
flat low tariff, is in `analysis-2026-10.md`; the optimiser does
markedly worse here than there, and this report says where.

Preliminary because it covers ten days, seven of them working days.
Re-run for the whole month.

Data source: VictoriaMetrics, `http://192.168.40.20:8428`. Totals,
P&L, solar and the hour-of-day profile come from `scripts/analyze.py`;
scenarios, holds and bursts from `scripts/simulate.py`; the 1KOMMA5
price check from `scripts/prices_1komma5.py`. The night-only optimum,
the night-fill rule, the per-day and per-night tables, the own-future
hold check and the consumption split were run from scripts that are
not yet in `scripts/`; see Method notes.

## Window and totals

Window: 2026-11-01 00:00 -> 2026-11-11 00:00 (10.0 days). Working days
are 11-02 to 11-06, 11-09 and 11-10, with the high tariff 06-22. SOC
ran 18 % to 28 %.

| Post                | kWh   |
| ------------------- | ----- |
| Grid import         | 552.9 |
| Grid export         | 6.3   |
| Battery charged     | 202.5 |
| Battery discharged  | 173.3 |
| EV charged (Zaptec) | ~156  |

The EV figure is partly estimated. `sensor.zag064494_laddeffekt` has
no data from 2026-11-05 09:50 to 2026-11-10 04:05 (the integration was
unavailable in Home Assistant too), so about 61 kWh of it is inferred
from total load. The charger's lifetime counter
`sensor.zag064494_forbrukad_energi` rose 61.7 kWh across the gap
against an inferred 60.6 kWh, so the inference holds in total. See
Method notes.

## The two behaviours, and holding

Grid-charging: 196.6 kWh, 97 % of all charging, at a mean import
price of 2.66 kr/kWh. 89.0 kWh of it (45 %) was in hours 06-21, and
47.3 kWh fell inside the high tariff on working days, at a mean 3.37
kr/kWh.

Selling to the grid: 6.3 kWh, 4 % of discharge. Negligible.

Holding: 195 kWh was imported while the battery had charge and sat
idle, 65 kWh of it during EV charging (the Battery hold automation)
and 130 kWh with no EV.

## What the battery earned

| Flow                | kWh   | kr     | kr/kWh              |
| ------------------- | ----- | ------ | ------------------- |
| Charged from grid   | 196.6 | -523.7 | 2.66 paid           |
| Charged from PV     | 5.9   | -8.6   | 1.44 export forgone |
| Discharged to house | 167.0 | +694.1 | 4.16 import avoided |
| Discharged to grid  | 6.3   | +15.5  | 2.47 earned         |

Net: +177 kr over 10.0 days, about 18 kr/day, against 10.7 kr/day in
October. The simulation, on 5-min data, puts the saving against no
battery at 172 kr. Both are slightly low: the window ends 10 SOC
points fuller, about 2 kWh bought here and not yet used. The battery
earns more per day now because winter prices are higher and more
spread out; whether it earns what it could is the next section.

## What the solar was worth

| Where it went                  | kWh  | kr   | kr/kWh       |
| ------------------------------ | ---- | ---- | ------------ |
| Used as it was generated       | 15.2 | 56.9 | 3.75 avoided |
| Stored, used later by house    | 5.4  | 21.9 | 4.08 avoided |
| Stored, later sold to the grid | 0.2  | 0.4  | 2.29 earned  |
| Exported as it was generated   | 0.1  | 0.1  | 1.60 earned  |
| Total                          | 20.9 | 79   |              |

79 kr, 8 kr/day. The DC-to-AC ratio came out at 0.540, so treat this
as rough. Solar no longer matters to the battery question.

## Against the alternatives

Same house load, PV, prices, 16 kW import cap and EV hold for every
strategy. The perfect-foresight runs end at no lower SOC than the
actual run.

| Strategy                               | Cost kr | Saved | Per day |
| -------------------------------------- | ------- | ----- | ------- |
| No battery                             | 1665    | --    | --      |
| Plain self-consumption, no grid charge | ~1642   | ~23   | ~2.3    |
| 1KOMMA5, actual                        | 1493    | 172   | 17.2    |
| Night-fill rule, no forecast           | ~1478   | ~187  | ~18.7   |
| Perfect foresight, 1KOMMA5 price view  | 1418    | 247   | 24.7    |
| Perfect foresight, grid charge 22-06   | 1396    | 269   | 26.9    |
| Perfect foresight, any time            | 1395    | 270   | 27.0    |

The night-fill rule uses day-ahead prices only and no load forecast.
It never discharges 22-06, fills to the top in the cheapest night
buckets, and covers the house from the battery 06-22. It ends the
window at 88 % against the actual 28 %, and the difference is credited
at the window's mean import price, which is rough. Plain
self-consumption ends at 8 % and is adjusted the same way.

Three things stand out.

- 1KOMMA5 captured 64 % of the perfect-foresight saving. The gap is
  98 kr over ten days, 9.8 kr/day, roughly 290 kr/month at this rate.
  Perfect foresight knows the load in advance, so this is an upper
  bound on what a better strategy could recover.
- Grid-charging only at night loses 1 kr against grid-charging at any
  time. In these ten days the best strategy is the plain one: fill at
  night, run the day on the battery. Daytime grid charging is worth
  nothing, yet 1KOMMA5 did about 89 kWh of it in hours 06-21.
- The night-fill rule, with no forecast at all, did about as well as
  1KOMMA5 or slightly better. In October the same rule did much worse
  (186 kr against 269 kr over 31 days), because it spent the battery
  on the morning and had less left for the evening peak.

## Morning SOC and the night charge

| Day       | SOC act | SOC opt | Import act  | Import opt  | Chg act |
| --------- | ------- | ------- | ----------- | ----------- | ------- |
| 11-01 Sun | 46      | 68      | 22.3 @ 2.76 | 25.2 @ 2.77 | 5.4     |
| 11-02 Mon | 28      | 77      | 22.1 @ 2.90 | 16.6 @ 2.94 | 6.7     |
| 11-03 Tue | 59      | 98      | 18.4 @ 3.27 | 2.9 @ 3.38  | 14.2    |
| 11-04 Wed | 62      | 82      | 8.5 @ 3.33  | 4.8 @ 3.42  | 2.9     |
| 11-05 Thu | 64      | 98      | 9.6 @ 2.75  | 1.7 @ 2.90  | 3.7     |
| 11-06 Fri | 90      | 98      | 9.8 @ 3.35  | 4.5 @ 3.49  | 8.2     |
| 11-07 Sat | 48      | 98      | 36.7 @ 2.93 | 22.8 @ 2.91 | 17.3    |
| 11-08 Sun | 27      | 74      | 36.3 @ 2.94 | 28.4 @ 2.88 | 15.5    |
| 11-09 Mon | 92      | 98      | 20.7 @ 4.78 | 10.7 @ 4.56 | 6.0     |
| 11-10 Tue | 96      | 98      | 14.1 @ 5.42 | 7.8 @ 4.97  | 3.9     |

SOC is at 06:00, in %. Import is grid import 06-22 in kWh at its mean
price in kr/kWh, including grid charging. Chg act is the actual grid
charging 06-22 in kWh.

On the first four working days the battery started the day at 28-64 %
where the optimum had it at 77-98 %. The nights before show it was not
held back by the car:

| Before    | Night kr min/mean | Day kr | Chg act | Chg opt | > 8 kW |
| --------- | ----------------- | ------ | ------- | ------- | ------ |
| 11-02 Mon | 2.51 / 2.69       | 3.49   | 1.8     | 4.1     | 14     |
| 11-03 Tue | 2.00 / 2.28       | 4.02   | 14.7    | 20.6    | 0      |
| 11-04 Wed | 2.14 / 2.80       | 3.92   | 5.6     | 17.6    | 4      |
| 11-05 Thu | 1.36 / 1.84       | 3.16   | 10.8    | 20.6    | 11     |
| 11-06 Fri | 1.65 / 1.96       | 4.51   | 14.5    | 20.8    | 0      |
| 11-07 Sat | 2.15 / 2.34       | 3.14   | 6.5     | 20.6    | 6      |
| 11-08 Sun | 2.61 / 2.79       | 3.33   | 10.4    | 15.1    | 3      |
| 11-09 Mon | 2.62 / 3.05       | 5.29   | 15.0    | 16.5    | 9      |
| 11-10 Tue | 2.31 / 2.66       | 6.06   | 14.1    | 20.6    | 5      |

Before is the morning that ends the night; the night is 22-06.
Prices are import kr/kWh, Day kr the mean 06-22. Chg is grid charging
in the night, kWh, actual and optimum. "> 8 kW" counts 15-min buckets
with house load including EV above 8 kW, which is mostly the car.

On the nights before 11-03 and 11-06 nothing big ran, and 1KOMMA5
still stopped at about 14.5 kWh where about 20.5 kWh fitted. The
optimum charges the extra 6 kWh under the same fuse cap. The gap
between the day mean and the night mean was 0.8-3.4 kr/kWh on working
days, well above the cost of the round-trip loss of about 13 %.

## Is a full battery a full day?

House consumption without the EV, in kWh:

| Day       | 06-22 | 22-06 | 24 h | EV   | EV source        |
| --------- | ----- | ----- | ---- | ---- | ---------------- |
| 11-01 Sun | 18.0  | 10.8  | 28.7 | 26.2 | measured         |
| 11-02 Mon | 20.1  | 10.3  | 30.4 | 27.5 | measured         |
| 11-03 Tue | 17.0  | 12.1  | 29.1 | 5.7  | measured         |
| 11-04 Wed | 17.6  | 11.8  | 29.4 | 8.1  | measured         |
| 11-05 Thu | 18.2  | 12.1  | 30.3 | 27.2 | partly estimated |
| 11-06 Fri | 20.5  | 13.0  | 33.6 | 0.9  | estimated        |
| 11-07 Sat | 40.2  | 16.7  | 56.9 | 17.2 | estimated        |
| 11-08 Sun | 36.9  | 14.5  | 51.4 | 27.6 | estimated        |
| 11-09 Mon | 27.9  | 15.1  | 43.0 | 2.7  | estimated        |
| 11-10 Tue | 22.3  | 13.4  | 35.8 | 12.7 | partly estimated |

The battery delivers about 18 kWh from full (8-98 % at 0.200 kWh per
point). A working day's 06-22 load, without the car, was 17-22 kWh,
and 28 kWh on 11-09. So a full battery carries most of a working day,
and all of a light one. The night load, 10-15 kWh, falls in the cheap
hours anyway.

The weekend days used 37-40 kWh between 06 and 22, with almost no
load above 8 kW (0.7 kWh). That is not the car charging at its normal
rate. The garage and
workshop heaters are not metered in Home Assistant and may be part of
it; the data cannot say.

## 9-10 November: full in the morning, idle while importing

The last two working days started nearly full, at 92 % and 96 %, and
still lost money in a different way. 11-10, hour by hour:

- 06-07: SOC held at 96 %, the house imports at 4.28-5.48 kr/kWh.
- 08-11: a little discharge, SOC 96 -> 78 %, the house still imports
  part of its load.
- 12-14: grid charge back to 94 %, at 5.54-5.80 kr/kWh.
- 15-23: the battery covers the house, and SOC is still 44 % at 22:00
  and 28 % at midnight.

11-09 has the same shape: grid charging at 06 and barely discharging
at 07 at 91-93 %, while importing at 4.21-4.94 kr/kWh, a midday
top-up at 4.91 kr/kWh, and 42 % left at 22:00. On
both days the energy left at 22:00 could have covered the morning
import at 4-6 kr/kWh. It was used after 22:00 instead, at about 3.5-3.7
kr/kWh.

## The holds, revisited

The first hold test, used in the 2026-10 report too, compares the
import price paid with the marginal value of stored energy in the
perfect-foresight plan. On this window it passes almost everything:
195 kWh imported during holds, 30 kWh of it above the stored value,
13 kr lost.

That test is biased in the optimiser's favour. It values a held kWh
by how the perfect plan would use it later, not by how 1KOMMA5 did. A
hold looks right whenever the energy could have earned more later,
even when 1KOMMA5 then topped up at midday anyway and finished the day
with charge to spare.

Checked against 1KOMMA5's own later use instead: count the grid
energy imported or grid-charged 06-22 while holding that the energy
still in the battery at 22:00 could have replaced, most expensive
first, valued at the difference to what that energy actually earned
after 22:00. That gives 31.6 kWh and 34 kr over the ten days, 25 kr
of it on 11-09 and 11-10. This is a lower bound: it only counts the
energy that happened to be left over, not what a full night charge
would have added.

In October the same check gave 8.6 kr over 31 days, because the
day's prices barely moved. In November the holds are a real loss, and on
days that start full they are the main one.

## Compared with October

| Measure                            | Oct 1-31 | Nov 1-10 |
| ---------------------------------- | -------- | -------- |
| Share of perfect-foresight saving  | 79 %     | 64 %     |
| Left on the table, kr/day          | 2.4      | 9.8      |
| Night-only charging costs, kr      | 27       | 1        |
| Night-fill rule vs 1KOMMA5, kr     | -83      | +15      |
| Holds, own-future check, kr        | 9        | 34       |
| 1KOMMA5 price view costs, kr/day   | 0.1      | 2.3      |

The October figures are over 31 days, November's over 10. Each month
uses its own battery refit, 0.219 for October and 0.229 for November.
Night-only charging is the cost of restricting the perfect plan to
grid charging 22-06; the night-fill rule figure is its saving minus
1KOMMA5's.

In October midday charging earned something and a naive night fill
lost to 1KOMMA5. In November both flipped. The optimiser does not
seem to have adapted when the price shape changed.

## What tariff-blindness costs

1KOMMA5's published price inputs are unchanged: `..._spot_price` is
spot times 1.25 in all 960 15-min samples (within 1 %), and
`..._grid_costs` is 1.4375 SEK/kWh in every sample, high and low
tariff alike. Planning on that view instead of the real prices costs
23 kr over the ten days (1418 against 1395 kr), 2.3 kr/day.

So the tariff explains 23 kr of the 98 kr gap. The remaining 75 kr is
not about the grid fee. Spot alone already says the night is cheaper
than the day; the shortfall is 1KOMMA5 not acting on that fully.

Behaviour is consistent with a spot-based plan. On the seven working
days the real-price plan and the 1KOMMA5-view plan disagree in 113
15-min buckets; the actual battery matched the 1KOMMA5-view plan in 58
of them and the real-price plan in 41. On non-working days, where the
two views barely differ, the plans disagree in only 9 buckets.

The 47.3 kWh grid-charged inside the high tariff carried a 0.46 kr/kWh
premium, 22 kr.

## The near-empty bursts

The battery dropped below its 8 % minimum and cycled 10 kW grid-charge
bursts on 11-02, 11-03, 11-07 and 11-08, 18 kWh in total. Small in
money, still not plan behaviour.

## Hour-of-day profile (local time)

Positive grid is import, negative is export. Positive battery is
charging, negative is discharging. Spot is ex VAT.

```
hr | spot  | grid W  | batt W  | grid->batt kWh | batt->grid kWh
 0 |  1.31 |  +4754  |  +1280  |      15.3      |       0.0
 1 |  1.26 |  +3741  |   +862  |       8.2      |       0.0
 2 |  1.23 |  +4075  |  +1451  |      14.9      |       0.0
 3 |  1.23 |  +6060  |  +2029  |      20.3      |       0.0
 4 |  1.25 |  +4284  |   +780  |       7.8      |       0.0
 5 |  1.28 |  +4109  |  +2211  |      22.3      |       0.0
 6 |  1.73 |  +2015  |    +59  |       5.6      |       0.0
 7 |  2.10 |  +1381  |   -427  |       3.8      |       0.1
 8 |  2.28 |   +507  |  -1184  |       0.8      |       2.1
 9 |  2.15 |  +1010  |   -578  |       6.2      |       2.1
10 |  1.99 |   +691  |   -423  |       2.2      |       0.1
11 |  1.86 |  +1063  |   +354  |       6.2      |       0.0
12 |  1.88 |  +2153  |  +1515  |      16.5      |       0.0
13 |  1.89 |  +2018  |   +985  |      11.9      |       0.0
14 |  1.94 |  +3225  |  +1877  |      22.6      |       0.0
15 |  2.39 |  +1637  |   +305  |       7.0      |       0.0
16 |  2.80 |   +494  |  -1168  |       0.5      |       0.1
17 |  3.00 |    -20  |  -1894  |       0.0      |       0.6
18 |  2.93 |   +249  |  -1706  |       0.0      |       0.3
19 |  2.69 |   +277  |  -1548  |       0.0      |       0.1
20 |  2.38 |   +436  |  -1307  |       2.4      |       0.4
21 |  2.00 |  +2398  |   -951  |       3.2      |       0.1
22 |  1.71 |  +3747  |    -17  |       7.2      |       0.1
23 |  1.42 |  +4235  |   +391  |      11.7      |       0.0
```

Hours 12-14 carry 51 kWh of grid charging at spot 1.9 ex VAT, against
1.2-1.3 in hours 0-5. In the high tariff those midday hours also carry
the 0.46 kr/kWh grid premium.

## Method notes and caveats

- Prices, the 16 kW import cap, 15-min netting and the house demand
  definition (grid minus battery) are as in the 2026-10 report.
- The October comparison figures are from the archived full-month
  October window (2026-10-01 -> 2026-11-01) with October's own refit
  (0.219), on prices recomputed before 2026-10-25 with the current
  template formulas; see `analysis-2026-10.md`.
- Battery constants: refitted on this window to 0.200 kWh per SOC
  point discharging and 0.229 kWh per point charging (87 % round
  trip). With the committed 0.225 the model drifts 14 points over ten
  days; with 0.229 it closes to 1 point. All scenario figures here use
  0.229. The committed `simulate.py` uses 0.225 and gives the optimum
  as 1387 kr and the 1KOMMA5-view optimum as 1410 kr on the same data,
  8 kr lower each; no conclusion changes.
- Coverage: 2880 of 2880 5-min rows and 960 of 960 15-min rows for
  every series except EV power. No spot backfill was needed.
- EV during the Zaptec gap: inferred as house load above 1.5 kW in
  any 5-min sample above 8 kW. On 2026-10-10 -> 2026-11-05, where EV
  power was measured, that rule found 338 of 404 kWh, missing
  charging the fuse guard throttled below 8 kW. Across this gap it
  found 60.6 kWh against the counter's 61.7 kWh. Per-day EV figures
  on estimated days are therefore approximate, and their house figures
  may carry a little EV load.
- Battery hold during the gap: with `sensor.zag064494_laddstatus`
  unavailable the Battery hold automation released after 30 minutes,
  so the actual battery was not held for the car from 11-05 09:50 to
  11-10 04:05. The simulations hold the battery only where EV data
  exists, which matches what the automation could do.
- The night-only optimum is the same dynamic program as the full
  optimum with grid charging restricted to 22-06 (charging from PV
  surplus is allowed any time).
- Scripts not yet in `scripts/`: the night-only optimum, the night-fill
  rule, the per-day and per-night tables, the own-future hold check
  and the EV inference. The input CSVs for this window are not
  archived in `data/` either.

## Recommendation

1. Raise the night charge with 1KOMMA5, with dates. On working days it
   starts the day at 28-64 % although night import is 0.8-3.4 kr/kWh
   cheaper than day import, and on nights with no car (before 11-03
   and 11-06) it stopped about 6 kWh short of full. Ask what target
   SOC or load forecast it plans the night charge against.
2. Raise the midday top-up. On 11-09 and 11-10 it grid-charged at
   4.9-5.8 kr/kWh at midday and still had 42-44 % left at 22:00. In
   these ten days a perfect plan restricted to night charging does as
   well as one allowed to charge any time.
3. The published price has no time-of-use grid fee and a flat adder
   that did not change on 1 November, worth about 2.3 kr/day now. It
   is the smaller part of the gap.
4. A plain night-fill rule matched 1KOMMA5 here without any forecast,
   but lost to it badly in October. If 1KOMMA5 cannot change its
   winter behaviour, a seasonal override for November-March is worth
   testing; it should not run all year.
5. Re-run for the whole of November, and again for a cold February
   week, when the daytime load is higher than the battery.
