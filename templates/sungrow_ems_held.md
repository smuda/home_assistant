# Sungrow EMS held values

`sungrow_ems_held.yaml` defines two trigger-based template sensors
that the Zaptec fuse guard reads instead of the raw Sungrow
holding-register sensors. Why the guard needs them is in
[Battery grid charge](../automations/zaptec/README.md#battery-grid-charge).

| Entity                                                | What it is                                          |
| ----------------------------------------------------- | --------------------------------------------------- |
| `sensor.ems_mode_selection_raw_held`                  | `sensor.ems_mode_selection_raw`, held over failures |
| `sensor.battery_forced_charge_discharge_cmd_raw_held` | The forced charge/discharge command, held likewise  |

## Held values

The SH10RT refuses about 8% of holding-register reads with Modbus
exception 04, and HA then shows the raw sensor as `unavailable` until
the next poll (10 s). Input registers are not affected.

- While the raw state is a real value, the held value equals it.
  `0`, `204` and every other real value pass through at once.
- When the raw state goes `unavailable` or `unknown`, the held value
  keeps the last good value.
- After 15 s (the second poll failed too) it writes one warning to
  the HA log (logger `fuse_guard.hold`) naming the raw entity, and
  keeps holding.
- After 25 s (the third poll failed) the held value goes
  `unavailable`, and the guard fails safe (no battery discount).
- On HA start and on a template reload the held value is
  `unavailable` until the raw sensor has a real value, so a restored
  state from before the restart is never used.

The two timers are `for:` state triggers, not `last_changed` (a
failed read resets that). They sit halfway between polls, so poll
jitter cannot race them. On 2026-11-20 every dropout lasted 1 or 2
polls, none 3.

The battery hold and the overload notification keep reading the raw
sensors, on purpose.
