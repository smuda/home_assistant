#!/usr/bin/env bash

for FILE in grafana/provisioning/dashboards/*
do
  jq '. | del(.version)' "${FILE}" > "${FILE}.json"
  mv "${FILE}.json" "${FILE}"
done
