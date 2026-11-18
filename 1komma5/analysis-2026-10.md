# Battery steering: October 2026

The whole month on the flat low tariff, with the house a heavy net
importer. Two questions: does the 1KOMMA5 optimiser leave the battery
idle when it should be covering the house, and does the price it plans
against match what this house actually pays?

November, when the winter grid tariff is live, is in
`analysis-2026-11-pre.md`. The verdict below does not carry over to
it.

Data source: VictoriaMetrics, `http://192.168.40.20:8428`. The totals,
P&L, solar and hour-of-day figures come from `scripts/analyze.py`. The
counterfactual simulation, hold valuation and near-empty bursts come
from `scripts/simulate.py`, and the 1KOMMA5 price comparison from
`scripts/prices_1komma5.py`, both reading what `scripts/pull_sim.py`
pulls. The night-only optimum, the night-fill rule, the own-future
hold check and the battery refit were run from scripts that are not
yet in `scripts/`.

## Window and totals

Window: 2026-10-01 00:00 -> 2026-11-01 00:00 (31.0 days; 31.04 in
`simulate.py`, since 10-25 has 25 hours), all on the flat low tariff.
SOC ran 19 % to 18 %, so the battery ends almost where it started.

| Post                | kWh    |
| ------------------- | ------ |
| Grid import         | 1247.5 |
| Grid export         | 42.1   |
| Battery charged     | 527.1  |
| Battery discharged  | 504.4  |
| EV charged (Zaptec) | ~415   |

PV gave 155.0 kWh AC over the month, about 5 kWh/day, so the battery
is almost entirely a price-arbitrage device: 91 % of its charge came
from the grid. The EV figure is 390.4 kWh measured, mostly at night
(19 sessions in `analyze.py`), plus an estimated 24.2 kWh for one
session on the night of 10-02 to 10-03, when the charger's power
sensor has no data.
The charger's lifetime counter rose 427.6 kWh over the month, so the
measured-plus-estimated total is 13.0 kWh (3 %) low.

Two things in the data need saying before any figure.

Prices before 2026-10-25 are derived, not recorded. The import and
export price sensors ran on an older formula until the templates were
corrected on 10-25 (commits af80998, e3fcd06 and bf94fa2): import was
spot + 0.83125, with no VAT on spot and no trader fees, and export was
spot + 0.104, with no trader fees. The new formulas are live from
10-25 04:25. Every row before that was recomputed in the archive with
today's formulas:

```
import = 1.25 x spot + 0.305 + 0.45 + 0.096875
export = spot + 0.104 - 0.1185
```

So every cost in this report is on one consistent price model. The
earlier version of this report (10-10 to 10-31) and the July and
August reports used the old formula. How the headline moved, all at
the refit battery constant (see Method notes):

| Measure                        | Old prices | Repriced   |
| ------------------------------ | ---------- | ---------- |
| No battery, kr                 | 1857.7     | 2053.0     |
| Saved by 1KOMMA5, kr           | 221.6      | 269.2      |
| Saved by perfect foresight, kr | 306.7      | 342.3      |
| Share captured                 | 72.2 %     | 78.6 %     |
| Left on the table, kr          | 85.2       | 73.1       |
| 1KOMMA5 price view costs, kr   | 20.1       | 2.6        |
| Optimum's battery export, kWh  | 143.4      | 48.2       |
| Battery P&L, `analyze.py`, kr  | 273.8      | 330.9      |
| Holds, test 1 / test 2, kr     | 10.6 / 7.3 | 18.4 / 8.6 |

The grid meter and the EV power are missing from 10-02 21:09 to 10-03
05:34. The grid power was filled from the inverter's own grid meter;
the EV power was left empty and its energy estimated. Both are in
Method notes.

## The two behaviours, and holding

Grid-charging: 479.4 kWh, 91 % of all charging, at a mean import price
of 1.37 kr/kWh. Most of it is at night: 289.8 kWh in hours 00-05 and
86.4 kWh in hours 22-23 (sums of the hourly profile below), in bursts
of about 10 kW in External EMS mode. A smaller band, 36.4 kWh, falls
at 12-14 when spot dips.

Selling to the grid: 35.1 kWh, 7 % of discharge, at 1.78 kr/kWh, more
than half of it (19.0 kWh) in hour 08. Small compared with August's
22 %: there is little PV surplus to sell into, and the optimiser keeps
the battery for the house.

Holding: between a charge and the price peak the optimiser blocks
discharge, so the house imports while the battery sits charged and
idle. Over the month that is 373.5 kWh: 152.9 kWh while the EV
charged, 220.6 kWh with no EV. How the battery was kept off the car
changed on 10-25; see Method notes.

The holds are found from the battery power. The plan calendar does not
show them faithfully: each `Battery: no discharge` slot appears as a
15-minute event at the top of the hour, and the decision sensor goes
back to NONE after it, but the battery stays idle the whole hour. So
`sensor.heartbeat_batteribeslut` undercounts holds. Max discharge
power, reserve SOC, discharge start power and EMS mode were unchanged
during holds, so how the optimiser enforces them is not visible from
Home Assistant.

## Were the holds right?

Two tests, because the first one is biased.

The first compares the import price paid during a hold with the
marginal value of stored energy in the perfect-foresight plan (see
below). Of the 373.5 kWh imported during holds, 85.2 kWh was at a
price above that value, and the loss is 18.4 kr: 3.8 kr while the EV
charged and 14.6 kr with no EV. This test values a held kWh by how
the perfect plan would use it later, not by how 1KOMMA5 did, so it
leans in the optimiser's favour.

The second uses 1KOMMA5's own later behaviour. It counts the grid
energy imported or grid-charged 06-22 during holds that the energy
still in the battery at 22:00 could have replaced, valued at the
difference to what that energy earned after 22:00. That gives 110.8
kWh but only 8.6 kr.

Both say the October holds cost little. A lot of energy was held
needlessly, but the day's prices barely moved, so it did not matter
much. 2026-10-10 is the largest case in both tests: the battery sat
at 89-91 % from 02:00 to 16:00 while the house imported at 1.04-1.27
kr/kWh, topped up to 99 % at 16, discharged a little at 17-19, and
ended the day at 84 %. The first test counts 29.2 kWh of idle import
with no EV that day; the second finds 15.5 kWh avoidable, worth 1.7
kr. By the first test's kr, 10-12 and 10-21 are the largest days, at
2.3 kr each.

## What the battery earned

Marginal P&L from `analyze.py`, on the repriced archive.

| Flow                | kWh   | kr     | kr/kWh              |
| ------------------- | ----- | ------ | ------------------- |
| Charged from grid   | 479.4 | -654.5 | 1.37 paid           |
| Charged from PV     | 47.7  | -34.0  | 0.71 export forgone |
| Discharged to house | 469.2 | +957.0 | 2.04 import avoided |
| Discharged to grid  | 35.1  | +62.4  | 1.78 earned         |

Net: +331 kr over 31.1 days, about 10.7 kr/day, a little above
August's 9 kr/day, which was on the old price formula. The simulation
on 5-min data puts the saving against no battery at 269 kr, 8.7
kr/day; `analyze.py` samples one instant per 15 min, and with 10 kW
charge bursts that sampling moves the total. SOC ends one point lower
than it started, about 0.2 kWh at 0.200 kWh per point, so the end
state does not distort either figure.

## What the solar was worth

| Where it went                  | kWh   | kr    | kr/kWh       |
| ------------------------------ | ----- | ----- | ------------ |
| Used as it was generated       | 100.3 | 194.2 | 1.93 avoided |
| Stored, used later by house    | 44.3  | 89.9  | 2.03 avoided |
| Stored, later sold to the grid | 2.0   | 2.9   | 1.43 earned  |
| Exported as it was generated   | 7.0   | 3.6   | 0.52 earned  |
| Total                          | 153.6 | 291   |              |

291 kr, 9 kr/day, against 35 kr/day in August. Solar is now worth
less than the battery. 1.4 kWh of stored solar was still in the
battery at the close and is not valued. The DC-to-AC ratio came out
at 0.761, below the usual 0.92, probably because the inverter's fixed
losses weigh more at low output. Treat the solar figures as rough.

## Against the alternatives

The house load and PV were replayed through alternative battery
strategies with the same prices, the same battery model, the same EV
hold, and a 16 kW import cap for the 25 A fuse. The perfect-foresight
runs end at no lower SOC than the actual run. All figures use the
October refit, 0.219 kWh per SOC point charging; the committed
constant gives slightly different numbers (Method notes).

| Strategy                               | Cost kr | Saved  | Per day |
| -------------------------------------- | ------- | ------ | ------- |
| No battery                             | 2053.0  | --     | --      |
| Plain self-consumption, no grid charge | ~1991.6 | ~61.5  | ~2.0    |
| 1KOMMA5, actual                        | 1783.9  | 269.2  | 8.7     |
| Night-fill rule, no forecast           | ~1867.2 | ~185.8 | ~6.0    |
| Perfect foresight, 1KOMMA5 price view  | 1713.4  | 339.7  | 10.9    |
| Perfect foresight, grid charge 22-06   | 1738.0  | 315.1  | 10.2    |
| Perfect foresight, any time            | 1710.8  | 342.3  | 11.0    |

Plain self-consumption ends at 8 % and the night-fill rule at 98 %,
against the actual 18 %; both are adjusted by the difference at the
window's mean import price, 1.88 kr/kWh, which is rough. The
night-fill rule never discharges 22-06, fills to the top in the
cheapest night buckets, and covers the house from the battery by day.

1KOMMA5 captured 79 % of the perfect-foresight saving. The gap is 73
kr over 31 days, 2.4 kr/day. Perfect foresight knows the house load in
advance, which no real optimiser can, so that is an upper bound.

What October shows:

- Daytime grid charging earns something here. Restricting the
  perfect plan to night charging costs 27 kr.
- The naive night-fill rule does much worse than 1KOMMA5 (186 against
  269 kr). It empties the battery from 06:00, when the morning cost
  2.10-2.20 kr/kWh at 07-08, and has less left for the evening peak at
  2.43-2.45 kr/kWh at 17-18 (hourly mean import prices).

Where the gap is, comparing actual with the real-price optimum. These
are the simulation's flows, netted per 15 min, so they differ from the
`analyze.py` totals above; the hour-band figures are sums of its
hourly table. The items overlap and do not add up to the gap.

- Charging price. The optimum grid-charges 399.7 kWh at 1.29 kr/kWh
  against the actual 447.9 kWh at 1.37. It charges much less at 00-01
  and 05 (65.4 against 139.7 kWh) and more at midday, 11-14 (56.1
  against 38.6 kWh). Buying the optimum's volume at the actual price
  would cost about 33 kr more (arithmetic on these figures).
- Discharge timing. The optimum delivers 355.8 kWh to the house at
  2.25 kr/kWh avoided, the actual 412.6 kWh at 2.08. The actual run
  spreads its discharge into 19-21, 118.9 kWh against the optimum's
  88.8; the optimum leans on 16-18, 107.4 kWh against 92.2.
- Selling. The optimum sells 48.2 kWh from the battery at 1.81
  kr/kWh, the actual 33.1 kWh at 1.68. With export at spot - 0.0145
  there is little to gain from selling. On the old export formula the
  optimum sold 143.4 kWh, which is where earlier versions of this
  report found a large selling gap.
- Price view, 2.6 kr (next section).

## Does 1KOMMA5 plan against the right price?

The integration publishes its price inputs as sensors, recorded from
2026-10-22. They decompose exactly:

- `..._spot_price` is Nord Pool spot times 1.25, which is spot
  including VAT. Within 1 % in 94 % of buckets with spot above 0.2;
  the rest are one-bucket lags at price steps.
- `..._grid_costs` is 1.4375 SEK/kWh in all 942 samples.
- `..._electricity_price` equals spot price plus grid costs to within
  0.0001 in every sample.

The unit labels say EUR, but the values are SEK.

The real import adder this month, incl VAT, is 0.852 kr/kWh (energy
tax 0.45 + low-tariff grid fee 0.305 + trader fees 0.097); measured as
import price minus 1.25 x spot it averages 0.8518. So 1KOMMA5
overprices import by about 0.59 kr/kWh.

On consistent prices that costs only 2.6 kr over the month: the
optimum planned on 1KOMMA5's view, costed at the real prices, comes to
1713.4 kr against the real-price optimum's 1710.8. A flat adder cannot
change which import hour is cheapest, and on the flat low tariff the
real adder is flat too. It only moves the trade between keeping a kWh
and selling it, and with export at spot - 0.0145 there is little
selling worth doing either way: the two optima sell 47.4 and 48.2 kWh
from the battery. The earlier claim that the view discouraged peak
sales does not hold on these prices; it came from the old export
formula, on which the view cost 20.1 kr.

The behaviour still matches that view: the real-price plan and the
1KOMMA5-view plan disagree in 183 15-min buckets, and the actual
battery matched the 1KOMMA5-view plan in 113 of them and the
real-price plan in 56.

Whether the adder changes when the high tariff starts on 1 November
is answered in `analysis-2026-11-pre.md`.

## The winter risk

103.2 kWh of this month's grid charging (22 %) was in hours 06-21. On
a winter working day those hours carry the high grid fee, 0.765
against 0.305 kr/kWh, 0.46 more, so the same pattern would cost about
47 kr extra (arithmetic on these figures). `analyze.py`'s what-if
prints 59 kr because it still multiplies by the 0.575 spread from the
stale table in `README.md`. The November report measures it.

## The near-empty bursts

On eleven days (10-01 to 10-05, 10-18 to 10-21, 10-24, 10-25) the
battery drained to 0-5 %, below its 8 % minimum SOC, and charged at
over 5 kW: 79.9 kWh in all, 20.5 kWh of it on 10-03. On the evenings
looked at in detail (10-18 to 10-25) it then cycled: a 5-10 minute
grid charge at about 9.6 kW in External EMS mode, then discharge at
1.5-3 kW, repeated for hours. That energy goes straight back into the
house.

The cost is only the round-trip loss, roughly 13 kr (estimate: the
refit's 91 % round trip at the month's mean import price). But this
looks like the inverter or the optimiser defending a floor it has
already passed, not a planned decision. The SOC reading below the
minimum, and the battery model drifting most on these same days (see
Method notes), suggest the battery's SOC calibration drifts.

## Hour-of-day profile (local time)

Positive grid is import, negative is export. Positive battery is
charging, negative is discharging. Spot is ex VAT.

```
hr | spot  | grid W  | batt W  | grid->batt kWh | batt->grid kWh
 0 |  0.56 |  +3751  |  +1199  |      52.7      |       0.1
 1 |  0.52 |  +3805  |  +1155  |      48.9      |       0.1
 2 |  0.49 |  +4398  |  +1153  |      49.5      |       0.1
 3 |  0.50 |  +4208  |   +712  |      39.9      |       0.0
 4 |  0.50 |  +4547  |  +1297  |      50.2      |       0.0
 5 |  0.57 |  +3894  |  +1204  |      48.6      |       0.1
 6 |  0.76 |  +1832  |   +279  |      23.1      |       0.1
 7 |  0.99 |   +931  |   -467  |      13.0      |       0.3
 8 |  1.09 |    -28  |  -1176  |       5.0      |      19.0
 9 |  1.02 |   +145  |   -588  |       2.4      |       5.5
10 |  0.91 |   +240  |   -434  |       1.6      |       0.3
11 |  0.80 |   +424  |    -24  |       4.4      |       0.2
12 |  0.74 |   +661  |   +454  |       8.1      |       0.1
13 |  0.72 |   +792  |   +544  |       8.2      |       0.2
14 |  0.74 |   +986  |   +801  |      20.1      |       0.1
15 |  0.86 |   +613  |    +38  |       7.8      |       0.1
16 |  1.04 |   +439  |   -603  |       2.3      |       0.3
17 |  1.25 |   +366  |   -931  |       0.0      |       0.3
18 |  1.30 |    +94  |  -1354  |       0.0      |       3.7
19 |  1.18 |   +252  |  -1474  |       0.0      |       3.3
20 |  1.01 |   +349  |  -1241  |       0.0      |       0.6
21 |  0.84 |   +437  |  -1015  |       7.3      |       0.4
22 |  0.71 |  +2213  |    +56  |      35.0      |       0.2
23 |  0.62 |  +3361  |  +1102  |      51.4      |       0.1
```

## Method notes and caveats

- Prices are read from `sensor.nordpool_se3_inkl_skatt_o_nat` and
  `sensor.elexport_ersattning`, with spot from
  `sensor.nord_pool_se3_aktuellt_pris` (ex VAT). From 2026-10-25 04:25
  the archive holds the recorded values. Before that it holds derived
  values, recomputed with today's template formulas (see Window and
  totals), because the recorded ones used the old formula: spot +
  0.83125 for import and spot + 0.104 for export. Rows changed: 2326
  in `2026-10.csv`, 6977 in `2026-10-sim.csv` and 2326 in
  `2026-10-prices.csv`, whose grid-fee column was also set from
  0.38125 to 0.305. No other column was touched. The formula check
  reproduces every recorded row after the switch exactly, except two,
  10-31 04:15 and 04:45, where spot steps and the template evidently
  rendered against a neighbouring spot value (recorded import 3.12 and
  2.65 against 3.01 and 2.79). Those two were left as recorded. After
  repricing, import minus 1.25 x spot averages 0.8518 over October.
- The window is archived in `data/`: `2026-10.csv` (`analyze.py`
  input), `2026-10-sim.csv` (`simulate.py` input) and
  `2026-10-prices.csv` (`prices_1komma5.py` input). Each script takes
  the path as its first argument. The archive is the reference: a
  fresh pull would not reproduce it, because of the repricing and the
  gap below.
- Coverage: 2981 15-min and 8940 5-min rows. Every series is complete
  except the P1 grid power and the EV power, which are missing from
  2026-10-02 21:09 to 2026-10-03 05:34 (99 5-min and 34 15-min rows).
  No spot backfill was needed. The 1KOMMA5 price sensors
  (`sensor.heartbeat_john_allberg_*`) have history only from
  2026-10-22 05:30.
- The grid gap was filled from `sensor.meter_active_power`, the
  inverter's own grid meter. Over the rest of October the two agree
  well: on 5-min rows the mean difference is -4.7 W, the mean absolute
  difference 82.6 W, the correlation 0.988, and the sign matches in
  4097 of 4123 samples above 300 W; import over the month is 1247.2
  against 1245.0 kWh. In the 24 hours either side of the gap the mean
  difference is +46.1 W and the correlation 0.983.
- The EV power was left empty in the archive. Its gap energy is
  estimated as house load minus 1.5 kW in each 5-min sample above 8
  kW, the rule used for November: 29 samples, 10-03 02:05-04:25, 24.2
  kWh. The Zaptec counter rose 25.4 kWh across the gap, so the
  estimate is 1.2 kWh (5 %) low. `sensor.zag064494_laddstatus` was
  unavailable throughout the gap. Since the 9 gap buckets above 8 kW
  have no EV flag, the simulation could use the battery for the car
  there; forcing them to EV hold moves the optima by 0.2 kr or less
  (committed constant).
- The committed pull scripts key their rows on the grid timestamps, so
  a re-run of `pull.py` or `pull_sim.py` would drop the gap rows
  instead of leaving them for filling. The archive was pulled keyed on
  the battery series.
- EV battery handling changed during the month. From 10-21 a
  charge-cap automation capped the battery's charge power while the
  car charged (commit 84bb6dc), and from 10-22 its discharge power too
  (c85a0c9). The optimiser writes those registers itself and overwrote
  the caps within about 10 s (commit 5d952c0), so the caps did not
  reliably keep the battery off the car. Before 10-21 the repo has no
  such automation. From 10-25 the Battery hold (5d952c0) holds the
  battery in Forced stop while the car charges. The simulation holds
  the battery idle in every EV-charging bucket all month, so for 1-24
  October it is an approximation: the actual battery may have covered
  some EV load then, which the counterfactuals do not allow. For
  scale, lifting the hold lowers the optimum from 1726 to 1704 kr
  (committed constant).
- The simulation works on 5-min samples averaged to 15 min, with house
  demand taken as grid power minus battery power. Inverter losses on
  battery flows are therefore counted as house load in every scenario.
  Grid import and export are netted per 15-min bucket.
- Battery model: 0.200 kWh delivered per SOC point discharging and
  0.219 kWh in per point charging (91 % round trip), SOC 8-98 %, 10 kW
  either way. 0.219 is October's own energy-balance fit, as the
  November report uses November's; with it the model, run on the
  actual flows, ends at 21 % against an actual 18 %. The committed
  `simulate.py` uses 0.225, fitted on 2026-10-10 -> 2026-11-10, with
  which the model ends at -38 %. Fitted separately, 10-01 to 10-09
  gives 0.210 and 10-10 to 10-31 0.222. The drift concentrates on the
  near-empty days: the largest per-day drifts at 0.225 are on 10-01
  to 10-03 and 10-18 to 10-22, with 10-13 the one exception. Leaving
  out the 5-min steps that touch SOC 5 % or below gives 0.217.
- With the committed 0.225: perfect foresight saves 327.2 kr, 1KOMMA5
  captures 82.3 % of it, and the gap is 58.0 kr, 1.87 kr/day. The
  1KOMMA5-view optimum saves 324.6 kr, so the view again costs 2.6
  kr; night-only charging costs 25.0 kr; the night-fill rule saves
  166.9 kr and plain self-consumption 59.1 kr. Hold test 1 gives 74.9
  kWh above stored value and 15.5 kr; test 2 is unchanged at 8.6 kr.
  The plans disagree in 173 buckets, the actual matching the view
  plan in 105 and the real-price plan in 56. No conclusion changes.
- The perfect-foresight optimum is a dynamic program over SOC in 1 %
  steps with known prices and load. During EV charging it holds the
  battery idle, like the Battery hold automation. It is an upper bound.
- The plain self-consumption replay discharges to cover any import and
  charges only from PV surplus, which is the Sungrow default.

## Recommendation

1. On October's flat tariff 1KOMMA5 did a reasonable job: about 79 %
   of the perfect-foresight saving, leaving 2.4 kr/day. The holds cost
   little, 9-18 kr over the month.
2. Its published price uses a flat 1.4375 SEK/kWh adder, 0.59 kr/kWh
   above what import actually costs on the low tariff. On consistent
   prices that cost only 2.6 kr in October. Raise it with 1KOMMA5
   together with the findings in `analysis-2026-11-pre.md`.
3. The near-empty bursts below 8 % are worth one support question to
   1KOMMA5 or Sungrow. Small in money, but they are not plan
   behaviour.
4. Do not extrapolate this month to winter; see
   `analysis-2026-11-pre.md`.
