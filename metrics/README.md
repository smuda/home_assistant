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


