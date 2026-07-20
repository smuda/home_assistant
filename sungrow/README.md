# Sungrow SHx local Modbus

Notes and source-of-truth for reading the Sungrow hybrid inverter
and battery into Home Assistant locally over Modbus TCP, so solar
and battery telemetry can be stored in VictoriaMetrics for analysis.

## What this is

A local integration of the Sungrow SH10RT inverter (LAN port,
Modbus TCP on 192.168.60.108:502) using the community package
[mkaiser/Sungrow-SHx-Inverter-Modbus-Home-Assistant][mkaiser]. It
exposes the inverter and battery as Home Assistant sensors, which
then flow to VictoriaMetrics through the Prometheus export.

The battery is a Pylontech Force H3 (20.4 kWh), connected to the
inverter over the CAN bus. Pylontech has approved this pairing;
Sungrow has not added it to their official compatibility list, but
it works in practice. The inverter reports battery state of charge,
power, voltage, current, state of health, and temperature through
its own Modbus registers regardless of battery brand, so all of
that reaches Home Assistant. Only the per-module cell registers
specific to Sungrow's own SBR/SBH batteries are unavailable, which
is expected and harmless.

See [INSTALL.md](INSTALL.md) for the step-by-step setup.

## Why local Modbus, not the 1KOMMA5° cloud

The primary goal is solar and battery data in VictoriaMetrics.
Reading Sungrow directly beats a 1KOMMA5° cloud integration for
that job:

- Local: no cloud dependency, no rate limits, no breakage when a
  reverse-engineered backend API changes.
- Higher resolution: the LAN port can be polled every few seconds.
- Full coverage: PV, battery, grid import/export, house load, and
  EMS control, all without a third party in the path.

The only thing the 1KOMMA5° cloud adds is the dynamic electricity
price, and that is already covered by the existing Nord Pool
integration. So no 1KOMMA5° integration is used.

## Data of interest

- Solar: PV power, per-string voltage/current, daily and total
  yield.
- Battery: state of charge, charge/discharge power, daily and
  total charge/discharge energy, temperature.
- Grid and load: import/export power and energy, house
  consumption.

## Deploy model

This repo is source-of-truth only; Home Assistant does not pull
from it. The Modbus package lives in the live HA config under
`/config/packages/`, and the Prometheus filter that lets these
sensors reach VictoriaMetrics lives in the live `configuration.yaml`
(mirrored here at `metrics/hass/configuration.yaml`). Edits are
applied on the running instance as described in INSTALL.md.

[mkaiser]: https://github.com/mkaiser/Sungrow-SHx-Inverter-Modbus-Home-Assistant
