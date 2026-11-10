# Battery steering: spot vs grid tariff (October 2026)

First check with the winter tariff live. Two questions: does the
1KOMMA5 optimiser leave the battery idle when it should be covering
the house, and does it price the time-of-use grid transfer fee that
started on 2026-11-01?

Data source: VictoriaMetrics, `http://192.168.40.20:8428`. The totals,
P&L, solar and hour-of-day figures come from `scripts/analyze.py`. The
counterfactual simulation, hold valuation and near-empty bursts come
from `scripts/simulate.py`, and the 1KOMMA5 price comparison from
`scripts/prices_1komma5.py`, both reading what `scripts/pull_sim.py`
pulls.

## Window and totals

Window: 2026-10-10 00:00 -> 2026-11-10 00:00 (31.0 days). That is 22
October days on the flat low tariff and 9 November days, 6 of them
working days (11-02 to 11-06, 11-09) with the high tariff 06-22. SOC
ran 58 % to 27 %, so the battery ends emptier than it started.

| Post                | kWh    |
| ------------------- | ------ |
| Grid import         | 1440.0 |
| Grid export         | 24.7   |
| Battery charged     | 534.8  |
| Battery discharged  | 496.0  |
| EV charged (Zaptec) | 404.0  |

The house is now a heavy net importer. PV is down to about 3 kWh/day
AC, so the battery is almost entirely a price-arbitrage device: 96 %
of its charge came from the grid. The EV figure is a lower bound,
since `sensor.zag064494_laddeffekt` has no data from 2026-11-05 10:05
onwards (see Method notes).

## The two behaviours

Behaviour 1, grid-charging. 513.5 kWh, 96 % of all charging, at a mean
import price of 1.80 kr/kWh. It is concentrated in two bands: 00-05,
in bursts of about 10 kW in External EMS mode, and a smaller midday
band 12-14 when spot dips. 43 kWh of it was charged inside the high
tariff on November working days.

Behaviour 2, battery selling to the grid. 23.3 kWh, 5 % of discharge,
at 2.34 kr/kWh. Almost gone compared with August's 22 %: there is no
PV surplus to sell into, and the optimiser keeps the battery for the
house.

The behaviour the household actually notices is a third one: holding.
Between a charge and the price peak the optimiser blocks discharge, so
the house imports while the battery sits charged and idle. Over the
window that is about 500 kWh: 188 kWh while the EV charged (the
Battery hold automation), 308 kWh with no EV.

The plan calendar does not show the holds faithfully. It shows each
`Battery: no discharge` slot as a 15-minute event at the top of the
hour (03:00-03:15, 04:00-04:15, ...), and the decision sensor goes
back to NONE after it, but the battery stays idle the whole hour. So
`sensor.heartbeat_batteribeslut` undercounts holds, and the battery
power is the only reliable signal. Max discharge power, reserve SOC,
discharge start power and EMS mode were all unchanged during these
holds, so how the optimiser enforces them is not visible from Home
Assistant.

## Were the holds right?

To judge a hold, compare the import price paid now with what the
stored kWh was worth when it was eventually used. That later value is
taken from a perfect-foresight optimisation over the same window (see
below), as the marginal value of one more kWh in the battery at that
moment.

Of the 308 kWh imported during holds with no EV, 49 kWh happened at a
price above that later value. The loss, capped at the battery's
discharge power, is 12 kr. For the 188 kWh during EV holds the figures
are 31 kWh and 6 kr. So about 18 kr over the window: the holds are
almost always correct.

2026-11-07 is typical. The battery held at 48 % from 03:00 to 08:00
while the house imported about 12 kW at 2.2-2.3 kr/kWh, then spent
that charge between 15:45 and 18:30 at 3.8-3.9 kr/kWh. Discharging at
night would have meant recharging at midday at about 2.6 kr/kWh to
cover the evening.

## What the battery earned

Marginal P&L from `analyze.py`, priced the same way as earlier
reports.

| Flow                | kWh   | kr      | kr/kWh              |
| ------------------- | ----- | ------- | ------------------- |
| Charged from grid   | 513.5 | -921.8  | 1.80 paid           |
| Charged from PV     | 21.3  | -24.4   | 1.15 export forgone |
| Discharged to house | 472.8 | +1232.2 | 2.61 import avoided |
| Discharged to grid  | 23.3  | +54.5   | 2.34 earned         |

Net: +341 kr over 31.1 days, about 11 kr/day. The same calculation on
5-min data averaged to 15 min gives +298 kr; `analyze.py` samples one
instant per 15 min, and with 10 kW charge bursts that sampling moves
the total. Take about 300-340 kr as the range. It is also
conservative: the window ends 31 SOC points emptier, but the charge
still in the battery at the end is not valued.

## What the solar was worth

| Where it went                  | kWh  | kr    | kr/kWh        |
| ------------------------------ | ---- | ----- | ------------- |
| Used as it was generated       | 71.7 | 159.3 | 2.22 avoided  |
| Stored, used later by house    | 19.5 | 51.1  | 2.62 avoided  |
| Stored, later sold to the grid | 0.7  | 1.5   | 2.19 earned   |
| Exported as it was generated   | 1.5  | 1.7   | 1.15 earned   |
| Total                          | 93.4 | 214   |               |

214 kr, 7 kr/day, against 35 kr/day in August. Solar is now worth less
than the battery. The DC-to-AC ratio came out at 0.650, far from the
usual 0.92, probably because the inverter's fixed losses dominate at
this low output. Treat the solar figures as rough.

## Against the alternatives

The house load and PV were replayed through three alternative battery
strategies with the same price sensors. All three use the same battery
model, fitted to this window (see Method notes), the same EV hold, and
a 16 kW import cap for the 25 A fuse.

| Strategy                                 | Cost kr | Saved vs none |
| ---------------------------------------- | ------- | ------------- |
| No battery                               | 2929    | --            |
| Plain self-consumption, no grid charging | ~2895   | ~35           |
| 1KOMMA5, actual                          | 2630    | 299           |
| Perfect foresight, real prices           | 2496    | 433           |
| Perfect foresight, 1KOMMA5's price view  | 2523    | 406           |

Plain self-consumption is adjusted by about 8 kr because it ends at
8 % rather than 27 %. The perfect-foresight runs end at no lower SOC
than the actual run.

1KOMMA5 captures about 69 % of the perfect-foresight saving, and the
gap is 134 kr over the month. Perfect foresight knows the house load
in advance, which no real optimiser can. So the gap is an upper bound
on what a better strategy could recover, not a loss you could expect
to win back in full.

Where the gap is, comparing actual with the real-price optimum:

- Charging price. The optimum grid-charges about the same energy, 478
  kWh, at 1.65 kr/kWh against the actual 1.80. That is about 70 kr,
  and it comes
  from timing: the optimum fills up at 02-05, while the actual run
  does a share of its charging at midday at about 2.2 kr/kWh.
- Discharge timing. The actual run discharges 29 kWh in hour 21 at
  about 2.26 kr/kWh, the optimum 5 kWh. The optimum keeps that charge
  for the 17-19 peak, or sells it then: it exports 98 kWh from the
  battery against the actual 20.
- Price view. Planning on 1KOMMA5's own price view instead of the real
  one costs 27 kr of the 134 (next section).

## Does 1KOMMA5 price the winter tariff?

The data says no.

The integration publishes its price inputs as sensors, recorded from
2026-10-22. They decompose exactly:

- `..._spot_price` is Nord Pool spot times 1.25, which is spot
  including VAT. Within 1 % in 97 % of buckets; the rest are one-bucket
  lags at price steps.
- `..._grid_costs` is 1.4375 SEK/kWh in every sample: October and
  November, high-tariff hours and low-tariff hours alike, 1806 samples
  with a single value.
- `..._electricity_price` equals spot price plus grid costs to within
  0.0001 in every sample.

The unit labels say EUR, but the values are SEK.

So the price 1KOMMA5 exposes is spot plus a flat adder that did not
change on 1 November and does not change at 06:00 or 22:00. A flat
adder cannot change which import hour is cheapest. In this view the
06-22 premium does not exist.

The flat adder also matches neither tariff level. The real import
adder, incl VAT, is 1.312 in the high tariff and 0.852 in the low
(energy tax 0.45 + grid fee + trader fees 0.097). So 1KOMMA5 overprices
import by 0.59 kr/kWh in low-tariff hours, which overstates the
asymmetry between import and export.

The behaviour points the same way, though the evidence is weaker. Two
perfect-foresight plans were run on the same load: one on the real
prices, one on 1KOMMA5's view (spot incl VAT + 1.4375 for import, spot
incl VAT + 0.104 for export). On November working days the two plans
disagree in 90 buckets. In those buckets the actual battery matched
the spot-view plan 47 times and the real-price plan 33 times. Six
working days is a small sample, and the morning and evening spot
peaks sit inside the high-tariff window anyway, so a spot planner does
the right thing at most hours by coincidence.

Neither test shows what the planner does internally. 1KOMMA5 could
use a different cost function from the one it publishes. But nothing
in the published series or in the behaviour shows the tariff being
priced.

## What tariff-blindness costs across the window

Re-pricing the plan made on 1KOMMA5's view with the real prices costs
27 kr more than the real-price optimum: 10 kr in the 22 October days,
18 kr in the 9 November days. That is about 2 kr/day once the tariff
is live, roughly 60 kr/month through March.

A cruder measure: 43 kWh was grid-charged inside the high tariff on
November working days, paying a 0.46 kr/kWh premium, 20 kr over six
working days. Not all of that was a mistake; some of the spreads were
wide enough to justify it.

That is smaller than the 2026-08 report's 42 kr per 26 days. That
estimate used the old 0.575 kr/kWh spread; the current template
spread is 0.46.

## The near-empty bursts

On ten evenings (10-18 to 10-21, 10-24, 10-25, 11-02, 11-03, 11-07,
11-08) the battery drained to 0-5 %, below its 8 % minimum SOC. It
then cycled: a 5-10 minute grid charge at about 9.6 kW in External EMS
mode, then discharge at 1.5-3 kW, repeated for hours. That is 69 kWh
of grid charging, often at peak prices, that goes straight back into
the house.

The cost is only the round-trip loss, roughly 20 kr (estimate). But
this looks like the inverter or the optimiser defending a floor it has
already passed, not a planned decision, and the SOC reading below the
minimum suggests the battery's SOC calibration drifts.

## Hour-of-day profile (local time)

Positive grid is import, negative is export. Positive battery is
charging, negative is discharging. Spot is ex VAT.

```
hr | spot  | grid W  | batt W  | grid->batt kWh | batt->grid kWh
 0 |  0.80 |  +4985  |  +1682  |      64.9      |       0.1
 1 |  0.78 |  +3587  |   +925  |      39.0      |       0.1
 2 |  0.73 |  +3516  |   +727  |      33.4      |       0.0
 3 |  0.75 |  +4349  |   +775  |      34.2      |       0.0
 4 |  0.75 |  +4532  |  +1227  |      42.4      |       0.0
 5 |  0.80 |  +4317  |  +1906  |      61.5      |       0.0
 6 |  1.05 |  +1884  |    +74  |      18.6      |       0.1
 7 |  1.31 |  +1153  |   -373  |      13.4      |       0.2
 8 |  1.42 |   +294  |  -1052  |       0.8      |       8.4
 9 |  1.35 |   +559  |   -542  |       8.7      |       5.5
10 |  1.22 |   +453  |   -350  |       3.8      |       0.2
11 |  1.12 |   +659  |    +96  |       8.1      |       0.2
12 |  1.07 |  +1256  |   +692  |      22.5      |       0.1
13 |  1.06 |  +1291  |   +490  |      17.2      |       0.2
14 |  1.10 |  +1854  |  +1074  |      38.6      |       0.1
15 |  1.33 |  +1008  |    +25  |      11.6      |       0.1
16 |  1.55 |   +496  |   -810  |       1.3      |       0.2
17 |  1.74 |   +313  |  -1301  |       0.0      |       0.8
18 |  1.76 |   +153  |  -1543  |       0.0      |       3.8
19 |  1.60 |   +208  |  -1355  |       0.0      |       1.9
20 |  1.39 |   +375  |  -1251  |       2.4      |       0.8
21 |  1.18 |  +1114  |   -932  |       8.0      |       0.3
22 |  1.02 |  +2850  |    -70  |      29.6      |       0.2
23 |  0.88 |  +4295  |  +1099  |      53.7      |       0.1
```

## Method notes and caveats

- Prices are the live template values, not the stale table in
  `README.md`: spot from `sensor.nord_pool_se3_aktuellt_pris` is ex VAT
  and multiplied by 1.25; energy tax 0.45, grid fee 0.765 high / 0.305
  low, trader fees 0.097, all incl VAT. Import and export prices are
  read from `sensor.nordpool_se3_inkl_skatt_o_nat` and
  `sensor.elexport_ersattning`, which have full coverage.
- The window is archived in `data/`: `2026-10.csv` (`analyze.py`
  input), `2026-10-sim.csv` (`simulate.py` input) and
  `2026-10-prices.csv` (`prices_1komma5.py` input). Each script takes
  the path as its first argument.
- Coverage: every series has 2981 of 2981 15-min buckets except the EV
  power. `sensor.zag064494_laddeffekt` and `sensor.zag064494_laddstatus`
  are missing from 2026-11-05 10:05 to 2026-11-10 04:05; the Zaptec
  integration was unavailable. Night loads of about 11.6 kW in that
  period look like EV charging. Because `laddstatus` was unavailable,
  the Battery hold automation released after 30 minutes, and EMS mode
  read Self-consumption, so idle battery in that period is the
  optimiser's doing. No spot backfill was needed.
- The 1KOMMA5 price sensors (`sensor.heartbeat_john_allberg_*`) have
  history only from 2026-10-22 05:30.
- The simulation works on 5-min samples averaged to 15 min, with house
  demand taken as grid power minus battery power. Inverter losses on
  battery flows are therefore counted as house load in every scenario.
  Grid import and export are netted per 15-min bucket.
- The battery model is fitted to this window: 0.200 kWh delivered per
  SOC point when discharging and 0.225 kWh in per point when charging
  (about 89 % round trip), SOC 8-98 %, 10 kW either way. With these
  constants the actual flows reproduce the actual end SOC to within 2
  points. The August constants (0.198 / 0.237) drift 140 points over
  this window and should not be reused for counterfactuals.
- The perfect-foresight optimum is a dynamic program over SOC in 1 %
  steps with known prices and load. During EV charging it holds the
  battery idle, like the Battery hold automation. It is an upper bound.
- The value of a hold is the optimum's marginal value of stored energy
  at the actual SOC at that moment. That is the value under the
  optimum's later use, not the actual later use.
- The plain self-consumption replay discharges to cover any import and
  charges only from PV surplus, which is the Sungrow default.

## Recommendation

1. The battery is earning about 300-340 kr a month, and it does so by
   arbitrage, not solar. The holds that look like waste are almost all
   correct, worth about 18 kr over the month in total. Disabling or
   overriding them would cost money.
2. 1KOMMA5's published price model has no time-of-use grid fee: a flat
   1.4375 SEK/kWh adder in all hours and both seasons. Raise it with
   1KOMMA5 and ask whether the planner uses the Vattenfall tariff. The
   measured cost of not using it is about 2 kr/day, roughly 60 kr/month
   until April.
3. The larger part of the gap (about 100 kr of 134) is charge and
   discharge timing, mainly midday charging at about 2.2 kr/kWh
   instead of night charging at about 1.7. Some of that is load
   forecasting no planner can fix. It is worth asking 1KOMMA5 about,
   but there is no lever for it in this house.
4. The near-empty bursts below 8 % are worth one support question to
   1KOMMA5 or Sungrow. Small in money, but they are not plan
   behaviour.
5. Fix the Zaptec data gap: with `laddstatus` unavailable the Battery
   hold cannot work, and the EV total is missing five days.
6. Re-run for December, a full winter month with more working days, to
   firm up the tariff-blindness figure.
