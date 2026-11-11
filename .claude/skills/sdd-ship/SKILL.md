---
description: Open the pull request for a verified feature into develop, with its spec, design and traceability linked. Usage — /sdd-ship F03
argument-hint: "[feature-id]"
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Bash(python3 scripts/sdd.py *), Bash(git status), Bash(git diff *), Bash(git log *)
---

# Ship: pull request for $0

## 1. Check the gate

Run `python3 scripts/sdd.py context $0` and `python3 scripts/sdd.py trace --feature $0 --strict`. Stop unless the spec is `done` and the trace passes.

## 2. Prepare the description

- Summary: what a user can do now, in two sentences.
- Links: `specs/<folder>/spec.md`, `design.md`, `tasks.md`, `traceability.md`.
- Requirement coverage: "N test requirements traced, M manual checks done" from the trace output.
- **Config changes** at the top if the branch touches `render.yaml`, `vercel.json`, `.github/workflows/`, `docker-compose.yml`, or adds environment variables (the CLAUDE.md rule).
- Deviations from the PRD recorded in design.md.
- Follow-ups and anything deferred.

## 3. Push and open the PR

Ask the user before pushing, then:
- `git push -u origin HEAD`
- `gh pr create --base develop --title "feat(f03): <feature title>" --body-file <file>`

Don't merge. Give the user the PR URL and remind them that CI must pass before merging into `develop`. Promotion to `staging` and `main` follows `docs/PRODUCTION.md`.
