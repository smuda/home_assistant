# Code-defined Grafana dashboards

Dashboards here are generated from Go using the
[grafana-foundation-sdk][sdk] instead of being hand-edited as JSON.
The generator prints a dashboard to stdout, and the Makefile writes
it into `../grafana/provisioning/dashboards/`, which the Grafana
container loads and reloads automatically.

## Layout

```
grafana-dashboards/
  Makefile          # regenerates the JSON into the provisioning folder
  sungrow/          # one Go module per dashboard
    main.go
    go.mod
```

## Regenerate

```sh
make sungrow      # writes ../grafana/provisioning/dashboards/sungrow.json
make all          # every dashboard
```

Grafana picks up the new file within its provisioning reload
interval (about 10 s); no restart is needed.

## Notes

- Metrics come from Home Assistant's Prometheus export scraped by
  VictoriaMetrics. Names follow HA's unit/device-class scheme
  (`homeassistant_sensor_power_w`, `homeassistant_sensor_battery_percent`,
  `homeassistant_sensor_energy_kwh`, ...), filtered by the `entity`
  label. The entity id is never itself the metric name.
- The datasource is referenced by the uid `P4169E866C3094E38`, the
  same VictoriaMetrics source the other dashboards in
  `../grafana/provisioning/dashboards/` use. If that uid ever
  changes, update the constant in the generator.
- The generated JSON is committed so the dashboard provisions even
  without running Go, but the Go source is the source of truth.
  Edit `main.go`, not the JSON.

[sdk]: https://github.com/grafana/grafana-foundation-sdk
