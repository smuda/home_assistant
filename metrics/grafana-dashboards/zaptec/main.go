// Generates the "Zaptec Charging" Grafana dashboard as JSON using the
// grafana-foundation-sdk. Output goes to stdout; the Makefile pipes it
// into ../grafana/provisioning/dashboards/Zaptec_charging.json.
//
// The board watches the load-balancing automation: charger current per
// phase against its configured max, total household current against the
// fuse, the non-car load the automation reacts to, and the resulting
// charge power/energy. Series come from Home Assistant's Prometheus
// export scraped by VictoriaMetrics.
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
	unitWatt = "watt"
	unitKWh  = "kwatth"
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

func currentA(entity string) string {
	return fmt.Sprintf(`homeassistant_sensor_current_a{entity="%s"}`, entity)
}

func cfg(id string, value any) dashboard.DynamicConfigValue {
	return dashboard.DynamicConfigValue{Id: id, Value: value}
}

func fixedColor(color string) map[string]string {
	return map[string]string{"mode": "fixed", "fixedColor": color}
}

func threshold(value float64, color string) dashboard.Threshold {
	return dashboard.Threshold{Value: cog.ToPtr(value), Color: color}
}

// tsPanel builds a timeseries with min 0 and a bottom legend. calcs sets
// the per-series stats shown in the legend; a non-empty calcs list renders
// the legend as a table, otherwise as a plain list.
func tsPanel(title, desc, unit string, span, height uint32, fillOpacity float64, tooltip common.TooltipDisplayMode, calcs []string, targets ...*prometheus.DataqueryBuilder) *timeseries.PanelBuilder {
	legend := common.NewVizLegendOptionsBuilder().
		ShowLegend(true).
		Placement(common.LegendPlacementBottom).
		Calcs(calcs)
	if len(calcs) > 0 {
		legend.DisplayMode(common.LegendDisplayModeTable)
	} else {
		legend.DisplayMode(common.LegendDisplayModeList)
	}
	b := timeseries.NewPanelBuilder().
		Title(title).
		Description(desc).
		Unit(unit).
		Datasource(ds()).
		Min(0).
		FillOpacity(fillOpacity).
		ShowPoints(common.VisibilityModeNever).
		Height(height).
		Span(span).
		Legend(legend).
		Tooltip(common.NewVizTooltipOptionsBuilder().Mode(tooltip))
	for _, t := range targets {
		b.WithTarget(t)
	}
	return b
}

func build() (dashboard.Dashboard, error) {
	legendCalcs := []string{"lastNotNull", "max"}

	// Charger current per phase vs the automation's control output and the
	// charger's own allocation.
	perPhase := tsPanel(
		"Laddström per fas vs konfigurerad max",
		"Actual charge current drawn per phase, the configured max (the automation's control output) and the current the charger allocates. Watch a session start at 6 A and ramp to 16 A.",
		unitAmp, 24, 9, 8, common.TooltipDisplayModeMulti, legendCalcs,
		q(currentA("sensor.zag064494_strom_fas_1"), "Fas 1"),
		q(currentA("sensor.zag064494_strom_fas_2"), "Fas 2"),
		q(currentA("sensor.zag064494_strom_fas_3"), "Fas 3"),
		q(`homeassistant_number_state_a{entity="number.zag064494_max_laddstrom"}`, "Max (konfig)"),
		q(currentA("sensor.zag064494_tilldelad_laddstrom"), "Tilldelad"),
	).
		OverrideByName("Max (konfig)", []dashboard.DynamicConfigValue{
			cfg("custom.lineInterpolation", common.LineInterpolationStepAfter),
			cfg("custom.lineWidth", 2),
			cfg("custom.fillOpacity", 0),
			cfg("color", fixedColor("red")),
		}).
		OverrideByName("Tilldelad", []dashboard.DynamicConfigValue{
			cfg("custom.lineInterpolation", common.LineInterpolationStepAfter),
			cfg("custom.fillOpacity", 0),
			cfg("color", fixedColor("super-light-blue")),
		})

	// Household current per phase against the effective cap and main fuse.
	household := tsPanel(
		"Hushållsström per fas vs säkring",
		"Total household current per phase from the P1 meter. The orange line is the automation's effective cap (fuse − margin = 22 A); the red line is the 25 A main fuse.",
		unitAmp, 12, 9, 8, common.TooltipDisplayModeMulti, legendCalcs,
		q(currentA("sensor.p1_meter_strom_fas_1"), "Fas 1"),
		q(currentA("sensor.p1_meter_strom_fas_2"), "Fas 2"),
		q(currentA("sensor.p1_meter_strom_fas_3"), "Fas 3"),
	).
		Thresholds(dashboard.NewThresholdsConfigBuilder().
			Mode(dashboard.ThresholdsModeAbsolute).
			Steps([]dashboard.Threshold{
				threshold(0, "green"),
				threshold(22, "orange"),
				threshold(25, "red"),
			})).
		ThresholdsStyle(common.NewGraphThresholdsStyleConfigBuilder().
			Mode(common.GraphThresholdsStyleModeLine))

	// Non-car load per phase (P1 minus charger) vs the last-resort stop.
	otherLoad := tsPanel(
		"Övrig last per fas (P1 − bil) vs stopp-tröskel",
		"Non-car load per phase (P1 meter minus the charger's own current). This is what the automation reacts to. The red line is the last-resort stop threshold: when this reaches ~19 A even 6 A of car current would breach the fuse.",
		unitAmp, 12, 9, 8, common.TooltipDisplayModeMulti, legendCalcs,
		q(currentA("sensor.p1_meter_strom_fas_1")+` - on() `+currentA("sensor.zag064494_strom_fas_1"), "Fas 1"),
		q(currentA("sensor.p1_meter_strom_fas_2")+` - on() `+currentA("sensor.zag064494_strom_fas_2"), "Fas 2"),
		q(currentA("sensor.p1_meter_strom_fas_3")+` - on() `+currentA("sensor.zag064494_strom_fas_3"), "Fas 3"),
	).
		Thresholds(dashboard.NewThresholdsConfigBuilder().
			Mode(dashboard.ThresholdsModeAbsolute).
			Steps([]dashboard.Threshold{
				threshold(0, "green"),
				threshold(19, "red"),
			})).
		ThresholdsStyle(common.NewGraphThresholdsStyleConfigBuilder().
			Mode(common.GraphThresholdsStyleModeLine))

	power := tsPanel(
		"Laddeffekt",
		"Charging power reported by the charger.",
		unitWatt, 12, 8, 15, common.TooltipDisplayModeSingle, legendCalcs,
		q(`homeassistant_sensor_power_w{entity="sensor.zag064494_laddeffekt"}`, "Laddeffekt"),
	)

	session := tsPanel(
		"Laddat denna session",
		"Energy delivered in the current charging session.",
		unitKWh, 12, 8, 15, common.TooltipDisplayModeSingle, legendCalcs,
		q(`homeassistant_sensor_energy_kwh{entity="sensor.zag064494_laddat_denna_sessionen"}`, "Denna session"),
	)

	b := dashboard.NewDashboardBuilder("Zaptec Charging").
		Uid("zaptec-charging").
		Tags([]string{"zaptec", "ev"}).
		Refresh("1m").
		Time("now-24h", "now").
		Timezone(common.TimeZoneBrowser).
		Tooltip(dashboard.DashboardCursorSyncCrosshair).
		WithPanel(perPhase).
		WithPanel(household).
		WithPanel(otherLoad).
		WithPanel(power).
		WithPanel(session)

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
