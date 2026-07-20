// Generates the "Energy import" Grafana dashboard as JSON using the
// grafana-foundation-sdk. Output goes to stdout; the Makefile pipes it
// into ../grafana/provisioning/dashboards/Energy_import.json.
//
// All series come from Home Assistant's Prometheus export, scraped by
// VictoriaMetrics. Metric names follow HA's unit/device-class scheme
// (homeassistant_sensor_current_a, _power_w, _energy_kwh, ...), filtered
// by the entity label.
package main

import (
	"encoding/json"
	"fmt"
	"os"

	"github.com/grafana/grafana-foundation-sdk/go/cog"
	"github.com/grafana/grafana-foundation-sdk/go/common"
	"github.com/grafana/grafana-foundation-sdk/go/dashboard"
	"github.com/grafana/grafana-foundation-sdk/go/prometheus"
	"github.com/grafana/grafana-foundation-sdk/go/timeseries"
)

// UID of the VictoriaMetrics (Prometheus) datasource in Grafana. Matches
// the other provisioned dashboards in this repo.
const datasourceUID = "P4169E866C3094E38"

// Grafana unit ids.
const (
	unitAmp  = "amp"
	unitKW   = "kwatt"
	unitNone = ""
)

func ds() dashboard.DataSourceRef {
	return dashboard.DataSourceRef{
		Type: cog.ToPtr("prometheus"),
		Uid:  cog.ToPtr(datasourceUID),
	}
}

func q(expr, legend string) *prometheus.DataqueryBuilder {
	return prometheus.NewDataqueryBuilder().Expr(expr).LegendFormat(legend)
}

// tsPanel builds a full-width timeseries. interval may be empty to leave
// the panel's query step at the dashboard default.
func tsPanel(title, unit, interval string, height uint32, tooltip common.TooltipDisplayMode, targets ...*prometheus.DataqueryBuilder) *timeseries.PanelBuilder {
	b := timeseries.NewPanelBuilder().
		Title(title).
		Unit(unit).
		Datasource(ds()).
		FillOpacity(0).
		ShowPoints(common.VisibilityModeNever).
		Height(height).
		Span(24).
		Legend(common.NewVizLegendOptionsBuilder().
			ShowLegend(true).
			DisplayMode(common.LegendDisplayModeList).
			Placement(common.LegendPlacementBottom)).
		Tooltip(common.NewVizTooltipOptionsBuilder().Mode(tooltip))
	if interval != "" {
		b.Interval(interval)
	}
	for _, t := range targets {
		b.WithTarget(t)
	}
	return b
}

func build() (dashboard.Dashboard, error) {
	b := dashboard.NewDashboardBuilder("Energy import").
		Uid("ad9lkhn").
		Refresh("1m").
		Time("now-30d", "now").
		Timezone(common.TimeZoneBrowser).
		WithPanel(tsPanel("Current Imported Current Ampere", unitNone, "", 9, common.TooltipDisplayModeMulti,
			q(`homeassistant_sensor_current_a{entity=~"sensor.p1.*"}`, "{{entity}}"),
		)).
		WithPanel(tsPanel("Max Imported Current", unitAmp, "1d", 9, common.TooltipDisplayModeMulti,
			q(`max_over_time(homeassistant_sensor_current_a{entity=~"sensor.p1.*"} [1d])`, "{{entity}}"),
		)).
		WithPanel(tsPanel("Imported power", unitKW, "", 9, common.TooltipDisplayModeMulti,
			q(`homeassistant_sensor_power_w{entity="sensor.p1_meter_effekt"} /1000`, "{{entity}}"),
		)).
		WithPanel(tsPanel("Max Imported power", unitKW, "1d", 9, common.TooltipDisplayModeMulti,
			q(`max_over_time(homeassistant_sensor_power_w{entity="sensor.p1_meter_effekt"} /1000 [1d])`, "{{entity}}"),
		)).
		WithPanel(tsPanel("Imported energy kWh/h", unitNone, "1h", 8, common.TooltipDisplayModeSingle,
			q(`increase(homeassistant_sensor_energy_kwh{entity="sensor.p1_meter_total_elimport"} [1h])`, "{{friendly_name}}"),
		)).
		WithPanel(tsPanel("Imported energy kWh/d", unitNone, "1d", 8, common.TooltipDisplayModeSingle,
			q(`increase(homeassistant_sensor_energy_kwh{entity="sensor.p1_meter_total_elimport"} [1d])`, "{{friendly_name}}"),
		))

	return b.Build()
}

func main() {
	dash, err := build()
	if err != nil {
		fmt.Fprintln(os.Stderr, "build dashboard:", err)
		os.Exit(1)
	}
	out, err := json.MarshalIndent(dash, "", "  ")
	if err != nil {
		fmt.Fprintln(os.Stderr, "marshal:", err)
		os.Exit(1)
	}
	fmt.Println(string(out))
}
