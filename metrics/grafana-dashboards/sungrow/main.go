// Generates the Sungrow solar & battery Grafana dashboard as JSON using
// the grafana-foundation-sdk. Output goes to stdout; the Makefile pipes
// it into ../grafana/provisioning/dashboards/sungrow.json.
//
// All series come from Home Assistant's Prometheus export, scraped by
// VictoriaMetrics. Metric names follow HA's unit/device-class scheme
// (homeassistant_sensor_power_w, _battery_percent, _energy_kwh, ...),
// filtered by the entity label.
package main

import (
	"encoding/json"
	"fmt"
	"os"

	"github.com/grafana/grafana-foundation-sdk/go/cog"
	"github.com/grafana/grafana-foundation-sdk/go/common"
	"github.com/grafana/grafana-foundation-sdk/go/dashboard"
	"github.com/grafana/grafana-foundation-sdk/go/prometheus"
	"github.com/grafana/grafana-foundation-sdk/go/stat"
	"github.com/grafana/grafana-foundation-sdk/go/timeseries"
)

// UID of the VictoriaMetrics (Prometheus) datasource in Grafana. Matches
// the other provisioned dashboards in this repo.
const datasourceUID = "P4169E866C3094E38"

// Grafana unit ids.
const (
	unitWatt    = "watt"
	unitPercent = "percent"
	unitCelsius = "celsius"
	unitKWh     = "kwatth"
)

func ds() dashboard.DataSourceRef {
	return dashboard.DataSourceRef{
		Type: cog.ToPtr("prometheus"),
		Uid:  cog.ToPtr(datasourceUID),
	}
}

// power_w returns a PromQL expr for a HA power sensor by entity id.
func powerW(entity string) string {
	return fmt.Sprintf(`homeassistant_sensor_power_w{entity="%s"}`, entity)
}

func q(expr, legend string) *prometheus.DataqueryBuilder {
	return prometheus.NewDataqueryBuilder().Expr(expr).LegendFormat(legend)
}

func tsPanel(title, unit string, span uint32, targets ...*prometheus.DataqueryBuilder) *timeseries.PanelBuilder {
	b := timeseries.NewPanelBuilder().
		Title(title).
		Unit(unit).
		Datasource(ds()).
		FillOpacity(10).
		Height(8).
		Span(span).
		Legend(common.NewVizLegendOptionsBuilder().
			DisplayMode(common.LegendDisplayModeList).
			Placement(common.LegendPlacementBottom))
	for _, t := range targets {
		b.WithTarget(t)
	}
	return b
}

// tilePanel is a compact timeseries used as a current-value tile: it
// shows the latest value in the legend (like a stat) but supports the
// same hover tooltip as the larger graphs.
func tilePanel(title, unit, expr string, span uint32) *timeseries.PanelBuilder {
	return timeseries.NewPanelBuilder().
		Title(title).
		Unit(unit).
		Datasource(ds()).
		Height(6).
		Span(span).
		FillOpacity(15).
		Tooltip(common.NewVizTooltipOptionsBuilder().Mode(common.TooltipDisplayModeSingle)).
		Legend(common.NewVizLegendOptionsBuilder().
			DisplayMode(common.LegendDisplayModeList).
			Placement(common.LegendPlacementBottom).
			Calcs([]string{"lastNotNull"})).
		WithTarget(q(expr, title))
}

func statPanel(title, unit, expr string, span uint32) *stat.PanelBuilder {
	return stat.NewPanelBuilder().
		Title(title).
		Unit(unit).
		Datasource(ds()).
		Height(6).
		Span(span).
		ReduceOptions(common.NewReduceDataOptionsBuilder().Calcs([]string{"lastNotNull"})).
		WithTarget(q(expr, title))
}

func build() (dashboard.Dashboard, error) {
	b := dashboard.NewDashboardBuilder("Sungrow – Sol & Batteri").
		Uid("sungrow-solar-battery").
		Tags([]string{"sungrow", "energy", "solar", "battery"}).
		Refresh("30s").
		Time("now-24h", "now").
		Timezone(common.TimeZoneBrowser).

		// --- Nu (aktuella värden) ---
		WithRow(dashboard.NewRowBuilder("Nu")).
		WithPanel(tilePanel("Solceller", unitWatt, powerW("sensor.total_dc_power"), 5)).
		WithPanel(tilePanel("Batteri (+urladdar/−laddar)", unitWatt, powerW("sensor.battery_discharging_power_signed"), 5)).
		WithPanel(tilePanel("Nät P1 (+import/−export)", unitWatt, powerW("sensor.p1_meter_effekt"), 5)).
		WithPanel(tilePanel("Hemförbrukning", unitWatt, powerW("sensor.load_power"), 5)).
		WithPanel(tilePanel("Laddningsnivå", unitPercent, `homeassistant_sensor_battery_percent{entity="sensor.battery_level"}`, 4)).

		// --- Effekt över tid ---
		WithRow(dashboard.NewRowBuilder("Effekt över tid")).
		WithPanel(tsPanel("Effektflöde", unitWatt, 24,
			q(powerW("sensor.total_dc_power"), "Solceller"),
			q(powerW("sensor.battery_discharging_power_signed"), "Batteri (+urladdar/−laddar)"),
			q(powerW("sensor.p1_meter_effekt"), "Nät P1 (+import/−export)"),
			q(powerW("sensor.load_power"), "Hemförbrukning"),
		)).
		WithPanel(tsPanel("Solel per sträng (MPPT)", unitWatt, 24,
			q(powerW("sensor.mppt1_power"), "Sträng 1"),
			q(powerW("sensor.mppt2_power"), "Sträng 2"),
			q(powerW("sensor.mppt3_power"), "Sträng 3"),
			q(powerW("sensor.mppt4_power"), "Sträng 4"),
		)).

		// --- Batteri ---
		WithRow(dashboard.NewRowBuilder("Batteri")).
		WithPanel(tsPanel("Laddningsnivå (SOC)", unitPercent, 8,
			q(`homeassistant_sensor_battery_percent{entity="sensor.battery_level"}`, "SOC"),
		)).
		WithPanel(tsPanel("Batterieffekt", unitWatt, 8,
			q(powerW("sensor.battery_charging_power"), "Laddning"),
			q(powerW("sensor.battery_discharging_power"), "Urladdning"),
		)).
		WithPanel(tsPanel("Batteritemperatur", unitCelsius, 8,
			q(`homeassistant_sensor_temperature_celsius{entity="sensor.battery_temperature"}`, "Temp"),
		)).

		// --- Energi idag ---
		WithRow(dashboard.NewRowBuilder("Energi idag")).
		WithPanel(statPanel("Solproduktion", unitKWh, energyKWh("sensor.daily_pv_generation"), 5)).
		WithPanel(statPanel("Batteri laddat", unitKWh, energyKWh("sensor.daily_battery_charge"), 5)).
		WithPanel(statPanel("Batteri urladdat", unitKWh, energyKWh("sensor.daily_battery_discharge"), 5)).
		WithPanel(statPanel("Import", unitKWh, energyKWh("sensor.daily_imported_energy"), 5)).
		WithPanel(statPanel("Export", unitKWh, energyKWh("sensor.daily_exported_energy"), 4))

	return b.Build()
}

func energyKWh(entity string) string {
	return fmt.Sprintf(`homeassistant_sensor_energy_kwh{entity="%s"}`, entity)
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
