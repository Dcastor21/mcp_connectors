"""Tests for scripts/sdd.py — the spec status, context and traceability helper."""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest

SDD_PATH = Path(__file__).resolve().parents[2] / "scripts" / "sdd.py"
_spec = importlib.util.spec_from_file_location("sdd", SDD_PATH)
assert _spec and _spec.loader
sdd = importlib.util.module_from_spec(_spec)
sys.modules["sdd"] = sdd  # dataclasses resolve types through sys.modules
_spec.loader.exec_module(sdd)

PRD = """\
# PRD — Demo

## 5. Features

### Feature 1 — Widgets (core)

**Behavior**
- Makes widgets.

```yaml
## not a heading
### Feature 9 — not a feature either
```

**Acceptance criteria**
- [x] Widgets exist.
- [ ] Widgets are blue.

### Feature 2 — Gadgets

- [ ] Gadgets exist.

## 6. Data model
"""

SPEC_DONE = """\
# F01 — Widgets

Status: done
Version: 2

## Requirements

| ID | Requirement | PRD | Verify |
| --- | --- | --- | --- |
| F01-R1 | The server shall make widgets. | AC1 | test |
| F01-R2 | The server shall paint widgets blue, e.g. `a\\|b`. | AC2 | test |
| ~~F01-R3~~ | Removed in v2. | — | test |
| F01-R4 | A person can see a widget in Claude Code. | added | manual |

## Manual verification

- [x] F01-R4 — open Claude Code and look.
"""


def write(root: Path, rel: str, content: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    write(tmp_path, "PRD.md", PRD)
    write(tmp_path, "specs/f01-widgets/spec.md", SPEC_DONE)
    write(
        tmp_path,
        "specs/f01-widgets/tasks.md",
        """\
        - [x] **T01 — Make widgets** · F01-R1 · ~45 min
            - Tests first: `tests/test_widgets.py::test_makes_widgets`
        - [ ] **T02 — Paint widgets** · F01-R2 · ~45 min
        """,
    )
    write(
        tmp_path,
        "tests/test_widgets.py",
        """\
        import pytest

        @pytest.mark.req("F01-R1")
        def test_makes_widgets():
            assert True

        @pytest.mark.req("F01-R2")
        async def test_paints_widgets_blue():
            assert True
        """,
    )
    return tmp_path


def run(root: Path, *args: str) -> int:
    return sdd.main(["--root", str(root), *args])


@pytest.mark.parametrize(
    ("raw", "expected"), [("F3", "F03"), ("f03", "F03"), ("3", "F03"), ("F12", "F12")]
)
def test_norm_fid_accepts_common_forms(raw: str, expected: str) -> None:
    assert sdd.norm_fid(raw) == expected


def test_norm_fid_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        sdd.norm_fid("feature three")


def test_parse_prd_ignores_headings_inside_code_fences() -> None:
    features = sdd.parse_prd(PRD)

    assert list(features) == ["F01", "F02"]
    assert features["F01"].title == "Widgets (core)"
    assert "## not a heading" in features["F01"].body
    assert features["F01"].acceptance == (1, 2)
    assert "Data model" not in features["F02"].body


def test_slugify_drops_parentheticals_and_punctuation() -> None:
    assert sdd.slugify("Postgres connector (centerpiece)") == "postgres-connector"
    assert (
        sdd.slugify("Server composition & middleware stack")
        == "server-composition-middleware-stack"
    )


def test_load_spec_reads_requirements_manual_checks_and_tasks(repo: Path) -> None:
    spec = sdd.load_spec(repo / "specs/f01-widgets", "F01")

    assert spec is not None
    assert spec.status == "done" and spec.version == "2"
    assert list(spec.requirements) == [
        "F01-R1",
        "F01-R2",
        "F01-R4",
    ]  # struck-through R3 is not tracked
    assert spec.requirements["F01-R2"].text.endswith("`a|b`.")
    assert spec.manual_checked == {"F01-R4"}
    assert [(t.tid, t.done, t.title, t.req_ids) for t in spec.tasks] == [
        ("T01", True, "Make widgets", ["F01-R1"]),
        ("T02", False, "Paint widgets", ["F01-R2"]),
    ]
    assert spec.errors == []


def test_load_spec_reports_duplicate_foreign_bad_verify_and_unlisted_manual(
    tmp_path: Path,
) -> None:
    write(
        tmp_path,
        "specs/f02-gadgets/spec.md",
        """\
        Status: approved
        | F02-R1 | One. | AC1 | test |
        | F02-R1 | Again. | AC1 | test |
        | F07-R1 | Wrong feature. | AC1 | test |
        | F02-R2 | Vague. | AC1 | maybe |
        | F02-R3 | Look at it. | AC1 | manual |
        """,
    )

    spec = sdd.load_spec(tmp_path / "specs/f02-gadgets", "F02")

    assert spec is not None
    joined = "\n".join(spec.errors)
    assert "duplicate requirement F02-R1" in joined
    assert "F07-R1 belongs to another feature" in joined
    assert "F02-R2 has Verify 'maybe'" in joined
    assert "F02-R3 is Verify=manual but missing" in joined


def test_collect_test_refs_reads_decorators_module_marks_and_classes(
    tmp_path: Path,
) -> None:
    write(
        tmp_path,
        "pkg/tests/test_mixed.py",
        """\
        import pytest

        pytestmark = [pytest.mark.req("F05-R1"), pytest.mark.asyncio]

        def test_module_level():
            ...

        @pytest.mark.req("F05-R2")
        class TestThing:
            @pytest.mark.req("F05-R3", "F05-R4")
            def test_method(self):
                ...

            def helper(self):
                ...
        """,
    )
    write(
        tmp_path,
        ".venv/lib/test_ignored.py",
        "import pytest\n@pytest.mark.req('F05-R9')\ndef test_x(): ...\n",
    )

    refs, warnings = sdd.collect_test_refs(tmp_path)

    node = "pkg/tests/test_mixed.py::"
    assert refs["F05-R1"] == [
        f"{node}test_module_level",
        f"{node}TestThing::test_method",
    ]
    assert refs["F05-R2"] == [f"{node}TestThing::test_method"]
    assert refs["F05-R4"] == [f"{node}TestThing::test_method"]
    assert "F05-R9" not in refs
    assert warnings == []


def test_trace_passes_when_done_spec_is_fully_traced(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(repo, "trace") == 0
    assert "test requirements traced: 2/2" in capsys.readouterr().out


def test_trace_fails_done_spec_with_untested_requirement(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / "tests/test_widgets.py").write_text(
        "def test_nothing():\n    pass\n", encoding="utf-8"
    )

    assert run(repo, "trace") == 1
    out = capsys.readouterr().out
    assert "no test yet: F01-R1, F01-R2" in out


def test_trace_does_not_gate_specs_that_are_not_done(repo: Path) -> None:
    spec = repo / "specs/f01-widgets/spec.md"
    spec.write_text(
        spec.read_text().replace("Status: done", "Status: building"), encoding="utf-8"
    )
    (repo / "tests/test_widgets.py").write_text(
        "def test_nothing():\n    pass\n", encoding="utf-8"
    )

    assert run(repo, "trace") == 0
    assert (
        run(repo, "trace", "--feature", "F1") == 1
    )  # an explicit feature check is always gated


@pytest.mark.parametrize("bad_id", ["F01-R99", "F3-R1"])
def test_trace_fails_on_unknown_or_malformed_ids(repo: Path, bad_id: str) -> None:
    write(
        repo,
        "tests/test_typo.py",
        f'import pytest\n@pytest.mark.req("{bad_id}")\ndef test_typo(): ...\n',
    )

    assert run(repo, "trace") == 1


def test_trace_strict_requires_manual_checks_ticked(repo: Path) -> None:
    spec = repo / "specs/f01-widgets/spec.md"
    spec.write_text(
        spec.read_text().replace("- [x] F01-R4", "- [ ] F01-R4"), encoding="utf-8"
    )
    spec.write_text(
        spec.read_text().replace("Status: done", "Status: building"), encoding="utf-8"
    )

    assert run(repo, "trace", "--feature", "F01") == 0
    assert run(repo, "trace", "--feature", "F01", "--strict") == 1


def test_trace_write_creates_a_traceability_matrix(repo: Path) -> None:
    assert run(repo, "trace", "--feature", "F01", "--write") == 0

    matrix = (repo / "specs/f01-widgets/traceability.md").read_text(encoding="utf-8")
    assert (
        "| F01-R1 | The server shall make widgets. | test | `tests/test_widgets.py::test_makes_widgets` |"
        in matrix
    )
    assert "`a\\|b`" in matrix
    assert (
        "| F01-R4 | A person can see a widget in Claude Code. | manual | checked |"
        in matrix
    )


def test_status_never_fails_even_without_a_prd(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(tmp_path, "status") == 0
    assert "PRD.md not found" in capsys.readouterr().out


def test_status_shows_spec_design_tasks_and_trace(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run(repo, "status")
    out = capsys.readouterr().out
    assert "| F01 | Widgets (core) | done v2 | — | 1/2 | 2/2 | 1/2 |" in out
    assert "| F02 | Gadgets | — | — | — | — | 0/1 |" in out


def test_context_prints_prd_section_next_task_and_untasked_requirements(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(repo, "context", "f1") == 0
    out = capsys.readouterr().out
    assert "expected: feat/f01-widgets" in out
    assert "next: T02 — Paint widgets" in out
    assert "requirements not in any task: F01-R4" in out
    assert "- Makes widgets." in out


def test_context_for_feature_without_spec_suggests_a_folder(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(repo, "context", "F02") == 0
    assert "specs/f02-gadgets/ (not created yet)" in capsys.readouterr().out


def test_context_for_unknown_feature_fails(repo: Path) -> None:
    assert run(repo, "context", "F42") == 1
