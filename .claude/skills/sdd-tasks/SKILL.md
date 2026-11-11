---
description: Break an approved design into ordered, test-first tasks of 45–90 minutes each. Usage — /sdd-tasks F03
argument-hint: "[feature-id]"
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Bash(python3 scripts/sdd.py *), Bash(git status), Bash(git add *), Bash(git commit *)
---

# Tasks: the build plan for $0

## 1. Check the gate

Run `python3 scripts/sdd.py context $0`. Stop unless the spec is approved and `Design status: approved`.

## 2. Write `specs/<folder>/tasks.md`

Use `specs/_templates/tasks.md`. Each task is one top-level checkbox line followed by indented details:

```
- [ ] **T03 — Executor: timeout and truncation** · F03-R10, F03-R11 · ~90 min
    - Tests first: `connectors/postgres/tests/test_executor.py::test_cancels_query_at_timeout`, …
    - Change: `connectors/postgres/executor.py`
    - Done when: those tests pass and `make lint` is clean
```

Rules:
- **45–90 minutes each.** Split anything bigger. One task should fit one weekday session.
- **Tests first.** Each task names the tests from the design's test plan that it writes before the code.
- **Ends green.** Every task leaves the test suite and lint passing, so it ends in a commit.
- **Order:** foundational and risky work first; config, docs and CHANGELOG near the end; the last task prepares any manual checks (deploy the preview, set env vars).
- **Coverage:** every requirement ID appears in at least one task line. Re-run `python3 scripts/sdd.py context $0` and fix anything listed under "requirements not in any task".

## 3. Hand back

Show the task list with the total estimate. Adjust order or size if the user asks, then commit `docs(f03): tasks`.

If this project is tracked in Linear and the Linear MCP is connected, offer to create one issue per task (title, requirement IDs, estimate) under the project. `tasks.md` stays the source of truth.
