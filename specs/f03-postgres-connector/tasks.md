# F03 — tasks

Each task takes 45–90 minutes, writes its tests first, and ends green with one commit. `/sdd-build F03` runs the next unchecked task. Total estimate: about 7.5 hours.

- [ ] **T01 — Statement-shape validation** · F03-R5, F03-R6, F03-R8 · ~75 min
    - Tests first: `connectors/postgres/tests/test_safety.py::test_rejects_anything_but_one_statement`, `::test_allows_single_trailing_semicolon`, `::test_rejects_non_select_statements`, `::test_allows_set_operations_of_selects`, `::test_rejection_messages_name_rule_and_fix`
    - Change: `connectors/postgres/safety.py` (`SqlRejected`, `validate()` statement rules)
    - Done when: those tests pass and `make lint` is clean
- [ ] **T02 — Functions, schemas, allowlist and the attack corpus** · F03-R4, F03-R7, F03-R9 · ~90 min
    - Tests first: `connectors/postgres/tests/test_safety.py::test_rejects_blocked_functions_and_schemas`, `::test_rejects_tables_outside_allowlist`, `::test_attack_corpus_is_fully_rejected`, `::test_attack_corpus_has_at_least_40_cases`
    - Change: `connectors/postgres/safety.py`, `tests/fixtures/sql_attacks.txt`
    - Done when: every corpus query is rejected with a rule and a hint
- [ ] **T03 — Executor: read-only transaction, timeout, truncation** · F03-R10, F03-R11, F03-R13 · ~90 min
    - Tests first: `connectors/postgres/tests/test_executor.py::test_cancels_query_at_timeout`, `::test_marks_truncation_when_more_rows_than_max`, `::test_not_truncated_at_exact_limit`, `::test_own_larger_limit_is_still_capped`, `::test_write_fails_even_without_validation`
    - Change: `connectors/postgres/executor.py` (`run()`, pool), `app/config.py`
    - Done when: those tests pass against docker compose Postgres in under 10 seconds
- [ ] **T04 — Result models and serialization** · F03-R14 · ~45 min
    - Tests first: `connectors/postgres/tests/test_executor.py::test_serializes_numeric_dates_uuid_bytea_and_null`, `::test_empty_result_shape`
    - Change: `connectors/postgres/models.py`, `connectors/postgres/executor.py`
    - Done when: results validate against `QueryResult` for every column type in the seed data
- [ ] **T05 — The three tools** · F03-R1, F03-R2, F03-R3, F03-R4, F03-R8, F03-R12, F03-R15 · ~90 min
    - Tests first: every `tests/integration/test_postgres_tools.py` test in the design's test plan
    - Change: `connectors/postgres/tools.py`, `connectors/postgres/__init__.py`, `app/server.py`; update the snapshot in `tests/integration/test_tool_surface.py`
    - Done when: the in-memory client lists exactly the three tools and every tools test passes
- [ ] **T06 — Config, docs and the staging preview** · F03-R16 · ~60 min
    - Change: `.env.example`, `render.yaml` (`PG_TABLE_ALLOWLIST`), `docs/PRODUCTION.md` env matrix, Horizon preview env vars, `CHANGELOG.md`
    - Then: push the branch so Horizon builds its preview
    - Done when: the preview is live with the allowlist set, ready for the manual check in `/sdd-verify F03`
