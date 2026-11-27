# House energy and automation

A single household's Home Assistant setup: what electricity costs and
earns, what the solar and battery do about it, and the automations
that steer heavy loads around the price. The repo is the written
source of truth for that house; the running instance is separate.

## Language

### Prices and tariffs

**Spot**:
The Nord Pool hourly energy price for price area SE3, taken as
VAT-inclusive.
_Avoid_: electricity price, market price, elpris

**Import cost**:
What one imported kWh actually costs: spot plus energy tax plus the
grid transfer fee.
_Avoid_: price, the price, cost per kWh

**Export compensation**:
What one exported kWh actually earns: spot plus the feed-in benefit.
_Avoid_: sale price, export price, revenue

**Grid transfer fee**:
The grid company's per-kWh charge for moving the energy, separate
from the energy itself. Swedish: elnatsavgift.
_Avoid_: network fee, grid fee, transmission cost

**High tariff / low tariff**:
The two levels the grid transfer fee takes. High applies only inside
the tariff window; low applies the rest of the time.
_Avoid_: peak, off-peak, day rate, night rate

**Tariff window**:
The condition under which the grid transfer fee is high: a working
day in November through March, between 06:00 and 22:00.
_Avoid_: peak hours, high period

**Working day**:
A day the grid company bills at the high tariff. Weekday red days,
including julafton and nyarsafton, are not working days.
_Avoid_: weekday, business day

**Feed-in benefit**:
The flat per-kWh payment the grid company makes for exported energy,
on top of spot. Swedish: elnatsersattning.
_Avoid_: export bonus, feed-in tariff

**Asymmetry**:
The gap between import cost and export compensation at the same spot
price. It is why a spot-only view of a trade can be wrong.
_Avoid_: spread, margin

**Price steering**:
Turning a load off, down, or later because the import cost crossed a
threshold. Swedish: prisstyrning.
_Avoid_: load shedding, demand response

### Generation, storage, and the optimiser

**Optimiser**:
The external 1KOMMA5 system that decides when the battery charges and
discharges. It plans against spot alone. Vendor name: Heartbeat AI.
_Avoid_: the AI, the controller, the EMS

**Grid charge**:
The optimiser charging the house battery from the grid rather than
from solar.
_Avoid_: forced charge, night charge

**Solar value**:
What the generated energy was worth, priced at the moment it was
consumed rather than the moment it was generated.
_Avoid_: solar earnings, PV revenue, yield

**Battery P&L**:
What the battery earned by shifting energy in time, counted over a
window that starts and ends at a comparable state of charge.
_Avoid_: battery savings, arbitrage profit

**Economic split**:
The rule for attributing a kWh to solar or to the grid: it counts as
grid-sourced if it did not reduce the bill, whatever the DC-side
meters say physically.
_Avoid_: PV split, physical split, source attribution

**Mixing model**:
The accounting that traces energy out of the battery back to what
went in, so a stored kWh is valued at the price when it is used.
_Avoid_: FIFO, allocation

**DC-to-AC ratio**:
The window's own ratio between metered DC generation and the AC side
that prices apply to.
_Avoid_: inverter efficiency, conversion factor

### Measurement and history

**Bucket**:
One sample interval in a pulled series, the unit everything is
counted and costed in.
_Avoid_: sample, data point, tick, interval

**Window**:
The time range an analysis covers, given as absolute UTC so it stays
reproducible.
_Avoid_: period, range, timeframe

**Coverage**:
How completely a window is populated with buckets. Checked before any
figure derived from it is trusted.
_Avoid_: completeness, data quality

**Backfill**:
Filling buckets a source never delivered from a substitute source.
_Avoid_: patch, interpolate, fill in

**Rescue**:
Recovering buckets from Home Assistant's recorder before it expires
them, when the long-term store missed the window entirely.
_Avoid_: recover, restore, import

**Recorder**:
Home Assistant's own short-lived history. The only second copy of
recent buckets, and it expires.
_Avoid_: database, local history

**State change / report**:
A state change is a write Home Assistant records as new: the value
differs, only the attributes differ, or the entity sets
`force_update`. It fires `state_changed` and moves `last_updated`;
`last_changed` moves only when the value differs or on
`force_update`. A report is a write of the same value and
attributes; it fires `state_reported` and moves only
`last_reported`. The `filter` platform reacts to state changes only.
Source: Home Assistant docs, "State objects"; `filter/sensor.py`.
_Avoid_: update

**Unknown Usage**:
Consumption seen at the meter that no monitored device accounts for.
A real bucket of load, not an error.
_Avoid_: other, unaccounted, missing load

### Controlled loads

**Fuse guard**:
The protection that holds total current under the main fuse when the
car charges alongside other heavy loads.
_Avoid_: load balancing, current limiter

**Last-resort stop**:
Stopping the car outright, chosen when holding it at the floor
current would no longer keep the phase under the fuse, and only once
that has held for the confirmation time (20 s).
_Avoid_: emergency stop, cutoff, trip

**Ramp**:
Raising the car's charge current in a few small steps with a pause
between them, instead of in one jump, so the optimiser has time to
make room before the next step lands. Only raises are ramped; a cut
is always immediate.
_Avoid_: soft start, step-up, slew

**Floor start**:
Setting the car's charge current to the floor (6 A) once it has
been unplugged, so the next session starts there and the ramp
takes it up.
_Avoid_: soft start, reset, pre-set

**Battery hold**:
The house battery held idle, neither charging nor discharging, while
the car charges, the fuse guard holds it paused, or shortly after a
resume, so it does not discharge into the car in the optimiser's
self-consumption windows. Stands aside, writing nothing, while the
optimiser is in External EMS. Released back to the optimiser
otherwise.
_Avoid_: forced stop, battery lock, charge cap

**Eco Mode nudge**:
A phone notification sent when Eco Mode is holding a plugged-in car
and waiting for the cheapest window before 06:00 (or the end of the
published prices, if earlier) would save less than a set threshold.
Watch-only: it never writes to the charger, it only asks a human to
start the charge by hand in the Zaptec app.
_Avoid_: auto start, override, smart charge

**Full**:
A dehumidifier's tank being full, inferred from the compressor having
stopped and stayed stopped.
_Avoid_: tank alarm, off, idle

### Deployment

**Live instance**:
The running Home Assistant. It never reads this repo; changes reach
it only by being deployed.
_Avoid_: production, the server, HA

**Mirror**:
A file in this repo that is a read-only copy of live configuration,
kept for reference rather than deployed from.
_Avoid_: backup, snapshot, copy
