# Coding standards

Review-time judgement calls that no linter catches and that no other
repo document asks for. Read this when reviewing a change; apply each
rule to the diff in front of you.

These are judgement calls, not lint rules. Enforcement in CI is out of
scope here (see issue #16).

## Glossary stays in step with behaviour

A change to the behaviour of a glossary term updates its `CONTEXT.md`
entry in the same change.

Why: `CONTEXT.md` is the written source of truth for what a term
means. If an automation's behaviour moves and the glossary entry does
not, the definition silently describes code that no longer exists, and
the next reader trusts it.

## Design rationale lives in one place

The rationale for a design lives in one README section. YAML comments
keep only what must sit next to the code, and point to that section.

Why: the same rationale copied into several files drifts. One file
gets updated, the others keep the old numbers, and there is no way to
tell which copy is current. One section owns the reasoning; everything
else refers to it.

## Entity ids and unique_ids are interface, not constants

Entity ids and `unique_id`s are interface, not constants: tests that
pin them are wanted. This overrides the global "don't test constants"
rule for these values.

Why: a changed or dropped `unique_id` makes Home Assistant register a
duplicate `..._2` entity. Every automation, template, and dashboard
that referenced the old id keeps reading an entity that no longer
updates, with no error raised. That is exactly the silent, lasting
failure `CLAUDE.md` tells us to guard against. A test that pins the id
turns that silent break into a loud one at review time.
