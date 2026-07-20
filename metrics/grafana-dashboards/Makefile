# Generates code-defined Grafana dashboards and writes the JSON into the
# provisioning folder that Grafana loads from.
#
#   make sungrow   # regenerate metrics/grafana/provisioning/dashboards/sungrow.json
#   make all       # regenerate every dashboard

OUT_DIR := $(CURDIR)/../grafana/provisioning/dashboards

.PHONY: all sungrow energy-import energy-usage energy-usage-monthly zaptec

all: sungrow energy-import energy-usage energy-usage-monthly zaptec

sungrow:
	cd sungrow && go run . > "$(OUT_DIR)/sungrow.json"
	@echo "wrote $(OUT_DIR)/sungrow.json"

energy-import:
	cd energy-import && go run . > "$(OUT_DIR)/Energy_import.json"
	@echo "wrote $(OUT_DIR)/Energy_import.json"

energy-usage:
	cd energy-usage && go run . > "$(OUT_DIR)/Energy_usage.json"
	@echo "wrote $(OUT_DIR)/Energy_usage.json"

energy-usage-monthly:
	cd energy-usage-monthly && go run . > "$(OUT_DIR)/Energy_usage_monthly.json"
	@echo "wrote $(OUT_DIR)/Energy_usage_monthly.json"

zaptec:
	cd zaptec && go run . > "$(OUT_DIR)/Zaptec_charging.json"
	@echo "wrote $(OUT_DIR)/Zaptec_charging.json"
