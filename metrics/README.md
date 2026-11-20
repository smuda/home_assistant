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

## Querying from the command line

`scripts/vmq.py` prints one row per step for a set of entities, the
UTC time first and then a column per entity in argument order. It
needs only Python 3, no venv.

```shell
python3 metrics/scripts/vmq.py \
  sensor.p1_meter_effekt sensor.zag064494_laddeffekt \
  --start 2026-11-19T14:00:00Z --end 2026-11-19T16:00:00Z
```

- `--step` sets the seconds between rows (default 60). Scraping runs
  every 5 minutes, so rows between scrapes show the last scraped
  value or an empty cell.
- `--changes ENTITY` keeps only the first row and the rows where that
  entity's value differs from the row before.
- `--csv` writes CSV; `--url` points at another VictoriaMetrics
  (default `http://192.168.40.20:8428`).

The query is `{entity="<id>",__name__!~"..."}`, which excludes the
sibling series HA exports under the same entity label
(`state_change`, `created`, `available`, `last_updated`, `_attr_`,
`info`). A plain `{__name__=~"homeassistant_.*"}` would return those
counters and timestamps as well. An entity that still matches more
than one series, for example after a unit change, gets a numbered
column per series and a note on stderr naming each one.

Requests go through `http_proxy` when it is set, even for an address
`no_proxy` lists, like `curl --noproxy ''`.

Tests, offline:

```shell
python3 -m unittest discover -s metrics/scripts
```

## Configuration in Victoria Metrics


