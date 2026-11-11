# CLAUDE.md — Engineering Standards

> Copy this file to the root of every portfolio repo. Claude Code reads it at the start of every session.
> **What to build** lives in `PRD.md`. **How it ships** lives in `docs/PRODUCTION.md`. These rules apply to every change.

---

## Branches

| Branch | Role | Deploys to |
|---|---|---|
| `main` | Production. Only release PRs from `staging` or `hotfix/*` land here. | Production (after manual approval) |
| `staging` | Release candidate. Only promotion PRs from `develop` land here. | Staging (automatic, after CI passes) |
| `develop` | Integration. Feature PRs land here. | Development (automatic, after CI passes) |

- Never commit directly to `main`, `staging`, or `develop`. Never force-push them.
- Start every feature from an up-to-date `develop`:
  `git switch develop && git pull && git switch -c feat/f03-prompt-registry`
- Branch prefixes: `feat/`, `fix/`, `test/`, `refactor/`, `chore/`, `docs/`, `hotfix/`.
- Use the PRD feature ID in the branch name and commits (`f03` = Feature 3).
- One PRD feature (or one sub-slice of it) per PR. Keep PRs under ~500 changed lines, excluding lockfiles and generated code.
- Hotfix: branch from `main` as `hotfix/<slug>`, PR into `main`, then merge `main` back into `staging` and `develop` the same day.

## Definition of done — every feature PR

1. **Tests ship with the code.** Every acceptance criterion in `PRD.md` maps to at least one test. Name tests after the behavior (`test_gateway_falls_back_to_secondary_provider_after_retries`).
2. **`make check` passes locally** (lint, types, unit, integration).
3. **Config is documented.** Any new env var is added to `.env.example`, the env matrix in `docs/PRODUCTION.md`, and `render.yaml` (backend) or the Vercel notes (frontend).
4. **Migrations are backward compatible.** Migrations run before new code is live, so use expand → migrate → contract. Never rename or drop a column in the same release that stops using it.
5. **Paperwork.** Add a line to `CHANGELOG.md` under `## Unreleased` and tick the acceptance boxes in `PRD.md`.
6. **Conventional commits:** `feat(f03): add prompt tag pointers`, `fix(gateway): honor retry-after`, `test(f02): cover circuit breaker reset`.

## Testing rules

- **Unit tests** (`tests/unit/`): no network, no database, no real LLM calls. Milliseconds each.
- **Integration tests** (`tests/integration/`): real Postgres (docker compose locally, service container in CI). All outbound HTTP — LLM providers, Stripe, GitHub, Pinecone, Places — is mocked with `respx` (Python) or `msw` (TypeScript) using recorded fixtures in `tests/fixtures/`.
- **E2E smoke tests** (`e2e/`): Playwright, run against the deployed staging URL after each staging deploy. A handful of critical paths, not exhaustive.
- **LLM evals** (`evals/`): quality scoring against golden datasets. Not part of `make test`. They cost money and run in their own workflow.
- Tests that call real paid APIs are marked `@pytest.mark.live` and are skipped unless `RUN_LIVE=1`.
- Never delete, skip, or loosen a failing test to get CI green. Fix the code, or explain in the PR why the test itself was wrong.
- Coverage floor: **80% on `app/` core modules**, enforced in CI. Don't pad coverage with assertion-free tests.
- Tests must be deterministic: freeze time (`time-machine`), seed randomness, and never depend on test order.

## Commands (keep the Makefile in sync with this list)

```
make dev               # docker compose up (postgres + redis) and run API + web with reload
make test              # unit tests
make test-integration  # integration tests (needs docker compose up)
make lint              # ruff + mypy (Python), eslint + tsc (TypeScript)
make check             # lint + test + test-integration + trace — run before every push
make trace             # requirement → test traceability (python3 scripts/sdd.py trace)
make spec-status       # every PRD feature and the state of its spec
make e2e BASE_URL=...  # Playwright smoke tests against a deployed URL
make eval              # LLM eval suite (spends API credits)
make migrate           # alembic upgrade head against $DATABASE_URL
```

## Config & secrets

- Never commit secrets. `.env` is gitignored; `.env.example` holds placeholders only.
- Settings load through `pydantic-settings` (Python) or a zod-validated `env.ts` (TypeScript). The app must fail fast at startup when a required variable is missing.
- `APP_ENV` is one of `development | staging | production`. Code must never branch on it for business logic — only for config selection and safety rails.
- Environments never share credentials, databases, vector namespaces, webhook endpoints, or Stripe keys.
- `NEXT_PUBLIC_*` variables are public. Never put a secret behind that prefix.

## Deploy rules

- Render deploys `develop` and `staging` automatically once CI passes on the commit. Production deploys only through the approval-gated `deploy-production` workflow.
- Vercel deploys every push: `main` → Production, every other branch → Preview.
- Any change to `render.yaml`, `vercel.json`, `.github/workflows/`, or `docker-compose.yml` must be called out at the top of the PR description.
- Before opening a `staging → main` release PR, run the release checklist in `docs/PRODUCTION.md`.

## Spec-driven workflow (repos with a `specs/` folder)

- No production code for a PRD feature until its `specs/fNN-*/spec.md` is `approved` and its `design.md` (approved) and `tasks.md` exist. The commands are `/sdd-spec`, `/sdd-design`, `/sdd-tasks`, `/sdd-build`, `/sdd-verify` and `/sdd-ship`; the guide is `docs/spec-driven-development.md`.
- Requirements are numbered (`F03-R4`). Every test that proves one carries `@pytest.mark.req("F03-R4")`.
- An approved spec changes only through `/sdd-spec <id> amend: …`, after the user agrees to the exact change. If code and spec disagree, stop and say which requirement is wrong and why. Never edit the spec or weaken a test to match the code.
- `/sdd-build` does one task per run and ends with one green commit.
- The spec, design, tasks and traceability live on the feature branch and merge with the code.

## How Claude Code should work in this repo

- Before writing code for a feature, restate its acceptance criteria (or, with `specs/`, its requirement IDs) and list the files you expect to create or change.
- Write or update the tests first when the behavior is well specified; otherwise write them alongside the code in the same PR.
- Use the Context7 MCP for current library docs (FastAPI, Pydantic, LangGraph, CrewAI, Next.js, the MCP SDK) instead of relying on memory.
- Stop and ask before: adding a paid service, changing the branch model, deleting data, editing production env vars, or rewriting git history.
- When CI fails, read the actual log before changing code. Don't guess.
