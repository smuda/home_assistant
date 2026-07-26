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

BLUEPRINT_SRC  := automations/avfuktare/tank_full_notify.blueprint.yaml
BLUEPRINT_DEST := $(HA_USER)@$(HA_HOST):$(HA_CONFIG_DIR)/blueprints/automation/smuda/

# Template sensors. configuration.yaml must include this dir once, via
#   template: !include templates/electricity_price.yaml
# and HA must be RESTARTED that first time (a reload cannot register a
# brand-new `template:` key). After that, edits reload without restart.
TEMPLATES_SRC  := templates/
TEMPLATES_DEST := $(HA_USER)@$(HA_HOST):$(HA_CONFIG_DIR)/templates/

.PHONY: deploy deploy-blueprint deploy-templates reload-automations reload-templates check-ssh

check-ssh:
	@$(SSH) $(HA_USER)@$(HA_HOST) 'echo SSH OK on $$(hostname)' \
	  || { echo "SSH failed. Is the Advanced SSH add-on running with the ha_deploy key in ssh.authorized_keys?"; exit 1; }

deploy-blueprint:
	@$(SSH) $(HA_USER)@$(HA_HOST) 'sudo mkdir -p $(HA_CONFIG_DIR)/blueprints/automation/smuda'
	$(RSYNC) $(BLUEPRINT_SRC) $(BLUEPRINT_DEST)

deploy-templates:
	@$(SSH) $(HA_USER)@$(HA_HOST) 'sudo mkdir -p $(HA_CONFIG_DIR)/templates'
	$(RSYNC) $(TEMPLATES_SRC) $(TEMPLATES_DEST)

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

deploy: deploy-blueprint deploy-templates reload-automations reload-templates
	@echo "Deployed blueprint(s) + templates and reloaded on $(HA_HOST)."
