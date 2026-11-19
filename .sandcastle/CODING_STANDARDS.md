# Coding standards

The reviewer checks agent changes against this file and `CLAUDE.md`.
Each rule below is what the repo already does; where the repo is
inconsistent, the rule is "match the surrounding file", not a new
convention.

## Layout and deploy

`make deploy` copies files to the live instance; you never run it.
A file only works if it lands where the Makefile and the live
includes expect it.

- Automations: one automation per file, a single mapping (the live
  config uses `!include_dir_list`). Subdirs group by device or domain.
  Deploy flattens subdirs, so a basename must be unique across all of
  `automations/`. Only `.yaml` files are copied, and a removed file is
  removed live.
- Templates: one concern per file in `templates/`, a list starting
  with `- sensor:` or `- binary_sensor:`, no top-level `template:`
  key.
- `sensors/` and `notify/`: each file is a list of `- platform:`
  entries. These need a restart to load; say so in the PR.
- Scripts: one script per file in `scripts/`; the basename is the
  script id (`!include_dir_named`). `scripts/_wip/` is not deployed.
- Helpers: `helpers/<domain>/<object_id>.yaml`; the basename is the
  object id. A new helper domain needs a Makefile change and a live
  include, which is a maintainer step: stop and say so instead.
- Blueprints: only the blueprint path hard-coded in the Makefile is
  deployed. A new blueprint needs a Makefile change: stop and say so.
- `config/configuration.yaml` is a read-only mirror of the live
  config. Never edit it to change behaviour. `scenes.yaml`,
  integrations and GUI-managed helpers are live-only and have no repo
  copy to edit.

## YAML

- Two-space indent, list items indented under their key.
- Current syntax only: `triggers:` / `conditions:` / `actions:`,
  `- trigger:` and `action:`. No legacy `service:` or `platform:`
  trigger keys.
- Automation `id:` is a quoted 13-digit epoch-milliseconds string,
  unique across the repo. A new automation gets a new id; an existing
  id never changes.
- Always set `mode:`. Add `max_exceeded: silent` when a trigger can
  fire while a run is still going (looping or minutely automations).
- New or substantially rewritten automations get a comment header
  explaining why the automation exists and a `description: >-` block.
- Tunable numbers go in `variables:` with an inline comment giving the
  unit or the reason for the value.
- Helpers have no `initial:`, so their state survives a restart.
- Alias, comment and file-name language and case vary by area: match
  the files next to the one you change. Do not normalise existing
  files.

## Templates

- `unique_id` is ASCII snake_case. The entity id comes from `name`,
  so choose `name` so its slug reproduces the intended entity id.
- Read states with a default, `states('x') | float(0)`, and round
  results that are shown to people.
- Set `availability:` so the sensor is unavailable when its sources
  are `unknown` or `unavailable`. If you leave it out on purpose,
  explain why in a comment.
- Set `unit_of_measurement`, `state_class` and `device_class` the way
  the existing sensor of the same kind does (for example `SEK/kWh` and
  `state_class: measurement` for price sensors).
- Keep a constant (tariffs, thresholds) in one place. If a duplicate
  cannot be avoided, mark both copies with a `DRY WARNING` comment.

## Things that must not break

- Never rename an entity id, helper object id or script id that
  something depends on: the Energy dashboard, another automation, a
  template or a dashboard. Search the repo for the id before changing
  anything that defines it.
- Never leave a duplicate `..._2` entity behind, and never remove a
  helper an automation still reads.
- Do not write to a helper that another automation owns. Some
  automations read a helper's `last_changed`, so an extra toggle
  changes their behaviour.
- No IP addresses, hostnames, tokens, phone numbers or other personal
  data in new code. Existing hard-coded values are not a pattern to
  copy.

## Tests

- `tests/` holds Python unittest suites that load the real YAML and
  render its Jinja against mocked states. If you change a file they
  cover, update the tests to match. Do not add another test
  framework.
- The sandbox cannot run them (no Python). State in the PR that the
  maintainer should run them, with the command from the suite's
  README or `python3 -m unittest discover -s tests/<suite>`.

## Docs

- Use the domain terms as `CONTEXT.md` defines them, and not the
  synonyms it lists as avoided.
- A behaviour change in an area with a README (for example
  `automations/zaptec/README.md`) updates that README. A new template
  gets a companion `.md` and a row in `templates/README.md`.
- Markdown follows `CLAUDE.md`: ASCII only, wrapped at 72 columns.
- Commits use conventional commits with an English subject under 72
  characters, a body that explains why, and `Refs #<issue>`.
