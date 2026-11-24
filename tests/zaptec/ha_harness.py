"""Shared helpers for the Zaptec automation tests.

Not collected by unittest (the file name does not match `test*.py`);
the test files import it because the start directory is on sys.path.
Needs jinja2 and pyyaml; `make test` installs them into .venv from
requirements-dev.txt.
"""

import datetime as dt
import math
import numbers
from pathlib import Path

import yaml
from jinja2 import StrictUndefined
from jinja2.nativetypes import NativeEnvironment

ROOT = Path(__file__).resolve().parents[2]

NOW = dt.datetime(2026, 11, 18, 12, 0, 0, tzinfo=dt.timezone.utc)

EMS = "sensor.ems_mode_selection_raw"
CMD = "sensor.battery_forced_charge_discharge_cmd_raw"
EMS_HELD = "sensor.ems_mode_selection_raw_held"
CMD_HELD = "sensor.battery_forced_charge_discharge_cmd_raw_held"
SUSTAINED = "binary_sensor.p1_sustained_overload"
PAUSED = "input_boolean.zaptec_fuse_paused"
STOP_PENDING = "input_boolean.zaptec_fuse_stop_pending"
RAMPING = "input_boolean.zaptec_fuse_ramping"
P1_RAW = [f"sensor.p1_meter_strom_fas_{n}" for n in (1, 2, 3)]


class Entity:
    def __init__(self, state, last_changed, last_reported, attributes=None):
        self.state = state
        self.last_changed = last_changed
        self.last_reported = last_reported
        self.attributes = attributes or {}


class Domain:
    def __init__(self, domain, entities):
        self._domain = domain
        self._entities = entities

    def __getattr__(self, object_id):
        # HA returns None for a missing entity, so `is none` guards work.
        if object_id.startswith("_"):
            raise AttributeError(object_id)
        return self._entities.get(f"{self._domain}.{object_id}")


class States:
    """`states('x')` and `states.<domain>.<object_id>` like HA."""

    def __init__(self, entities):
        self._entities = entities

    def __call__(self, entity_id):
        entity = self._entities.get(entity_id)
        return "unknown" if entity is None else entity.state

    def __getattr__(self, domain):
        if domain.startswith("_"):
            raise AttributeError(domain)
        return Domain(domain, self._entities)


def make_env(entities, now=NOW):
    env = NativeEnvironment(undefined=StrictUndefined)
    env.globals["states"] = States(entities)
    env.globals["is_state"] = lambda eid, value: (
        eid in entities and entities[eid].state == value
    )
    env.globals["now"] = lambda: now
    env.globals["state_attr"] = lambda eid, attr: (
        entities[eid].attributes.get(attr) if eid in entities else None
    )
    env.globals["as_timestamp"] = lambda v: (
        v.timestamp() if isinstance(v, dt.datetime) else float(v)
    )
    env.globals["timedelta"] = dt.timedelta
    # Tests treat "local" as UTC (NOW is UTC), so the whole chain -- the
    # 06:00 deadline, the series epochs and this formatter -- stays in
    # one zone, the same self-consistency the live system has in
    # Europe/Stockholm.
    env.filters["timestamp_custom"] = lambda ts, fmt, local=True: (
        dt.datetime.fromtimestamp(float(ts), dt.timezone.utc).strftime(fmt)
    )
    env.filters["is_number"] = _is_number
    env.filters["bool"] = _bool
    env.filters["as_local"] = _as_local
    return env


def _is_number(value):
    # Like Home Assistant's is_number: a finite float, so "unavailable",
    # "unknown", nan and inf are all not numbers.
    try:
        return math.isfinite(float(value))
    except (ValueError, TypeError):
        return False


_NO_DEFAULT = object()


def _bool(value, default=_NO_DEFAULT):
    # Like Home Assistant's bool filter (forgiving_boolean): the usual
    # truthy/falsy words and numbers convert, anything else returns the
    # default, or raises when none was given.
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.lower().strip()
        if text in ("1", "true", "yes", "on", "enable"):
            return True
        if text in ("0", "false", "no", "off", "disable"):
            return False
    elif isinstance(value, numbers.Number):
        return value != 0
    if default is _NO_DEFAULT:
        raise ValueError(
            f"bool got invalid input {value!r} and no default was specified"
        )
    return default


def _as_local(value):
    # Like Home Assistant's as_local, with local = UTC as for
    # timestamp_custom above: a naive datetime is taken to be local.
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(dt.timezone.utc)


def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)


def as_list(value):
    return value if isinstance(value, list) else [value]


def state_triggers(automation, entity_id):
    """The `trigger: state` entries of an automation for one entity."""
    return [
        t
        for t in as_list(automation["triggers"])
        if t.get("trigger") == "state" and t.get("entity_id") == entity_id
    ]


def render_variables(env, variables, context):
    """Evaluate a `variables:` block in order the way HA does.

    Each string is rendered as a template against the variables so far
    (plus context) and the native result kept. Returns the full scope.
    """
    scope = dict(context)
    for name, value in variables.items():
        if isinstance(value, str):
            value = env.from_string(value).render(**scope)
        scope[name] = value
    return scope
