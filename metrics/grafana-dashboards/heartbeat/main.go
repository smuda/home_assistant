// Generates the "1KOMMA5 Heartbeat" Grafana dashboard as JSON using the
// grafana-foundation-sdk. Output goes to stdout; the Makefile pipes it
// into ../grafana/provisioning/dashboards/Heartbeat.json.
//
// The board looks back at what the 1KOMMA5 optimiser did: when it held
// the battery, what the battery actually did, the prices it planned
// against next to the house's own price, and the money it reports. The
// forward plan is not here: HA's Prometheus export carries numeric
// states only, so the decision text, the plan calendar and the price
// forecast never reach VictoriaMetrics. The HA "1KOMMA5" view shows those.
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
	"github.com/grafana/grafana-foundation-sdk/go/statetimeline"
	"github.com/grafana/grafana-foundation-sdk/go/timeseries"
)

// UID of the VictoriaMetrics (Prometheus) datasource in Grafana. Matches
// the other provisioned dashboards in this repo.
const datasourceUID = "P4169E866C3094E38"

// Suffix the integration appends to every entity id of this house's system.
const system = "_afc12081_4304_4878_97df_a160569e3faf"

// Grafana unit ids. The integration labels its money EUR but the values
// are SEK incl VAT, so the units are set here rather than read from HA.
const (
	unitWatt      = "watt"
	unitPercent   = "percent"
	unitSEK       = "currencySEK"
	unitSEKPerKWh = "suffix: kr/kWh"
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

// heartbeat returns a PromQL expr for a numeric Heartbeat sensor. It
// matches any homeassistant_sensor_* name because the metric name embeds
// the (wrong) unit, which would change if the integration fixed it.
func heartbeat(name string) string {
	return fmt.Sprintf(`{__name__=~"homeassistant_sensor_.+", entity="sensor.heartbeat_john_allberg_%s%s"}`, name, system)
}

func tsPanel(title, unit string, span uint32, targets ...*prometheus.DataqueryBuilder) *timeseries.PanelBuilder {
	b := timeseries.NewPanelBuilder().
		Title(title).
		Unit(unit).
		Datasource(ds()).
		FillOpacity(10).
		LineInterpolation(common.LineInterpolationStepAfter).
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

func statPanel(title, unit, expr string, span uint32) *stat.PanelBuilder {
	return stat.NewPanelBuilder().
		Title(title).
		Unit(unit).
		Datasource(ds()).
		Height(5).
		Span(span).
		ReduceOptions(common.NewReduceDataOptionsBuilder().Calcs([]string{"lastNotNull"})).
		WithTarget(q(expr, title))
}

func mapping(value, text, color string) dashboard.ValueMapping {
	return dashboard.ValueMapping{ValueMap: &dashboard.ValueMap{
		Type: dashboard.MappingTypeValueToText,
		Options: map[string]dashboard.ValueMappingResult{
			value: {Text: cog.ToPtr(text), Color: cog.ToPtr(color)},
		},
	}}
}

func build() (dashboard.Dashboard, error) {
	b := dashboard.NewDashboardBuilder("1KOMMA5 Heartbeat").
		Uid("heartbeat-1komma5").
		Tags([]string{"1komma5", "heartbeat", "energy", "battery"}).
		Refresh("1m").
		Time("now-48h", "now").
		Timezone(common.TimeZoneBrowser).
		Tooltip(dashboard.DashboardCursorSyncCrosshair).

		// --- Plan mot utfall ---
		WithRow(dashboard.NewRowBuilder("Plan mot utfall")).
		// Beslut is templates/heartbeat_beslut.yaml and only has history
		// from when it was deployed; the no-discharge binary sensor
		// covers the time before that. Both share the 0/1 codes.
		WithPanel(statetimeline.NewPanelBuilder().
			Title("Plan (1KOMMA5-beslut)").
			Datasource(ds()).
			Height(5).
			Span(24).
			ShowValue(common.VisibilityModeNever).
			Mappings([]dashboard.ValueMapping{
				mapping("0", "Fri", "transparent"),
				mapping("1", "Ingen urladdning", "orange"),
				mapping("2", "Laddar från nät", "blue"),
				mapping("3", "Okänt beslut", "red"),
			}).
			WithTarget(q(`homeassistant_sensor_state{entity="sensor.heartbeat_batteribeslut"}`, "Beslut")).
			WithTarget(q(fmt.Sprintf(`homeassistant_binary_sensor_state{entity="binary_sensor.sh10_0rt_20_battery_no_discharge_active%s"}`, system), "Ingen urladdning"))).
		WithPanel(tsPanel("Heartbeat-elpris", unitSEKPerKWh, 24,
			q(heartbeat("electricity_price"), "Heartbeat-elpris"),
		)).
		WithPanel(tsPanel("Batteri (+urladdar/−laddar)", unitWatt, 16,
			q(`homeassistant_sensor_power_w{entity="sensor.battery_discharging_power_signed"}`, "Batteri"),
			q(`homeassistant_sensor_power_w{entity="sensor.total_dc_power"}`, "Solceller"),
		)).
		WithPanel(tsPanel("Laddningsnivå", unitPercent, 8,
			q(`homeassistant_sensor_battery_percent{entity="sensor.battery_level"}`, "SOC"),
		).Min(0).Max(100)).

		// --- Priser ---
		WithRow(dashboard.NewRowBuilder("Priser")).
		WithPanel(tsPanel("Heartbeats pris mot husets", unitSEKPerKWh, 12,
			q(heartbeat("electricity_price"), "Heartbeat elpris"),
			q(heartbeat("spot_price"), "Heartbeat spot"),
			q(heartbeat("grid_costs"), "Heartbeat nät och skatt"),
			q(`homeassistant_sensor_unit_sek_per_kwh{entity="sensor.nordpool_se3_inkl_skatt_o_nat"}`, "Husets fullpris"),
		)).
		WithPanel(tsPanel("Heartbeat-pris mot jämförpris", unitSEKPerKWh, 12,
			q(heartbeat("heartbeat_price"), "Heartbeat-pris"),
			q(heartbeat("comparison_price"), "Jämförpris"),
		)).

		// --- Pengar ---
		WithRow(dashboard.NewRowBuilder("Pengar")).
		WithPanel(statPanel("Köpt el idag", unitSEK, heartbeat("grid_supply_cost_today"), 5)).
		WithPanel(statPanel("Såld el idag", unitSEK, heartbeat("feed_in_earnings_today"), 5)).
		WithPanel(statPanel("Besparing 30 d", unitSEK, heartbeat("heartbeat_savings_30_days"), 5)).
		WithPanel(statPanel("Trader-besparing", unitSEK, heartbeat("energy_trader_savings"), 4)).
		WithPanel(statPanel("Snittbesparing/mån", unitSEK, heartbeat("energy_trader_average_monthly_savings"), 5)).
		WithPanel(tsPanel("Kostnad och intäkt idag", unitSEK, 24,
			q(heartbeat("grid_supply_cost_today"), "Köpt el"),
			q(heartbeat("feed_in_earnings_today"), "Såld el"),
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
