// Generates the "Energy Usage" Grafana dashboard as JSON using the
// grafana-foundation-sdk. Output goes to stdout; the Makefile pipes it
// into ../grafana/provisioning/dashboards/Energy_usage.json.
//
// All series come from Home Assistant's Prometheus export, scraped by
// VictoriaMetrics. Every panel buckets energy with increase(...[1h]);
// the last panel derives "unknown" load as total import minus the sum of
// every metered consumer, and overlays outdoor temperature on a second
// axis.
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

const unitKWh = "kwatth"

// Entities excluded from the "known consumers" sum: the grid meter itself,
// double-counted Daikin totals, per-climatecontrol yearly counters, energy
// return meters, and the charger's session/total duplicates. Kept as one
// string so the exclusion is identical in the "Usage" sum and the
// "Unknown" subtraction.
const knownExclusions = `entity!="sensor.p1_meter_total_elimport", entity!="sensor.daikinap24848_energiforbrukning", entity!~".*climatecontrol.*", entity!~".*aterford_energi", entity!~"sensor.zag064494_(forbrukad_energi|energiforbrukning_denna_laddningen)"`

func ds() dashboard.DataSourceRef {
	return dashboard.DataSourceRef{
		Type: cog.ToPtr("prometheus"),
		Uid:  cog.ToPtr(datasourceUID),
	}
}

func q(expr, legend string) *prometheus.DataqueryBuilder {
	return prometheus.NewDataqueryBuilder().Expr(expr).LegendFormat(legend)
}

func hidden(expr, legend string) *prometheus.DataqueryBuilder {
	return q(expr, legend).Hide(true)
}

func cfg(id string, value any) dashboard.DynamicConfigValue {
	return dashboard.DynamicConfigValue{Id: id, Value: value}
}

// tsPanel builds a full-width timeseries stepped at 1h.
func tsPanel(title, unit string, height uint32, stacking common.StackingMode, targets ...*prometheus.DataqueryBuilder) *timeseries.PanelBuilder {
	b := timeseries.NewPanelBuilder().
		Title(title).
		Unit(unit).
		Datasource(ds()).
		Interval("1h").
		FillOpacity(0).
		Height(height).
		Span(24).
		Stacking(common.NewStackingConfigBuilder().Mode(stacking).Group("A")).
		Legend(common.NewVizLegendOptionsBuilder().
			ShowLegend(true).
			DisplayMode(common.LegendDisplayModeList).
			Placement(common.LegendPlacementBottom)).
		Tooltip(common.NewVizTooltipOptionsBuilder().Mode(common.TooltipDisplayModeMulti))
	for _, t := range targets {
		b.WithTarget(t)
	}
	return b
}

func build() (dashboard.Dashboard, error) {
	usageSum := `sum(increase(homeassistant_sensor_energy_kwh{` + knownExclusions + `}[1h]))`
	daikinUppe := `sum(increase(homeassistant_sensor_energy_kwh{entity=~"sensor.daikinap42080_uppe_climatecontrol_arlig_energiforbrukning_for_(varme|kyla)"}[1h]))`
	daikinNere := `sum(increase(homeassistant_sensor_energy_kwh{entity=~"sensor.daikinap24848_nere_climatecontrol_arlig_energiforbrukning_for_(varme|kyla)"}[1h]))`
	totalImport := `increase(homeassistant_sensor_energy_kwh{entity="sensor.p1_meter_total_elimport"} [1h])`
	// Unknown load = total grid import minus every metered consumer (the
	// known sum plus the two Daikin climate totals summed separately).
	unknown := totalImport + " - " + usageSum + " - " + daikinUppe + " - " + daikinNere

	b := dashboard.NewDashboardBuilder("Energy Usage").
		Uid("ad68vjg").
		Refresh("1m").
		Time("now-7d", "now").
		Timezone(common.TimeZoneBrowser).
		WithPanel(tsPanel("Energy kWh", "", 8, common.StackingModeNormal,
			q(totalImport, "{{friendly_name}}"),
		)).
		WithPanel(tsPanel("Usage kWh", unitKWh, 9, common.StackingModeNormal,
			q(`increase(homeassistant_sensor_energy_kwh{`+knownExclusions+`}[1h])`, "{{friendly_name}}"),
			q(daikinUppe, "DaikinAP42080 uppe Energiförbrukning"),
			q(daikinNere, "DaikinAP24848 nere Energiförbrukning"),
		)).
		WithPanel(tsPanel("EV Charger kWh", unitKWh, 9, common.StackingModeNone,
			q(`increase(homeassistant_sensor_energy_kwh{entity=~"sensor.zag064494_.*"}[1h])`, "{{friendly_name}}"),
		)).
		WithPanel(tsPanel("Unknown Usage", unitKWh, 9, common.StackingModeNone,
			q(unknown, "Unknown"),
			hidden(totalImport, "Total"),
			hidden(usageSum, "Known"),
			q(`avg(homeassistant_sensor_temperature_celsius{entity=~".*utomhustemperatur"})`, "Outdoor temp"),
		).OverrideByName("Outdoor temp", []dashboard.DynamicConfigValue{
			cfg("unit", "celsius"),
			cfg("custom.axisPlacement", "right"),
			cfg("custom.axisLabel", "Outdoor temperature"),
			cfg("color", map[string]string{"mode": "fixed", "fixedColor": "orange"}),
		}))

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
