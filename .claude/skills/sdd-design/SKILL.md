---
description: Write the technical design for an approved feature spec — library APIs confirmed in current docs, files, interfaces, config changes, and a test for every requirement. Usage — /sdd-design F03
argument-hint: "[feature-id]"
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Bash(python3 scripts/sdd.py *), Bash(git status), Bash(git add *), Bash(git commit *)
---

# Design: how $0 gets built

Current branch: !`git branch --show-current 2>/dev/null || echo "(not a git repo)"`

## 1. Check the gate

Run `python3 scripts/sdd.py context $0`. Stop if the spec is still `draft` — tell the user to approve it with `/sdd-spec` first. Make sure you're on the feature branch it names.

## 2. Read

The spec, `CLAUDE.md`, `docs/PRODUCTION.md` (environment matrix and deploy rules), `specs/_templates/design.md`, and the code this feature touches (Glob/Grep — early features may have little to read).

## 3. Confirm library APIs against current docs

For every third-party call the design depends on (FastMCP, sqlglot, asyncpg, httpx, Pydantic, the Anthropic SDK…), look it up with the Context7 MCP and record in **API notes**: library, version or doc date, the exact API, and a ✓. If the docs contradict the PRD (a renamed function, a removed option), follow the docs and record it under **Deviations from PRD or spec wording**. Don't design around an API you couldn't confirm; list it as a risk instead.

## 4. Write `specs/<folder>/design.md`

From the template:

- **Approach:** at most 10 lines. What the layers are and which one provides the real guarantee.
- **Components and files:** each file to create or change, with its responsibility.
- **Interfaces:** signatures, Pydantic models, tool names and schemas. No function bodies.
- **Data and config:** migrations, roles, environment variables — and for each, every place it must be added (`.env.example`, `render.yaml`, `docs/PRODUCTION.md`, Horizon environment).
- **Test plan:** every `test` requirement maps to at least one test (`file::test_name`) and a level (unit, integration, contract). Security and limit requirements also get a negative case and a boundary case. Test names read like the behavior.
- **Risks** with mitigations.
- **Deviations from PRD or spec wording**, with reasons.
- **ADR:** if this makes a decision a client would ask about (choosing a library, a data store, an auth approach), write `docs/adr/NNN-<slug>.md` — use the `engineering:architecture` skill if it's available. Otherwise write "None — choices are local to this feature."

If a requirement can't be met as written, stop and propose an amendment through `/sdd-spec $0 amend: …`. Don't design around the spec.

## 5. Hand back

Summarize the approach, new dependencies, config changes and open risks. Ask the user to reply "approve". When they do, set `Design status: approved` and commit `docs(f03): design approved`.
