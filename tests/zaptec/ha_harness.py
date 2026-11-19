"""Shared helpers for the Zaptec automation tests.

Not collected by unittest (the file name does not match `test*.py`);
the test files import it because the start directory is on sys.path.
Needs jinja2 and pyyaml; `make test` installs them into .venv from
requirements-dev.txt.
"""

import datetime as dt
from pathlib import Path

import yaml
from jinja2 import StrictUndefined
from jinja2.nativetypes import NativeEnvironment

ROOT = Path(__file__).resolve().parents[2]

NOW = dt.datetime(2026, 11, 18, 12, 0, 0, tzinfo=dt.timezone.utc)

EMS = "sensor.ems_mode_selection_raw"
CMD = "sensor.battery_forced_charge_discharge_cmd_raw"
SUSTAINED = "binary_sensor.p1_sustained_overload"
PAUSED = "input_boolean.zaptec_fuse_paused"
P1_RAW = [f"sensor.p1_meter_strom_fas_{n}" for n in (1, 2, 3)]


class Entity:
    def __init__(self, state, last_changed, last_reported):
        self.state = state
        self.last_changed = last_changed
        self.last_reported = last_reported


class Domain:
    def __init__(self, domain, entities):
        self._domain = domain
        self._entities = entities

    def __getattr__(self, object_id):
        try:
            return self._entities[f"{self._domain}.{object_id}"]
        except KeyError:
            raise AttributeError(object_id)


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


def make_env(entities):
    env = NativeEnvironment(undefined=StrictUndefined)
    env.globals["states"] = States(entities)
    env.globals["is_state"] = lambda eid, value: (
        eid in entities and entities[eid].state == value
    )
    env.globals["now"] = lambda: NOW
    return env


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
