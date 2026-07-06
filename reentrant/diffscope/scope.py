"""Filter whole-repo findings down to the ones a diff actually touched."""
from __future__ import annotations

from pathlib import Path

from reentrant.model.findings import Finding


def _rel(file: Path, repo_root: Path) -> str:
    try:
        return str(file.relative_to(repo_root))
    except ValueError:
        return str(file)


def filter_by_diff(
    findings: list[Finding],
    changed_lines: dict[str, set[int]],
    repo_root: Path,
) -> list[Finding]:
    """Keep only findings with at least one contributing line inside the diff.

    A contributing line is the declaration, any ISR access, or any non-ISR
    access — checked with OR, not AND. A finding surfaces if the PR introduced
    the ISR write, introduced the unguarded read, or touched the declaration
    (e.g. dropped 'volatile'), even if the other side of the race predates
    the PR. A finding where none of those lines were touched is a pre-existing
    issue and is suppressed in diff mode.
    """
    in_scope: list[Finding] = []
    for f in findings:
        candidate_lines = [(f.declaring_file, f.declaring_line)]
        candidate_lines += [(a.file, a.line) for a in f.isr_accesses]
        candidate_lines += [(a.file, a.line) for a in f.non_isr_accesses]

        if any(
            line in changed_lines.get(_rel(file, repo_root), ())
            for file, line in candidate_lines
        ):
            in_scope.append(f)

    return in_scope
