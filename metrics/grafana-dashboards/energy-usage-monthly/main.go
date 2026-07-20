// Generates the "Energy Usage Monthly" Grafana dashboard as JSON using
// the grafana-foundation-sdk. Output goes to stdout; the Makefile pipes
// it into ../grafana/provisioning/dashboards/Energy_usage_monthly.json.
//
// Unlike the rolling "Energy Usage" board, this one is instant-only: both
// panels evaluate increase(...[$__range]) once over the picked month and
// rank consumers as a horizontal bar chart.
package main

import (
	"encoding/json"
	"fmt"
	"os"

	"github.com/grafana/grafana-foundation-sdk/go/barchart"
	"github.com/grafana/grafana-foundation-sdk/go/cog"
	"github.com/grafana/grafana-foundation-sdk/go/common"
	"github.com/grafana/grafana-foundation-sdk/go/dashboard"
	"github.com/grafana/grafana-foundation-sdk/go/prometheus"
	"github.com/grafana/grafana-foundation-sdk/go/stat"
)

// UID of the VictoriaMetrics (Prometheus) datasource in Grafana. Matches
// the other provisioned dashboards in this repo.
const datasourceUID = "P4169E866C3094E38"

const unitKWh = "kwatth"

func ds() dashboard.DataSourceRef {
	return dashboard.DataSourceRef{
		Type: cog.ToPtr("prometheus"),
		Uid:  cog.ToPtr(datasourceUID),
	}
}

// instant returns a single-point ($__range) PromQL query.
func instant(expr, legend string) *prometheus.DataqueryBuilder {
	return prometheus.NewDataqueryBuilder().
		Expr(expr).
		LegendFormat(legend).
		Instant()
}

// usageBars is the month's per-consumer ranking. Trivial (<1 kWh) series
// are dropped, the charger's total is substituted for its noisy
// per-session counters, and each Daikin unit's heat+cool split is summed
// back into one relabelled series.
const usageBars = `sort_desc(increase(homeassistant_sensor_energy_kwh{entity!="sensor.p1_meter_total_elimport",entity!="sensor.zag064494_energiforbrukning_denna_laddningen",entity!~"sensor.zag064494_.*",entity!="sensor.water_heater_meter_energy_returned",entity!="sensor.shelly3em63g3_e4b063f32810_energy_returned",entity!="sensor.shelly3em63g3_e4b063f32810_energy",entity!="sensor.daikinap24848_energiforbrukning",entity!~".*climatecontrol.*"} [$__range]) > 1 or increase(homeassistant_sensor_energy_kwh{entity="sensor.zag064494_forbrukad_energi"} [$__range]) > 1 or label_replace(sum(increase(homeassistant_sensor_energy_kwh{entity=~"sensor.daikinap24848_nere_climatecontrol_arlig_energiforbrukning_for_(varme|kyla)"} [$__range])), "friendly_name", "DaikinAP24848 nere Energiförbrukning", "", "") > 1 or label_replace(sum(increase(homeassistant_sensor_energy_kwh{entity=~"sensor.daikinap42080_uppe_climatecontrol_arlig_energiforbrukning_for_(varme|kyla)"} [$__range])), "friendly_name", "DaikinAP42080 uppe Energiförbrukning", "", "") > 1)`

func build() (dashboard.Dashboard, error) {
	total := stat.NewPanelBuilder().
		Title("Energy kWh").
		Unit(unitKWh).
		Datasource(ds()).
		Height(4).
		Span(24).
		ColorMode(common.BigValueColorModeValue).
		GraphMode(common.BigValueGraphModeNone).
		JustifyMode(common.BigValueJustifyModeAuto).
		TextMode(common.BigValueTextModeAuto).
		Orientation(common.VizOrientationAuto).
		ReduceOptions(common.NewReduceDataOptionsBuilder().Calcs([]string{"lastNotNull"})).
		WithTarget(instant(`increase(homeassistant_sensor_energy_kwh{entity="sensor.p1_meter_total_elimport"} [$__range])`, "{{friendly_name}}"))

	usage := barchart.NewPanelBuilder().
		Title("Usage kWh").
		Unit(unitKWh).
		Datasource(ds()).
		Height(14).
		Span(24).
		Orientation(common.VizOrientationHorizontal).
		ShowValue(common.VisibilityModeAlways).
		Stacking(common.StackingModeNone).
		BarWidth(0.8).
		GroupWidth(0.7).
		BarRadius(0.1).
		XTickLabelSpacing(0).
		Legend(common.NewVizLegendOptionsBuilder().
			ShowLegend(true).
			DisplayMode(common.LegendDisplayModeList).
			Placement(common.LegendPlacementBottom)).
		Tooltip(common.NewVizTooltipOptionsBuilder().Mode(common.TooltipDisplayModeSingle)).
		WithTarget(instant(usageBars, "{{friendly_name}}"))

	b := dashboard.NewDashboardBuilder("Energy Usage Monthly").
		Uid("ad68vjg-monthly").
		Time("2026-02-01T00:00:00.000Z", "2026-02-28T23:59:59.000Z").
		Timezone(common.TimeZoneBrowser).
		WithPanel(total).
		WithPanel(usage)

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
