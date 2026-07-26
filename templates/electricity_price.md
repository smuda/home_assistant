# Electricity price template

Template sensors that compute the real cost of imported
electricity in price area SE3: the Nord Pool spot price plus energy
tax plus the time-of-use grid transfer fee, all including 25 % VAT.

Defined in `electricity_price.yaml`. See `README.md` in this
directory for how the templates are included and deployed.

## Why this exists

The house runs a battery whose charge/discharge is steered by an
external optimiser (1KOMMA5°) that plans against the Nord Pool spot
price alone. But an imported kWh actually costs spot plus a fixed
adder of about 0.94 kr/kWh — energy tax and grid transfer — that you
never get back when you export. A spot-only view is blind to that
asymmetry, which showed up in the data as the battery selling to the
grid at the morning spot peak and occasionally grid-charging at
expensive hours.

These sensors expose the true per-kWh import cost so automations (and
the human reading a dashboard) can reason about the price that is
actually paid, not just the raw spot.

## Sensors

| Entity | Role |
|---|---|
| `sensor.elnatsavgift_aktuell` | The grid transfer fee in effect right now. All the time-of-use and working-day logic lives here. |
| `sensor.nordpool_se3_inkl_skatt_o_nat` | Full imported-kWh cost. Reuses `elnatsavgift_aktuell` and adds spot + energy tax, so the tariff logic is not duplicated. The sensor's name is chosen so its slug is this entity id, which the Energy dashboard depends on — keeping the id reproducible from this repo on a clean reinstall. |

## How the tariff works

The grid transfer fee is time-of-use. It is HIGH only when all hold:

- month is January, February, March, November or December
- it is a working day
- the hour is 06:00–21:59

Otherwise it is LOW. The full price sensor is then simply
`spot + energy tax + grid fee`.

Component values (öre/kWh ex VAT → SEK/kWh incl VAT), from the
Vattenfall invoice:

| Component | öre ex VAT | SEK incl VAT |
|---|---|---|
| Energy tax | 36.0 | 0.45 |
| Grid, high tariff | 76.5 | 0.95625 |
| Grid, low tariff | 30.5 | 0.38125 |
| Trader markup | 0 | 0 |

Update the öre value in the template, not the incl-VAT product; the
template multiplies by 1.25.

## Working-day logic (holiday precision)

The grid company bills these weekday holidays as low tariff:
nyårsdagen, trettondedag jul, långfredag, annandag påsk, julafton,
juldagen, annandag jul, nyårsafton.

`binary_sensor.workday_sensor_se` (Workday integration, country Sweden)
is the single source of truth for working days, shared with other
automations. Verified against the `holidays` library it uses: within
the high-tariff months it flags exactly the grid company's list and
no extra days, including the moving Easter days.

Two exceptions: julafton (24 Dec) and nyårsafton (31 Dec) are not red
days in the holidays library, so they are added to the Workday
config's `add_holidays`. That option does not recur across years, so
each year is listed explicitly (currently through 2030) — extend it
in the Workday integration, not here, since the sensor is shared.

If `binary_sensor.workday_sensor_se` is missing or unavailable the
template falls back to a plain Mon–Fri check, so the price is never
left undefined. That fallback does not know about holidays; it is a
degraded path only while the sensor is down.

## Setup specific to this template

Add the Workday integration: Settings → Devices & services → Add
integration → Workday, Country = Sweden, with julafton and nyårsafton
in `add_holidays`. The directory-level include and restart are
covered in `README.md`.

## Assumptions to re-check if the invoice stops matching

- `sensor.nord_pool_se3_aktuellt_pris` is assumed to be
  VAT-inclusive. If the Nord Pool integration is set to exclude VAT,
  change `spot` to `spot * 1.25` in the template.
- `now()` makes Home Assistant re-render the templates every minute,
  so the 06:00 / 22:00 switch and the midnight workday flip take
  effect within a minute — no separate time trigger is needed.
