# Zaptec dynamic fuse protection

Home Assistant automation that throttles the Zaptec Go charge
current so the main fuse is never exceeded when the car charges at
the same time as other heavy loads (electric heating, washing
machine, etc.) on a winter day.

Crucially, it changes the current rarely -- frequent changes
make the car abort the session (see below).

## Why this exists

Zaptec has two independent layers:

1. [Available current
   mode](https://help.zaptec.com/using-products/charging-modes) -- *how*
   current is regulated:
   - Standard charging -- fixed allocation, no dynamic
     load balancing. *(This is what I run.)*
   - Scheduled charging.
   - Automatic charging (Zaptec Sense / APM) -- regulates
     current in real time against the household's total load and
     protects the main fuse, but starts charging immediately
     and therefore ignores cheap-hour timing.
2. [Eco
   Mode](https://help.zaptec.com/using-products/smart-charge-with-eco-mode)
   -- a separate feature layer on top of the mode
   above. It decides *when* to charge (departure time, distance,
   price area -> cheapest Nord Pool hours). *(I run Eco: ready by
   06:00, 100 km, my price area.)*

Real-time fuse protection only exists in *Automatic charging
(Sense)*, which would break my Eco timing. So I keep standard
charging + Eco for the timing and add fuse protection here in
Home Assistant. It works because the charger-level `max charge
current` entity can be written regardless of the active mode.

## Keep changes infrequent (important)

According to [Zaptec's own
documentation](https://docs.zaptec.com/docs/dynamic-load-balancing-with-the-zaptec-api):

> "Frequent changes to the charge current and phase may cause the
> vehicle to interrupt the charging session ... we recommend
> updating this setting no more than once every 15 minutes."

Changing the current every few seconds makes the VW ID.4 abort
the session, requiring a manual restart in the Zaptec app.
Repeated stop/start is also
[flagged by the
charger](https://help.zaptec.com/hc/en-001/articles/32342566434833-Warning-Charging-has-been-stopped-too-many-times)
("Charging has been stopped too many times", API warning
[`WARNING_MAX_SESSION_RESTART`](https://github.com/stekker/zaptec/blob/main/data/constants.json)).
The threshold is firmware-dependent: on Zaptec Go firmware 2.3 and
later roughly 20 restarts within an hour (or 20 plus one per hour
since the session began), below 2.3 roughly 20 per session. The
automation therefore:

- only changes when the new target differs by at least a
  deadband (3 A), and
- not more often than a minimum interval (15 min) for normal
  changes (a ramp is the one exception, see "Ramp"), and
- floors at 6 A rather than pausing for ordinary load swings, and
- allows one immediate reduction if a phase nears the fuse.

Net effect: the current typically changes only once or twice per
charging session, not continuously.

### Ramp

A raise bigger than `ramp_step` (4 A) is written in steps of at most
4 A, at least `ramp_interval` (115 s) apart. A cut is never ramped:
it is written in one step. Only the emergency cut skips
`min_interval`; a normal cut still waits `min_interval`, which counts
from the last ramp step. No write is ever below `ev_min` (6 A).

Why: on 2026-11-21 01:00:58 a 6 -> 16 A raise came while the
optimiser was grid-charging the battery. P1 phase 2 reached 37.8 A
on the 25 A fuse for about 30 s. The battery discount assumes the
optimiser gives way at once, but it reacts in a median 10 s, worst
31 s, and the 11-20 resumes held P1 at or above 25 A for 90-120 s.
The emergency cut misses it, because `ptot_max` excludes the
discounted battery.

Why +4 A: the expected spike is about 29-30 A, against 36-38 A for
one jump.

Why 115 s: just under 120 s, so a step lands on every second
one-minute run, and nearly 4x the worst observed optimiser reaction.

Why it is OK to break the 15-min rule here: 30 days of history,
50 charging runs, no session aborted, including bursts of six
changes in four minutes. evcc adjusts every 30 s by default, and
Zaptec's 15 min is a recommendation with no vehicle or threshold
named. The ramp is the one exception to the 15-min rule;
`min_interval` counts from the last ramp step. The deadband does not
apply to ramp steps (14 -> 16 is written).

The ramp is tracked by `input_boolean.zaptec_fuse_ramping`. A normal
raise bigger than `ramp_step` writes the first step and turns it on.
It turns off when `max_laddstrom` reaches the target, but only after
the charger's phase sensors (they update every ~2 min) have reported
since the last write: a stale reading overestimates household load,
and ending on it would make the next raise wait `min_interval`. It
also turns off at once on a cut (emergency or normal), a last-resort
stop or a pause. A flag older than the `laddstatus` `last_changed`
(an earlier session, or a status blip) is ignored and cleared; then
the normal rules apply.

### Last-resort stop (and auto-resume)

Flooring at 6 A only protects the fuse while 6 A of car current
actually fits under it. If non-car load on a phase is so high that
even 6 A would push that phase to/over the fuse, keeping the car at
6 A no longer helps -- the main fuse would trip for the whole
house, which can disrupt or damage computers and other
electronics. A controlled stop of the car is the lesser harm (same
probability, smaller consequence), so in that case the automation
presses stop once and sets the helper
`input_boolean.zaptec_fuse_paused`.

"Presses stop" is literal: it calls `button.press` on the charger's
`button.zag064494_stoppa_laddning` entity (the same action as the
Stop button in the Zaptec app). It does not set the charge
current to 0 -- that is not a stop, and the current is already
floored at the 6 A minimum. Resume is the matching
`button.zag064494_ateruppta_laddning` press.

It is a single, deliberate stop in a genuine emergency -- not the
rapid cycling that made the car abort. When household load falls
back below the threshold (with a small hysteresis), the automation
presses resume and clears the helper, so charging restarts
without manual intervention. The helper also lets it tell "we
paused for the fuse" apart from a normally finished charge, and is
cleared if the car is unplugged while paused, or if the car charges
again after a resume from outside HA (see "Resumed outside HA"
below).

Several guards keep this from becoming a rapid stop/resume cascade,
which can trip the charger's restart warning (see above) and abort
the car. A fuse-stop is now held a minimum time (`resume_min_hold`,
300 s) before auto-resume is allowed. A resume then imposes a short
re-stop lockout (`restop_lockout`, 30 s) before another stop can
fire. The resume hysteresis was widened (`resume_hyst` 2 -> 6 A) so
load must fall further below the stop threshold before resuming, and
the `laddstatus` trigger is debounced 10 s so a flickering status
does not re-evaluate the logic repeatedly. Together these damp the
flapping that would otherwise restart the session too often.
`resume_min_hold` (300 s) and `restop_lockout` (30 s) are
self-imposed values chosen for this house, not figures documented by
Zaptec.

Stop confirmation. A last-resort stop needs `must_stop` true for
`stop_confirm` (20 s). The timer is
`input_boolean.zaptec_fuse_stop_pending`: the guard turns it on when
`must_stop` first holds, off as soon as a run sees `must_stop`
false, and off after the stop. A `for: 20 s` trigger on it wakes the
guard when the time runs out.

Why: on 2026-11-20 `must_stop` held for 4-10 s at each stop while the
Sungrow readings and P1 disagreed (a 204 blip, a real stop that P1
had not caught up with yet, a dropout). The longest was about 7 s
with the hold in place. 20 s rides through that, and a 25 A gG fuse
must carry 1.25 x In for its conventional time, so 20 s at these
currents is harmless to the fuse. The 24 A emergency cut stays
immediate.

Limitations: the guard only sees `must_stop` on its runs, so a dip
between runs does not reset the timer (the stop is then
conservative, not late). `mode: single` drops a re-check that
arrives while another run is in progress; the stop then waits for
the next trigger, at most the minute tick. The `for:` timer and
`now()` use different clocks, so the re-check can read 19.99 s; its
trigger id (`stop_confirm`) therefore counts as confirmed. If
`input_boolean.zaptec_fuse_stop_pending` is missing, `stop_pending`
never turns on and the last-resort stop cannot fire; the helper must
be deployed with the automation (accepted risk).

Resumed outside HA. While `input_boolean.zaptec_fuse_paused` is on,
the stop and current-write steps do not run. On 2026-11-18 04:14 UTC
a human pressed resume in the Zaptec app during a fuse pause (#32)
and the guard could neither stop nor lower the car until load fell
enough to resume.

The guard clears the flag when `laddstatus` is
`connected_charging` and its `last_changed` is later than the flag's.
The comparison keeps the flag on during the cloud lag right after our
own stop, when `laddstatus` can still read `connected_charging` from
before.

It only clears the flag; later runs stop or limit as usual. A manual
resume does not override fuse protection: if `must_stop` still holds,
the guard stops the car again after `stop_confirm` and
`restop_lockout` (counted from the flag's `last_changed`, so from the
clear), plus up to a minute or two more because the next run comes
on the minute tick. Battery hold is unaffected: it holds while
`laddstatus` is `connected_charging` whatever the flag says.

Limitations: if someone resumes before the cloud has shown our stop
(`laddstatus` never leaves `connected_charging` in HA), its
`last_changed` stays older than the flag's, so the flag is not
cleared and the guard stays blind until load falls enough to resume
or the car is unplugged. Accepted: it needs a resume within the
cloud lag of our stop (minutes), and the 2026-11-18 resume came 11
minutes in. The car is at 6 A meanwhile. The clear is a state check
on every run, not a one-shot trigger on the transition, so a dropped
run (`mode: single`) or a restart cannot lose it. The cost: any
`laddstatus` change that ends in `connected_charging` after the flag
counts, for example a blip through `unavailable` during the lag. If
`must_stop` still holds, the guard stops again; otherwise the car
can stay stopped, a lost charge, not a fuse risk.

## How it works

For each phase:

```
other_load = P1_phase_current - charger_phase_current   (>= 0)
headroom   = (fuse - margin) - other_load
```

The lowest phase headroom wins (safe whether the car charges on
one phase or three). The result is floored to whole amps and clamped
to the car's 6-16 A window -> `raw_target`.

Each evaluation picks one action, in priority order:

1. Clear the pause helper if the car is unplugged while paused, and
   Floor start once it has been unplugged for `floor_start_delay`
   (60 s).
2. Clear the pause helper (and nothing else) if we are paused and
   the car is charging again, with `laddstatus` changed after the
   helper (resumed from outside HA).
3. Resume (press resume, clear helper) if we are paused and load
   has fallen so `other_load + 6 A <= fuse - resume_hyst`, and the
   stop has been held at least `resume_min_hold` (300 s).
4. Stop (press stop, set helper) if not paused, charging, even 6 A
   would breach the fuse (`other_load + 6 A >= fuse`), that has held
   for `stop_confirm` (20 s), and at least `restop_lockout` (30 s)
   has passed since the last resume.
5. Set the max charge current to `raw_target`, capped at
   `current + ramp_step`, if not paused, charging, and either
   `|raw_target - current| >= deadband` and `min_interval` has passed
   (normal path), or a phase is `>= emergency_phase` (24 A) and a
   reduction is needed (safety path, bypasses the interval), or a
   ramp is in progress, `ramp_interval` has passed and the target is
   above the current (ramp step: write
   `min(raw_target, current + ramp_step)`, no deadband or
   `min_interval`). See "Ramp".
6. Floor start: write `ev_min` if not paused, `laddstatus` has read
   `disconnected` for `floor_start_delay` (60 s) and
   `max_laddstrom` is not already 6 A. See "Do not disturb Eco
   Mode".

Evaluated once a minute, on charge-status changes, immediately
when a phase crosses 23 A, or when
`binary_sensor.p1_sustained_overload` turns on. It runs only while
actually charging (`connected_charging`), while the fuse-pause
helper is on (so resume can be evaluated), while a stop is pending,
or while disconnected with `max_laddstrom` not at 6 A (Floor start)
-- never while `connected_requesting` (see Eco Mode below).

### Do not disturb Eco Mode

Writing the charger's max current
[overrides Zaptec's load
balancer](https://docs.zaptec.com/docs/dynamic-load-balancing-with-the-zaptec-api).
[Eco
Mode](https://help.zaptec.com/using-products/smart-charge-with-eco-mode)
is observed to be suspended by such a write as well. That is
community knowledge, not a documented API contract: no Zaptec source
states the mechanism. The closest
third-party statement is that external current control and Eco Mode
cannot be active at the same time
([Futurehome's Zaptec integration
docs](https://support.futurehome.no/hc/en-no/articles/360055610911-Zaptec)).
Eco Mode is what delays charging to the cheap night hours. If a
write while the car is waiting suspends Eco, the session charges
immediately at the wrong (expensive) time, so the automation is
written as if it does.

One test says a write while disconnected is harmless. On 2026-11-21
`max_laddstrom` was set 16 -> 6 A over the HA REST API with the car
disconnected. At the next plug-in the car waited about 6 h in
`connected_requesting` for Eco Mode and started at about 6 A (about
4 kW). A write while disconnected did not suspend Eco that time; it
is a single data point.

So the automation writes while a charge is under way
(`connected_charging`), plus the Floor start while disconnected. It
never writes while `connected_requesting`, so Eco Mode keeps full
control over when to charge; this automation limits the current
once Eco has started a session.

Floor start: once the car has been unplugged for `floor_start_delay`
(60 s), the automation sets `max_laddstrom` to `ev_min` (6 A). Every
session then starts at 6 A and the Ramp takes it up, instead of the
car drawing the stored max until the first in-session evaluation.
The delay skips the few-second `disconnected` blips seen at plug-in,
just before `connected_requesting`. The check is level-triggered by
the once-a-minute trigger, so a failed write is retried and a change
to `max_laddstrom` while unplugged is undone within a minute. It
also needs `max_laddstrom` to hold a number: an unavailable entity
would read as 0 A and make the guard write every minute.

There is no installation-level `AvailableCurrent` entity available
on this account (charger-level permissions only), so
`max_laddstrom` is the only lever.

### Noise filtering (avoids false stops)

The stop and 24 A emergency paths react to the meter reading, so a
transient spike from the P1 meter (a one-sample blip while the car
draws far less) could otherwise trigger a false stop -- the very
abort we are trying to avoid. To prevent that, `P1_phase_current`
above is read from filtered sensors
(`sensor.p1_fas_{1,2,3}_filtrerad`, see
`../../sensors/p1_filtered_sensors.yaml`):
a 20-second moving average dilutes a one-sample spike below the
stop and emergency thresholds while still tracking real, sustained
load. The normal current-adjustment path is already noise-tolerant
via its deadband and 15-minute interval.

The charger's own current (`c1..c3`) is deliberately read raw
(`sensor.zag064494_strom_fas_{1,2,3}`), not filtered. The Zaptec
sensor updates via the cloud only every few minutes, and a `filter`
sensor recomputes only when its source updates, so a filtered
charger value shows the previous reading for a whole update
interval. Right after a charge starts it still read 0 A, so the
car's own ~15 A was counted as household load and the automation
fuse-stopped the car every time it resumed (observed 2026-10-11).
The raw value is capped at `number.zag064494_max_laddstrom`: the
car cannot draw more than the commanded max, so a reading stuck
high after a reduction cannot hide household load. Because that cap
drops the moment a reduction lands, while the filtered P1 still holds
up to 20 s of the old car current, the stop decision alone uses the
lower of filtered and raw P1 per phase; otherwise that lag would read
as household load and false-stop the car.

Fail-safe on meter loss. The Home Assistant `filter` platform
keeps emitting its last value when its source stops updating, so a
frozen filtered sensor can read numeric-but-stale. The automation
therefore judges the feed's *liveness* from the raw meter's
`last_reported` (it advances on every meter push, even an unchanged
value; no push for `max_age` seconds means the feed is dead). If the
feed is dead, the phase's non-car load is set to `failsafe_other`
(18 A), which floors the car to 6 A -- a meter dropout is never read
as zero load (which would wrongly allow the full 16 A). If even the
raw meter is gone, the same fail-safe applies. The wake-up trigger
still watches the raw
meter for a fast surge; only the decision uses the filtered values.
See "Filtered P1 sensors" under setup below.

The `outlier` filter is deliberately not used: it can reject a
*genuine* large load step (above its radius) indefinitely, hiding
real load -- a fail-unsafe blind spot for a fuse guard. The moving
average has no such failure mode.

### Battery grid charge

The 1KOMMA5 optimiser grid-charges the house battery at about
9.7 kW (~14 A per phase). The fuse guard ignores that charge while
the optimiser is in control: `sensor.ems_mode_selection_raw` is 3
(External EMS) and `sensor.battery_forced_charge_discharge_cmd_raw`
is 170 (the `Forced charge` command). The battery's per-phase share
(`sensor.battery_charging_power` / 3 / 230 V, capped at 10 kW) is
subtracted from the other load, so the car gets the headroom and the
battery takes what is left. The
estimate is slightly below the real grid draw, which errs on the safe
side. Data 2026-10-15 to 11-18 shows the optimiser holds the highest
phase at about 25.6 A on P1 and cuts the battery within a median 10 s
(worst 31 s) when load rises. It never sustained an overload; the
only full-power run over the fuse for minutes was our own Forced-mode
charge.

Fallback: `binary_sensor.p1_sustained_overload` (templates/) turns on
when the highest raw P1 phase is at or above 27 A for 60 s, meaning
the battery is not yielding. The guard then counts the battery as
household load again, as before, and stays that way for 60 min after
the overload ends, so the fuse cools down. After that the guard uses
the discount again. This retry is by design, with no latch: the
optimiser's battery control runs on the local 1KOMMA5 Heartbeat box
(a gridX gateway on the LAN, Modbus TCP to the inverter), not in the
cloud. If the box dies, the External EMS heartbeat (13080 = 12 s)
lapses, the mode leaves 3 and the discount turns off by itself. A box
that is alive but not yielding is a faulty or misbehaving component;
it costs at most one 60-120 s overload pulse per hour.
`Overload_notify.yaml` sends a phone notification each time the
sensor turns on. The sensor turning on also triggers the guard at
once. If the overload sensor is not `off` there is no discount.

The guard reads the EMS mode and command from held copies
(`sensor.ems_mode_selection_raw_held`,
`sensor.battery_forced_charge_discharge_cmd_raw_held`, see
[the held values](../../templates/sungrow_ems_held.md)). The
inverter sometimes refuses a holding-register read, so a raw sensor
goes `unavailable` for a poll or two. Each dropout ended the discount
while P1 still carried the battery's ~14 A per phase, which caused
the fuse-stops of #44. A held copy keeps the last good value for 2
failed polls and then goes `unavailable`, which ends the discount as
before. The dropout figures and timers are in that file.

Check the first nights with the car charging under mode 3/170: the
data never showed the optimiser absorbing a 6 -> 16 A car step.

## Entities used

| Entity                                   | Role                                                 |
| ---------------------------------------- | ---------------------------------------------------- |
| `number.zag064494_max_laddstrom`         | Control -- max charge current, 0-16 A, step 1        |
| `button.zag064494_stoppa_laddning`       | Control -- stop charging (last resort)               |
| `button.zag064494_ateruppta_laddning`    | Control -- resume charging                           |
| `input_boolean.zaptec_fuse_paused`       | Helper -- set while paused for the fuse              |
| `input_boolean.zaptec_fuse_stop_pending` | Helper -- must_stop is true, stop confirmation timer |
| `input_boolean.zaptec_fuse_ramping`      | Helper -- a ramp is in progress                      |
| `sensor.zag064494_strom_fas_1..3`        | Charger's own current per phase                      |
| `sensor.zag064494_laddstatus`            | Charge status (`connected_charging`, ...)            |
| `sensor.p1_meter_strom_fas_1..3`         | Household total current per phase (incl. the car)    |
| `sensor.p1_fas_1..3_filtrerad`           | Filtered P1 current used by the stop/emergency logic |

`ZAG064494` is the Zaptec Go (device type "Apollo"); network is
`tn_3_phase`, installation type "Smart". The 16 A cap is the
installer-set installation limit and cannot be raised in the app.

### Required helper

`helpers/input_boolean/zaptec_fuse_paused.yaml` (repo root) defines
the toggle, and the filename is the object id:
`input_boolean.zaptec_fuse_paused`. It is loaded via
`input_boolean: !include_dir_named helpers/input_boolean/` in
`configuration.yaml` and shipped by `make deploy`, which also calls
`input_boolean.reload`. Note that `deploy-helpers` syncs with
`--delete`: moving or renaming this file in the repo without
repointing the include first removes the entity on the live host, and
the automation reads its `last_changed` unguarded. The automation uses
it to remember a fuse-pause so it can resume automatically and not
confuse that with a normally finished charge; its `last_changed` is the
stop/resume timestamp, so nothing else should toggle it.

`helpers/input_boolean/zaptec_fuse_stop_pending.yaml` defines the
stop-confirmation timer, `input_boolean.zaptec_fuse_stop_pending`,
loaded and deployed the same way. Its `last_changed` is when
`must_stop` first held, so nothing else should toggle it. It sets
`initial: false` so a pending stop from before a restart never
counts toward the 20 s.

`helpers/input_boolean/zaptec_fuse_ramping.yaml` defines the ramp
flag, `input_boolean.zaptec_fuse_ramping`, loaded and deployed the
same way. Its `last_changed` is compared with that of
`laddstatus`, so nothing else should toggle it. It sets
`initial: false` so a ramp never survives a restart.

### Filtered P1 sensors

`sensors/p1_filtered_sensors.yaml` (repo root) defines three `filter`
sensors that clean the P1 phase currents (a 20-second moving
average). They are platform sensors, not automations, loaded via
`sensor: !include_dir_merge_list sensors/` in `configuration.yaml`
and shipped by `make deploy`. Changing them needs a Home Assistant
restart, not just an automation reload.
Confirm the resulting entity ids are `sensor.p1_fas_1_filtrerad`,
`_2_`, `_3_` (Home Assistant derives them from the friendly names).
Until they exist the automation falls back to the raw P1 sensors.

## Battery hold

The 1KOMMA5 optimiser's grid charge of the house battery (~9.7 kW,
~14 A per phase) used to count as household load, so the fuse guard
floored the car at 6 A. The fuse guard's only lever is the car
current, so the battery always won. In the optimiser's
self-consumption windows the battery would also cover the car at
~10 kW, spending grid-bought charge on it.

The fuse headroom part is now the fuse guard's job; see
[Battery grid charge](#battery-grid-charge).

`Battery_hold.yaml` now has one job: stop the battery discharging
into the car in the optimiser's self-consumption windows
(`sensor.ems_mode_selection_raw` 0), where it would spend stored
charge on the car. Fuse headroom for the optimiser's grid charge is
the fuse guard's job (above). While the car charges (hold condition
below) it takes the battery out of the optimiser's control and
writes, in this order:

1. `select.battery_forced_charge_discharge` to `Stop (default)`.
2. `select.ems_mode` to `Forced mode`, but only once
   `sensor.battery_forced_charge_discharge_cmd_raw` reads 204 (0xCC,
   Stop).

It never fights External EMS. Neither the hold nor the release
writes while `sensor.ems_mode_selection_raw` is 3, checked live on
each of the three writes, so a takeover between them stops the rest.
The test is `!= '3'`, so an unknown/unavailable raw sensor still
writes and a Modbus blip does not skip the hold. Releasing is gated
too: writing Self-consumption over a running External EMS knocks the
optimiser out of control for no gain.

Seen 2026-11-18 (logbook): when the optimiser wants to grid-charge it
wrote External EMS + the `Forced charge` command within about 10 s
of every hold write, so the hold lost every round and only churned
the registers.
In self-consumption windows the hold won and held (01:49-02:45 UTC).
The optimiser also takes control back from Forced mode by writing
External EMS itself when its plan says so (02:45, 04:00), so a
healthy optimiser does overwrite Forced mode, and the hold now lets
it. Capping the power limits (33046/33047) did not work either: the
optimiser writes them itself and rewrote them within ~10 s (seen
2026-10-25, #10/#11).

The order matters: the command select can sit at `Forced charge`, and
Forced mode first would start a grid charge. A Stop write can be
skipped (unavailable entity) or refused without an error, hence the
gate. It reads the raw sensor because the select maps unknown values
to `Stop (default)`. Otherwise it writes only
`select.ems_mode` to `Self-consumption mode (default)`. It never
writes External EMS (that needs a live heartbeat, 13080 = 12 s, which
the optimiser sets itself) and never a `number.*` entity.

The hold condition is `sensor.zag064494_laddstatus` is
`connected_charging`, or `input_boolean.zaptec_fuse_paused` is on, or
the pause helper changed less than `hold_after_pause` (600 s) ago. The
pause helper is included because a fuse-stop shows
`connected_finished`, the same as a full car; releasing then would
block the resume. The 600 s hold exists because the fuse guard
decides to resume against the idle battery, and `laddstatus` lags
minutes behind in the cloud, so the guard does not run again until it
reads `connected_charging`. Releasing at the resume would put the
battery back on top of the restarting car while nothing watches the
fuse.

- The battery is idle during a fuse pause too, unless the optimiser
  is in External EMS, where the hold writes nothing. That loses the
  fuse support the battery covering the house would give; decided
  and accepted.
- Daytime PV surplus is exported while the battery is held; decided.
- There is no watchdog if HA dies mid-hold: the battery stays idle,
  as long as nothing else rewrites the command register, until HA is
  back and the hourly run releases it. One idle battery day is
  accepted.
- It writes three times, 30 s apart, on every transition, hourly and
  when `sensor.ems_mode_selection_raw` has been 0 for 30 s (the
  optimiser's window ended mid-charge; the 30 s skips its own brief
  0 -> 3 flips).
  Refused writes are silent. An unknown/unavailable `laddstatus`
  skips the run for its first 30 min; after that the hourly rewrite
  releases. That does not cover `laddstatus` or the pause helper
  stuck at a hold value, or missing altogether.
- There is no `/15` rewrite after the window boundaries: the
  optimiser overwrites Forced mode when it wants control, and the
  mode-0 trigger re-applies the hold when it hands control back.
- It is a separate automation because the fuse guard's
  `charging or is_paused` condition would block the release.

To verify, read `sensor.ems_mode_selection_raw` while the car
charges. Not `select.ems_mode`: it shows unknown raw values as
Self-consumption.

- 2 (Forced): the hold is in force, and `sensor.battery_power`
  should be about 0.
- 3 (External EMS): the optimiser has taken over, which is normal.
  With command raw 170 it grid-charges the battery, and the busiest
  P1 phase should settle around 25.6 A while the car still gets the
  fuse guard's headroom.
- 0 (Self-consumption) for more than about a minute: the hold
  should have re-applied; check the automation's trace.

After the car is done it should read 0 or 3.

Caveat: disabling the automation while held leaves Forced mode in
place. Restore by hand with `select.select_option`
`Self-consumption mode (default)` on `select.ems_mode` ("Egen
forbrukning" in iSolarCloud).

When first deployed, the old caps are not undone: set
`number.battery_max_charge_power` and
`number.battery_max_discharge_power` to 10600 by hand if the car was
charging at the time.

## Eco Mode nudge

`Eco_mode_nudge.yaml` is the odd one out here: it only watches and
notifies, and never writes to the charger. When the car is plugged
in, Eco Mode either starts charging at once or holds the session in
`connected_requesting` until the cheapest hours before its 06:00
"ready by" deadline. Home Assistant cannot override that hold (a
charger write would suspend Eco; see "Do not disturb Eco Mode"
above), but tapping "Start charging" in the Zaptec app does. The
nudge tells a human when a hold is worth that tap and leaves the
decision, and every charger action, to them.

It fires when `sensor.zag064494_laddstatus` has been
`connected_requesting` for two minutes (`for: "00:02:00"`). The delay
is load-bearing: when Eco decides to start at once the status passes
through `connected_requesting` in a few seconds (seen 2026-09-20), so
without the wait every plug-in would notify pointlessly. Two minutes
means Eco is genuinely holding.

It then compares the import cost now against the cheapest charging
window still ahead, in the automation's `variables:` (no template
sensor; nothing else needs the number):

```
gap = price_now - min(mean import cost over any N-hour window that
                      starts at or after now and ends by the horizon)
```

- The curve is the `today` and `tomorrow` attributes of
  `sensor.elpris_serie_se3` (`../../templates/`), each
  `[epoch_ms, SEK/kWh]` at 15-minute resolution, full import cost.
- N is `input_number.elbil_laddfonster_timmar`, the same window-length
  helper the charge-window price sensor reads. The backtest showed
  window length moves the median gap by about 3 ore, so there is no
  second knob.
- It notifies only when `gap` is below
  `input_number.elbil_laddpris_gap` (SEK/kWh). A negative gap -- now is
  already the cheapest -- is below the threshold too, so it notifies.
- The horizon is 06:00, or the end of the published series if that is
  earlier. Before tomorrow's prices are out the series ends at 24:00
  today, so a midday plug-in searches up to midnight.
- It fails quiet. If not even a full N-hour window fits before the
  horizon, or the current quarter-hour is missing, it sends nothing
  rather than a misleading number.

The notification goes to `notify.parents` in Swedish, naming the price
now, the cheapest window's mean price and start time, and the gap in
ore/kWh. Its wording suggests and never claims a charge started -- the
automation has started nothing and cannot know whether anyone acts. It
carries a `URI` action deep-linking to the Zaptec app
(`https://portal.zaptec.com/app/config/x`), so it is one tap from the
notification to the override.

One nudge per plug-in: the trigger fires once on entering the hold and
there is no periodic re-check, so a price that falls further during a
long hold stays quiet. Add a `time_pattern` trigger later if that
proves too quiet in practice.

The deadline here is 06:00, the live Eco "ready by" time (above, and
the fuse guard's README). The issue's summer backtest used a 07:00
horizon and a G = 0.50 threshold giving roughly two nudges a month; in
winter the high grid tariff from 06:00 to 22:00 keeps evening gaps
above about 0.46 SEK/kWh, so expect few nudges from November to March.

### Required helper

`helpers/input_number/elbil_laddpris_gap.yaml` (repo root) defines
`input_number.elbil_laddpris_gap`, the smallest saving worth a nudge,
loaded via `input_number: !include_dir_named helpers/input_number/` in
`configuration.yaml`. Like the other helpers it has no `initial:`, so
a fresh instance comes up at `min` (0); set it to 0.50 once after the
first deploy:

```
input_number.set_value, entity elbil_laddpris_gap, value 0.50
```

## Configuration

Edit the `variables` block in `Dynamic_fuse_protection.yaml`:

- `fuse` -- main fuse, amps per phase. Currently 25.
- `margin` -- safety headroom, amps. Currently 3 (effective cap
  22 A/phase). Covers control latency and the gap between the rare
  normal updates.
- `deadband` -- minimum change in amps before writing. 3.
- `min_interval` -- minimum seconds between normal changes. 900
  (15 min, per Zaptec). Lower to e.g. `300` (5 min) if 15 min feels
  too sluggish; safety still rests on the emergency path.
- `ramp_step` -- largest raise in one write, amps. 4. See Ramp
  above.
- `ramp_interval` -- minimum seconds between ramp steps. 115. See
  Ramp above.
- `emergency_phase` -- any phase at/above this (amps) forces an
  immediate reduction regardless of the interval. 24 (1 A below
  the fuse).
- `resume_hyst` -- extra amps non-car load must fall below the stop
  threshold before resuming, to avoid stop/resume flapping. 6.
- `resume_min_hold` -- minimum seconds a fuse-stop is held before
  auto-resume is allowed, so a stop is not undone immediately. 300.
- `restop_lockout` -- minimum seconds after a resume before another
  stop may fire, damping a stop/resume cascade. 30.
- `max_age` -- seconds without a raw P1 update before the feed is
  treated as dead and the fail-safe kicks in. 60.
- `failsafe_other` -- assumed non-car load per phase (amps) when P1
  is dead; 18 floors the car to 6 A without forcing a stop. 18.
- `batt_max_w` -- SH10RT charge rating in watts, caps a bad battery
  power reading. 10000.
- `nominal_v` -- volts used to turn battery watts into per-phase
  amps. 230.
- `ev_min` / `ev_max` -- 6 and 16 (do not exceed the installer cap).
- `floor_start_delay` -- seconds `laddstatus` must read
  `disconnected` before Floor start writes `ev_min`. 60.

The moving-average `window_size` for the noise filter lives in
`sensors/p1_filtered_sensors.yaml`, not here.

The battery hold has its own `variables` block in
`Battery_hold.yaml`:

- `hold_after_pause` -- seconds the hold is kept after the pause
  helper changes. 600.

## Caveats

- Cloud-based control. The Zaptec HA integration
  (`custom-components/zaptec`, HACS) talks to the Zaptec cloud, so
  changes take seconds. Combined with the 15-min normal cadence,
  the car can sit above the ideal current for a while if load
  creeps up without reaching 24 A; the margin and the fuse's own
  time-current curve cover that. The 24 A emergency path is the
  fast safety net.
- Stop only as a last resort. For ordinary load swings it never
  pauses -- it floors at 6 A -- because frequent stop/start is what
  makes the car abort. It stops *only* when even 6 A would breach
  the fuse, i.e. when not stopping would trip the whole-house main
  fuse anyway. That is a single deliberate stop, and it auto-resumes
  when load falls, so it does not reintroduce the abort problem.
- Filter lag is deliberate. The moving average means the stop and
  emergency paths react to a sustained load a few seconds late rather
  than to an instantaneous spike. That is safe: the fuse tolerates
  brief overcurrent (its time-current curve) and the margin absorbs
  the rest, while the gain is immunity to false stops.
- Eco Mode coexistence. Because writing the charge current is
  observed to suspend Eco Mode, the automation never writes while
  `connected_requesting` and never pre-empts a waiting session.
  Floor start sets 6 A while the car is unplugged, so every session
  starts low. The 2026-11-21 test (see "Do not disturb Eco Mode")
  showed no Eco suspension from a write while disconnected, but it
  is a single data point. If a later session charges at plug-in
  instead of waiting, Floor start is the suspect.
- Mode is not visible in HA. The integration exposes no entity
  for the available-current mode or Eco Mode (custom-components/zaptec
  [issue #153](https://github.com/custom-components/zaptec/issues/153)),
  so Eco cannot be read or toggled from HA -- it
  is set in the Zaptec app. Standard charging + Eco is assumed.

## Testing

0. Deploy `sensors/p1_filtered_sensors.yaml` (`make deploy`), restart,
   and confirm `sensor.p1_fas_{1,2,3}_filtrerad` exist and track the
   raw P1 sensors (smoother, not stuck).
1. Plug in and start charging; confirm `max_laddstrom` settles at
   a sensible value.
2. Turn on a heavy load on the constrained phase (phase 3 here) and
   confirm the current steps down -- once, after the deadband is
   exceeded -- rather than oscillating.
3. Confirm no phase in `sensor.p1_meter_strom_fas_*` exceeds the
   fuse, and that the session does NOT abort.
4. To exercise the last-resort path, drive non-car load on one phase
   above ~19 A while charging: confirm the car stops once, the
   helper turns on, and that it resumes (helper off) when the load
   drops. Do this deliberately, not repeatedly.
5. Only after this holds across a real winter day, consider the
   formal fuse downgrade 25 A -> 20 A (set `fuse: 20`).

## References

- Zaptec -- dynamic load balancing API (15-minute update guidance;
  maxChargeCurrent overrides the load balancer):
  https://docs.zaptec.com/docs/dynamic-load-balancing-with-the-zaptec-api
- Zaptec -- Warning: Charging has been stopped too many times
  (restart thresholds, firmware-dependent):
  https://help.zaptec.com/hc/en-001/articles/32342566434833-Warning-Charging-has-been-stopped-too-many-times
- Zaptec API constants including `WARNING_MAX_SESSION_RESTART`
  (third-party client copy):
  https://github.com/stekker/zaptec/blob/main/data/constants.json
- Zaptec -- API usage guidelines:
  https://docs.zaptec.com/docs/api-usage-guidelines
- evcc -- interval (adjusts every 30 s by default):
  https://docs.evcc.io/en/reference/configuration/interval
- Zaptec -- Smart charge with Eco Mode:
  https://help.zaptec.com/using-products/smart-charge-with-eco-mode
- Zaptec -- Charging modes:
  https://help.zaptec.com/using-products/charging-modes
- Futurehome -- Zaptec (external control cannot run with Eco Mode):
  https://support.futurehome.no/hc/en-no/articles/360055610911-Zaptec
- VW ID.4 charging interruptions (community reports):
  https://www.vwidtalk.com/threads/id-4-charging-issues-without-specific-faults-resolutions.1647/
- custom-components/zaptec (HACS integration):
  https://github.com/custom-components/zaptec
- HomeWizard P1 meter (Home Assistant integration):
  https://www.home-assistant.io/integrations/homewizard/
