# Export compensation template

One template sensor, `sensor.elexport_ersattning`, giving what you are
paid per kWh sent to the grid: Nord Pool spot plus a fixed 10.4
öre/kWh grid feed-in benefit (elnätsersättning).

Defined in `export_compensation.yaml`. See `README.md` in this
directory for how the templates are included and deployed.

## Why it is separate

It is the counterpart to the import cost in `electricity_price.md`,
but a distinct concern (what you earn vs what you pay), so it lives in
its own file. The Energy dashboard uses it as the return-to-grid
price.

## Value

```
spot + 0.104 SEK/kWh
```

The 10.4 öre is the grid feed-in benefit; change the constant in the
template if the contract changes. Spot is assumed VAT-inclusive, the
same assumption as the import sensors -- see `electricity_price.md`.
