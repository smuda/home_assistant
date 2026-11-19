# Metrics

This directory handles how metrics are scraped and handled from
Home Assistant.

In my case I've decided to use Victoria Metrics instead of Prometheus
because of their outstanding model for handling a lot of metrics
with low resource usage. 
VictoriaMetrics is running on a QNAP NAS in a docker container.

Scraping is done every 5 minutes.
Reasoning behind this is I want to keep metrics for a long time
and I prefer to have lower resolution and longer retention.

## References

- [Home Assistant Long Lived Token](https://developers.home-assistant.io/docs/auth_api/#long-lived-access-token)
- [Victoria Metrics Scraping](https://docs.victoriametrics.com/victoriametrics/scrape_config_examples/)

## Configuration in Home Assistant

[Home Assistant Prometheus Integration](https://www.home-assistant.io/integrations/prometheus/)

1. Open `configuration.yaml` and add
   ```yaml
   prometheus:
    filter:
      include_domains:
        - climate
      include_entities:
        - sensor.nord_pool_se3_aktuellt_pris
      exclude_entities:
        - climate.kitchen_light
   ```

2. Create a [longlived token for API access](https://developers.home-assistant.io/docs/auth_api/#long-lived-access-token).

3. Verify configuration with curl.
   ```shell
   curl -v \
     -H "Authorization: Bearer ${HASS_TOKEN}" \
     http://homeassistant.local:8123/api/prometheus
   ```

## Configuration in Victoria Metrics

## Querying for incident analysis

VictoriaMetrics is read-only reachable at `http://192.168.40.20:8428`
(no auth). A raw query against the HTTP API looks like this:

```shell
curl --noproxy '' -s -G \
  http://192.168.40.20:8428/api/v1/query_range \
  --data-urlencode 'query={entity="sensor.p1_meter_effekt",__name__!~".*(available|last_updated|state_change|_attr_|created|info).*"}' \
  --data-urlencode start=2026-11-19T06:00:00Z \
  --data-urlencode end=2026-11-19T09:00:00Z \
  --data-urlencode step=60
```

The `__name__` exclusion drops the sibling series that share the
`entity` label (availability, attributes, the `state_change` counters
and `_created` timestamps, `_info`, `_last_updated`), so the result is
the value gauge and not a counter or a timestamp.

`scripts/vmq.py` wraps that for a set of entities and prints a table,
one row per step, first column the UTC timestamp then one column per
entity in the order given. Standard library only, so no venv:

```shell
cd metrics/scripts
python3 vmq.py \
  sensor.zag064494_laddeffekt sensor.p1_meter_effekt \
  --start 2026-11-19T06:00:00Z --end 2026-11-19T09:00:00Z
```

Options:

- `--step` seconds per row (default 60).
- `--changes ENTITY` prints only the rows where that entity's value
  differs from the row before, for spotting when something switched.
- `--url` points at a different VictoriaMetrics instance.

A step with no sample for an entity prints an empty cell. If an entity
matches more than one value series, `vmq.py` says so and stops rather
than picking one silently; narrow it with an explicit `__name__`.

The reshaping is covered by offline tests on canned responses:

```shell
cd metrics/scripts
python3 -m unittest test_vmq
```

