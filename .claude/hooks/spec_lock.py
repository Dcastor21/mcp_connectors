#!/usr/bin/env python3
"""PreToolUse(Edit|Write|MultiEdit) hook: an approved spec changes only through /sdd-spec amend mode.

Once specs/<feature>/spec.md says `Status: approved`, `building` or `done`, Claude may only:
  * move the status forward (approved -> building, building -> done), and
  * tick or untick checklist items (the Manual verification list).
Anything else is blocked with exit code 2, unless specs/<feature>/.amend exists. /sdd-spec creates
that file after the user agrees to a change and deletes it when the amendment is logged.

A guardrail against spec drift, not a security boundary.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

LOCKED = {"approved", "building", "done"}
FORWARD = {("approved", "building"), ("building", "done")}
STATUS = re.compile(r"^\s*Status:\s*([A-Za-z]+)")
CHECKBOX = re.compile(r"\[( |x|X)\]")


def status_of(text: str) -> str | None:
    for line in text.splitlines():
        match = STATUS.match(line)
        if match:
            return match.group(1).lower()
    return None


def is_bookkeeping(old: str, new: str) -> bool:
    old_lines, new_lines = old.splitlines(), new.splitlines()
    if not old_lines or len(old_lines) != len(new_lines):
        return False
    for a, b in zip(old_lines, new_lines, strict=True):
        if a == b:
            continue
        sa, sb = STATUS.match(a), STATUS.match(b)
        if sa and sb:
            if (sa.group(1).lower(), sb.group(1).lower()) in FORWARD and STATUS.sub(
                "", a
            ) == STATUS.sub("", b):
                continue
            return False
        if a.lstrip().startswith("- [") and CHECKBOX.sub(
            "[ ]", a, count=1
        ) == CHECKBOX.sub("[ ]", b, count=1):
            continue
        return False
    return True


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return
    tool = data.get("tool_name", "")
    tool_input = data.get("tool_input") or {}
    raw_path = tool_input.get("file_path", "")
    if not raw_path:
        return
    path = Path(raw_path)
    if (
        path.name != "spec.md"
        or path.parent.parent.name != "specs"
        or path.parent.name.startswith("_")
    ):
        return
    if not path.is_file():
        return  # a new spec
    status = status_of(path.read_text(encoding="utf-8"))
    if status not in LOCKED or (path.parent / ".amend").exists():
        return

    if tool == "Edit":
        edits = [tool_input]
    elif tool == "MultiEdit":
        edits = tool_input.get("edits") or []
    else:
        edits = []
    if edits and all(
        is_bookkeeping(e.get("old_string", ""), e.get("new_string", "")) for e in edits
    ):
        return

    rel = f"specs/{path.parent.name}/spec.md"
    print(
        f"Blocked: {rel} is {status}. Requirements change only through `/sdd-spec <feature> amend: <change>`, "
        "after the user approves the exact change. If the code disagrees with the spec, stop and tell the user "
        "which requirement is wrong and why — don't edit the spec or weaken a test to make the code pass.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
