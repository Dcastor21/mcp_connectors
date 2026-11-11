#!/usr/bin/env python3
"""PostToolUse(Edit|Write|MultiEdit) hook: format and lint the Python file Claude just changed.

Runs `ruff format` and `ruff check --fix` through uv. Lint errors that ruff can't fix go back to
Claude (exit code 2) so it fixes them right away. Does nothing until the project has ruff installed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys


def ruff(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "--quiet", "ruff", *args],
        capture_output=True,
        text=True,
        timeout=50,
    )


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return
    path = (data.get("tool_input") or {}).get("file_path", "")
    if not path.endswith(".py") or shutil.which("uv") is None:
        return
    try:
        if ruff("--version").returncode != 0:
            return  # ruff isn't a project dependency yet
        ruff("format", path)
        result = ruff("check", "--fix", path)
    except (OSError, subprocess.SubprocessError):
        return
    if result.returncode != 0:
        print(
            f"ruff found problems it couldn't fix in {path}:\n{result.stdout}{result.stderr}",
            file=sys.stderr,
        )
        sys.exit(2)


if __name__ == "__main__":
    main()
