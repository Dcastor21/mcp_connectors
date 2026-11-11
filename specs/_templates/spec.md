# F00 — <feature title from PRD.md>

Status: draft   <!-- draft → approved → building → done -->
Version: 1
PRD: PRD.md § Feature 0
Branch: feat/f00-<slug>

## Goal

<One or two sentences: what a user or client can do once this ships.>

## Scope

**In scope**
- <capability>

**Out of scope**
- <item> — <the feature or version that picks it up>

## Requirements

EARS patterns: "The server shall …" · "When <trigger>, the server shall …" · "If <unwanted condition>, then the server shall …" · "While <state>, the server shall …". One observable behavior per row, numbers instead of adjectives. Remove a requirement by striking its ID (`~~F00-R3~~`); never renumber.

| ID | Requirement | PRD | Verify |
| --- | --- | --- | --- |
| F00-R1 | When <trigger>, the server shall <observable result>. | AC1 | test |
| F00-R2 | <Something only a person can check, e.g. a client sign-in>. | AC2 | manual |

## Edge cases and errors

| Case | Expected behavior | Requirement |
| --- | --- | --- |
| <empty / maximum / malformed input, missing permission, upstream down> | <behavior> | F00-Rn |

## Open questions

<Must be empty before approval. Move each answer to Decisions.>

## Decisions

| Question | Decision | Why |
| --- | --- | --- |

## Manual verification

- [ ] F00-R2 — <exact steps: environment or URL, client, what to do, what you should see>

## Change log

| Version | Date | Change | Reason |
| --- | --- | --- | --- |
