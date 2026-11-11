#!/usr/bin/env python3
"""PreToolUse(Bash) hook: keep Claude's git work on feature branches.

Blocks, with exit code 2 (the reason goes back to Claude):
  * commit / merge / rebase / cherry-pick / revert / reset / am while on main, staging or develop
  * pushing to main, staging or develop (explicitly, or a bare `git push` from one of them)
  * force pushes anywhere, and --no-verify anywhere

A guardrail against mistakes, not a security boundary: a chained command such as
`git switch develop && git commit` is judged against the branch you are on now.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys

PROTECTED = {"main", "staging", "develop"}
GIT = r"\bgit\s+(?:-C\s+\S+\s+)?"
HISTORY_CHANGING = re.compile(
    GIT + r"(commit|merge|rebase|cherry-pick|revert|reset|am)\b"
)
PUSH = re.compile(GIT + r"push\b([^;&|]*)")
FORCE = re.compile(r"(?:^|\s)(--force(?:-with-lease)?(?:=\S+)?|-f|\+\S+)(?=\s|$)")


def current_branch(cwd: str) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", cwd, "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip()


def block(reason: str) -> None:
    print(reason, file=sys.stderr)
    sys.exit(2)


def push_targets(args: str) -> list[str]:
    try:
        tokens = shlex.split(args)
    except ValueError:
        tokens = args.split()
    positional = [t for t in tokens if not t.startswith("-")]
    refspecs = positional[1:]  # first positional is the remote
    return [
        spec.split(":")[-1].removeprefix("refs/heads/").lstrip("+") for spec in refspecs
    ]


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return
    if data.get("tool_name") != "Bash":
        return
    command = (data.get("tool_input") or {}).get("command", "")
    if not re.search(r"\bgit\b", command):
        return

    if re.search(r"(?:^|\s)--no-verify(?=\s|$)", command):
        block(
            "Blocked: --no-verify skips the repo's hooks. Fix what the hook reports instead, or ask the user."
        )

    branch = current_branch(data.get("cwd") or ".")
    on_protected = branch in PROTECTED

    history = HISTORY_CHANGING.search(command)
    if history and on_protected:
        block(
            f"Blocked: `git {history.group(1)}` on protected branch '{branch}'. "
            "Work on a feature branch (feat/fNN-<slug>, created from an up-to-date develop) and open a PR."
        )

    for match in PUSH.finditer(command):
        args = match.group(1)
        if FORCE.search(args):
            block(
                "Blocked: force push. Ask the user before rewriting any pushed history."
            )
        targets = push_targets(args)
        hit = sorted(PROTECTED.intersection(targets))
        if hit:
            block(
                f"Blocked: push to protected branch {', '.join(hit)}. Push the feature branch and open a PR."
            )
        if on_protected and not targets:
            block(
                f"Blocked: `git push` from protected branch '{branch}'. Push a feature branch instead."
            )


if __name__ == "__main__":
    main()
