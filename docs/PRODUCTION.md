# Production Playbook — Render + Vercel

> Copy this file into every portfolio repo as `docs/PRODUCTION.md`.
> It's the shared "how it ships" layer for all five PRDs. Each PRD's **Feature 0** adds the project-specific pieces (its `render.yaml`, env vars, and test layout) on top of this.
> Platform facts verified November 2026. Free tiers change, so re-check the linked docs before relying on a specific limit.

---

## 1. Environment model

Three long-lived branches, three deployed environments. Feature branches get throwaway previews.

| Git branch        | Environment | Backend (Render)                 | Frontend (Vercel)                      | Database (Neon branch) | Deploy gate                                              |
| ----------------- | ----------- | -------------------------------- | -------------------------------------- | ---------------------- | -------------------------------------------------------- |
| `feat/*`, `fix/*` | Preview     | none (run locally)               | Automatic preview URL per push         | local docker Postgres  | CI on the PR                                             |
| `develop`         | Development | `<app>-api-dev`, auto-deploy     | Preview, branch URL + dev env vars     | `dev`                  | CI passes → Render deploys                               |
| `staging`         | Staging     | `<app>-api-staging`, auto-deploy | Preview, branch URL + staging env vars | `staging`              | CI passes → deploy → Playwright smoke + eval gate        |
| `main`            | Production  | `<app>-api-prod`, approval-gated | Production                             | `main`                 | CI passes → **your approval** → migrate → deploy → smoke |

**Promotion flow**

```
feat/f03-prompt-registry ──PR──▶ develop ──promotion PR──▶ staging ──release PR──▶ main
        (CI)                  (CI → dev deploy)        (CI → staging deploy      (CI → approval →
                                                        → e2e smoke → evals)      prod deploy → smoke)
hotfix/* ──PR──▶ main, then merge main back into staging and develop
```

**Why this split:** Render runs the Python backend as a long-lived container (needed for LangGraph and CrewAI runs, SSE streaming, and MCP connections). Vercel runs the Next.js frontend with per-branch previews. Neon holds Postgres because its branching gives every environment an isolated copy and its free tier doesn't expire.

---

## 2. Stack per environment

| Concern             | Service                                         | Free-tier notes                                                                                                                        |
| ------------------- | ----------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| Backend API         | Render web service (Docker runtime)             | Spins down after 15 min idle; ~1 min cold start; 750 free instance-hours/month **shared across the whole workspace**; 512 MB RAM       |
| Frontend            | Vercel (Next.js)                                | Hobby plan is for personal, non-commercial use; custom environments are Pro-only, so staging uses a branch with branch-scoped env vars |
| Postgres + pgvector | Neon                                            | Free: 10 branches per project, 1 GB per project, scales to zero after 5 min idle                                                       |
| Cache / rate limits | Upstash Redis                                   | Works from both Render and Vercel; one database per environment or a key prefix per environment                                        |
| Background jobs     | Inngest (or in-process for short tasks)         | Render background workers and cron jobs have no free tier                                                                              |
| Object storage      | Cloudflare R2 or Vercel Blob                    | Render free services have no persistent disk                                                                                           |
| Errors              | Sentry (one project, `environment` tag per env) |                                                                                                                                        |
| LLM tracing         | Langfuse or Helicone (per PRD)                  | Separate project or environment tag per env                                                                                            |

**Don't use on the free tier:** Render free Postgres (one per workspace, deleted after 30 days + 14-day grace) and Render free Key Value (one per workspace, in-memory, wiped on restart).

**Plan-ID gotcha:** Render's default service plan in a Blueprint is the paid `0.5c-512mb` tier. Every free service in `render.yaml` must say `plan: free` explicitly.

---

## 3. One-time setup checklist (per repo)

### GitHub

- [ ] Repo is **public**. Environments, environment secrets, required reviewers, and branch protection are free on public repos; on a free account's private repos, most of them aren't available. Public repos are also what Upwork clients and recruiters will click.
- [ ] Create `develop` and `staging` from `main`. Set `develop` as the default branch so PRs target it automatically.
- [ ] Ruleset for `main`, `staging`, `develop`: require a PR, require status checks `backend` and `frontend` to pass, require branches to be up to date, block force-push and deletion. Don't require approving reviews: you can't approve your own PR, so that would lock a solo repo. The production gate lives on the GitHub Environment instead.
- [ ] Environments: `development`, `staging`, `production`, plus `evals`. Each holds its own secrets (`DATABASE_URL_DIRECT` for migrations, provider keys) and variables (`API_URL`, `WEB_URL` — used by the deploy and e2e workflows). On `production`, add yourself as a **required reviewer**, restrict deployments to `main`, and add the `RENDER_DEPLOY_HOOK_URL` secret.
- [ ] Enable secret scanning + push protection, and Dependabot (security updates + version updates, weekly).

### Neon

- [ ] One Neon project per app. Branches: `main` (production), `staging`, `dev`.
- [ ] Create an app role per branch. For anything an LLM can query (the MCP Connectors project's Postgres connector), create a separate **read-only** role.
- [ ] Use the **pooled** connection string for the app and the direct one for migrations.

### Render

- [ ] Commit `render.yaml` (from the PRD's Feature 0) to `main`, then create a Blueprint in the dashboard linked to `main`. Review the resource preview before applying.
- [ ] The Hobby workspace allows **2 environments per project**: use `production` and `staging`. The dev service lives outside the project as a root-level service.
- [ ] Fill every `sync: false` secret in the dashboard per service.
- [ ] Copy the production service's **Deploy Hook URL** into the GitHub `production` environment as `RENDER_DEPLOY_HOOK_URL`.
- [ ] Optional: mark the `production` Render environment as protected.

### Vercel

- [ ] Import the repo. Set Root Directory to the frontend folder (`web` or `apps/web`). Production branch: `main`.
- [ ] Environment variables:
  - Production → production API URL and keys
  - Preview, scoped to branch `staging` → staging API URL and keys
  - Preview, scoped to branch `develop` → dev API URL and keys
  - Preview (all other branches) → dev API URL
- [ ] Use the stable **branch URL** Vercel generates for `staging` and `develop`, or assign custom domains like `staging.yourdomain.dev` to those branches.
- [ ] Ignored Build Step: `git diff --quiet HEAD^ HEAD -- .` so backend-only commits don't rebuild the frontend.
- [ ] If Deployment Protection is on for previews, either configure an automation bypass for Playwright or turn it off for this project.

### Providers

- [ ] Separate API keys per environment for every LLM provider, with a **hard monthly spend limit** on each (smallest on dev, largest on prod).
- [ ] Stripe and similar: test-mode keys in every environment, **including production**, until a real customer exists.

---

## 4. CI/CD workflows

Three workflows cover every repo. Paths assume `api/` (Python) and `web/` (Next.js); adjust per PRD.

### `.github/workflows/ci.yml` — every PR and every push to a long-lived branch

```yaml
name: CI
on:
  pull_request:
    branches: [develop, staging, main]
  push:
    branches: [develop, staging, main]

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  backend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: api
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_USER: app
          POSTGRES_PASSWORD: app
          POSTGRES_DB: app_test
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U app"
          --health-interval 5s --health-timeout 5s --health-retries 10
    env:
      APP_ENV: development
      DATABASE_URL: postgresql+psycopg://app:app@localhost:5432/app_test
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with:
          enable-cache: true
      - run: uv sync --frozen
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run mypy app
      - run: uv run alembic upgrade head
      - run: uv run pytest tests/unit tests/integration --cov=app --cov-report=xml --cov-fail-under=80 --junitxml=reports/junit.xml
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: backend-reports
          path: api/reports

  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: web
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
          cache-dependency-path: web/pnpm-lock.yaml
      - run: pnpm install --frozen-lockfile
      - run: pnpm lint
      - run: pnpm typecheck
      - run: pnpm test --run
      - run: pnpm build

  migrate:
    # Runs migrations against dev/staging after tests pass on a push.
    # Render's autoDeployTrigger: checksPass waits for this job before deploying.
    if: github.event_name == 'push' && (github.ref_name == 'develop' || github.ref_name == 'staging')
    needs: [backend, frontend]
    runs-on: ubuntu-latest
    environment: ${{ github.ref_name == 'staging' && 'staging' || 'development' }}
    defaults:
      run:
        working-directory: api
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: uv sync --frozen
      - run: uv run alembic upgrade head
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL_DIRECT }}
```

Migrations run from CI rather than Render's `preDeployCommand` because pre-deploy commands may not be available on free instances. If you upgrade a service to a paid instance, you can move them into `render.yaml`.

### `.github/workflows/deploy-production.yml` — approval-gated release

```yaml
name: Deploy production
on:
  workflow_run:
    workflows: [CI]
    types: [completed]
    branches: [main]

concurrency:
  group: deploy-production
  cancel-in-progress: false

jobs:
  deploy:
    if: github.event.workflow_run.conclusion == 'success' && github.event.workflow_run.event == 'push'
    runs-on: ubuntu-latest
    environment: production # pauses here until you approve in the GitHub UI
    env:
      SHA: ${{ github.event.workflow_run.head_sha }}
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.workflow_run.head_sha }}
      - uses: astral-sh/setup-uv@v6

      - name: Run migrations (expand-only, backward compatible)
        working-directory: api
        run: uv sync --frozen && uv run alembic upgrade head
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL_DIRECT }}

      - name: Trigger Render deploy
        run: curl -fsS -X POST "${{ secrets.RENDER_DEPLOY_HOOK_URL }}"

      - name: Wait for the new commit to go live
        run: |
          for i in $(seq 1 60); do
            live=$(curl -fsS "${{ vars.API_URL }}/healthz" | jq -r '.commit' || true)
            if [ "$live" = "$SHA" ]; then echo "Live: $live"; exit 0; fi
            sleep 15
          done
          echo "Timed out waiting for $SHA"; exit 1

      - name: Production smoke test (read-only)
        run: |
          curl -fsS "${{ vars.API_URL }}/healthz"
          curl -fsS "${{ vars.API_URL }}/readyz"
```

`/healthz` must return the running commit. Render sets `RENDER_GIT_COMMIT` at runtime; return it as `commit`.

Vercel deploys `main` on its own when the release PR merges, so every release must keep the frontend and backend **compatible in both directions** for a few minutes. If you'd rather release them together, disable "Auto-assign Custom Production Domains" in Vercel and add a `vercel promote` step after the smoke test.

### `.github/workflows/e2e-staging.yml` — smoke tests after each staging deploy

```yaml
name: E2E (staging)
on:
  workflow_run:
    workflows: [CI]
    types: [completed]
    branches: [staging]

jobs:
  smoke:
    if: github.event.workflow_run.conclusion == 'success' && github.event.workflow_run.event == 'push'
    runs-on: ubuntu-latest
    environment: staging
    env:
      SHA: ${{ github.event.workflow_run.head_sha }}
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.workflow_run.head_sha }}
      - name: Wait for staging API to serve this commit
        run: |
          for i in $(seq 1 60); do
            live=$(curl -fsS "${{ vars.API_URL }}/healthz" | jq -r '.commit' || true)
            [ "$live" = "$SHA" ] && exit 0
            sleep 15
          done
          exit 1
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
      - run: pnpm --dir e2e install --frozen-lockfile && pnpm --dir e2e exec playwright install --with-deps chromium
      - run: pnpm --dir e2e exec playwright test
        env:
          BASE_URL: ${{ vars.WEB_URL }}
          API_URL: ${{ vars.API_URL }}
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-report
          path: e2e/playwright-report
```

### `.github/workflows/eval.yml` — LLM quality gate

- **Triggers:** PRs into `staging` or `main` that touch prompts, model config, retrieval, or agent code (path filter), plus `workflow_dispatch`.
- **Runs:** `make eval` with the `evals` environment's low-limit API key and a `MAX_EVAL_COST_USD` budget.
- **Gate:** fails when the aggregate score drops more than the allowed delta below `evals/baseline.json`. Writes a score table to the job summary.
- **Baseline updates:** only through a PR that changes `evals/baseline.json`, with the reason in the description.

---

## 5. Testing strategy

### The pyramid

| Layer           | Folder                                  | Runs                        | Talks to                              | Target                                                              |
| --------------- | --------------------------------------- | --------------------------- | ------------------------------------- | ------------------------------------------------------------------- |
| Unit            | `api/tests/unit`, `web/**/*.test.ts(x)` | every commit, CI            | nothing external                      | Most tests; milliseconds each                                       |
| Integration     | `api/tests/integration`                 | `make check`, CI            | real Postgres; HTTP mocked with respx | Every API route, DB query, and external client                      |
| Contract        | `api/tests/contract`                    | CI                          | OpenAPI schema snapshot               | API shape changes are deliberate; frontend types regenerate from it |
| E2E smoke       | `e2e/`                                  | after each staging deploy   | deployed staging                      | 3–6 critical user paths                                             |
| LLM evals       | `api/evals/`                            | prompt changes, pre-release | real models, small golden set         | Quality doesn't regress                                             |
| Load (optional) | `load/` (k6)                            | manual                      | staging                               | Gateway and MCP projects only                                       |

### Folder layout

```
api/
  app/
  tests/
    conftest.py            # app factory, DB session with per-test rollback, respx router, frozen clock
    fixtures/
      llm/                 # recorded provider responses (JSON), one file per scenario
      documents/           # synthetic PDFs/DOCX — never real personal data
    unit/
    integration/
    contract/
      openapi.snapshot.json
  evals/
    datasets/
    baseline.json
    run.py
web/
  src/**/*.test.tsx        # Vitest + Testing Library
e2e/
  playwright.config.ts
  tests/smoke.spec.ts
```

### Core fixtures (`api/tests/conftest.py`)

```python
import pytest
import respx
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import get_settings
from app.main import create_app


@pytest.fixture(scope="session")
def engine():
    return create_async_engine(get_settings().database_url)


@pytest.fixture
async def db(engine):
    """Each test runs inside a transaction that is rolled back afterward."""
    async with engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()


@pytest.fixture
def mock_http():
    """Blocks all real outbound HTTP. Tests register the routes they expect."""
    with respx.mock(assert_all_called=False) as router:
        yield router


@pytest.fixture
async def client(db, mock_http):
    app = create_app(db_session_override=db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
```

### Conventions

- One test file per module (`app/gateway/resilience.py` → `tests/unit/gateway/test_resilience.py`).
- Each PRD acceptance criterion gets a test whose name reads like the criterion.
- Recorded LLM fixtures are small, hand-trimmed JSON files. Re-record them with a script, never by hand-editing model output to make a test pass.
- Synthetic test documents only. No real résumés, contracts, or customer data in the repo.
- Frontend: test behavior (what the user sees and clicks) with Testing Library, not implementation details.

---

## 6. Health, observability, and safety baseline

Every backend ships these in Feature 0, before any product feature:

- `GET /healthz` → `{"status": "ok", "commit": RENDER_GIT_COMMIT, "env": APP_ENV}`. No dependencies checked. Used by Render's health check and the deploy workflows.
- `GET /readyz` → checks the DB (and Redis, if used). Returns 503 when a dependency is down.
- Structured JSON logs with a request ID on every line, propagated to LLM traces.
- Sentry initialized with `environment=APP_ENV` and `release=commit`.
- CORS allowlist per environment (the matching Vercel URL), never `*`.
- **Public demo protection** (any endpoint that spends LLM money):
  - per-IP rate limit (Upstash Ratelimit)
  - a daily global LLM budget; when it's hit, the app switches to a cached "demo mode" instead of calling providers
  - Cloudflare Turnstile on expensive actions
  - input caps (file size, page count, prompt length)
- **Cold-start-aware UI:** on load, the frontend pings `/healthz`. If it takes more than 2 seconds, show "Waking up the demo server (free tier, about a minute)" instead of a spinner that looks broken.

---

## 7. Release process

### Promote `develop` → `staging`

1. Open a PR from `develop` into `staging` titled `release: vX.Y.Z-rc`.
2. CI runs, the eval gate runs (if prompts changed), and staging deploys after merge.
3. `e2e-staging` must pass. Click through the staging app yourself for 5 minutes.

### Release `staging` → `main`

1. Move `CHANGELOG.md`'s `Unreleased` section under the new version.
2. Open a PR from `staging` into `main` titled `release: vX.Y.Z`. Merge when green.
3. Approve the `deploy-production` job in GitHub. Watch it finish its smoke test.
4. Tag the release: `git tag vX.Y.Z && git push --tags`, and create a GitHub Release with the changelog section.

### Release checklist

- [ ] All PRD acceptance boxes for this release are ticked and covered by tests
- [ ] Migrations are expand-only (nothing renamed or dropped that old code still reads)
- [ ] New env vars exist in Render (prod), Vercel (Production), and GitHub `production`
- [ ] Eval scores at or above baseline
- [ ] Staging smoke passed on the exact commit being released

### Rollback

- **Backend:** Render dashboard → Deploys → roll back. Free instances can roll back to the two most recent previous deploys.
- **Frontend:** Vercel → Deployments → promote the previous production deployment.
- **Database:** roll forward with a fix migration. Neon's free plan keeps 6 hours of restore history for emergencies.
- After any rollback, open a `hotfix/*` branch, add a test that reproduces the failure, then fix.

---

## 8. Free-tier budget across all five projects

Five apps × three environments = 15 backend services in one Render workspace.

| Limit                                                  | Impact                                                                                      | What to do                                                                                                                               |
| ------------------------------------------------------ | ------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| 750 free instance-hours/month, shared by the workspace | Sleeping services use nothing, so 15 mostly idle services fit. You can't keep several warm. | Don't run keep-alive pingers on free services; they'd drain the shared pool.                                                             |
| ~1 minute cold start                                   | A client opening your demo waits a minute on first load                                     | Upgrade the **production** API of your 1–2 flagship demos to the `0.5c-512mb` instance (about $7/month each). Keep dev and staging free. |
| 500 build minutes/month on the Hobby workspace         | Docker builds on every `develop` push add up across five repos                              | Use `buildFilter` so frontend-only commits don't rebuild the API; keep images slim. Overage is billed per 1K minutes.                    |
| 512 MB RAM on free instances                           | Heavy agent frameworks can run out of memory                                                | Measure peak RSS in staging (TableCrew especially) before you need it in production.                                                     |
| Hobby workspace: 2 environments per project            | No third Render environment for dev                                                         | Dev service sits at the Blueprint's root level, outside the project.                                                                     |
| Vercel Hobby is non-commercial                         | Fine for portfolio demos                                                                    | Anything you build for a paying client runs on the client's account or Vercel Pro.                                                       |

**Baseline cost:** $0 hosting. **Recommended:** about $14/month to keep two flagship production APIs warm, plus LLM usage under hard per-key spend limits.

---

## 9. MCP servers and skills that help in Claude Code

| Tool                      | Use it for                                                                                         | Setup                                                                                                                                                                     |
| ------------------------- | -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Render MCP** (official) | Create services, read logs and metrics, trigger deploys, run read-only SQL against Render Postgres | `claude mcp add --transport http render https://mcp.render.com/mcp --header "Authorization: Bearer <RENDER_API_KEY>"` or `/plugin install render@claude-plugins-official` |
| **Vercel MCP** (official) | Deployment status, build logs, runtime logs, Vercel docs search                                    | Server URL `https://mcp.vercel.com` (OAuth)                                                                                                                               |
| **GitHub MCP**            | Issues per feature, PRs, reading CI results                                                        |                                                                                                                                                                           |
| **Context7**              | Current docs for FastAPI, LangGraph, CrewAI, Next.js, MCP SDK                                      |                                                                                                                                                                           |
| **Linear MCP**            | Track each PRD feature as an issue if you plan in Linear                                           |                                                                                                                                                                           |
| **Sentry MCP**            | Triage staging and production errors from inside a session                                         |                                                                                                                                                                           |

Skills worth loading when they're installed: `engineering:testing-strategy` (test plans per feature), `engineering:deploy-checklist` (before each release PR), `engineering:code-review` (self-review before merging to `develop`), `engineering:architecture` (ADRs for decisions like Neon vs Render Postgres), and `frontend-design` for any user-facing screen.

---

## Sources

- [Render — Deploy for Free](https://render.com/docs/free)
- [Render — Projects and environments](https://render.com/docs/projects)
- [Render — Preview environments](https://render.com/docs/preview-environments)
- [Render — Blueprint YAML reference](https://render.com/docs/blueprint-spec)
- [Render — Pricing](https://render.com/pricing)
- [Render — MCP server](https://render.com/docs/mcp-server)
- [Vercel — Environments and staging](https://vercel.com/docs/deployments/custom-environments)
- [Vercel — Hobby plan](https://vercel.com/docs/plans/hobby-plan)
- [Neon — Free plan limits](https://neon.com/faqs/free-plan-limits-and-quotas)
- [GitHub — Environments availability](https://docs.github.com/actions/reference/environments)
