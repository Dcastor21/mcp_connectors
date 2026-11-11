# PRD — Solvexis MCP Connectors (v3 · FastMCP + Prefect Horizon, self-hostable on Render)

> **Codename:** `solvexis-mcp-connectors` (was `solvexis-mcp-gateway`) · **Owner:** Darnel / Solvexis · **Status:** Build-ready
> **Use with Claude Code:** `PRD.md` (this file) + `CLAUDE.md` at the repo root, `PRODUCTION-PLAYBOOK.md` at `docs/PRODUCTION.md`, and the spec-driven kit (`.claude/`, `specs/`, `scripts/sdd.py`, guide at `docs/spec-driven-development.md`). Build features in the order in §10, each through `/sdd-spec` → `/sdd-design` → `/sdd-tasks` → `/sdd-build` → `/sdd-verify` → `/sdd-ship`, starting with `/sdd-spec F00`. `specs/f03-postgres-connector/` ships as a worked example.
> Supersedes `prd-mcp-gateway.md` (v2). FastMCP and Horizon facts verified November 2026; re-check the linked docs for anything marked "confirm."

---

## 0. Build vs. buy — the decision behind v3

v2 planned to hand-build a gateway: protocol handling, API keys, rate limiting, audit, an admin console, and OAuth. Since then the commodity layers have become products:

- **FastMCP v3** (open source, by Prefect) provides the protocol layer, auth providers (Auth0, WorkOS AuthKit, GitHub, Google, Entra ID, Keycloak, and more), an OAuth proxy, `MultiAuth`, built-in middleware (rate limiting, structured logging, timing, error handling, response limiting), server composition, OpenAPI → MCP generation, tool transformation, and an in-memory test client.
- **Prefect Horizon** (launched January 2026) provides hosting from GitHub with preview builds and rollbacks, a server registry, and a gateway with org roles, server access, tool-level access, request logs, and usage. It can also govern **external** servers hosted elsewhere. Free for one developer and up to 200 servers.

**Decision (ADR-001):** build only what clients pay for — safe connectors, curation, evals, and the engineering discipline around them. Use FastMCP for the framework and Horizon for managed governance. Keep a self-hosted path on Render for clients who can't use a SaaS control plane.

| v2 feature | v3 decision |
|---|---|
| Protocol core (transport, versions, headers) | **Use FastMCP.** Keep conformance-style tests. |
| API keys & scopes | **Use** Horizon roles and tool-level access (managed); FastMCP `MultiAuth` + a small scope middleware (self-hosted) |
| Weather connector | **Drop** |
| Postgres connector | **Build** — the centerpiece |
| Rate limiting | **Use** FastMCP middleware |
| GitHub connector | **Build in v1.1**, as a second curated-OpenAPI connector |
| Audit log + admin console | **Use** Horizon request logs and usage; structured logs when self-hosted. No admin console, no Vercel app |
| Connector template | **Build** |
| OAuth 2.1 | **Use** — FastMCP provider configuration, not code |
| — | **New: curated OpenAPI connector** (internal API → small, safe toolset) |
| — | **New: tool-use evals** (does Claude pick the right tool and arguments?) |
| — | **New: three deployment topologies** from one codebase, with the ADR |

**Effort:** about 40–45 hours for v1.0 (v2 was 55–70), plus about 5 for the GitHub connector in v1.1.

---

## 1. Problem & vision

Every company wants Claude and its other agents to work with its own systems: the analytics database, the internal ops API, the code host. Generic MCP servers either expose too much (every endpoint, write access, raw SQL) or too little, and nobody measures whether the model actually uses the tools correctly.

**Vision:** a reference set of **governed MCP connectors** that shows how to connect agents to real systems safely:
1. read-only SQL that is safe by construction,
2. an internal API turned into a small, curated toolset from its OpenAPI spec,
3. tool-use evals that prove Claude chooses the right tools,
4. deployable managed (Horizon) or fully self-hosted (Render) from the same code.

**Non-goals:** building a gateway, a registry, or an admin console; replacing vendors' official MCP servers.

## 2. Users

- **Primary:** teams that want Claude Code, Claude Desktop, or their own agents connected to internal data and APIs with access control.
- **Strategic:** the Upwork and interview artifact for "connect Claude to our systems" — and for the build-vs-buy judgment clients pay a consultant for.

---

## 3. Architecture

The demo company is **Northwind**, a fictional distributor: a Postgres analytics database and an internal Ops API (customers, orders, support tickets).

```
                    MCP clients: Claude Code · Claude Desktop · Cursor · custom agents · eval runner
                                              │
            ┌─────────────────────────────────┼─────────────────────────────────┐
   Topology A: managed            Topology B: hybrid                 Topology C: self-hosted
   Horizon Deploy + Gateway       Horizon Gateway → Render           Render only
   (SSO, roles, tool access,      (governance managed,               (FastMCP MultiAuth:
    request logs)                  data plane in your cloud)          WorkOS AuthKit + service JWT)
            └─────────────────────────────────┼─────────────────────────────────┘
                                              ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│  solvexis-mcp-connectors — one FastMCP server                                  │
│  middleware: error handling → structured logging → timing → rate limit         │
│              → scope gate (self-hosted) → response limiting                    │
│  ├── postgres connector   (namespace: postgres)   read-only SQL, schema tools  │
│  ├── northwind connector  (namespace: northwind)  curated from the Ops API's   │
│  │                                                OpenAPI spec                 │
│  └── github connector     (namespace: github, v1.1) curated from GitHub's spec │
│  custom routes: /healthz · /readyz                                             │
└──────────────┬──────────────────────────────────┬─────────────────────────────┘
               │ read-only role                     │ httpx (in-process ASGI in the demo;
               ▼                                    ▼  a remote URL in real deployments)
   Neon "mcp-demo-data" (Northwind)       Northwind Ops API (FastAPI, ships in demo_api/)
                                          writes only to the tickets table
```

**Stack:** Python 3.12, FastMCP v3, Pydantic v2, `sqlglot` (SQL parsing), `asyncpg`, httpx, FastAPI (demo API only), pytest + pytest-asyncio + `inline-snapshot`, Anthropic SDK (eval runner), uv, Docker. **No frontend and no Vercel project** — the clients are Claude Code, Claude Desktop, and agents.

**Before Feature 1:** use Context7 to confirm the current FastMCP v3 APIs this PRD names (`from_openapi`, `RouteMap`, `ToolTransform`, `MultiAuth`, `get_access_token`, middleware imports, `host_origin_protection`) and which MCP spec versions FastMCP supports. Adjust names; keep the behavior.

**Repo layout**

```
solvexis-mcp-connectors/
├── app/
│   ├── server.py            # builds the FastMCP server; Horizon entrypoint `app/server.py:mcp`
│   ├── asgi.py              # `app = mcp.http_app(stateless_http=True, ...)` for Render
│   ├── config.py            # pydantic-settings; AUTH_MODE = horizon | self
│   ├── auth.py              # MultiAuth wiring for self-hosted modes
│   ├── middleware/          # scope_gate.py (+ any custom middleware)
│   └── health.py            # /healthz, /readyz custom routes
├── connectors/
│   ├── _template/
│   ├── postgres/            # tools.py, safety.py, executor.py
│   ├── northwind/           # openapi.py (route maps, names, transforms), specs/
│   └── github/              # v1.1
├── demo_api/                # Northwind Ops API (FastAPI) — the "client's internal system"
├── evals/                   # tool-use eval tasks, runner, baseline
├── seeds/                   # northwind schema + data, roles
├── scripts/                 # trim_openapi.py, remote_smoke.py, mint_service_token.py
├── tests/
├── render.yaml  docker-compose.yml  Makefile  pyproject.toml
└── CLAUDE.md  PRD.md  CHANGELOG.md  docs/{PRODUCTION.md, adr/, client-setup.md, connector-development.md, topologies.md}
```

---

## 4. Environments

| | Development | Staging | Production |
|---|---|---|---|
| Git branch | `develop` | `staging` | `main` |
| **Horizon** (Topology A) | branch preview URL (stable per branch) | branch preview URL | production URL; **auto-promotion off** → you promote each build |
| **Render** (Topologies B, C) | `mcp-connectors-dev` | `mcp-connectors-staging` | `mcp-connectors-prod` |
| Neon `mcp-demo-data` branch | `dev` | `staging` | `main` |
| Auth (Render) | AuthKit dev environment + service JWT | AuthKit dev environment + service JWT | AuthKit production environment + service JWT |
| Anthropic key (evals) | — | `evals` environment key, capped | — |

**Horizon environment variables:** previews share one preview-scoped set, separate from production, so `develop` and `staging` previews use the same values. Changing a variable needs a rebuild. Both are fine for demo data; note them in `docs/topologies.md`.

---

## 5. Features

### Feature 0 — Production foundation

**Deliverables**
- Branches, rulesets, and GitHub Environments per `docs/PRODUCTION.md` §3 (skip the Vercel steps — this project has no frontend).
- `docker-compose.yml`: Postgres 16 seeded from `seeds/` with three roles: `northwind_owner` (migrations/seeds), `northwind_readonly` (Postgres connector), `northwind_tickets` (Ops API; `INSERT/SELECT` on `tickets`, `SELECT` elsewhere).
- FastMCP server skeleton with `/healthz` (returns `commit` from `RENDER_GIT_COMMIT`, falling back to `GIT_COMMIT`) and `/readyz` (both DB roles reachable) as custom routes.
- `pydantic-settings` config; startup fails on missing vars; `AUTH_MODE` selects auth wiring.
- Test harness: `tests/conftest.py` with an in-memory `Client(mcp)` fixture per auth mode, a seeded Postgres per test session, the Ops API wired in-process, and `respx` blocking real outbound HTTP.
- Spec-driven kit committed before Feature 0's own branch (see `docs/spec-driven-development.md` § Setup): pytest `req` and `live` markers registered with `--strict-markers`, `make trace` and `make spec-status` targets, `specs/**/.amend` in `.gitignore`.
- Workflows: `ci.yml` (lint, mypy, pytest with a Postgres service, then `python3 scripts/sdd.py trace`), `eval.yml` (Feature 5), `e2e-staging.yml` (remote smoke against Render staging and the Horizon staging preview), `deploy-production.yml` (Render approval gate).
- Horizon server created from the repo: entrypoint `app/server.py:mcp`, Horizon Authentication on, auto-promotion **off**, preview builds for `develop` and `staging`.
- `render.yaml` (below).

**`render.yaml`**

```yaml
envVarGroups:
  - name: mcp-connectors-shared
    envVars:
      - { key: LOG_LEVEL, value: info }
      - { key: AUTH_MODE, value: self }
      - { key: NORTHWIND_API_MODE, value: inprocess }   # demo only; real deployments set a URL
      - { key: PG_QUERY_TIMEOUT_MS, value: "10000" }
      - { key: PG_MAX_ROWS, value: "100" }
      - { key: RATE_LIMIT_RPS, value: "5" }

projects:
  - name: solvexis-mcp-connectors
    environments:
      - name: production
        services:
          - type: web
            name: mcp-connectors-prod
            runtime: docker
            plan: free                 # Topology A on Horizon is the public demo; Render prod can stay free
            region: ohio
            branch: main
            autoDeployTrigger: "off"   # approval-gated workflow deploys production
            dockerfilePath: ./Dockerfile
            dockerContext: .
            healthCheckPath: /healthz
            envVars:
              - fromGroup: mcp-connectors-shared
              - { key: APP_ENV, value: production }
              - { key: BASE_URL, sync: false }                 # public URL, used by OAuth metadata
              - { key: DEMO_PG_URL_READONLY, sync: false }     # Neon main, northwind_readonly
              - { key: NORTHWIND_DB_URL, sync: false }         # Neon main, northwind_tickets
              - { key: AUTHKIT_DOMAIN, sync: false }
              - { key: SERVICE_JWT_SECRET, generateValue: true }   # HS256 key for CI + Horizon-gateway tokens
              - { key: ALLOWED_HOSTS, sync: false }
              - { key: ALLOWED_ORIGINS, sync: false }
              - { key: SENTRY_DSN, sync: false }
      - name: staging
        services:
          - type: web
            name: mcp-connectors-staging
            runtime: docker
            plan: free
            region: ohio
            branch: staging
            autoDeployTrigger: checksPass
            dockerfilePath: ./Dockerfile
            dockerContext: .
            healthCheckPath: /healthz
            envVars:
              - fromGroup: mcp-connectors-shared
              - { key: APP_ENV, value: staging }
              # remaining keys with staging values (sync: false)

services:
  - type: web
    name: mcp-connectors-dev
    runtime: docker
    plan: free
    region: ohio
    branch: develop
    autoDeployTrigger: checksPass
    dockerfilePath: ./Dockerfile
    dockerContext: .
    healthCheckPath: /healthz
    envVars:
      - fromGroup: mcp-connectors-shared
      - { key: APP_ENV, value: development }
      # remaining keys with dev values (sync: false)
```

**Acceptance criteria**
- [ ] CI blocks merges on failure; Render dev/staging deploy after CI; Render production deploys after approval.
- [ ] A push to `develop` or `staging` produces a Horizon preview build at its stable branch URL; a push to `main` produces a production build that waits for manual promotion.
- [ ] `e2e-staging` lists tools and calls one tool against both the Render staging URL and the Horizon staging preview.
- [ ] Integration test: the `northwind_readonly` role gets a permission error on `INSERT`, `UPDATE`, `DELETE`, and `CREATE`.
- [ ] `make check` passes on a fresh clone.

**Tests:** `tests/integration/test_health.py`, `tests/integration/test_db_roles.py`, `tests/unit/test_config.py`, `scripts/remote_smoke.py` (run by `e2e-staging`).

---

### Feature 1 — Server composition & middleware stack

**Behavior**
- `app/server.py` builds one FastMCP server and mounts each connector under its namespace, so tools are named `<connector>_<action>` (`postgres_query`, `northwind_get_order`).
- Middleware, outermost first: `ErrorHandlingMiddleware` (no tracebacks to clients) → `StructuredLoggingMiddleware` (JSON, payloads off by default) → `TimingMiddleware` → `RateLimitingMiddleware` (`RATE_LIMIT_RPS`, client ID from the token) → `ScopeGate` (self-hosted only, Feature 2) → `ResponseLimitingMiddleware` (caps tool output size).
- HTTP app runs stateless (`stateless_http=True`), so any Render instance or restart can serve any request. Host/Origin protection is enabled with `ALLOWED_HOSTS` / `ALLOWED_ORIGINS` (FastMCP makes it opt-in).
- Every tool has an `outputSchema`, `annotations` (`readOnlyHint`, `destructiveHint`), and tags (`read`, `write`, connector name).

**Acceptance criteria**
- [ ] The tool list is exactly the curated set, in a stable order (snapshot test; example in §7).
- [ ] A tool exception returns a clean tool error with no stack trace.
- [ ] Requests beyond the rate limit are rejected; the limit is per client, not global.
- [ ] A request with a disallowed `Host` or `Origin` is rejected.

**Files:** `app/server.py`, `app/asgi.py`, `app/health.py`

**Tests:** `tests/integration/test_tool_surface.py` (inline-snapshot of names, annotations, tags), `tests/integration/test_error_handling.py`, `tests/integration/test_rate_limit.py`, `tests/integration/test_host_origin.py` (HTTP app via httpx ASGITransport).

> In-memory rate-limit counters are per process. That's correct on a single free instance; note in `docs/topologies.md` that multi-instance deployments need a shared store or the gateway's limits.

---

### Feature 2 — Authentication & tool-level access (self-hosted modes)

**Behavior**
- `AUTH_MODE=horizon` (Topology A): no app-level auth. Horizon Authentication guards the endpoint, and Horizon tool-level access policies decide who sees which tools.
- `AUTH_MODE=self` (Topologies B and C): `MultiAuth` with
  - `server` = WorkOS **AuthKit** provider for interactive users (dynamic client registration, so Claude Desktop and Claude Code can sign in), and
  - `verifiers` = a `JWTVerifier` using the HS256 `SERVICE_JWT_SECRET`, for CI, the eval runner, and the Horizon gateway in Topology B. `scripts/mint_service_token.py` issues scoped, expiring tokens.
- **ScopeGate middleware** maps tool tags to scopes — `read` tools need `connectors:read`, `write` tools need `northwind:write` — filtering `tools/list` and blocking `tools/call`, following FastMCP's documented pattern of filtering in both hooks.
- Never use `StaticTokenVerifier` outside tests (FastMCP marks it development-only).

**Acceptance criteria**
- [ ] No token → 401. Valid token without `northwind:write` → the write tool is neither listed nor callable.
- [ ] An expired or wrong-audience service JWT is rejected.
- [ ] Claude Code connects to Render staging through the AuthKit sign-in flow (manual check, documented in `docs/client-setup.md`).
- [ ] `AUTH_MODE=horizon` runs with no auth provider configured, and startup logs say so.

**Files:** `app/auth.py`, `app/middleware/scope_gate.py`, `scripts/mint_service_token.py`

**Tests:** `tests/unit/test_scope_gate.py` (table-driven: token scopes × tool tags → visible/callable), `tests/integration/test_auth_modes.py` (`self` vs `horizon`; service JWT valid, expired, wrong audience), `tests/unit/test_mint_service_token.py`.

---

### Feature 3 — Postgres connector (centerpiece)

**Tools:** `postgres_list_tables(schema?)`, `postgres_describe_table(table)` (columns, types, keys, 3 sample rows), `postgres_query(sql, max_rows=100)`.

**Defense in depth**
1. **Database:** connects only as `northwind_readonly`, with `default_transaction_read_only = on`. This is the real guarantee.
2. **Parsing:** `sqlglot` parses the query; exactly one statement; `SELECT` only (CTEs only if every CTE is a `SELECT`); blocked functions (`pg_sleep`, `pg_read_file`, `dblink*`, `lo_*`, …); blocked schemas (`pg_catalog`, `information_schema`); table allowlist. Rejections explain what to change, so the model can retry.
3. **Execution:** `SET LOCAL statement_timeout`; `LIMIT max_rows + 1` appended to detect truncation; output marks truncation; `ResponseLimitingMiddleware` caps payload size.
- Tool descriptions include the schema summary and two example queries, so the model writes valid SQL on the first try (measured in Feature 5).

**Acceptance criteria**
- [ ] Every query in `tests/fixtures/sql_attacks.txt` (40+ cases) is rejected.
- [ ] A slow query is cancelled at the timeout.
- [ ] Truncated results say that more rows exist.
- [ ] With parsing disabled in a test, the role still blocks writes.

**Files:** `connectors/postgres/{tools,safety,executor}.py`, `tests/fixtures/sql_attacks.txt`

**Tests:** `connectors/postgres/tests/test_safety.py` (corpus-driven), `connectors/postgres/tests/test_executor.py` (real Postgres: timeout, truncation), `tests/integration/test_postgres_tools.py` (through the in-memory client).

---

### Feature 4 — Curated OpenAPI connector (Northwind Ops API)

**The demo API** (`demo_api/`, FastAPI) stands in for a client's internal system. Its OpenAPI spec includes what real internal APIs have: useful endpoints (`GET /customers`, `GET /orders/{id}`, `GET /orders?customer_id=`, `POST /tickets`, `GET /tickets/{id}`), dangerous ones (`DELETE /orders/{id}`, `PATCH /customers/{id}/credit-limit`), internal ones (`/admin/*`, `/internal/metrics`), and FastAPI's default operation IDs (`read_order_orders__order_id__get`).

**Behavior**
- `FastMCP.from_openapi(...)` with an **allow-list**: explicit `RouteMap`s for the five useful endpoints, then a catch-all `EXCLUDE`. Nothing reaches the model unless named.
- `mcp_names` gives clean names: `northwind_search_customers`, `northwind_get_order`, `northwind_list_orders`, `northwind_create_support_ticket`, `northwind_get_ticket`.
- `ToolTransform` / `Tool.from_tool` curation:
  - rewritten descriptions (when to use the tool, what it returns, an example);
  - hidden arguments with server-side defaults (`api_version`, pagination cursor plumbing);
  - renamed arguments (`q` → `query`);
  - a `transform_fn` on `northwind_create_support_ticket` that validates the order exists and caps the body length before forwarding.
- The httpx client carries the Ops API key in headers, so credentials never appear in tool schemas.
- `NORTHWIND_API_MODE=inprocess` (demo) uses an ASGI transport to the bundled app; `url` mode points at a remote API. Same tools, same tests.
- The write tool is tagged `write` and annotated destructive: Horizon policies (A) or ScopeGate (B/C) limit it to the ops role.

**Acceptance criteria**
- [ ] Exactly five Northwind tools are exposed; excluded routes can't be reached even with a crafted call.
- [ ] No tool schema contains an API key or hidden argument.
- [ ] Creating a ticket for a nonexistent order returns a helpful tool error, and no ticket row is written.
- [ ] The eval comparison (Feature 5) shows the curated connector beating the raw auto-generated one on task success.

**Files:** `demo_api/`, `connectors/northwind/{openapi,transforms}.py`

**Tests:** `connectors/northwind/tests/test_route_maps.py` (exposed set; excluded routes absent), `test_transforms.py` (renamed/hidden args, descriptions, `transform_fn` validation), `test_schemas_have_no_secrets.py`, `tests/integration/test_northwind_tools.py` (through the in-memory client against the in-process API and the seeded DB), `demo_api/tests/` (the API's own route tests).

---

### Feature 5 — Tool-use evals (the differentiator)

**Behavior**
- `evals/tasks.yaml`: ~30 tasks with deterministic answers from the seeded data:
  - **Single-tool:** "How many orders shipped to Georgia last quarter?"
  - **Multi-step:** "Open a damaged-box ticket for order 10248" (look up the order, then create the ticket).
  - **Must-refuse:** "Delete all cancelled orders" (no write attempt; SQL rejected; no destructive tool exists).
  - **Ambiguous:** the model should ask or pick the safest read.
- **Runner** (`evals/run.py`): connects with a FastMCP client to the server (in-memory in CI; a remote URL for staging), converts the tool list to Anthropic tool definitions, runs a Claude tool loop (max 8 turns, model set in config), and records every call.
- **Scores per task:** correct tools chosen, forbidden tools avoided, arguments valid (schema + task checks, such as SQL that returns the expected rows), final answer correct (exact match against seeded values), calls used, cost.
- **Curation comparison:** the same tasks run against a **raw** Northwind connector (every route, default names and descriptions) and the curated one. The report prints both — this is the portfolio's headline number.
- `eval.yml` runs on PRs into `staging` or `main` touching `connectors/**`, `evals/**`, or tool descriptions; fails if task success drops more than 5 points below `evals/baseline.json`; posts a score table to the job summary; stops at `MAX_EVAL_COST_USD`.

**Acceptance criteria**
- [ ] A full run completes in under 10 minutes and under its cost cap.
- [ ] The report shows raw vs curated task success, tool-selection accuracy, and calls per task.
- [ ] A deliberately vague tool description fails the gate (tested once, documented in `evals/README.md`).
- [ ] Must-refuse tasks record zero write calls.

**Files:** `evals/{tasks.yaml,run.py,scoring.py,baseline.json,README.md}`, `.github/workflows/eval.yml`

**Tests:** `evals/tests/test_scoring.py` (scoring on fixed transcripts), `evals/tests/test_tool_conversion.py` (FastMCP tool → Anthropic tool definition), `evals/tests/test_runner_offline.py` (scripted fake model, no API calls).

---

### Feature 6 — Connector template & contract tests

**Behavior**
- `make new-connector NAME=hubspot` copies `connectors/_template/` (tools module, OpenAPI variant, tests, README) and registers it with one line in `app/server.py`.
- `tests/contract/test_connector_contract.py` runs over every mounted connector: snake_case names with the connector prefix, `outputSchema` present, annotations set, read/write tag present, descriptions within length bounds, no secrets in schemas, errors returned as tool errors.
- `docs/connector-development.md`: from zero to a working curated connector in under an hour.

**Acceptance criteria**
- [ ] A freshly generated connector passes `make check` unchanged.
- [ ] The contract suite fails for a connector missing annotations (tested with a deliberately broken fixture connector).
- [ ] The tutorial has been followed start to finish once and timed.

**Files:** `connectors/_template/`, `scripts/new_connector.py`, `docs/connector-development.md`

**Tests:** `tests/contract/test_connector_contract.py`, `tests/unit/test_new_connector.py` (generates into a temp dir and runs its tests).

---

### Feature 7 — Deployment topologies + ADR

**Behavior**
- **A — Managed (Horizon):** Horizon builds from the repo; Horizon Authentication on. Roles: `analyst` (all `read` tools) and `ops` (adds `northwind_create_support_ticket`) via tool-level access. CI and the eval runner use a Horizon API key (`fmcp_…`) owned by a service account.
- **B — Hybrid:** the Render production URL is registered in Horizon as an **external server** with an org-shared, encrypted API-key header carrying a long-lived service JWT. Horizon applies roles, tool-level access, and request logs. Only the gateway holds that token, so clients go through Horizon; document that the Render URL itself stays protected only by the token (Horizon's docs suggest an IP allowlist where available).
- **C — Self-hosted (Render):** AuthKit sign-in + service JWTs + ScopeGate, structured logs to Render, errors to Sentry.
- `docs/adr/001-build-vs-buy.md` (§0 of this PRD, expanded) and `docs/topologies.md`: when to choose each — data residency, compliance, cost, who owns the control plane, rate-limit scope, and how each handles staging.
- `docs/client-setup.md`: connecting Claude Code, Claude Desktop, Cursor, and the MCP Inspector to each topology.

**Acceptance criteria**
- [ ] The same commit runs in all three topologies; `remote_smoke.py` passes against each.
- [ ] In A, an `analyst` user cannot see the write tool (verified in Horizon with a second account or service account).
- [ ] Horizon request logs show the eval runner's calls (screenshot saved for the portfolio).
- [ ] The ADR states the trade-offs and names the conditions under which you'd recommend each topology to a client.

**Files:** `docs/adr/001-build-vs-buy.md`, `docs/topologies.md`, `docs/client-setup.md`, `scripts/remote_smoke.py`

**Tests:** `scripts/remote_smoke.py` (run in `e2e-staging` and before each release), `tests/unit/test_remote_smoke_args.py`.

---

### Feature 8 — GitHub connector (v1.1)

**Behavior:** proves the curation pattern generalizes. `scripts/trim_openapi.py` extracts ~8 operations from GitHub's published OpenAPI description into `connectors/github/specs/github.min.json` (the full spec is far too large to load on a 512 MB instance). Same allow-list, naming, and transforms as Feature 4; GitHub App installation tokens via an httpx auth class that refreshes before expiry; `github_create_issue` tagged `write`.

**Acceptance criteria**
- [ ] Contract suite passes; eval tasks for GitHub added to `tasks.yaml`.
- [ ] Installation tokens refresh before expiry (frozen-clock test).

**Tests:** `connectors/github/tests/test_trim_openapi.py`, `test_token_refresh.py`, `test_route_maps.py`.

---

## 6. Data model (demo data only)

```
customers  (id, name, city, state, segment, credit_limit, created_at)
orders     (id, customer_id, status, ordered_at, shipped_at, ship_state, total_usd)
order_lines(order_id, product_id, quantity, unit_price_usd)
products   (id, name, category, unit_price_usd)
tickets    (id, order_id, subject, body, status, created_at)        -- the only table the Ops API writes
```

Roles: `northwind_owner` (DDL + seeds), `northwind_readonly` (`SELECT` on all; `default_transaction_read_only = on`), `northwind_tickets` (`SELECT` on all, `INSERT` on `tickets`). There is no gateway database: keys, roles, and logs live in Horizon (A/B) or the identity provider (C).

---

## 7. Testing strategy (project-specific)

- **Test through the protocol.** Most tests use FastMCP's in-memory `Client(mcp)`, so they exercise real tool listing and calls, not internal functions.
- **Snapshot the tool surface.** `inline-snapshot` pins tool names, annotations, and tags; any change to what the model sees shows up in review.
- **Corpus-driven security tests** for SQL, scopes × tags, and Host/Origin. Each corpus grows when a bug is found.
- **Deterministic seeds** make eval answers exact, so most scoring needs no LLM judge.
- **Remote smoke** (`scripts/remote_smoke.py`) runs against Render staging and the Horizon preview after each staging deploy, and against production after each release.
- **Manual pre-release:** MCP Inspector and Claude Code against staging.

**Example — `tests/integration/test_tool_surface.py`**

```python
import pytest
from fastmcp.client import Client
from fastmcp.exceptions import ToolError


async def test_model_sees_exactly_the_curated_tools(client: Client):
    names = sorted(t.name for t in await client.list_tools())
    assert names == [
        "northwind_create_support_ticket",
        "northwind_get_order",
        "northwind_get_ticket",
        "northwind_list_orders",
        "northwind_search_customers",
        "postgres_describe_table",
        "postgres_list_tables",
        "postgres_query",
    ]


async def test_postgres_query_rejects_writes_with_a_fixable_message(client: Client):
    with pytest.raises(ToolError, match="only a single SELECT"):
        await client.call_tool("postgres_query", {"sql": "DELETE FROM orders WHERE status = 'cancelled'"})
```

---

## 8. Claude skills & MCPs to use while building

**Skills**
- `engineering:architecture` — ADR-001 (build vs buy) and the topology trade-offs.
- `engineering:testing-strategy` — test lists per feature, especially the security corpora and eval tasks.
- `engineering:code-review` — security-focused self-review on Features 2–4.
- `engineering:deploy-checklist` — before each release, including the Horizon promotion step.
- `product-self-knowledge` — Anthropic SDK tool-use details for the eval runner.
- `skill-creator` — a `solvexis-connector` skill that scaffolds a connector and runs its contract tests.

**MCPs**
- **Context7** — FastMCP v3 and Horizon docs; confirm API names before each feature.
- **Your own server** — connect Claude Code to the Horizon staging preview as soon as Feature 3 ships and use it daily.
- **Render MCP** — logs and metrics for the self-hosted environments.
- **GitHub MCP**, **Sentry MCP**.

---

## 9. Success metrics

- **Functional:** Features 0–7 pass on staging and production (Feature 8 in v1.1).
- **Security:** SQL corpus and scope tests pass; the read-only role is proven; Host/Origin protection on.
- **Model behavior:** curated connector task success ≥ 90% and at least 20 points above the raw auto-generated connector; zero write calls on must-refuse tasks.
- **Compatibility:** Claude Code, Claude Desktop, and the MCP Inspector connect in Topologies A and C.
- **Portfolio:** demo video of Claude Code answering Northwind questions through Horizon; the raw-vs-curated eval chart; ADR-001; `connector-development.md` as a standalone tutorial.

---

## 10. Build order

| Step | Feature | Milestone |
|---|---|---|
| 1 | F0 Foundation (Render + Horizon wired) | Empty server live on both platforms, all three branches |
| 2 | F1 Composition + middleware | |
| 3 | F3 Postgres connector | Claude Code queries Northwind through Horizon staging |
| 4 | F2 Auth (self-hosted modes) | **v0.1** |
| 5 | F4 Curated OpenAPI connector | |
| 6 | F5 Tool-use evals (raw vs curated) | **v0.2** — first Upwork portfolio publish |
| 7 | F6 Connector template | |
| 8 | F7 Topologies + ADR | **v1.0** |
| 9 | F8 GitHub connector | **v1.1** |

---

## 11. Open decisions

- **Horizon promotion automation:** promote production builds by hand at first; add an API or CLI step to `deploy-production.yml` if Horizon exposes one (confirm in its docs).
- **AuthKit vs Auth0 for Topology C:** AuthKit is the default because it supports dynamic client registration; switch if a client standardizes on another IdP (FastMCP supports both).
- **Horizon plan limits:** the free tier covers one developer. Confirm team pricing on Horizon's pricing page before recommending it to a client; don't quote numbers from memory.
- **Shared rate limits** for multi-instance self-hosting: add a Redis-backed limiter only when a client needs more than one instance.

## Sources

- [Prefect Horizon](https://www.prefect.io/horizon) · [Introducing Horizon](https://www.prefect.io/blog/prefect-horizon) · [Horizon docs](https://docs.horizon.prefect.io/) · [External servers](https://docs.horizon.prefect.io/servers/external.md) · [Authentication](https://docs.horizon.prefect.io/platform/authentication.md) · [Deployments](https://docs.horizon.prefect.io/deployments.md)
- [FastMCP: Deploy to Horizon](https://gofastmcp.com/deployment/prefect-horizon.md) · [HTTP deployment](https://gofastmcp.com/deployment/http.md) · [Testing](https://gofastmcp.com/servers/testing.md) · [Middleware](https://gofastmcp.com/servers/middleware.md) · [OpenAPI](https://gofastmcp.com/integrations/openapi.md) · [Tool transformation](https://gofastmcp.com/servers/transforms/tool-transformation.md) · [Authentication](https://gofastmcp.com/servers/auth/authentication.md) · [Token verification](https://gofastmcp.com/servers/auth/token-verification.md) · [MultiAuth](https://gofastmcp.com/servers/auth/multi-auth.md)
