# Installing the Sungrow SHx local Modbus integration

Step-by-step setup. Everything except the last VictoriaMetrics
step is done on the live Home Assistant instance; this repo does
not control `configuration.yaml`.

## Prerequisites (already verified)

- Modbus TCP reaches the inverter: `192.168.60.108:502` responds.
- The inverter LAN port is in use (the WiNet web UI on 8082 is
  closed), which gives the full register set and fast polling.

## 1. Fetch the package file onto HA

The integration is a YAML package, not a HACS integration. The
simplest path is the terminal in the "Advanced SSH & Web Terminal"
add-on (the same one used for `make deploy`):

```sh
mkdir -p /config/integrations
cd /config/integrations
wget -O modbus_sungrow.yaml \
  https://raw.githubusercontent.com/mkaiser/Sungrow-SHx-Inverter-Modbus-Home-Assistant/main/modbus_sungrow.yaml
```

## 2. Set the connection values in secrets.yaml

Do not edit the `modbus:` block in `modbus_sungrow.yaml`. The hub
reads everything through `!secret`, so the values go in
`/config/secrets.yaml` (create the file if it does not exist). The
package references six secrets, and every one must exist or the
config check fails. Add:

```yaml
sungrow_modbus_host_ip: 192.168.60.108
sungrow_modbus_port: 502
sungrow_modbus_wait_milliseconds: 5      # 5 for LAN port; 30+ for WiNet-S
sungrow_modbus_device_address: 1         # inverter unit/slave id
sungrow_modbus_sbr_device_address: 200   # battery modbus address; confirm for your model
sungrow_modbus_battery_max_power: 5000   # battery rated power in W; set to your model
```

The LAN port uses `wait_milliseconds: 5`; WiNet-S would need 30 or
higher. Keep every key present even if you refine a value later, or
the config check fails on a missing secret.

The two battery keys assume a Sungrow SBR/SBH battery, but this
system uses a Pylontech Force H3 over CAN:

- `sungrow_modbus_sbr_device_address: 200` — leave as is. It points
  at a Sungrow battery sub-device that does not exist here, so the
  per-module cell reads fail silently. Core battery data (SOC,
  power, voltage, current, SOH, temperature) is read from the
  inverter's own registers and works regardless.
- `sungrow_modbus_battery_max_power: 10000` — only bounds the
  manual charge/discharge control entity, so it is not critical for
  read-only telemetry. 10000 W matches the SH10RT inverter limit.

## 3. Load the package in configuration.yaml

Load the file as a single named package in
`/config/configuration.yaml`:

```yaml
homeassistant:
  packages:
    modbus_sungrow: !include integrations/modbus_sungrow.yaml
```

If a `homeassistant:` key already exists, add only the `packages:`
block under it; do not duplicate the key. Do not combine this with
`!include_dir_named packages` on the same line — pick one form. The
named-include form above loads the single file directly and does
not need a `packages/` directory.

## 4. Check config and do a full restart

- Developer Tools -> YAML -> Check Configuration (should be green).
- Then Restart. A full restart is required; Modbus and packages do
  not reload warm.

## 5. Verify the sensors came up

Developer Tools -> States, search `battery_level` and
`total_dc_power`. You should see state of charge (%), PV power (W),
charge/discharge power, and daily yield, among others. If
everything is `unavailable`, the host, port, unit id, or LAN/WiNet
setting is wrong.

## 6. Send the data to VictoriaMetrics (last step)

The new sensors do not reach VictoriaMetrics until they are listed
in the Prometheus filter. That lives in the `prometheus:` block of
the live `configuration.yaml` (source-of-truth mirror:
`metrics/hass/configuration.yaml`). The Sungrow entity ids are in
English (`sensor.total_dc_power`, `sensor.battery_level`, ...), so
they do not match the existing `sensor.*_effekt` /
`sensor.*_energi` wildcards and each needs an explicit
`include_entities` line.

Once the sensors are live, capture their exact entity ids from
Developer Tools -> States and add them to the filter, then reload
or restart HA so the export picks them up.

[install]: https://github.com/mkaiser/Sungrow-SHx-Inverter-Modbus-Home-Assistant/blob/main/doc/installation.md
