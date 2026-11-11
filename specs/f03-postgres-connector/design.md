# F03 — design

Design status: draft   <!-- draft → approved -->
Spec: spec.md v1

> Worked example. The API notes list what this design relies on; `/sdd-design F03` confirms each one in Context7 and ticks it before the design is approved.

## Approach

Three layers, each testable on its own:

1. `safety.validate()` parses the SQL with sqlglot (Postgres dialect) and applies the statement, function, schema and allowlist rules. It returns the original SQL or raises `SqlRejected` with a rule name and a fix hint.
2. `executor.run()` executes as `northwind_readonly` inside a read-only transaction with `SET LOCAL statement_timeout`, and fetches `max_rows + 1` rows from a server-side cursor to detect truncation.
3. `tools.py` registers the three FastMCP tools, clamps `max_rows`, and turns `SqlRejected` and database errors into `ToolError`s.

The read-only role and transaction are the real guarantee. Validation exists to give the model fast, fixable feedback.

## API notes (confirmed with Context7)

| Library | Version or doc date | API this design relies on | Confirmed |
| --- | --- | --- | --- |
| sqlglot | — | `sqlglot.parse(sql, read="postgres")` returns one expression per statement; `exp.Select` and set operations (`exp.Union`, `exp.Intersect`, `exp.Except`); `expression.find_all(exp.Table)`; `find_all(exp.Func)` with `exp.Anonymous` names for functions sqlglot doesn't model; `Select.args["into"]` and `Select.args["locks"]` | ☐ |
| asyncpg | — | `asyncpg.create_pool(dsn, min_size=0, max_size=2)`; `conn.transaction(readonly=True)`; `conn.cursor(sql)` inside a transaction, then `await cursor.fetch(n)`; exceptions `QueryCanceledError`, `ReadOnlySQLTransactionError`, `InsufficientPrivilegeError`, `PostgresSyntaxError` | ☐ |
| FastMCP | — | `@mcp.tool(annotations=..., tags=...)`; output schema generated from a Pydantic return type; `fastmcp.exceptions.ToolError`; in-memory `Client(mcp)` for tests | ☐ |

## Components and files

| File | Create or change | Responsibility |
| --- | --- | --- |
| `connectors/postgres/safety.py` | create | `SqlRejected`, `validate()`, blocked function and schema lists |
| `connectors/postgres/executor.py` | create | pool lifecycle, `run()`, `list_tables()`, `describe_table()`, value serialization |
| `connectors/postgres/models.py` | create | `QueryResult`, `TableInfo`, `TableDescription`, `ColumnInfo`, `ForeignKey` |
| `connectors/postgres/tools.py` | create | the three tools, descriptions built from the allowlist, error mapping, `max_rows` clamp |
| `connectors/postgres/__init__.py` | create | `build_server(settings) -> FastMCP`, mounted under the `postgres` namespace |
| `app/config.py` | change | `demo_pg_url_readonly`, `pg_query_timeout_ms`, `pg_max_rows`, `pg_table_allowlist` |
| `app/server.py` | change | mount the connector |
| `tests/fixtures/sql_attacks.txt` | create | at least 40 attack queries, one per line, `#` for comments |
| `tests/integration/test_tool_surface.py` | change | snapshot now includes the three Postgres tools |

## Interfaces

```python
class SqlRejected(Exception):
    rule: str   # "single_statement" | "select_only" | "blocked_function" | "blocked_schema" | "table_not_allowed" | "unparseable"
    hint: str   # how to fix the query; shown to the model


def validate(sql: str, *, allowed_tables: frozenset[str]) -> str: ...


JsonScalar = str | int | float | bool | None


class QueryResult(BaseModel):
    columns: list[str]
    rows: list[list[JsonScalar]]
    row_count: int
    max_rows: int
    truncated: bool


class TableInfo(BaseModel):
    name: str
    kind: Literal["table", "view"]
    approx_rows: int


class TableDescription(BaseModel):
    name: str
    columns: list[ColumnInfo]          # name, type, nullable
    primary_key: list[str]
    foreign_keys: list[ForeignKey]     # column, references_table, references_column
    sample_rows: list[list[JsonScalar]]


async def run(pool: asyncpg.Pool, sql: str, *, max_rows: int, timeout_ms: int) -> QueryResult: ...
async def list_tables(pool: asyncpg.Pool, schema: str, allowed: frozenset[str]) -> list[TableInfo]: ...
async def describe_table(pool: asyncpg.Pool, table: str, allowed: frozenset[str]) -> TableDescription: ...
```

## Data and config

| Item | Change | Must be added to |
| --- | --- | --- |
| `PG_TABLE_ALLOWLIST` | new; default `customers,orders,order_lines,products,tickets` | `.env.example`, `render.yaml` (shared group), `docs/PRODUCTION.md`, Horizon env |
| `PG_QUERY_TIMEOUT_MS`, `PG_MAX_ROWS` | already in `render.yaml` | `.env.example`, Horizon env |
| `DEMO_PG_URL_READONLY` | exists from F00 | — |

## Test plan

| Requirement | Test (`file::name`) | Level |
| --- | --- | --- |
| F03-R1 | `tests/integration/test_postgres_tools.py::test_exposes_exactly_three_read_only_postgres_tools` | integration |
| F03-R2 | `tests/integration/test_postgres_tools.py::test_list_tables_returns_allowlisted_tables_sorted_with_approx_rows` | integration |
| F03-R3 | `tests/integration/test_postgres_tools.py::test_describe_table_returns_columns_keys_and_three_sample_rows` | integration |
| F03-R4 | `connectors/postgres/tests/test_safety.py::test_rejects_tables_outside_allowlist`; `tests/integration/test_postgres_tools.py::test_describe_table_outside_allowlist_lists_allowed_tables` | unit, integration |
| F03-R5 | `connectors/postgres/tests/test_safety.py::test_rejects_anything_but_one_statement`; `::test_allows_single_trailing_semicolon` | unit |
| F03-R6 | `connectors/postgres/tests/test_safety.py::test_rejects_non_select_statements` (DML, DDL, CTE with DML, SELECT INTO, FOR UPDATE, SET); `::test_allows_set_operations_of_selects` | unit |
| F03-R7 | `connectors/postgres/tests/test_safety.py::test_rejects_blocked_functions_and_schemas` (case, quoting, schema-qualified) | unit |
| F03-R8 | `connectors/postgres/tests/test_safety.py::test_rejection_messages_name_rule_and_fix`; `tests/integration/test_postgres_tools.py::test_errors_reach_client_without_stack_trace` | unit, integration |
| F03-R9 | `connectors/postgres/tests/test_safety.py::test_attack_corpus_is_fully_rejected`; `::test_attack_corpus_has_at_least_40_cases` | unit |
| F03-R10 | `connectors/postgres/tests/test_executor.py::test_cancels_query_at_timeout` (200 ms timeout, `pg_sleep` called directly on the executor) | integration |
| F03-R11 | `connectors/postgres/tests/test_executor.py::test_marks_truncation_when_more_rows_than_max`; `::test_not_truncated_at_exact_limit`; `::test_own_larger_limit_is_still_capped` | integration |
| F03-R12 | `tests/integration/test_postgres_tools.py::test_clamps_max_rows_and_reports_applied_value` (0, 1, 100, 10000) | integration |
| F03-R13 | `connectors/postgres/tests/test_executor.py::test_write_fails_even_without_validation` (row count unchanged afterwards) | integration |
| F03-R14 | `connectors/postgres/tests/test_executor.py::test_serializes_numeric_dates_uuid_bytea_and_null`; `::test_empty_result_shape` | integration |
| F03-R15 | `tests/integration/test_postgres_tools.py::test_query_description_lists_tables_and_examples` (inline snapshot) | integration |

## Risks

| Risk | Mitigation |
| --- | --- |
| sqlglot parses some Postgres syntax differently from Postgres | Validation is advisory. The read-only role, read-only transaction and prepared statements (one command only) are the guarantee. SQL sqlglot can't parse is rejected with a hint to simplify. |
| Sample rows expose sensitive columns in a real client database | Demo data is fictional. For client work, add a column denylist to the connector template (F06). |
| Connection pool exhausts a 512 MB instance | `max_size=2`, `min_size=0`, 5-second acquire timeout |
| The first query after Neon scales to zero is slower | Tests use local Postgres; note the behavior in `docs/topologies.md` |

## Deviations from PRD or spec wording

- PRD Feature 3 suggests appending `LIMIT max_rows + 1`. This design fetches `max_rows + 1` rows from a server-side cursor instead: same behavior, no SQL rewriting, and it still works when the query has its own LIMIT, ORDER BY or UNION.

## ADR

None — choices are local to this connector.
