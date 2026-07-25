// Generates the "Energy Usage" Grafana dashboard as JSON using the
// grafana-foundation-sdk. Output goes to stdout; the Makefile pipes it
// into ../grafana/provisioning/dashboards/Energy_usage.json.
//
// All series come from Home Assistant's Prometheus export, scraped by
// VictoriaMetrics. Every panel buckets energy with increase(...[1h]).
//
// The "Unknown Usage" panel derives unmetered load as total house
// consumption minus the sum of every metered consumer, and overlays
// outdoor temperature on a second axis. It is based on the Sungrow
// inverter's total_consumed_energy rather than grid import so that solar
// and battery generation no longer distort it: before the PV install
// grid import equalled consumption, but now much of the load is covered
// locally. The "Transformer kWh" panel shows that local contribution
// (consumption minus grid import) on its own.
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
// return meters, the whole Zaptec charger family, and the whole Sungrow
// inverter family (sensor.total_* / sensor.daily_* — PV, battery,
// import/export and consumption aggregates). The Sungrow counters are
// generation and storage flows, not discrete consumers; the Zaptec
// counters are the EV, which is metered and subtracted separately below.
// Both would otherwise pollute the per-entity "Usage" bars and, being
// counted as load, distort "Unknown". No real consumer meter uses those
// prefixes.
//
// Every zag064494_* counter is excluded here and the EV is re-added
// exactly once as the evCharger term in the Unknown subtraction, so the
// charger is neither double-counted nor left in Unknown. (The narrower
// old regex left sensor.zag064494_laddat_denna_sessionen leaking into the
// sum.) Kept as one string so the exclusion is identical in the "Usage"
// sum and the "Unknown" subtraction.
const knownExclusions = `entity!="sensor.p1_meter_total_elimport", entity!="sensor.daikinap24848_energiforbrukning", entity!~".*climatecontrol.*", entity!~".*aterford_energi", entity!~"sensor.zag064494_.*", entity!~"sensor.total_.*", entity!~"sensor.daily_.*"`

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
	daikinUppe := `sum(increase(homeassistant_sensor_energy_kwh{entity=~"sensor.daikinap42080_uppe_climatecontrol_arlig_energiforbrukning_for_(varme|kyla)"}[1h]))`
	daikinNere := `sum(increase(homeassistant_sensor_energy_kwh{entity=~"sensor.daikinap24848_nere_climatecontrol_arlig_energiforbrukning_for_(varme|kyla)"}[1h]))`
	gridImport := `increase(homeassistant_sensor_energy_kwh{entity="sensor.p1_meter_total_elimport"} [1h])`
	// Grid export, negated so the panel dips below zero when we feed the
	// grid. From the P1 billing meter's own export counter, which ships
	// disabled by default in Home Assistant and was enabled 2026-07-25.
	// VictoriaMetrics has history only from that date, so the Export line is
	// blank before it and fills in going forward. The Sungrow inverter's
	// total_exported_energy — which matched the P1 power integral to within
	// a few percent — is the pre-history fallback:
	//   - increase(homeassistant_sensor_energy_kwh{entity="sensor.total_exported_energy"} [1h])
	gridExport := `- increase(homeassistant_sensor_energy_kwh{entity="sensor.p1_meter_total_elexport"} [1h])`
	// Total house consumption from the Sungrow inverter. This, not grid
	// import, is the correct basis for the unknown-load figure now that
	// solar and the battery cover part of the load.
	consumed := `increase(homeassistant_sensor_energy_kwh{entity="sensor.total_consumed_energy"} [1h])`
	// Energy the inverter pushed into the house from sun + battery: the
	// consumption the grid did not supply. consumed = gridImport +
	// transformerPush (the two grid meters agree to ~1%). on() pairs the
	// two single-series counters, which carry different entity labels.
	transformerPush := consumed + " - on() " + `increase(homeassistant_sensor_energy_kwh{entity="sensor.total_imported_energy"} [1h])`

	usageSum := `sum(increase(homeassistant_sensor_energy_kwh{` + knownExclusions + `}[1h]))`
	// EV charging energy per bucket, derived from the charger's POWER
	// sensor rather than its energy counter. The Zaptec's forbrukad_energi
	// counter reports to Home Assistant in large delayed batches — a whole
	// session's kWh can land in a single sample — so subtracting it from
	// the continuously-accruing total_consumed_energy produced paired ±10
	// kWh spikes at every session (the range-sum was correct, the graph was
	// not). The laddeffekt power sensor is instead sampled continuously,
	// exactly as consumption accrues, so integrating it (mean watts over the
	// hour ÷ 1000 = kWh) cancels the EV cleanly with no timing skew and no
	// smoothing. sum() drops the entity label so it subtracts against the
	// label-less energy sums.
	evCharger := `sum(avg_over_time(homeassistant_sensor_power_w{entity="sensor.zag064494_laddeffekt"}[1h])) / 1000`
	// Unknown load = total consumption minus every metered consumer (the
	// known sum, the two Daikin climate totals, and the EV charger). What
	// remains is genuinely unmetered load. consumed is wrapped in sum() so
	// every term is label-less and subtracts cleanly.
	unknown := "sum(" + consumed + ") - " + usageSum + " - " + daikinUppe + " - " + daikinNere + " - " + evCharger

	b := dashboard.NewDashboardBuilder("Energy Usage").
		Uid("ad68vjg").
		Refresh("1m").
		Time("now-7d", "now").
		Timezone(common.TimeZoneBrowser).
		WithPanel(tsPanel("Energy kWh", "", 8, common.StackingModeNormal,
			q(gridImport, "Import"),
			q(gridExport, "Export"),
		)).
		WithPanel(tsPanel("Usage kWh", unitKWh, 9, common.StackingModeNormal,
			q(`increase(homeassistant_sensor_energy_kwh{`+knownExclusions+`}[1h])`, "{{friendly_name}}"),
			q(daikinUppe, "DaikinAP42080 uppe Energiförbrukning"),
			q(daikinNere, "DaikinAP24848 nere Energiförbrukning"),
		)).
		WithPanel(tsPanel("EV Charger kWh", unitKWh, 9, common.StackingModeNone,
			q(`increase(homeassistant_sensor_energy_kwh{entity=~"sensor.zag064494_.*"}[1h])`, "{{friendly_name}}"),
		)).
		WithPanel(tsPanel("Transformer kWh", unitKWh, 9, common.StackingModeNone,
			q(transformerPush, "Sol + batteri"),
		).Description("Energy the Sungrow inverter delivered to the house from solar and the battery (total consumption minus grid import). This is the local generation that no longer shows up as grid import, and it is what the Unknown Usage panel now adds back.")).
		WithPanel(tsPanel("Unknown Usage", unitKWh, 9, common.StackingModeNone,
			q(unknown, "Unknown"),
			hidden(consumed, "Total consumption"),
			hidden(usageSum, "Known"),
			hidden(gridImport, "Grid import"),
			hidden(evCharger, "EV charger"),
			q(`avg(homeassistant_sensor_temperature_celsius{entity=~".*utomhustemperatur"})`, "Outdoor temp"),
		).Description("Unmetered load: total house consumption minus every metered consumer (known meters, both Daikin units, and the EV charger). The EV is subtracted via its power sensor integrated per hour, not its energy counter, because the counter reports in delayed batches that would otherwise cause large ± spikes at each charging session. Outdoor temperature is overlaid on the right axis.").OverrideByName("Outdoor temp", []dashboard.DynamicConfigValue{
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
