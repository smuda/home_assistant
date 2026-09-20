# Repository guidelines

Project-specific instructions for this Home Assistant repo. These add
to the user's global CLAUDE.md, they do not replace it.

## Markdown files

- Do not use em-dashes. Use a double hyphen (`--`) for a parenthetical
  break, or rewrite the sentence to avoid it.
- Avoid non-ASCII characters. Use ASCII equivalents for punctuation
  and symbols: `->` not an arrow, `--` not an em-dash, straight quotes
  not curly ones. If a Swedish term genuinely needs accented letters
  in prose, that is tolerated; the firm rule is no non-ASCII
  punctuation or symbols.

## Changes to the live instance

This is a house, not a service with an uptime target. A
restart-length window where an automation is offline -- adding a new
top-level key to `configuration.yaml`, recreating a helper -- is
acceptable. Do not design staged cutovers, temporary object ids, or
elaborate timing around it.

State the risk in a line or two, pick the cheap mitigation (do it at
low household load), and get on with it. Save the caution for silent,
lasting failures: a duplicate `..._2` entity, a broken entity
reference, a helper that no longer exists where an automation reads
it.

## Agent skills

### Issue tracker

Issues live as GitHub issues in `smuda/home_assistant`, via the `gh`
CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five default triage labels, each label string equal to its
canonical role name. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repo root, both
created lazily. See `docs/agents/domain.md`.
