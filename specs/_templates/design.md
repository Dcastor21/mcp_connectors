# F00 — design

Design status: draft   <!-- draft → approved -->
Spec: spec.md v1

## Approach

<At most 10 lines: the layers, how a request flows through them, and which layer provides the real guarantee.>

## API notes (confirmed with Context7)

| Library | Version or doc date | API this design relies on | Confirmed |
| --- | --- | --- | --- |
| <library> | <version> | <function, class, option> | ☐ |

## Components and files

| File | Create or change | Responsibility |
| --- | --- | --- |

## Interfaces

```python
# Signatures, models and tool schemas only — no function bodies.
```

## Data and config

| Item | Change | Must be added to |
| --- | --- | --- |
| <ENV_VAR> | <new / changed, default> | `.env.example`, `render.yaml`, `docs/PRODUCTION.md`, Horizon env |

## Test plan

Every `test` requirement maps to at least one test. Security and limit requirements also get a negative and a boundary case.

| Requirement | Test (`file::name`) | Level |
| --- | --- | --- |
| F00-R1 | `tests/...::test_...` | unit |

## Risks

| Risk | Mitigation |
| --- | --- |

## Deviations from PRD or spec wording

<None, or each deviation and why.>

## ADR

<None — choices are local to this feature. Or: docs/adr/NNN-<slug>.md>
