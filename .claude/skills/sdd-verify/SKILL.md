---
description: Prove a feature meets its spec — full checks, requirement-to-test traceability, two independent reviews, your manual checks — then mark it done. Usage — /sdd-verify F03
argument-hint: "[feature-id]"
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Edit, Bash(python3 scripts/sdd.py *), Bash(make check), Bash(uv run pytest *), Bash(git status), Bash(git diff *), Bash(git log *), Bash(git add *), Bash(git commit *)
---

# Verify: does $0 do what the spec says?

## 1. Check the gate

Run `python3 scripts/sdd.py context $0`. If any task is unchecked, list them and stop.

## 2. Full checks

Run `make check`. Fix failures in the code; never weaken, skip or delete a test to get green.

## 3. Traceability

Run `python3 scripts/sdd.py trace --feature $0`. Every `test` requirement needs a test tagged `@pytest.mark.req`, and no test may reference an unknown ID. Fix gaps by writing the missing test.

## 4. Independent reviews

Get the changed files with `git diff --name-only develop...HEAD`, then delegate in parallel:
- `test-auditor`: "Audit the tests for every requirement in specs/<folder>/spec.md."
- `spec-reviewer`: "Conformance mode: compare these changed files with specs/<folder>/spec.md and design.md: <file list>."

Fix confirmed blockers and majors. For anything you leave, tell the user why.

## 5. Config and docs

Every item in design.md's Data and config section is in each place it lists (`.env.example`, `render.yaml` with `sync: false` for secrets, `docs/PRODUCTION.md`, Horizon environment). `CHANGELOG.md` has an Unreleased entry.

## 6. Manual checks

For each `manual` requirement, give the user exact steps: which URL or environment, which client, what to ask or click, and what they should see. Wait for their results. Tick the boxes that passed in spec.md. For a failure, add a fix task to tasks.md and stop here.

## 7. Mark done

Once everything passes:
1. `python3 scripts/sdd.py trace --feature $0 --strict --write` (writes `traceability.md`).
2. Tick this feature's acceptance boxes in `PRD.md` that are now satisfied.
3. Change only the status line in spec.md to `Status: done`.
4. Commit `docs(f03): verified` with traceability.md.

Tell the user it's ready for `/sdd-ship $0`.
