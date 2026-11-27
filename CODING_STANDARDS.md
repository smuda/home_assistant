# Coding standards

Review-time judgement calls that no linter catches and that no other
repo document asks for. Read this when reviewing a change; apply each
rule to the diff in front of you.

These are judgement calls, not lint rules. Enforcement in CI is out of
scope here (see issue #16).

## Glossary stays in step with behaviour

A change to the behaviour of a glossary term updates its `CONTEXT.md`
entry in the same change.

Why: `CONTEXT.md` is the written source of truth for what a term
means. If an automation's behaviour moves and the glossary entry does
not, the definition silently describes code that no longer exists, and
the next reader trusts it.

## Design rationale lives in one place

The rationale for a design lives in one README section. YAML comments
keep only what must sit next to the code, and point to that section.

Why: the same rationale copied into several files drifts. One file
gets updated, the others keep the old numbers, and there is no way to
tell which copy is current. One section owns the reasoning; everything
else refers to it.

## Entity ids and unique_ids are interface, not constants

Entity ids and `unique_id`s are interface, not constants: tests that
pin them are wanted. This overrides the global "don't test constants"
rule for these values.

Why: a changed or dropped `unique_id` makes Home Assistant register a
duplicate `..._2` entity. Every automation, template, and dashboard
that referenced the old id keeps reading an entity that no longer
updates, with no error raised. That is exactly the silent, lasting
failure `CLAUDE.md` tells us to guard against. A test that pins the id
turns that silent break into a loud one at review time.

## A write's condition stays false on a degraded input

A write's condition stays false when an input it reads is `unknown`,
`unavailable` or missing. The usual way to meet this is an explicit
`|is_number` check on the raw state in the write's condition, as the
fuse guard's Floor start does for the charger's max current.

One exception: an input that measures the hazard itself, such as a
P1 phase current, may be replaced on a degraded reading by a
conservative substitute, chosen so the protective decision it feeds
takes its safe action without escalating. The write still needs its
other conditions, and it stops repeating once the target is at the
safe value. The fuse guard's `failsafe_other` does this for a dead
P1 phase: it reads as 18 A of other load, which floors the car to
its minimum current without stopping it. The state of the device
being written, and inputs that gate the write, stay under the rule
above.

Why: a numeric default such as `|int(0)` or `|float(0)` makes an
outage look like a real reading, so the condition can pass on data
that does not exist. In a level-triggered automation (a `time_pattern`
trigger) the resulting write repeats on every run, so one bad default
becomes a stream of writes. A conservative substitute for a hazard
reading is a default that errs safe on purpose, and it stays bounded
only because the write converges. Weigh which side a default falls
on rather than banning defaults.

## A protective decision still fires on a stale input

A decision that protects hardware (a cut, a floor, a stop) still
fires when an input it reads lags its source. This covers every input
of such a decision that can lag: a `filter` sensor, a template that
depends on time passing or holds its last good value, and a raw
input polled from a cloud service. For each, the change states what
the input shows when its source steps and then holds steady, and how
the decision still fires in that case. The statement goes in the
README section that owns the decision's design (see "Design
rationale lives in one place").

Why: the `filter` platform recomputes only on a state change of its
source and has no timer, and its `time_simple_moving_average` gives
the newest value no weight until the next state change arrives
(`homeassistant/components/filter/sensor.py`). A source that steps
and then holds steady sends only reports (unless it sets
`force_update` or its attributes change), which are not state
changes (see "State change / report" in `CONTEXT.md`), so the
filtered value keeps the pre-step average for as long as the source
holds (#63: filtered P1 read 3.75 A low for 150 s while the car
charged). A plain template is correct after the step; the hazard is
an output that depends on time passing. A liveness check on the
source does not see it: the source is live, only the copy is old. A
raw input polled from a cloud service lags for a different reason,
its poll interval, but the decision sees the same thing: an old
value. The degraded-input rule above covers an input that is
degraded; this one covers an input that is present but old.

## A claim about upstream behaviour cites its evidence

A statement that says how a component outside this repo behaves (a
lag, an update rate, what makes it recompute) cites what shows it: a
recorded trace (VictoriaMetrics query and time range), the upstream
source or docs, or a test. This covers code comments, READMEs and
other repo documents (this file and `CONTEXT.md` included), commit
messages, PR descriptions and agent memory notes. Without evidence,
the statement is worded as an assumption, and review flags it.

Why: c177a17 said the filtered P1 was "still tracking a real,
sustained load (only ~10 s late on average", and 121e5ef that it
"holds up to 20 s of the old car current". Neither was checked. The
security auditor's memory turned them into the premise that the
emergency cut depends only on P1, and later reviews built on it.
VictoriaMetrics held the data to disprove both from the first night
(#63).

## A shared component's property is checked at every input using it

A fix that finds a property of a component several inputs go through
(the `filter` platform, a cloud-polled integration, a template that
holds its last good value) lists the other inputs that use it and
says for each whether the property applies. Each input where it
applies gets its own issue, which says so when the input feeds a
protective decision. Fixing them is a separate change.

Why: 5030bbf found that "a filter recomputes only on a source update"
and switched the charger currents to raw. The P1 filters in the same
file share that property, but the fix framed it as a fact about the
slow Zaptec source, so nobody asked whether it applied to P1 (#63).
An issue keeps such a finding open until someone acts on it; a line
in a PR description is closed with the PR.
