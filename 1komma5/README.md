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

The full price model lives in `../templates/electricity_price.md`
(import cost) and `../templates/export_compensation.md` (export pay).

## Contents

- `analysis-2026-07.md` -- first evaluation, on 10.7 days of summer
  data. Verdict in short: the summer behaviour is mostly spot-rational
  and grid-charging is net beneficial; the genuine risk is the winter
  time-of-use grid tariff, which is dormant in summer and so cannot be
  tested from this data. Re-run in Nov-Mar.
- `scripts/` -- the pull and analysis scripts, so any evaluation is
  reproducible. See below.

## Re-running

VictoriaMetrics is read-only reachable at `http://192.168.40.20:8428`
(no auth). The scripts shell out to `curl` because the sandbox blocks
Python's own socket layer but allows curl.

```
cd 1komma5/scripts
python3 pull.py       # writes data.csv (14 days, 15-min steps)
python3 analyze.py    # totals, the two behaviours, hour-of-day profile
python3 dist.py       # grid-charge spot/hour distribution + winter what-if
```

Adjust `RANGE_DAYS` / `STEP` in `pull.py` for other windows. The
entity ids and sign conventions are documented at the top of each
script.
