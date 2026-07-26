# Template sensors

Home Assistant template entities, one `.yaml` file per concern, each
with a companion `.md` that documents it.

`configuration.yaml` pulls in the whole directory:

```yaml
template: !include_dir_merge_list templates/
```

That merges the list in every `.yaml` file here into one `template:`
list, so a new template deploys just by dropping a file in — no edit
to `configuration.yaml`. Two rules follow from the merge:

- Each `.yaml` file must be a YAML list of template blocks (starting
  with `- sensor:` / `- binary_sensor:` etc.), never its own
  top-level `template:` key.
- Non-`.yaml` files (this README, the per-template `.md` docs) are
  ignored by the include.

## Templates

| File | Docs | What it does |
|---|---|---|
| `electricity_price.yaml` | [electricity_price.md](electricity_price.md) | Real cost of imported electricity in SE3: spot + energy tax + time-of-use grid fee, incl VAT. |

## Deploying

`make deploy` rsyncs this directory to `/config/templates/` and calls
`template.reload`, so new and edited files take effect without a
restart. The one exception is the very first time the `template:` key
is added to `configuration.yaml`: that needs a single Home Assistant
restart, because a reload cannot register a brand-new `template:`
key. See `../DEPLOY.md` for the deploy setup.
