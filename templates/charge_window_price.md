# Charge-window mean price template

One template sensor, `sensor.elpris_medel_laddfonster`, giving the
mean all-in price of a kWh over a forward window of N hours, where N
is read from `input_number.elbil_laddfonster_timmar`.

Defined in `charge_window_price.yaml`. See `README.md` in this
directory for how the templates are included and deployed.

## Why it is separate

`sensor.nordpool_se3_inkl_skatt_o_nat` answers "what does a kWh cost
right now". A charging decision needs the other question: "what will
a kWh cost on average over the next few hours". The two will often
disagree, and that is the point -- at 13:00 on a sunny Saturday the
current price may be 90 ore while the next three hours average 78,
because the cheap stretch is ahead of you.

The sensor ships on its own and is useful on its own: put it on the
dashboard and watch how often it dips under a candidate EV-charging
threshold, and at what times of day, before any automation is armed.

## Value

The mean of the first `4 * N` entries of the price curve at or after
the current quarter-hour:

```
mean(serie[now_quarter : now_quarter + N hours])
```

The curve is the `today` and `tomorrow` attributes of
`sensor.elpris_serie_se3` (`electricity_price_series.yaml`), each an
array of `[epoch_ms, SEK/kWh]` at 15-minute resolution, already
all-in (spot + energiskatt + elnat + moms) with the grid tariff
computed per entry from that entry's own timestamp. Nothing is
recomputed here, so the tariff constants stay in one place.

Unit is SEK/kWh, matching every neighbouring price sensor.

## Window edges

- It starts at the CURRENT quarter-hour, not the next one: a charge
  started now pays for the quarter it is standing in. Quarter hours
  are aligned to the epoch (every timezone offset in play is a whole
  hour), so flooring the epoch to a 900 s boundary is the same
  instant as the local quarter-hour.
- It spans midnight by continuing into `tomorrow` when `today` runs
  out at 23:45. `tomorrow` is `[]` until the day-ahead prices release
  around 15-16, which is why the sensor goes `unknown` during the
  afternoon for the longer window settings.
- `now()` in the template makes HA re-render every minute, so the
  window advances on its own.

## Coverage guard

If fewer than `4 * N` entries remain, the sensor is `unknown` rather
than an average of a short window. That is the only check a consumer
needs: a number here always covers the full window, so no separate
interval count has to be inspected.

## The hours helper

`input_number.elbil_laddfonster_timmar` (1 to 8 h, step 1) lives in
`helpers/input_number/`. Changing it re-renders the sensor
immediately, no restart. It carries no `initial:`, so a value set on
the dashboard survives a restart; a fresh instance therefore comes up
at the minimum and wants setting to 3 once:

```sh
curl -X POST \
  -H "Authorization: Bearer $(tr -d '\r\n' < metrics/vmconfig/homeassistant-token)" \
  -H "Content-Type: application/json" \
  -d '{"entity_id":"input_number.elbil_laddfonster_timmar","value":3}' \
  http://homeassistant.local:8123/api/services/input_number/set_value
```

That reads the same token file the Makefile uses
(`HA_TOKEN_FILE`), so no credential ends up in shell history.
