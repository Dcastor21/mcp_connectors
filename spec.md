# F03 — Postgres connector

Status: draft   <!-- draft → approved → building → done -->
Version: 1
PRD: PRD.md § Feature 3
Branch: feat/f03-postgres-connector

> Worked example of what `/sdd-spec F03` should produce. Review it critically when you reach F03 and approve it yourself.

## Goal

Claude Code and other MCP clients can explore and query the Northwind analytics database through three read-only tools, and nothing they send can change data, read system catalogs, or run an unbounded query.

## Scope

**In scope**
- `postgres_list_tables`, `postgres_describe_table`, `postgres_query`
- SQL validation, execution limits, result serialization
- Proof that the read-only role holds even if validation is bypassed (role created in F00)

**Out of scope**
- Tables exposed as MCP resources (`postgres://public/<table>`) — v1.1
- Any write access — never; writes go through the curated Northwind API (F04)
- Row-level security per user — not planned for v1
- Authentication and scopes — F02 (these tools carry the `read` tag F02's scope gate uses)

## Requirements

| ID | Requirement | PRD | Verify |
| --- | --- | --- | --- |
| F03-R1 | The server shall expose exactly three Postgres tools — `postgres_list_tables`, `postgres_describe_table`, `postgres_query` — each annotated `readOnlyHint: true` and tagged `read` and `postgres`. | Tools; F1 tool rules | test |
| F03-R2 | When `postgres_list_tables` is called, the server shall return every allowlisted table and view in the requested schema (default `public`) with its kind and an approximate row count, sorted by name. | Tools | test |
| F03-R3 | When `postgres_describe_table` is called for an allowlisted table, the server shall return its columns (name, type, nullable), primary key, foreign keys, and at most 3 sample rows. | Tools | test |
| F03-R4 | If a tool call names a table or view outside the allowlist, then the server shall return a tool error listing the allowed tables, without querying that table. | Defense 2 | test |
| F03-R5 | If `postgres_query` receives SQL that does not parse into exactly one statement, then the server shall reject it without executing anything. One trailing semicolon is allowed. | Defense 2 | test |
| F03-R6 | If the statement is anything other than a read-only `SELECT` — including DML inside a CTE, `SELECT … INTO`, `SELECT … FOR UPDATE` or `FOR SHARE`, and `SET` — then the server shall reject it. `UNION`, `INTERSECT` and `EXCEPT` of SELECTs are allowed. | Defense 2 | test |
| F03-R7 | If the SQL calls a blocked function (`pg_sleep*`, `pg_read_file`, `pg_read_binary_file`, `pg_ls_dir`, `pg_stat_file`, `lo_*`, `dblink*`, `set_config`, `pg_terminate_backend`, `pg_cancel_backend`, `pg_advisory_*`) or references the `pg_catalog` or `information_schema` schemas, then the server shall reject it, regardless of letter case, quoting or schema qualification. | Defense 2 | test |
| F03-R8 | Every rejection or execution error shall reach the client as a tool error whose message names the rule or problem and how to fix the query (for example "only a single SELECT statement is allowed"), with no stack trace or parser internals. | Defense 2 | test |
| F03-R9 | The server shall reject every query in `tests/fixtures/sql_attacks.txt`, which shall contain at least 40 cases. | AC1 | test |
| F03-R10 | If a query runs longer than `PG_QUERY_TIMEOUT_MS` (default 10000), then the server shall cancel it and return a tool error saying the query timed out and suggesting a narrower filter. | Defense 3; AC2 | test |
| F03-R11 | When a query produces more than `max_rows` rows, the server shall return the first `max_rows` rows with `truncated: true`; otherwise `truncated: false`. This holds even when the SQL has its own larger `LIMIT`. | Defense 3; AC3 | test |
| F03-R12 | The server shall clamp `max_rows` to the range 1 to `PG_MAX_ROWS` (default 100) and report the applied value in the result. | Defense 3 | test |
| F03-R13 | The connector shall run every query as the `northwind_readonly` role inside a read-only transaction, so a write that bypasses validation fails with a database error and changes nothing. | Defense 1; AC4 | test |
| F03-R14 | `postgres_query` results shall match its output schema `{columns, rows, row_count, max_rows, truncated}`, with `numeric` as strings, dates and timestamps as ISO 8601, UUIDs as strings, `bytea` as `"<bytea N bytes>"`, and NULL as JSON null. | added: clients need stable JSON | test |
| F03-R15 | The `postgres_query` description shall list the allowlisted tables with their key columns and include two example queries. | Behavior | test |
| F03-R16 | Claude Code, connected to the Horizon staging preview, answers "How many orders shipped to Georgia in the last full quarter?" by calling `postgres_query`, and the number matches the seeded data. | Build order step 3 | manual |

## Edge cases and errors

| Case | Expected behavior | Requirement |
| --- | --- | --- |
| Query returns no rows | `rows: []`, `row_count: 0`, `truncated: false` | F03-R11, F03-R14 |
| SQL with `--` or `/* */` comments | Allowed; rules apply to the parsed statement | F03-R5 |
| SQL already has `LIMIT 5000` | Still capped at `max_rows` and marked truncated | F03-R11 |
| `pg_catalog.pg_sleep(1)`, `PG_SLEEP(1)` | Rejected | F03-R7 |
| `"pg_catalog"."pg_authid"` | Rejected | F03-R7 |
| `SET search_path = …` or `SET ROLE …` | Rejected: not a SELECT | F03-R6 |
| `max_rows` of 0 or 10000 | Clamped to 1 or 100; applied value reported | F03-R12 |
| Postgres syntax error at execution | Tool error with Postgres's message, no stack trace | F03-R8 |
| Database unreachable | Tool error "database unavailable, try again shortly"; logged with the request ID | F03-R8 |

## Open questions

None.

## Decisions

| Question | Decision | Why |
| --- | --- | --- |
| Does the allowlist also apply to the schema tools? | Yes: non-allowlisted tables are invisible to all three tools | Listing tables the model can't query wastes calls |
| Exact or approximate row counts? | Approximate, labeled `approx_rows` | `COUNT(*)` on every table is slow on real databases |
| Error or clamp when `max_rows` is out of range? | Clamp and report | The model recovers without another call |
| Should views be queryable? | Only views in the allowlist | Same rule as tables, no special case |

## Manual verification

- [ ] F03-R16 — Connect Claude Code to the Horizon staging preview URL. Ask "How many orders shipped to Georgia in the last full quarter?". Confirm the transcript shows a `postgres_query` call, and that the answer matches the same count run in psql against the Neon `staging` branch.

## Change log

| Version | Date | Change | Reason |
| --- | --- | --- | --- |
