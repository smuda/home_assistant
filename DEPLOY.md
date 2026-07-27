# Deploying to the live Home Assistant

This repo is source-of-truth only. Home Assistant does not pull from
GitHub. Changes reach the running instance through `make deploy`,
which rsyncs files over SSH and reloads automations via the REST API.

## One-time setup

### 1. Deploy key (already generated)

A dedicated key lives at `~/.ssh/ha_deploy` on the Mac. The public
half is `~/.ssh/ha_deploy.pub`.

### 2. Enable SSH on the add-on (security step)

The "Advanced SSH & Web Terminal" add-on is installed but was in an
Error state because it had neither a password nor an authorized key.
Add the deploy key and start it:

1. Settings -> Apps -> Advanced SSH & Web Terminal -> Configuration.
2. Open the `ssh` section and set `username: hassio`, then add the
   public key (contents of `ha_deploy.pub`) under `authorized_keys`.

   In the GUI list field, paste the key with NO surrounding quotes:

   ```text
   ssh-ed25519 AAAA... ha-deploy@mac
   ```

   Quotes are only correct in the raw-YAML editor (three-dot menu ->
   Edit in YAML). A key stored with literal quotes is rejected by SSH
   with "Permission denied (publickey)" even though the add-on starts.

3. Save. The Network port is already `22 -> 22/tcp`, so no port change
   is needed.
4. Info tab -> Restart. The Error clears once a valid key is present.

The SSH login user is `hassio` (it matches `ssh.username`), which is the
Makefile's `HA_USER` default.

Protection mode can stay on; `/config` is still reachable for rsync.
The add-on already includes `rsync`. If a future update drops it, add
`rsync` under the `packages` option.

## Deploying

```sh
make check-ssh   # verify the channel is up
make deploy      # rsync blueprint(s) + reload automations
```

`make deploy` ships:

- `blueprints/automation/smuda/tank_full_notify.blueprint.yaml` to
  `/config/blueprints/automation/smuda/`.
- the `templates/` directory to `/config/templates/`, then
  `template.reload`.
- every `.yaml` under `automations/` (kept in subdirs for
  readability) FLATTENED into `/config/automations/`, with `--delete`
  so removed automations are pruned, then `automation.reload`.
- the `sensors/` directory to `/config/sensors/`.
- the `dashboards/` directory to `/config/dashboards/` (YAML-mode
  Lovelace dashboards).

It then pulls `configuration.yaml` back from the live host into
`config/configuration.yaml` as a read-only mirror (see below).

Add more files by extending the Makefile.

## Dashboards (one-time step)

YAML-mode dashboards live under `dashboards/` and deploy to
`/config/dashboards/`. Each is registered in the live
`configuration.yaml` under `lovelace:`. The built-in auto-generated
Overview is left intact because no top-level `mode:` is set:

```yaml
lovelace:
  dashboards:
    home-hemma:
      mode: yaml
      title: Hemma
      icon: mdi:sofa
      show_in_sidebar: true
      filename: dashboards/home.yaml
```

The dashboard url slug (`home-hemma`) MUST contain a hyphen -- HA
rejects a slug without one. A brand-new dashboard needs one HA RESTART
to register the `lovelace:` entry; after that, edits to the YAML file
show on a browser refresh (there is no reload service for YAML
dashboards). Each user selects their own default under Profile ->
Default dashboard, so the admin Overview and this everyday view can
coexist without anyone compromising.

The "Hemma" dashboard uses the ApexCharts custom card (installed via
HACS) for the electricity-price curve. It reads the `today` /
`tomorrow` attributes of `sensor.elpris_serie_se3`
(`templates/electricity_price_series.yaml`), which fetches the day-ahead
prices via the `nordpool.get_prices_for_date` action because the
official Nord Pool integration exposes no raw hourly arrays.

## Config mirror (configuration.yaml)

This repo is NOT the source of truth for `configuration.yaml`. Edits are
made on the live host (File editor or SSH). `make deploy` (and
`make pull-config`) fetch the live file back into
`config/configuration.yaml` so its history is visible in git and diffs
over time are easy to see. The mirror is read-only -- deploy never
pushes it back.

`pull-config` refuses to write if it finds an inline secret (anything
other than a `!secret` reference), so credentials never reach git.
Review `git diff config/` before committing.

## Automations and sensors (one-time step)

Automations and platform/filter sensors use the same directory model
as templates. In the live `configuration.yaml`:

```yaml
automation: !include_dir_list automations/
sensor: !include_dir_merge_list sensors/
```

`automation` uses `!include_dir_list` because each file holds ONE
automation (a dict); `sensor` uses `!include_dir_merge_list` because
each file holds a LIST of sensor configs. Deploy flattens the
automation subdirs into `/config/automations/`, so basenames must be
unique across `avfuktare/`, `golvvärme/`, `zaptec/`, etc.

RESTART Home Assistant once after adding these keys. Automations then
reload live via `automation.reload` on each deploy, but changed
platform sensors under `sensors/` need a restart (no reload service).

## Template sensors (one-time step)

Template entities under `templates/` need a single manual step the
first time. In the live `configuration.yaml`, add:

```yaml
template: !include_dir_merge_list templates/
```

This merges the list in every `.yaml` file under `templates/` into
one `template:` list, so new template files deploy without touching
`configuration.yaml` again. Each file must be a YAML list of template
blocks (starting with `- sensor:` etc.), not its own `template:` key.

Then RESTART Home Assistant once -- a reload cannot register a
brand-new `template:` key. After that first restart, `make deploy`
picks up new and edited files via `template.reload`, no restart
needed.

The electricity-price template also depends on the Workday
integration: Settings -> Devices & services -> Add integration ->
Workday, Country = Sweden. Without it the template falls back to a
plain Mon-Fri check.

Overrides, if anything differs from the defaults:

```sh
make deploy HA_USER=hassio HA_HOST=192.168.60.10
```

The reload token is read from `metrics/vmconfig/homeassistant-token`.
