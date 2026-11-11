#!/usr/bin/env python3
"""Spec-driven development helper for PRD-based repos.

    python3 scripts/sdd.py status                    every PRD feature and the state of its spec
    python3 scripts/sdd.py context F03               PRD section + spec, design and task state for one feature
    python3 scripts/sdd.py trace                     CI gate: every spec marked done is fully traced
    python3 scripts/sdd.py trace --feature F03 [--strict] [--write]

Conventions (docs/spec-driven-development.md has the full workflow):
  * PRD.md has headings "### Feature <n> — <title>".
  * Specs live in specs/f<nn>-<slug>/spec.md. They have a "Status:" line (draft, approved,
    building, done) and a requirements table whose rows start with an ID such as "| F03-R4 |"
    and whose last column is "test" or "manual".
  * Tests link to requirements with @pytest.mark.req("F03-R4").

Standard library only, so it runs before the project's dependencies are installed.
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import re
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent

FEATURE_HEADING = re.compile(r"^###\s+Feature\s+(\d+)\s*[—–:-]\s*(.+?)\s*$")
HEADING_UP_TO_3 = re.compile(r"^#{1,3}\s")
FENCE = re.compile(r"^\s*(```|~~~)")
CHECKBOX = re.compile(r"^\s*-\s\[( |x|X)\]")
TOP_TASK = re.compile(r"^-\s\[( |x|X)\]\s+\*\*(T\d+)\b(.*)$")
REQ_ROW = re.compile(r"^\|\s*(F\d{2}-R\d+)\s*\|")
MANUAL_ITEM = re.compile(r"^\s*-\s\[( |x|X)\]\s+(F\d{2}-R\d+)\b")
STATUS_LINE = re.compile(r"^Status:\s*([A-Za-z]+)", re.M)
VERSION_LINE = re.compile(r"^Version:\s*(\S+)", re.M)
DESIGN_STATUS_LINE = re.compile(r"^Design status:\s*([A-Za-z]+)", re.M)
TITLE_LINE = re.compile(r"^#\s+(.+?)\s*$", re.M)
REQ_ID = re.compile(r"^F\d{2}-R\d+$")
ID_IN_TEXT = re.compile(r"\bF\d{2}-R\d+\b")
SPEC_FOLDER = re.compile(r"^[Ff](\d+)(?:-|$)")

STATUSES = ("draft", "approved", "building", "done")
VERIFY_METHODS = ("test", "manual")
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".tox",
    ".nox",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    "site-packages",
    "build",
    "dist",
}


# ---------------------------------------------------------------------------- helpers


def norm_fid(raw: str) -> str:
    """'F3', 'f03', '3' -> 'F03'."""
    match = re.fullmatch(r"\s*[Ff]?0*(\d+)\s*", raw)
    if not match:
        raise ValueError(f"not a feature id: {raw!r} (use F03, f3 or 3)")
    return f"F{int(match.group(1)):02d}"


def slugify(title: str) -> str:
    title = re.sub(r"\(.*?\)", "", title)
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:48].rstrip("-") or "feature"


def git_branch(root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip()


def is_checked(mark: str) -> bool:
    return mark in ("x", "X")


# ---------------------------------------------------------------------------- PRD


@dataclass
class PrdFeature:
    fid: str
    title: str
    lines: list[str] = field(default_factory=list)

    @property
    def body(self) -> str:
        return "".join(self.lines)

    @property
    def acceptance(self) -> tuple[int, int]:
        done = total = 0
        in_fence = False
        for line in self.lines:
            if FENCE.match(line):
                in_fence = not in_fence
                continue
            match = None if in_fence else CHECKBOX.match(line)
            if match:
                total += 1
                done += is_checked(match.group(1))
        return done, total


def parse_prd(text: str) -> dict[str, PrdFeature]:
    """Split PRD.md into '### Feature <n> — <title>' sections, ignoring headings inside code fences."""
    features: dict[str, PrdFeature] = {}
    current: PrdFeature | None = None
    in_fence = False
    for line in text.splitlines(keepends=True):
        if FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence:
            heading = FEATURE_HEADING.match(line)
            if heading:
                current = PrdFeature(
                    norm_fid(heading.group(1)), heading.group(2).strip()
                )
                features[current.fid] = current
            elif HEADING_UP_TO_3.match(line):
                current = None
        if current is not None:
            current.lines.append(line)
    return features


def load_prd(root: Path) -> dict[str, PrdFeature]:
    path = root / "PRD.md"
    return parse_prd(path.read_text(encoding="utf-8")) if path.is_file() else {}


# ---------------------------------------------------------------------------- specs


@dataclass
class Requirement:
    rid: str
    text: str
    verify: str


@dataclass
class Task:
    tid: str
    done: bool
    title: str
    req_ids: list[str]


@dataclass
class Spec:
    fid: str
    folder: Path
    title: str
    status: str
    version: str
    requirements: dict[str, Requirement]
    manual_listed: set[str]
    manual_checked: set[str]
    design_status: str | None
    tasks: list[Task]
    errors: list[str]


def split_row(line: str) -> list[str]:
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|") and not inner.endswith("\\|"):
        inner = inner[:-1]
    return [cell.strip().replace("\\|", "|") for cell in re.split(r"(?<!\\)\|", inner)]


def find_spec_folder(root: Path, fid: str) -> Path | None:
    specs_dir = root / "specs"
    if not specs_dir.is_dir():
        return None
    for path in sorted(specs_dir.iterdir()):
        match = SPEC_FOLDER.match(path.name)
        if path.is_dir() and match and norm_fid(match.group(1)) == fid:
            return path
    return None


def load_spec(folder: Path, fid: str) -> Spec | None:
    spec_path = folder / "spec.md"
    if not spec_path.is_file():
        return None
    text = spec_path.read_text(encoding="utf-8")
    errors: list[str] = []

    status_match = STATUS_LINE.search(text)
    status = status_match.group(1).lower() if status_match else "draft"
    if status_match is None:
        errors.append("no 'Status:' line (treated as draft)")
    elif status not in STATUSES:
        errors.append(f"unknown status {status!r}; use one of {', '.join(STATUSES)}")
    version_match = VERSION_LINE.search(text)
    title_match = TITLE_LINE.search(text)

    requirements: dict[str, Requirement] = {}
    listed: set[str] = set()
    checked: set[str] = set()
    in_fence = False
    for number, line in enumerate(text.splitlines(), start=1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        row = REQ_ROW.match(line)
        if row:
            rid = row.group(1)
            cells = split_row(line)
            verify = cells[-1].split()[0].lower() if cells and cells[-1].split() else ""
            if not rid.startswith(f"{fid}-"):
                errors.append(f"line {number}: {rid} belongs to another feature")
            elif rid in requirements:
                errors.append(f"line {number}: duplicate requirement {rid}")
            else:
                if verify not in VERIFY_METHODS:
                    errors.append(
                        f"line {number}: {rid} has Verify {cells[-1]!r}; use 'test' or 'manual'"
                    )
                requirements[rid] = Requirement(
                    rid, cells[1] if len(cells) > 1 else "", verify
                )
            continue
        item = MANUAL_ITEM.match(line)
        if item:
            listed.add(item.group(2))
            if is_checked(item.group(1)):
                checked.add(item.group(2))

    for req in requirements.values():
        if req.verify == "manual" and req.rid not in listed:
            errors.append(
                f"{req.rid} is Verify=manual but missing from the Manual verification checklist"
            )

    design_status = None
    design_path = folder / "design.md"
    if design_path.is_file():
        design_match = DESIGN_STATUS_LINE.search(
            design_path.read_text(encoding="utf-8")
        )
        design_status = design_match.group(1).lower() if design_match else "draft"

    tasks: list[Task] = []
    tasks_path = folder / "tasks.md"
    if tasks_path.is_file():
        for line in tasks_path.read_text(encoding="utf-8").splitlines():
            task = TOP_TASK.match(line)
            if task:
                rest = task.group(3)
                title = rest.split("**")[0].strip(" —–-:")
                tasks.append(
                    Task(
                        task.group(2),
                        is_checked(task.group(1)),
                        title,
                        ID_IN_TEXT.findall(rest),
                    )
                )

    return Spec(
        fid=fid,
        folder=folder,
        title=title_match.group(1) if title_match else fid,
        status=status,
        version=version_match.group(1) if version_match else "?",
        requirements=requirements,
        manual_listed=listed,
        manual_checked=checked,
        design_status=design_status,
        tasks=tasks,
        errors=errors,
    )


def all_specs(root: Path) -> dict[str, Spec]:
    specs: dict[str, Spec] = {}
    specs_dir = root / "specs"
    if not specs_dir.is_dir():
        return specs
    for path in sorted(specs_dir.iterdir()):
        match = SPEC_FOLDER.match(path.name)
        if not (path.is_dir() and match):
            continue
        fid = norm_fid(match.group(1))
        spec = load_spec(path, fid)
        if spec is None:
            continue
        if fid in specs:
            specs[fid].errors.append(f"second spec folder for {fid}: specs/{path.name}")
            continue
        specs[fid] = spec
    return specs


# ---------------------------------------------------------------------------- tests


def iter_test_files(root: Path) -> Iterator[Path]:
    seen: set[Path] = set()
    for pattern in ("test_*.py", "*_test.py"):
        for path in root.rglob(pattern):
            rel_parts = path.relative_to(root).parts
            if path in seen or any(part in SKIP_DIRS for part in rel_parts):
                continue
            seen.add(path)
            yield path


def _is_req_marker(func: ast.expr) -> bool:
    if isinstance(func, ast.Attribute) and func.attr == "req":
        return isinstance(func.value, ast.Attribute) and func.value.attr == "mark"
    return isinstance(func, ast.Name) and func.id == "req"


def marker_ids(node: ast.expr) -> list[str]:
    if isinstance(node, (ast.List, ast.Tuple)):
        return [rid for element in node.elts for rid in marker_ids(element)]
    if isinstance(node, ast.Call) and _is_req_marker(node.func):
        return [
            arg.value
            for arg in node.args
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
        ]
    return []


def collect_test_refs(root: Path) -> tuple[dict[str, list[str]], list[str]]:
    """Map requirement ID -> pytest node IDs that carry @pytest.mark.req(<ID>)."""
    refs: dict[str, list[str]] = {}
    warnings: list[str] = []
    for path in sorted(iter_test_files(root)):
        rel = path.relative_to(root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except (SyntaxError, UnicodeDecodeError) as exc:
            warnings.append(f"{rel}: skipped ({exc.__class__.__name__})")
            continue

        module_ids: list[str] = []
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "pytestmark"
                for target in node.targets
            ):
                module_ids += marker_ids(node.value)

        def visit(
            body: list[ast.stmt], prefix: str, inherited: list[str], rel: str = rel
        ) -> None:
            for node in body:
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef)
                ) and node.name.startswith("test"):
                    ids = inherited + [
                        rid for deco in node.decorator_list for rid in marker_ids(deco)
                    ]
                    for rid in dict.fromkeys(ids):
                        refs.setdefault(rid, []).append(f"{rel}::{prefix}{node.name}")
                elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                    class_ids = inherited + [
                        rid for deco in node.decorator_list for rid in marker_ids(deco)
                    ]
                    visit(node.body, f"{prefix}{node.name}::", class_ids)

        visit(tree.body, "", module_ids)
    return refs, warnings


# ---------------------------------------------------------------------------- trace


@dataclass
class FeatureTrace:
    spec: Spec
    covered: dict[str, list[str]]
    missing: list[str]
    manual_pending: list[str]

    @property
    def test_total(self) -> int:
        return sum(
            1 for req in self.spec.requirements.values() if req.verify != "manual"
        )


def trace_feature(spec: Spec, refs: dict[str, list[str]]) -> FeatureTrace:
    covered: dict[str, list[str]] = {}
    missing: list[str] = []
    pending: list[str] = []
    for rid, req in spec.requirements.items():
        if req.verify == "manual":
            if rid not in spec.manual_checked:
                pending.append(rid)
        elif refs.get(rid):
            covered[rid] = refs[rid]
        else:
            missing.append(rid)
    return FeatureTrace(spec, covered, missing, pending)


def write_matrix(trace: FeatureTrace) -> Path:
    spec = trace.spec
    lines = [
        f"# {spec.fid} — traceability",
        "",
        f"Generated by `python3 scripts/sdd.py trace --feature {spec.fid} --write` on "
        f"{dt.date.today().isoformat()} from spec v{spec.version} (status {spec.status}).",
        "",
        "| ID | Requirement | Verify | Evidence |",
        "| --- | --- | --- | --- |",
    ]
    for rid, req in spec.requirements.items():
        if req.verify == "manual":
            evidence = "checked" if rid in spec.manual_checked else "**not checked**"
        elif rid in trace.covered:
            evidence = "<br>".join(f"`{node}`" for node in trace.covered[rid])
        else:
            evidence = "**no test**"
        text = req.text.replace("|", "\\|")
        lines.append(f"| {rid} | {text} | {req.verify} | {evidence} |")
    out = spec.folder / "traceability.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def cmd_trace(root: Path, feature: str | None, strict: bool, write: bool) -> int:
    if write and not feature:
        print("--write needs --feature")
        return 2
    specs = all_specs(root)
    refs, warnings = collect_test_refs(root)
    for warning in warnings:
        print(f"warning: {warning}")

    known = {rid for spec in specs.values() for rid in spec.requirements}
    malformed = {rid: nodes for rid, nodes in refs.items() if not REQ_ID.match(rid)}
    unknown = {
        rid: nodes
        for rid, nodes in refs.items()
        if REQ_ID.match(rid) and rid not in known
    }
    failures: list[str] = []

    if feature:
        fid = norm_fid(feature)
        if fid not in specs:
            print(f"{fid}: no spec at specs/{fid.lower()}-*/spec.md")
            return 1
        targets = [specs[fid]]
        unknown = {
            rid: nodes for rid, nodes in unknown.items() if rid.startswith(f"{fid}-")
        }
    else:
        targets = list(specs.values())

    if not targets:
        print("No specs yet (specs/f<nn>-<slug>/spec.md).")

    for spec in targets:
        trace = trace_feature(spec, refs)
        gated = bool(feature) or spec.status == "done"
        label = "gate" if gated else "info"
        name = (
            spec.title
            if spec.title.startswith(spec.fid)
            else f"{spec.fid} {spec.title}"
        )
        print(f"{name} — status {spec.status}, v{spec.version} [{label}]")
        print(f"  test requirements traced: {len(trace.covered)}/{trace.test_total}")
        if trace.missing:
            print(f"  no test yet: {', '.join(trace.missing)}")
        if trace.manual_pending:
            print(f"  manual checks not ticked: {', '.join(trace.manual_pending)}")
        for error in spec.errors:
            print(f"  spec error: {error}")

        if spec.errors and spec.status != "draft":
            failures.append(f"{spec.fid}: {len(spec.errors)} spec error(s)")
        if gated and trace.missing:
            failures.append(
                f"{spec.fid}: {len(trace.missing)} requirement(s) without a tagged test"
            )
        if trace.manual_pending and (strict or (not feature and spec.status == "done")):
            failures.append(
                f"{spec.fid}: {len(trace.manual_pending)} manual check(s) not ticked"
            )
        if write:
            print(f"  wrote {write_matrix(trace).relative_to(root).as_posix()}")

    for label, bad in (
        ("unknown requirement", unknown),
        ("malformed requirement ID", malformed),
    ):
        for rid, nodes in sorted(bad.items()):
            print(f"{label} {rid!r} referenced by: {', '.join(nodes)}")
            failures.append(f"{label} {rid!r}")

    if failures:
        print("\nFAILED:\n  " + "\n  ".join(failures))
        return 1
    print("\nOK")
    return 0


# ---------------------------------------------------------------------------- status & context


def cmd_status(root: Path) -> int:
    features = load_prd(root)
    specs = all_specs(root)
    refs, _ = collect_test_refs(root)
    print(f"Branch: {git_branch(root) or '(unknown)'}")
    if not features:
        print("PRD.md not found, or it has no '### Feature <n> — <title>' headings.")
    print("| Feature | Title | Spec | Design | Tasks | Traced | PRD ACs |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for fid in sorted(set(features) | set(specs)):
        prd = features.get(fid)
        spec = specs.get(fid)
        title = prd.title if prd else spec.title if spec else ""
        acs = "{}/{}".format(*prd.acceptance) if prd else "—"
        if spec:
            trace = trace_feature(spec, refs)
            cells = [
                f"{spec.status} v{spec.version}",
                spec.design_status or "—",
                f"{sum(t.done for t in spec.tasks)}/{len(spec.tasks)}"
                if spec.tasks
                else "—",
                f"{len(trace.covered)}/{trace.test_total}",
            ]
        else:
            cells = ["—", "—", "—", "—"]
        print(f"| {fid} | {title} | " + " | ".join(cells) + f" | {acs} |")
    return 0


def cmd_context(root: Path, raw_fid: str) -> int:
    fid = norm_fid(raw_fid)
    features = load_prd(root)
    prd = features.get(fid)
    if prd is None:
        print(
            f"{fid} is not in PRD.md. Features found: {', '.join(sorted(features)) or 'none'}"
        )
        return 1

    folder = find_spec_folder(root, fid)
    spec = load_spec(folder, fid) if folder else None
    folder_name = folder.name if folder else f"{fid.lower()}-{slugify(prd.title)}"
    branch = git_branch(root)
    expected = f"feat/{folder_name}"

    print(f"# {fid} — {prd.title}")
    print(
        f"Branch: {branch or '(unknown)'} · expected: {expected}"
        + (" (ok)" if branch == expected else "")
    )
    print(
        f"Spec folder: specs/{folder_name}/" + ("" if folder else " (not created yet)")
    )
    if spec is None:
        print("Spec: none yet — start from specs/_templates/spec.md")
    else:
        tests = sum(1 for r in spec.requirements.values() if r.verify != "manual")
        print(
            f"Spec: status {spec.status}, v{spec.version}, {len(spec.requirements)} requirements "
            f"({tests} test, {len(spec.requirements) - tests} manual)"
        )
        for error in spec.errors:
            print(f"  spec error: {error}")
        print(f"Design: {spec.design_status or 'none yet'}")
        if spec.tasks:
            done = sum(t.done for t in spec.tasks)
            nxt = next((t for t in spec.tasks if not t.done), None)
            print(
                f"Tasks: {done}/{len(spec.tasks)} done"
                + (f" · next: {nxt.tid} — {nxt.title}" if nxt else "")
            )
            tasked = {rid for t in spec.tasks for rid in t.req_ids}
            untasked = [rid for rid in spec.requirements if rid not in tasked]
            if untasked:
                print(f"  requirements not in any task: {', '.join(untasked)}")
        else:
            print("Tasks: none yet")
        refs, _ = collect_test_refs(root)
        trace = trace_feature(spec, refs)
        print(f"Traced: {len(trace.covered)}/{trace.test_total} test requirements")
    print(f"\n--- PRD.md § Feature {int(fid[1:])} ---\n")
    print(prd.body.rstrip())
    return 0


# ---------------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Spec-driven development helper.")
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help="repo root (default: parent of scripts/)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser(
        "status", help="board of PRD features and spec state (always exits 0)"
    )
    context = sub.add_parser(
        "context", help="PRD section and spec state for one feature"
    )
    context.add_argument("feature")
    trace = sub.add_parser("trace", help="requirement → test traceability gate")
    trace.add_argument("--feature", help="check one feature (always gated)")
    trace.add_argument(
        "--strict", action="store_true", help="also require manual checks to be ticked"
    )
    trace.add_argument(
        "--write", action="store_true", help="write specs/<feature>/traceability.md"
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()

    if args.cmd == "status":
        try:
            return cmd_status(root)
        except Exception as exc:  # never break a skill's context injection
            print(f"(status unavailable: {exc})")
            return 0
    try:
        if args.cmd == "context":
            return cmd_context(root, args.feature)
        return cmd_trace(root, args.feature, args.strict, args.write)
    except ValueError as exc:
        print(exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
