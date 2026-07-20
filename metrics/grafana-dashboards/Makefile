# Generates code-defined Grafana dashboards and writes the JSON into the
# provisioning folder that Grafana loads from.
#
#   make sungrow   # regenerate metrics/grafana/provisioning/dashboards/sungrow.json
#   make all       # regenerate every dashboard

OUT_DIR := $(CURDIR)/../grafana/provisioning/dashboards

.PHONY: all sungrow
all: sungrow

sungrow:
	cd sungrow && go run . > "$(OUT_DIR)/sungrow.json"
	@echo "wrote $(OUT_DIR)/sungrow.json"
