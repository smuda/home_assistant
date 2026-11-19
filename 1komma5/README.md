# 1KOMMA5 battery steering -- analysis

This directory holds evaluations of how the external 1KOMMA5
optimiser ("Heartbeat AI") steers the house battery, checked against
the actual VictoriaMetrics history rather than against intuition.

The optimiser plans battery charge/discharge against the Nord Pool
spot price. An imported kWh actually costs spot plus energy tax plus
a grid transfer fee, and an exported kWh only earns spot plus a small
feed-in benefit. A spot-only view is blind to that asymmetry, and in
winter it is also blind to the time-of-use grid tariff. The question
these analyses answer is whether that blindness costs real money, and
how much.

## Price model

These are the numbers every analysis in this directory is costed
with. They are the same values the live template sensors use, see
`../templates/electricity_price.md` (import cost) and
`../templates/export_compensation.md` (export pay). Invoice figures
are quoted ex VAT; the analyses use the incl-VAT column, since that
is what is actually paid.

| Component                     | ex VAT | incl VAT (x1.25) |
| ----------------------------- | ------ | ---------------- |
| Energy (Nord Pool spot)       | spot   | spot             |
| Trader markup                 | 0      | 0                |
| Energy tax                    | 0.360  | 0.450            |
| Grid transfer, high tariff    | 0.765  | 0.95625          |
| Grid transfer, low tariff     | 0.305  | 0.38125          |
| Grid feed-in benefit (export) | 0.104  | 0.104            |

Formulas, SEK/kWh incl VAT:

```
import = spot + 0.450 + grid           (grid = 0.95625 or 0.38125)
export = spot + 0.104
```

The high/low spread is therefore 0.575 SEK/kWh incl VAT. That spread
is the whole reason a spot-only optimiser can be wrong in winter: it
is invisible in the spot series.

### Grid tariff window

The grid transfer fee is high only when all three hold:

- month is November, December, January, February or March
- it is a working day
- the hour is 06:00-21:59

Otherwise it is low. Working day means
`binary_sensor.workday_sensor_se` (Sweden, with julafton and
nyarsafton added); the grid company bills weekday red days as low
tariff. Holiday details are in `../templates/electricity_price.md`.

Spot is assumed VAT-inclusive as delivered by the Nord Pool
integration. The 0.104 feed-in benefit is a flat grid-company
payment, not VAT-adjusted.

## Contents

- `analysis-2026-07.md` -- evaluation on 16.4 days of summer data
  (2026-07-15 15:15 -> 2026-08-01 00:00). Verdict in short: the solar
  is worth 33 kr/day and the battery nets 9 kr/day on top; the summer
  behaviour is mostly spot-rational and adder-blindness costs 5 kr
  over the window; the genuine risk is the winter time-of-use grid
  tariff, which is dormant in summer and so cannot be tested from this
  data. Re-run in Nov-Mar.
- `analysis-2026-08.md` -- full month, 31.0 days (2026-08-01 ->
  2026-09-01), covering the mid-month price spike. Verdict in short:
  the solar is worth 35 kr/day and the battery nets about 9 kr/day;
  grid-charging at 2.4 kr/kWh during the spike was correct arbitrage;
  the one bad day is an unforecastable 44 kWh EV charge, not a pricing
  error, and costs about 3 kr. The house turned net importer over the
  month on the back of the last five days. Winter still untested.
- `analysis-2026-10.md` -- full month, 31.0 days (2026-10-01 ->
  2026-11-01), all on the flat low tariff, with prices before 10-25
  recomputed on the current template formulas. Verdict in short: the
  battery nets about 9-11 kr/day, almost all arbitrage; 1KOMMA5
  captures 79 % of a perfect-foresight optimum, leaving 2.4 kr/day,
  and its holds cost only 9-18 kr because the day's prices barely
  moved. Its published price is spot plus a flat 1.4375 SEK/kWh, 0.59
  above the real low-tariff adder, but that cost only 2.6 kr. Does not
  carry over to winter.
- `analysis-2026-11-pre.md` -- preliminary, 2026-11-01 -> 2026-11-11
  (10.0 days, 7 working days). Verdict in short: 1KOMMA5 captures 64 %
  of the perfect-foresight saving, leaving about 10 kr/day. It does not
  fill the battery at night, tops up at midday at day prices, and on
  days that start full holds while importing and ends the day with
  charge left. Charging only at night would have been as good as
  charging any time. The flat price view explains 23 kr of the 98 kr
  gap. Its holds are a real loss here (34 kr), unlike October.
- `report-prompt.md` -- the prompt to hand Claude when writing the
  next month's analysis. Carries the method, the traps, and the
  conventions, so a new report does not re-derive them.
- `data/` -- archived windows, committed. Anything rescued from
  Home Assistant's recorder lands here, because that source expires
  after about ten days. `2026-10*.csv` are the October 2026 inputs to
  `analyze.py`, `simulate.py` and `prices_1komma5.py`.
- `scripts/` -- the pull and analysis scripts, so any evaluation is
  reproducible. See below.

## Re-running

VictoriaMetrics is read-only reachable at `http://192.168.40.20:8428`
(no auth). The scripts shell out to `curl`.

```
cd 1komma5/scripts
python3 pull.py       # writes data.csv for the window in START/END
python3 analyze.py    # everything: totals, the two behaviours, solar
                      # value, battery P&L, EV sessions, hour-of-day
                      # profile, winter what-if, spot distribution
```

Adjust `START` / `END` / `STEP` in `pull.py` for other windows. They
are absolute UTC timestamps, so a window is reproducible. `pull.py`
backfills spot from elprisetjustnu.se when the Nord Pool integration
has dropped out.

`analyze.py` takes an optional path, so an archived window is read the
same way:

```
python3 analyze.py ../data/2026-09.csv
```

The counterfactual comparison (plain self-consumption and a
perfect-foresight optimum replayed on the actual load, hold valuation,
1KOMMA5's published price inputs) has its own pull, at 5-min
resolution with the optimiser's control-state series:

```
python3 pull_sim.py         # writes sim.csv and prices.csv
python3 simulate.py         # scenario costs, holds, tariff agreement
python3 prices_1komma5.py   # decomposes 1KOMMA5's price sensors
python3 -m unittest test_simulate
```

The battery constants at the top of `simulate.py` are fitted to the
October 2026 window. Check its SOC-model line before trusting a new
window: if the model's end SOC drifts far from the actual, refit.

When VictoriaMetrics has missed a window entirely, `from_hass.py`
rescues it from Home Assistant's recorder into `data/`. That recorder
keeps roughly ten days, so it only works while the gap is fresh.

The entity ids and sign conventions are documented at the top of each
script.
