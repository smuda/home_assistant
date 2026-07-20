# Generates code-defined Grafana dashboards and writes the JSON into the
# provisioning folder that Grafana loads from.
#
#   make sungrow   # regenerate metrics/grafana/provisioning/dashboards/sungrow.json
#   make all       # regenerate every dashboard
#   make deploy    # regenerate every dashboard and confirm Grafana will reload

OUT_DIR := $(CURDIR)/../grafana/provisioning/dashboards

.PHONY: all deploy sungrow energy-import energy-usage energy-usage-monthly zaptec

all: sungrow energy-import energy-usage energy-usage-monthly zaptec

# The local Grafana container (see `make grafana` in ../) bind-mounts
# ../grafana/provisioning, so regenerating the JSON above is the whole
# deploy: Grafana reloads provisioned dashboards within its interval
# (~10 s). No copy or restart needed; this target only nudges you if the
# container is not up to pick them up.
deploy: all
	@docker ps --filter name=grafana --filter status=running -q | grep -q . \
	  && echo "Grafana is running; it will reload the dashboards within ~10 s." \
	  || echo "Grafana container is not running. Start it with 'make grafana' in ../ (metrics/)."

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
