include $(PWD)/env-secrets

.PHONY: vm-docker
vm-docker:
	mkdir -p vmdata
	echo "${HASS_TOKEN}" > vmconfig/homeassistant-token
	docker ps --filter name=victoriametrics --filter status=running -aq | xargs docker stop
	docker ps -a --filter name=victoriametrics --filter status=exited -aq | xargs docker rm
	docker run -d --name victoriametrics \
		-p 8428:8428 \
		-v ${PWD}/vmdata:/victoria-metrics-data \
		-v ${PWD}/vmconfig:/victoria-metrics-config \
		--add-host homeassistant.local=192.168.60.10 \
  		victoriametrics/victoria-metrics:latest \
  		-storageDataPath=/victoria-metrics-data \
  		-promscrape.config=/victoria-metrics-config/scrape.yaml \
		-retentionPeriod=2

.PHONY: vm-lts-docker
vm-lts-docker:
	mkdir -p vmdata-lts
	echo "${HASS_TOKEN}" > vmconfig-lts/homeassistant-token
	docker ps --filter name=victoriametrics-lts --filter status=running -aq | xargs docker stop
	docker ps -a --filter name=victoriametrics-lts --filter status=exited -aq | xargs docker rm
	docker run -d --name victoriametrics-lts \
		-p 8429:8428 \
		-v ${PWD}/vmdata-lts:/victoria-metrics-data \
		-v ${PWD}/vmconfig-lts:/victoria-metrics-config \
		--add-host homeassistant.local=192.168.60.10 \
  		victoriametrics/victoria-metrics:latest \
  		-storageDataPath=/victoria-metrics-data \
  		-promscrape.config=/victoria-metrics-config/scrape.yaml \
		-retentionPeriod=3y

.PHONY: grafana
grafana:
	mkdir -p grafana-data
	docker ps --filter name=grafana --filter status=running -aq | xargs docker stop
	docker ps -a --filter name=grafana --filter status=exited -aq | xargs docker rm
	docker run -d --name=grafana \
 		-p 3000:3000 \
 		-v $(PWD)/grafana-data:/var/lib/grafana \
 		-v $(PWD)/grafana/provisioning/:/etc/grafana/provisioning \
 		grafana/grafana
