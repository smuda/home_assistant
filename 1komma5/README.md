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

| Component | ex VAT | incl VAT (x1.25) |
|---|---|---|
| Energy (Nord Pool spot) | spot | spot |
| Trader markup | 0 | 0 |
| Energy tax | 0.360 | 0.450 |
| Grid transfer, high tariff | 0.765 | 0.95625 |
| Grid transfer, low tariff | 0.305 | 0.38125 |
| Grid feed-in benefit (export) | 0.104 | 0.104 |

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
  (2026-07-15 15:15 -> 2026-08-01 00:00). Verdict in short: the summer
  behaviour is mostly spot-rational and grid-charging is net
  beneficial; the genuine risk is the winter time-of-use grid tariff,
  which is dormant in summer and so cannot be tested from this data.
  Re-run in Nov-Mar.
- `scripts/` -- the pull and analysis scripts, so any evaluation is
  reproducible. See below.

## Re-running

VictoriaMetrics is read-only reachable at `http://192.168.40.20:8428`
(no auth). The scripts shell out to `curl`.

```
cd 1komma5/scripts
python3 pull.py       # writes data.csv (14 days, 15-min steps)
python3 analyze.py    # totals, the two behaviours, hour-of-day profile
python3 dist.py       # grid-charge spot/hour distribution + winter what-if
```

Adjust `RANGE_DAYS` / `STEP` in `pull.py` for other windows. The
entity ids and sign conventions are documented at the top of each
script.
