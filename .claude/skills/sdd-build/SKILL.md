---
description: Implement the next task of a feature test-first and finish with one green commit. Usage — /sdd-build F03 (next unchecked task) or /sdd-build F03 T04
argument-hint: "[feature-id] [task-id]"
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Edit, Write, Bash(python3 scripts/sdd.py *), Bash(uv run pytest *), Bash(uv run ruff *), Bash(uv run mypy *), Bash(make test), Bash(make lint), Bash(make test-integration), Bash(git status), Bash(git diff *), Bash(git add *), Bash(git commit *)
---

# Build: one task of $0

Current branch: !`git branch --show-current 2>/dev/null || echo "(not a git repo)"`

## 1. Check the gate

Run `python3 scripts/sdd.py context $0`. Continue only if:
- you're on the feature branch it names;
- the spec is `approved` or `building` (if `approved`, change only that line to `Status: building`);
- `Design status: approved` and `tasks.md` exists.

## 2. Pick the task

Task requested: "$1" (empty means the first unchecked task). Restate it in three lines: requirement IDs, the tests to write first, the files to change. Re-read those requirements in spec.md and their rows in design.md's test plan.

## 3. Red

Write the task's tests first. Tag each test with the requirements it proves:

```python
@pytest.mark.req("F03-R10")
async def test_cancels_query_at_timeout(pool): ...
```

Run just those tests (`uv run pytest <files> -q`). Confirm each fails because the behavior is missing — not because of an import error or a typo in the test.

## 4. Green

Write the smallest change that makes them pass, following the interfaces in design.md. If you must deviate from the design, note it under Deviations in design.md. Don't change files the task doesn't name unless a test forces it.

Then run the feature's test files and `make lint`, and fix until both are green.

## 5. When the spec looks wrong

If a requirement can't be met as written, two requirements conflict, or the task reveals a missing requirement: **stop**. Don't edit the spec, don't loosen or delete a test, don't skip it. Tell the user which requirement, what you found, and suggest `/sdd-spec $0 amend: <change>`.

## 6. Commit and stop

Tick the task in tasks.md, then commit code, tests and the ticked box together with a conventional message: `feat(f03): T03 executor with timeout and truncation` (use `fix`, `test` or `chore` when they fit better).

Stop after this one task. Report what changed, which requirement IDs now have tests, anything deferred, and the next task.
