# Zaptec dynamic fuse protection

Home Assistant automation that throttles the Zaptec Go charge
current so the main fuse is never exceeded when the car charges at
the same time as other heavy loads (electric heating, washing
machine, etc.) on a winter day.

Crucially, it changes the current rarely — frequent changes
make the car abort the session (see below).

## Why this exists

Zaptec has two independent layers:

1. [Available current mode](https://help.zaptec.com/using-products/charging-modes) — *how* current is regulated:
   - Standard charging — fixed allocation, no dynamic
     load balancing. *(This is what I run.)*
   - Scheduled charging.
   - Automatic charging (Zaptec Sense / APM) — regulates
     current in real time against the household's total load and
     protects the main fuse, but starts charging immediately
     and therefore ignores cheap-hour timing.
2. [Eco Mode](https://help.zaptec.com/using-products/smart-charge-with-eco-mode) — a separate feature layer on top of the mode
   above. It decides *when* to charge (departure time, distance,
   price area -> cheapest Nord Pool hours). *(I run Eco: ready by
   06:00, 100 km, my price area.)*

Real-time fuse protection only exists in *Automatic charging
(Sense)*, which would break my Eco timing. So I keep standard
charging + Eco for the timing and add fuse protection here in
Home Assistant. It works because the charger-level `max charge
current` entity can be written regardless of the active mode.

## Keep changes infrequent (important)

According to [Zaptec's own documentation](https://docs.zaptec.com/docs/dynamic-load-balancing-with-the-zaptec-api):

> "Frequent changes to the charge current and phase may cause the
> vehicle to interrupt the charging session ... we recommend
> updating this setting no more than once every 15 minutes."

Changing the current every few seconds makes the VW ID.4 abort
the session, requiring a manual restart in the Zaptec app.
Repeated stop/start is also
[flagged by Zaptec](https://docs.zaptec.com/docs/dynamic-load-balancing-with-the-zaptec-api)
(`WARNING_MAX_SESSION_RESTART`). The automation therefore:

- only changes when the new target differs by at least a
  deadband (3 A), and
- not more often than a minimum interval (15 min) for normal
  changes, and
- floors at 6 A rather than pausing for ordinary load swings, and
- allows one immediate reduction if a phase nears the fuse.

Net effect: the current typically changes only once or twice per
charging session, not continuously.

### Last-resort stop (and auto-resume)

Flooring at 6 A only protects the fuse while 6 A of car current
actually fits under it. If non-car load on a phase is so high that
even 6 A would push that phase to/over the fuse, keeping the car at
6 A no longer helps — the main fuse would trip for the whole
house, which can disrupt or damage computers and other
electronics. A controlled stop of the car is the lesser harm (same
probability, smaller consequence), so in that case the automation
presses stop once and sets the helper
`input_boolean.zaptec_fuse_paused`.

"Presses stop" is literal: it calls `button.press` on the charger's
`button.zag064494_stoppa_laddning` entity (the same action as the
Stop button in the Zaptec app). It does not set the charge
current to 0 — that is not a stop, and the current is already
floored at the 6 A minimum. Resume is the matching
`button.zag064494_ateruppta_laddning` press.

It is a single, deliberate stop in a genuine emergency — not the
rapid cycling that made the car abort. When household load falls
back below the threshold (with a small hysteresis), the automation
presses resume and clears the helper, so charging restarts
without manual intervention. The helper also lets it tell "we
paused for the fuse" apart from a normally finished charge, and is
cleared if the car is unplugged while paused.

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

1. Clear the pause helper if the car is unplugged while paused.
2. Resume (press resume, clear helper) if we are paused and load
   has fallen so `other_load + 6 A <= fuse - resume_hyst`.
3. Stop (press stop, set helper) if not paused, charging, and
   even 6 A would breach the fuse (`other_load + 6 A >= fuse`).
4. Set the max charge current to `raw_target` if not paused,
   charging, and either `|raw_target - current| >= deadband`
   and `min_interval` has passed (normal path), or a phase
   is `>= emergency_phase` (24 A) and a reduction is needed (safety
   path, bypasses the interval).

Evaluated once a minute, on charge-status changes, and immediately
when a phase crosses 23 A. It runs only while actually charging
(`connected_charging`) or while the fuse-pause helper is on (so
resume can be evaluated) — never while disconnected or merely
`connected_requesting` (see Eco Mode below).

### Do not disturb Eco Mode

Writing the charger's max current
[overrides Zaptec's load balancer](https://docs.zaptec.com/docs/dynamic-load-balancing-with-the-zaptec-api)
and suspends [Eco Mode](https://help.zaptec.com/using-products/smart-charge-with-eco-mode)
— external current control and Eco Mode cannot be active at the same
time ([noted in Futurehome's Zaptec integration docs](https://support.futurehome.no/hc/en-no/articles/360055610911-Zaptec)).
Eco Mode is what delays charging to the cheap night hours. If the
automation writes the current while the car is disconnected or
waiting, Eco is suspended and the next plug-in charges immediately at
the wrong (expensive) time.

So the automation only ever touches the charger while a charge is
already under way (`connected_charging`). It leaves the charger
completely alone while disconnected or `connected_requesting`, so
Eco Mode keeps full control over *when* to charge; this automation
only limits the current *once Eco has started a session*. There is
no installation-level `AvailableCurrent` entity available on this
account (charger-level permissions only), so `max_laddstrom` is the
only lever — hence the strict "charging-only" gate rather than a
gentler one.

### Noise filtering (avoids false stops)

The stop and 24 A emergency paths react to the meter reading, so a
transient spike from the P1 meter (a one-sample blip while the car
draws far less) could otherwise trigger a false stop — the very
abort we are trying to avoid. To prevent that, `P1_phase_current`
above is read from filtered sensors
(`sensor.p1_fas_{1,2,3}_filtrerad`, see `p1_filtered_sensors.yaml`):
a 20-second moving average dilutes a one-sample spike below the
stop and emergency thresholds while still tracking real, sustained
load. The normal current-adjustment path is already noise-tolerant
via its deadband and 15-minute interval.

Fail-safe on meter loss. The Home Assistant `filter` platform
keeps emitting its last value when its source stops updating, so a
frozen filtered sensor can read numeric-but-stale. The automation
therefore judges the feed's *liveness* from the raw meter's
`last_reported` (it advances on every meter push, even an unchanged
value; no push for `max_age` seconds means the feed is dead). If the
feed is dead, the phase's non-car load is set to `failsafe_other`
(18 A), which floors the car to 6 A — a meter dropout is never read
as zero load (which would wrongly allow the full 16 A). If even the
raw meter is gone, the same fail-safe applies. The wake-up trigger
still watches the raw
meter for a fast surge; only the decision uses the filtered values.
See "Filtered P1 sensors" under setup below.

The `outlier` filter is deliberately not used: it can reject a
*genuine* large load step (above its radius) indefinitely, hiding
real load — a fail-unsafe blind spot for a fuse guard. The moving
average has no such failure mode.

## Entities used

| Entity | Role |
|---|---|
| `number.zag064494_max_laddstrom` | Control — max charge current, 0-16 A, step 1 |
| `button.zag064494_stoppa_laddning` | Control — stop charging (last resort) |
| `button.zag064494_ateruppta_laddning` | Control — resume charging |
| `input_boolean.zaptec_fuse_paused` | Helper — set while paused for the fuse |
| `sensor.zag064494_strom_fas_1..3` | Charger's own current per phase |
| `sensor.zag064494_laddstatus` | Charge status (`connected_charging`, ...) |
| `sensor.p1_meter_strom_fas_1..3` | Household total current per phase (incl. the car) |
| `sensor.p1_fas_1..3_filtrerad` | Filtered P1 current used by the stop/emergency logic |

`ZAG064494` is the Zaptec Go (device type "Apollo"); network is
`tn_3_phase`, installation type "Smart". The 16 A cap is the
installer-set installation limit and cannot be raised in the app.

### Required helper

Create the toggle helper once (Settings -> Devices & services ->
Helpers -> Create helper -> Toggle), named so its entity id is
`input_boolean.zaptec_fuse_paused`. The automation uses it to
remember a fuse-pause so it can resume automatically and not confuse
that with a normally finished charge.

### Filtered P1 sensors

`p1_filtered_sensors.yaml` defines three `filter` sensors that clean
the P1 phase currents (a 20-second moving average). They are sensor
platforms, not automations, so they go in
`configuration.yaml` under `sensor:` (or a `!include` / package) and
need a Home Assistant restart, not just an automation reload.
Confirm the resulting entity ids are `sensor.p1_fas_1_filtrerad`,
`_2_`, `_3_` (Home Assistant derives them from the friendly names).
Until they exist the automation falls back to the raw P1 sensors.

## Configuration

Edit the `variables` block in `Dynamic_fuse_protection.yaml`:

- `fuse` — main fuse, amps per phase. Currently 25.
- `margin` — safety headroom, amps. Currently 3 (effective cap
  22 A/phase). Covers control latency and the gap between the rare
  normal updates.
- `deadband` — minimum change in amps before writing. 3.
- `min_interval` — minimum seconds between normal changes. 900
  (15 min, per Zaptec). Lower to e.g. `300` (5 min) if 15 min feels
  too sluggish; safety still rests on the emergency path.
- `emergency_phase` — any phase at/above this (amps) forces an
  immediate reduction regardless of the interval. 24 (1 A below
  the fuse).
- `resume_hyst` — extra amps non-car load must fall below the stop
  threshold before resuming, to avoid stop/resume flapping. 2.
- `max_age` — seconds without a raw P1 update before the feed is
  treated as dead and the fail-safe kicks in. 60.
- `failsafe_other` — assumed non-car load per phase (amps) when P1
  is dead; 18 floors the car to 6 A without forcing a stop. 18.
- `ev_min` / `ev_max` — 6 and 16 (do not exceed the installer cap).

The moving-average `window_size` for the noise filter lives in
`p1_filtered_sensors.yaml`, not here.

## Caveats

- Cloud-based control. The Zaptec HA integration
  (`custom-components/zaptec`, HACS) talks to the Zaptec cloud, so
  changes take seconds. Combined with the 15-min normal cadence,
  the car can sit above the ideal current for a while if load
  creeps up without reaching 24 A; the margin and the fuse's own
  time-current curve cover that. The 24 A emergency path is the
  fast safety net.
- Stop only as a last resort. For ordinary load swings it never
  pauses — it floors at 6 A — because frequent stop/start is what
  makes the car abort. It stops *only* when even 6 A would breach
  the fuse, i.e. when not stopping would trip the whole-house main
  fuse anyway. That is a single deliberate stop, and it auto-resumes
  when load falls, so it does not reintroduce the abort problem.
- Filter lag is deliberate. The moving average means the stop and
  emergency paths react to a sustained load a few seconds late rather
  than to an instantaneous spike. That is safe: the fuse tolerates
  brief overcurrent (its time-current curve) and the margin absorbs
  the rest, while the gain is immunity to false stops.
- Eco Mode coexistence. Because writing the charge current
  suspends Eco Mode, the automation acts only while
  `connected_charging` and never pre-empts a waiting session. The
  trade-off: it cannot soft-start the car at 6 A before a session,
  so a charge may briefly draw the stored max for the few seconds
  until the first in-session evaluation. That is acceptable; keeping
  Eco's cheap-hour scheduling intact matters more.
- Mode is not visible in HA. The integration exposes no entity
  for the available-current mode or Eco Mode (custom-components/zaptec
  [issue #153](https://github.com/custom-components/zaptec/issues/153)),
  so Eco cannot be read or toggled from HA — it
  is set in the Zaptec app. Standard charging + Eco is assumed.

## Testing

0. Add `p1_filtered_sensors.yaml` to `configuration.yaml`, restart,
   and confirm `sensor.p1_fas_{1,2,3}_filtrerad` exist and track the
   raw P1 sensors (smoother, not stuck).
1. Plug in and start charging; confirm `max_laddstrom` settles at
   a sensible value.
2. Turn on a heavy load on the constrained phase (phase 3 here) and
   confirm the current steps down — once, after the deadband is
   exceeded — rather than oscillating.
3. Confirm no phase in `sensor.p1_meter_strom_fas_*` exceeds the
   fuse, and that the session does NOT abort.
4. To exercise the last-resort path, drive non-car load on one phase
   above ~19 A while charging: confirm the car stops once, the
   helper turns on, and that it resumes (helper off) when the load
   drops. Do this deliberately, not repeatedly.
5. Only after this holds across a real winter day, consider the
   formal fuse downgrade 25 A -> 20 A (set `fuse: 20`).

## References

- Zaptec — dynamic load balancing API (15-minute update guidance;
  maxChargeCurrent overrides the load balancer):
  https://docs.zaptec.com/docs/dynamic-load-balancing-with-the-zaptec-api
- Zaptec — Smart charge with Eco Mode:
  https://help.zaptec.com/using-products/smart-charge-with-eco-mode
- Zaptec — Charging modes:
  https://help.zaptec.com/using-products/charging-modes
- Futurehome — Zaptec (external control cannot run with Eco Mode):
  https://support.futurehome.no/hc/en-no/articles/360055610911-Zaptec
- VW ID.4 charging interruptions (community reports):
  https://www.vwidtalk.com/threads/id-4-charging-issues-without-specific-faults-resolutions.1647/
- custom-components/zaptec (HACS integration):
  https://github.com/custom-components/zaptec
- HomeWizard P1 meter (Home Assistant integration):
  https://www.home-assistant.io/integrations/homewizard/
