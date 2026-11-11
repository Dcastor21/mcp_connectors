---
description: "Draft the spec (numbered, testable requirements) for one PRD feature, or amend an approved spec. Usage — /sdd-spec F03, or /sdd-spec F03 amend: <what should change>"
argument-hint: "[feature-id e.g. F03] [amend: <change>]"
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Bash(python3 scripts/sdd.py *), Bash(git status), Bash(git branch *), Bash(git switch *), Bash(git pull *), Bash(git add *), Bash(git commit *), Bash(touch specs/*), Bash(rm specs/*/.amend)
---

# Specify: requirements for $0

Current branch: !`git branch --show-current 2>/dev/null || echo "(not a git repo)"`

!`python3 scripts/sdd.py status 2>/dev/null || echo "(scripts/sdd.py not found — install the SDD kit first)"`

Request: $ARGUMENTS

## 1. Load context

Run `python3 scripts/sdd.py context $0`. It prints the PRD section, the expected branch and spec folder, and the state of any existing spec. Read `specs/_templates/spec.md` and `CLAUDE.md` if they aren't already in context.

## 2. Get on the feature branch

Use the branch `context` prints (`feat/f03-<slug>`). If you're not on it: `git switch develop && git pull --ff-only && git switch -c <branch>` (or `git switch <branch>` if it exists). Never write specs on `main`, `staging` or `develop`.

## 3a. New spec (no spec.md yet, or Status: draft)

Create or update `specs/<folder>/spec.md` from the template.

- **Goal:** one or two sentences on what a user or client can do once this ships.
- **Requirements:** turn every PRD acceptance criterion into one or more requirements, then add one for each PRD "Behavior" bullet a test could check. Each requirement:
  - has the next ID (`F03-R1`, `F03-R2`, …); IDs are never reused or renumbered;
  - uses EARS phrasing — "The server shall …", "When <trigger>, the server shall …", "If <unwanted condition>, then the server shall …", "While <state>, the server shall …";
  - describes one observable behavior, with numbers instead of adjectives (no "fast", "secure", "robust");
  - names its PRD source in the PRD column (`AC2`, `Behavior`, or `added: <reason>`);
  - has Verify = `test`, unless only a person can check it (a client sign-in, a hosted dashboard) — then `manual`, with a matching checkbox under Manual verification that says exactly what to do and what to see.
- **Scope:** copy PRD non-goals that touch this feature into Out of scope, each with the feature or version that picks it up.
- **Edge cases and errors:** empty, maximum and malformed inputs, missing permissions, upstream failures. Each needs an expected behavior and a requirement that covers it.
- Describe behavior, not mechanism. "Truncation is reported" belongs here; "append LIMIT n+1" belongs in design.md.

## 3b. Amend (spec is approved, building or done)

1. Show the user the exact change as before/after requirement rows, why it's needed, and which tasks and tests it affects. Wait for an explicit yes.
2. After the yes: `touch specs/<folder>/.amend`, make the change, bump `Version`, add a Change log row (date, change, reason), then `rm specs/<folder>/.amend`.
3. New requirements get new IDs. Remove a requirement by striking its ID (`~~F03-R7~~`) and noting the version — never delete or renumber rows.
4. If the status was `done`, set it back to `building` while the `.amend` file exists. Update `tasks.md` with any new or changed tasks.

## 4. Questions

Ask up to five questions about real ambiguities — use AskUserQuestion when it's available — each with your recommended answer first. Record every answer in Decisions. Open questions must be empty before approval.

## 5. Independent review

Delegate to the `spec-reviewer` subagent: "Spec mode: review specs/<folder>/spec.md against PRD.md § Feature <n>." Fix what it finds, or tell the user why you didn't.

## 6. Hand back

Leave `Status: draft` for a new spec. Tell the user: the number of requirements (test vs manual), anything you added beyond the PRD, the decisions recorded, and any risk. Ask them to read the spec and reply "approve". When they do, set `Status: approved`, add Change log row `1 | <date> | First approved version`, and commit `docs(f03): spec v1 approved`.

Don't write design.md, tasks.md or code in this step.
