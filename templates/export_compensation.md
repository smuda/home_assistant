# Export compensation template

One template sensor, `sensor.elexport_ersattning`, giving what you are
paid per kWh sent to the grid: Nord Pool spot plus a fixed 10.4
öre/kWh grid feed-in benefit (elnätsersättning), minus the trader's
per-kWh fees.

Defined in `export_compensation.yaml`. See `README.md` in this
directory for how the templates are included and deployed.

## Why it is separate

It is the counterpart to the import cost in `electricity_price.md`,
but a distinct concern (what you earn vs what you pay), so it lives in
its own file. The Energy dashboard uses it as the return-to-grid
price.

## Value

```
spot + 0.104 - 0.1185 SEK/kWh
```

The 10.4 öre is the grid feed-in benefit; change the constant in the
template if the contract changes. The 11.85 öre is the sum of the
per-kWh fees on the 1KOMMA5 sales invoice (Sep 2026: Svenska
Kraftnät 1.80, Nord Pool 0.06, balansansvar 9.99; Aug was 12.13).
They vary month to month, so update them from the latest invoice. Spot is used excl. VAT, which is
correct here: export compensation is paid without VAT, unlike the
import sensors (see `electricity_price.md`) which add 25 %.
