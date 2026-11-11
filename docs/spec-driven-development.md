# Spec-driven development in this repo

`PRD.md` says what the product does. Each PRD feature then moves through three small documents and six Claude Code commands before it reaches `develop`. You approve at three points; Claude does the rest, one reviewable step at a time.

| Step | Command | Produces | Your gate |
| --- | --- | --- | --- |
| 1. Specify | `/sdd-spec F03` | `specs/f03-…/spec.md`: numbered EARS requirements, edge cases, decisions, manual checks | Answer its questions, read it, reply "approve" |
| 2. Design | `/sdd-design F03` | `design.md`: APIs confirmed in Context7, files, interfaces, config changes, a test for every requirement | Reply "approve" |
| 3. Plan | `/sdd-tasks F03` | `tasks.md`: ordered 45–90 minute tasks, tests first | Adjust order or size |
| 4. Build | `/sdd-build F03`, repeated | One task per run: failing tests → code → green commit | Skim each commit |
| 5. Verify | `/sdd-verify F03` | `make check`, traceability, two independent reviews, your manual checks, `traceability.md` | Do the manual checks |
| 6. Ship | `/sdd-ship F03` | PR into `develop` with spec, design and traceability linked | Merge when CI is green |

Everything for a feature happens on `feat/f03-<slug>`, so the spec, design, tasks, tests and code arrive in one PR.

## What keeps the spec in charge

- **IDs and verify methods.** Every requirement has an ID (`F03-R4`) and a Verify method: `test` or `manual`.
- **Tagged tests.** Every test that proves a requirement carries `@pytest.mark.req("F03-R4")`.
- **A CI gate.** `python3 scripts/sdd.py trace` runs in CI. It fails the build when a spec marked `done` has a `test` requirement without a tagged test or an unticked manual check, or when any test references an ID that doesn't exist (a typo, or a removed requirement).
- **Spec lock.** Once a spec is approved, the `spec_lock` hook blocks Claude from editing it. Two exceptions: moving the status forward (approved → building → done) and ticking manual checks. Requirement changes go through `/sdd-spec F03 amend: <change>`, which shows you the change first and logs it in the spec's change log.
- **Stop on disagreement.** When the code and the spec disagree, Claude stops and asks. It never edits the spec or weakens a test to make code pass.
- **Branch guard.** The `guard_git` hook blocks commits and pushes on `main`, `staging` and `develop`, force pushes, and `--no-verify`.
- **Auto-format.** The `format_python` hook runs ruff on every Python file Claude edits and sends back what ruff can't fix.

The hooks are guardrails against drift and mistakes, not a security boundary.

## Helper commands

```
python3 scripts/sdd.py status                           # every PRD feature: spec, design, tasks, traced, PRD ACs
python3 scripts/sdd.py context F03                      # PRD section + spec state + next task
python3 scripts/sdd.py trace                            # CI gate
python3 scripts/sdd.py trace --feature F03 --strict --write   # gate one feature, write traceability.md
```

## Setup (once per repo)

1. **Copy the kit** into the repo root: `.claude/`, `specs/`, `scripts/sdd.py`, `tests/unit/test_sdd.py`, `tests/unit/test_claude_hooks.py` and this file. If `.claude/settings.json` already exists, merge the `permissions` and `hooks` blocks.
2. **Bootstrap order.** Make the first commit on `main` with `PRD.md`, `CLAUDE.md`, `docs/PRODUCTION.md` and the kit. Then create `develop` and `staging` and add branch protection. Everything after that, including Feature 0, goes through `/sdd-spec F00`.
3. **Register the pytest markers** in `pyproject.toml`:

   ```toml
   [tool.pytest.ini_options]
   addopts = "--strict-markers"
   markers = [
     "req(*ids): links a test to spec requirement IDs, e.g. req('F03-R4')",
     "live: calls real external services; skipped unless RUN_LIVE=1",
   ]
   ```

4. **Add Makefile targets**, and include `trace` in `check`:

   ```make
   trace:
   	python3 scripts/sdd.py trace

   spec-status:
   	python3 scripts/sdd.py status

   check: lint test test-integration trace
   ```

5. **Add a CI step** to the backend job in `.github/workflows/ci.yml`, after the tests: `- run: python3 scripts/sdd.py trace`.
6. **Ignore the amend marker:** add `specs/**/.amend` to `.gitignore`.
7. **Restart Claude Code once** after copying, so it picks up the new `.claude/agents/` folder.

On Windows, replace `python3` with `python` in `.claude/settings.json` and the skills.

## Conventions the helper relies on

- PRD feature headings look like `### Feature 3 — Postgres connector`.
- Spec folders are `specs/f<nn>-<slug>/` (`f03-postgres-connector`). Templates live in `specs/_templates/`.
- spec.md has `Status:` and `Version:` lines. Requirement rows start with the ID cell (`| F03-R4 |`), and their last cell is `test` or `manual`.
- Manual checks are checklist lines starting with the ID: `- [ ] F03-R16 — …`.
- design.md has a `Design status:` line.
- Tasks are top-level checklist lines: `- [ ] **T03 — title** · F03-R10, F03-R11 · ~90 min`.
