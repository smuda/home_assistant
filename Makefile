# Deploy this repo's blueprints/config to the live Home Assistant.
#
# One-time prerequisite (security step, done in the HA UI):
#   Settings -> Apps -> Advanced SSH & Web Terminal -> Configuration,
#   add this repo's deploy key to ssh.authorized_keys, then Start the
#   add-on. Public key: ~/.ssh/ha_deploy.pub. See DEPLOY.md.
#
# Usage:
#   make check-ssh   # verify the SSH channel is up
#   make deploy      # rsync blueprint(s) + reload automations
#
# Override host/user/key/token on the command line if they differ, e.g.
#   make deploy HA_USER=hassio

HA_HOST     ?= homeassistant.local
HA_USER     ?= hassio
HA_SSH_KEY  ?= $(HOME)/.ssh/ha_deploy
HA_URL      ?= http://$(HA_HOST):8123
HA_TOKEN_FILE ?= metrics/vmconfig/homeassistant-token

# HAOS mounts the config dir at both /config and /homeassistant; use /config.
HA_CONFIG_DIR ?= /config

SSH   := ssh -i $(HA_SSH_KEY) -o StrictHostKeyChecking=accept-new
# The add-on's SSH user (hassio) is uid 1000, but /config is owned by
# root. hassio has passwordless sudo, so run the remote rsync as root.
# No --mkpath: macOS ships rsync 2.6.9 which lacks it; the dest dir is
# created up front by deploy-blueprint via a remote sudo mkdir -p.
RSYNC := rsync -az --rsync-path='sudo rsync' -e '$(SSH)'

BLUEPRINT_SRC  := blueprints/automation/smuda/tank_full_notify.blueprint.yaml
BLUEPRINT_DEST := $(HA_USER)@$(HA_HOST):$(HA_CONFIG_DIR)/blueprints/automation/smuda/

# Template sensors. configuration.yaml includes the dir once, via
#   template: !include_dir_merge_list templates/
# and HA must be RESTARTED that first time (a reload cannot register a
# brand-new `template:` key). After that, edits reload without restart.
TEMPLATES_SRC  := templates/
TEMPLATES_DEST := $(HA_USER)@$(HA_HOST):$(HA_CONFIG_DIR)/templates/

# Platform/filter sensors, included via
#   sensor: !include_dir_merge_list sensors/
# Platform sensors need a RESTART to (re)load, not just a reload.
SENSORS_SRC  := sensors/
SENSORS_DEST := $(HA_USER)@$(HA_HOST):$(HA_CONFIG_DIR)/sensors/

.PHONY: deploy deploy-blueprint deploy-templates deploy-automations deploy-sensors reload-automations reload-templates check-ssh

check-ssh:
	@$(SSH) $(HA_USER)@$(HA_HOST) 'echo SSH OK on $$(hostname)' \
	  || { echo "SSH failed. Is the Advanced SSH add-on running with the ha_deploy key in ssh.authorized_keys?"; exit 1; }

deploy-blueprint:
	@$(SSH) $(HA_USER)@$(HA_HOST) 'sudo mkdir -p $(HA_CONFIG_DIR)/blueprints/automation/smuda'
	$(RSYNC) $(BLUEPRINT_SRC) $(BLUEPRINT_DEST)

deploy-templates:
	@$(SSH) $(HA_USER)@$(HA_HOST) 'sudo mkdir -p $(HA_CONFIG_DIR)/templates'
	$(RSYNC) $(TEMPLATES_SRC) $(TEMPLATES_DEST)

# Automations are one-per-file, kept in subdirs (avfuktare, golvvarme,
# zaptec, ...) for readability. HA loads them flat via
#   automation: !include_dir_list automations/
# so deploy FLATTENS every .yaml into /config/automations/ (READMEs and
# other non-.yaml are skipped). --delete prunes automations removed from
# the repo. Basenames must be unique across the subdirs.
# mktemp -d is 0700, and rsync -a copies that to /config/automations/,
# leaving it unreadable by the HA core process (a different uid) so zero
# automations load. macOS rsync 2.6.9 has no --chmod, so make the stage
# world-readable before syncing and chmod the remote dir as a guarantee.
deploy-automations:
	@stage=$$(mktemp -d); chmod 755 $$stage; \
	  find automations -name '*.yaml' -exec cp {} $$stage/ \; ; \
	  $(SSH) $(HA_USER)@$(HA_HOST) 'sudo mkdir -p $(HA_CONFIG_DIR)/automations'; \
	  $(RSYNC) --delete $$stage/ $(HA_USER)@$(HA_HOST):$(HA_CONFIG_DIR)/automations/; \
	  $(SSH) $(HA_USER)@$(HA_HOST) 'sudo chmod 755 $(HA_CONFIG_DIR)/automations'; \
	  rm -rf $$stage

deploy-sensors:
	@$(SSH) $(HA_USER)@$(HA_HOST) 'sudo mkdir -p $(HA_CONFIG_DIR)/sensors'
	$(RSYNC) $(SENSORS_SRC) $(SENSORS_DEST)

reload-automations:
	@curl -sf -X POST \
	  -H "Authorization: Bearer $$(tr -d '\r\n' < $(HA_TOKEN_FILE))" \
	  $(HA_URL)/api/services/automation/reload >/dev/null \
	  && echo "automations reloaded" \
	  || { echo "reload failed (check token/URL)"; exit 1; }

# Reloads YAML template entities without a restart. Only works once the
# `template:` include exists and HA has been restarted at least once.
reload-templates:
	@curl -sf -X POST \
	  -H "Authorization: Bearer $$(tr -d '\r\n' < $(HA_TOKEN_FILE))" \
	  $(HA_URL)/api/services/template/reload >/dev/null \
	  && echo "template entities reloaded" \
	  || { echo "template reload failed (first deploy? add the include and RESTART HA once)"; exit 1; }

deploy: deploy-blueprint deploy-templates deploy-automations deploy-sensors reload-automations reload-templates
	@echo "Deployed blueprint + templates + automations + sensors on $(HA_HOST)."
	@echo "Note: changed platform sensors under sensors/ need a HA restart."
