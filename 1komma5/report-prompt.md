# Prompt: write the next 1KOMMA5 analysis

Feed this file to Claude when a new month is ready. It is a prompt,
not a script. Say which window, then let it work.

> Write the 1KOMMA5 analysis for <MONTH>, following
> `1komma5/report-prompt.md`.

## What the analysis is for

Two standing questions, plus whatever the month throws up:

1. Does the optimiser lose money by planning against raw Nord Pool
   spot while ignoring the grid transfer fee and the import/export
   asymmetry? Open until winter data exists.
2. What did the solar and the battery actually earn?

Read `README.md` for the price model before costing anything. Read the
two most recent `analysis-*.md` files: every report compares against
the previous one, and the numbers only mean something in sequence.

## Getting the data

1. Set `START` / `END` in `scripts/pull.py`. Absolute UTC, whole local
   days. Europe/Stockholm is UTC+2 in summer, UTC+1 in winter.
2. Run `python3 pull.py`, then `python3 analyze.py`.
3. VictoriaMetrics is at `http://192.168.40.20:8428`, read-only, no
   auth. It is a LAN host, so the agent sandbox blocks it; run these
   unsandboxed.

Before trusting any number, check coverage. Count samples per day per
column and look for gaps. Two failures have happened and will happen
again:

- VictoriaMetrics down. It stopped for eleven days in September 2026
  and nobody noticed. Nothing recovers those buckets except Home
  Assistant's recorder, which keeps about ten days -- so run
  `scripts/from_hass.py` while the gap is fresh, and archive the
  result under `data/`. Anything older is gone for good.
- The Nord Pool integration dropping out while everything else keeps
  reporting. `pull.py` backfills spot from elprisetjustnu.se
  automatically. It is calibrated: the Home Assistant sensor lags the
  published series by exactly one bucket. If you ever recalibrate,
  pick a day with full local coverage and compare offsets.

Say in the report which buckets were backfilled and from where.

## Method, and the traps in it

The scripts already implement all of this. Do not silently change it,
and do restate the shortcuts in the report.

- The PV/grid split is economic, not physical. A kWh that charged the
  battery while the house was importing counts as grid-sourced,
  because it did not reduce the bill. Sungrow's DC-side
  `total_battery_charge_from_pv` answers a different question and will
  tempt you into "correcting" figures that are already right. It is
  not the basis for costing. This mistake has been made once.
- Solar is valued at consumption time, not generation time. Energy
  into the battery is traced back out with a mixing model, so an
  evening kWh gets the evening price. That is the whole point of the
  battery and it is what makes the number feel real.
- Do not add the solar value and the battery P&L together. The
  battery's time-shift gain appears in both, seen from two sides.
- Generation is metered DC, prices apply AC, so generation is scaled
  by the window's own DC-to-AC ratio. It runs about 0.92.
- A single day's P&L is not meaningful if the battery ends fuller or
  emptier than it started. Check SOC at both ends of any window.
- Conversion losses are not charged against stored solar, and energy
  still in the battery at the close is not valued. Say so.
- No microproduction tax reduction. It has been withdrawn. Export
  earns spot + 0.104 and nothing else.

## Before blaming the price model

Load explains more than price does. Check EV sessions against any day
that looks bad: an unforecastable charge has already been mistaken for
a pricing error once, in August 2026. The charger reacts to Nord Pool
prices only and knows nothing about the panels or the battery.

When a sale looks expensive, bound it by battery headroom before
costing it. The battery holds roughly 19-20 kWh usable, about 0.198
kWh per SOC point discharging and 0.237 charging. It cannot have kept
more than it had room for, so the naive sold-then-re-imported overlap
is an upper bound, often close to double the real figure.

## Shape of the report

Follow the existing files. Sections, in order:

1. Window and totals, with a table and the EV total.
2. The two behaviours, grid-charging and selling to the grid.
3. What the battery earned. Marginal P&L table.
4. What the solar was worth. Consumption-time table.
5. Anything specific the month raises, as its own section.
6. What adder-blindness costs across the window.
7. The winter risk.
8. Hour-of-day profile.
9. Method notes and caveats.
10. Recommendation.

Then update `README.md`'s Contents entry for the new file, and adjust
the previous month's entry if this month changes how it reads.

## Writing

Project conventions in `../CLAUDE.md` apply and are not optional:
wrap at 72 characters, no em-dashes (use `--`), ASCII punctuation
only, and no bold or italics for emphasis in prose. Swedish words may
keep their accents.

State what the data shows. If a number is an estimate, an upper bound,
or rests on an assumption, say which in the sentence that uses it. If
something cannot be answered from the window, say that too rather than
reaching. The winter tariff question has stayed open across three
reports because summer cannot answer it, and saying so each time is
the correct outcome.
