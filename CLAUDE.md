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
