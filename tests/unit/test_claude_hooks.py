"""Tests for the Claude Code hooks in .claude/hooks/ (run as subprocesses with hook JSON on stdin)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[2] / ".claude" / "hooks"


def run_hook(name: str, payload: dict) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HOOKS / name)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "develop")
    git(
        tmp_path,
        "-c",
        "user.email=t@example.com",
        "-c",
        "user.name=t",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "init",
    )
    return tmp_path


def bash(repo: Path, command: str) -> subprocess.CompletedProcess[str]:
    return run_hook(
        "guard_git.py",
        {"tool_name": "Bash", "cwd": str(repo), "tool_input": {"command": command}},
    )


# ------------------------------------------------------------------ guard_git


@pytest.mark.parametrize(
    "command",
    ["git commit -m 'wip'", "git -C . merge feat/x", "git reset --hard HEAD~1"],
)
def test_guard_blocks_history_changes_on_protected_branch(
    repo: Path, command: str
) -> None:
    result = bash(repo, command)
    assert result.returncode == 2
    assert "protected branch 'develop'" in result.stderr


def test_guard_allows_commits_on_feature_branch(repo: Path) -> None:
    git(repo, "switch", "-q", "-c", "feat/f03-postgres-connector")
    assert bash(repo, "git add -A && git commit -m 'feat(f03): T01'").returncode == 0


@pytest.mark.parametrize(
    "command",
    [
        "git push origin main",
        "git push origin HEAD:staging",
        "git push -u origin develop",
        "git push origin +feat/x",
    ],
)
def test_guard_blocks_pushes_to_protected_branches_and_force(
    repo: Path, command: str
) -> None:
    git(repo, "switch", "-q", "-c", "feat/x")
    assert bash(repo, command).returncode == 2


@pytest.mark.parametrize(
    "command",
    ["git push --force", "git push -f origin feat/x", "git push --force-with-lease"],
)
def test_guard_blocks_force_pushes(repo: Path, command: str) -> None:
    git(repo, "switch", "-q", "-c", "feat/x")
    result = bash(repo, command)
    assert result.returncode == 2
    assert "force push" in result.stderr


def test_guard_blocks_bare_push_from_protected_branch(repo: Path) -> None:
    assert bash(repo, "git push").returncode == 2


def test_guard_allows_feature_branch_push(repo: Path) -> None:
    git(repo, "switch", "-q", "-c", "feat/x")
    assert bash(repo, "git push -u origin HEAD").returncode == 0


def test_guard_blocks_no_verify(repo: Path) -> None:
    git(repo, "switch", "-q", "-c", "feat/x")
    assert bash(repo, "git commit --no-verify -m x").returncode == 2


@pytest.mark.parametrize(
    "command",
    ["git pull --ff-only", "git status", "make check", "git switch -c feat/y"],
)
def test_guard_allows_safe_commands_on_protected_branch(
    repo: Path, command: str
) -> None:
    assert bash(repo, command).returncode == 0


# ------------------------------------------------------------------ spec_lock

SPEC = """\
# F03 — Postgres connector

Status: {status}   <!-- draft → approved → building → done -->
Version: 1

| ID | Requirement | PRD | Verify |
| --- | --- | --- | --- |
| F03-R1 | The server shall expose three tools. | Tools | test |

## Manual verification

- [ ] F03-R16 — ask Claude Code the Georgia question.
"""


def spec_file(tmp_path: Path, status: str) -> Path:
    path = tmp_path / "specs" / "f03-postgres-connector" / "spec.md"
    path.parent.mkdir(parents=True)
    path.write_text(SPEC.format(status=status), encoding="utf-8")
    return path


def edit(
    path: Path, old: str, new: str, tool: str = "Edit"
) -> subprocess.CompletedProcess[str]:
    tool_input = {"file_path": str(path), "old_string": old, "new_string": new}
    if tool == "MultiEdit":
        tool_input = {
            "file_path": str(path),
            "edits": [{"old_string": old, "new_string": new}],
        }
    return run_hook("spec_lock.py", {"tool_name": tool, "tool_input": tool_input})


def test_spec_lock_allows_any_edit_to_a_draft(tmp_path: Path) -> None:
    path = spec_file(tmp_path, "draft")
    assert edit(path, "three tools", "four tools").returncode == 0


@pytest.mark.parametrize("status", ["approved", "building", "done"])
def test_spec_lock_blocks_requirement_changes_once_approved(
    tmp_path: Path, status: str
) -> None:
    path = spec_file(tmp_path, status)
    result = edit(path, "three tools", "four tools")
    assert result.returncode == 2
    assert "/sdd-spec" in result.stderr


def test_spec_lock_blocks_full_rewrites_once_approved(tmp_path: Path) -> None:
    path = spec_file(tmp_path, "approved")
    payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(path), "content": "Status: draft\n"},
    }
    assert run_hook("spec_lock.py", payload).returncode == 2


@pytest.mark.parametrize(
    ("old", "new"), [("approved", "building"), ("building", "done")]
)
def test_spec_lock_allows_forward_status_moves(
    tmp_path: Path, old: str, new: str
) -> None:
    path = spec_file(tmp_path, old)
    line = f"Status: {old}   <!-- draft → approved → building → done -->"
    assert edit(path, line, line.replace(old, new, 1)).returncode == 0


def test_spec_lock_blocks_status_move_that_also_changes_the_rest_of_the_line(
    tmp_path: Path,
) -> None:
    path = spec_file(tmp_path, "approved")
    line = "Status: approved   <!-- draft → approved → building → done -->"
    assert (
        edit(path, line, "Status: building   <!-- anything goes now -->").returncode
        == 2
    )


def test_spec_lock_blocks_moving_status_backwards(tmp_path: Path) -> None:
    path = spec_file(tmp_path, "approved")
    line = "Status: approved   <!-- draft → approved → building → done -->"
    assert edit(path, line, line.replace("approved", "draft", 1)).returncode == 2


@pytest.mark.parametrize("tool", ["Edit", "MultiEdit"])
def test_spec_lock_allows_ticking_manual_checks(tmp_path: Path, tool: str) -> None:
    path = spec_file(tmp_path, "building")
    old = "- [ ] F03-R16 — ask Claude Code the Georgia question."
    assert edit(path, old, old.replace("[ ]", "[x]"), tool).returncode == 0


def test_spec_lock_blocks_ticking_plus_rewording(tmp_path: Path) -> None:
    path = spec_file(tmp_path, "building")
    old = "- [ ] F03-R16 — ask Claude Code the Georgia question."
    assert edit(path, old, "- [x] F03-R16 — skip it.").returncode == 2


def test_spec_lock_allows_edits_during_an_approved_amendment(tmp_path: Path) -> None:
    path = spec_file(tmp_path, "approved")
    (path.parent / ".amend").touch()
    assert edit(path, "three tools", "four tools").returncode == 0


def test_spec_lock_ignores_other_files_and_new_specs(tmp_path: Path) -> None:
    other = tmp_path / "specs" / "f03-postgres-connector" / "design.md"
    assert edit(other, "a", "b").returncode == 0
    new_spec = tmp_path / "specs" / "f04-curated-openapi" / "spec.md"
    assert edit(new_spec, "a", "b").returncode == 0


# ------------------------------------------------------------------ format_python


def test_format_hook_ignores_non_python_files(tmp_path: Path) -> None:
    payload = {
        "tool_name": "Edit",
        "tool_input": {"file_path": str(tmp_path / "notes.md")},
    }
    assert run_hook("format_python.py", payload).returncode == 0


def test_hooks_tolerate_empty_or_invalid_input() -> None:
    for name in ("guard_git.py", "spec_lock.py", "format_python.py"):
        result = subprocess.run(
            [sys.executable, str(HOOKS / name)],
            input="not json",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, name
