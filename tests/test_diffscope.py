"""Diff-aware scoping: parsing unified diffs and filtering findings by them."""
from __future__ import annotations

import subprocess
from pathlib import Path

from reentrant.diffscope import filter_by_diff, git_diff_lines, parse_unified_diff
from reentrant.model.findings import Access, Finding

# A hand-verified -U0 diff: line 2 modified ("int b;" -> "int x;"),
# line 4 newly appended ("int d;"). Expected changed lines: {2, 4}.
_SAMPLE_DIFF = """\
diff --git a/foo.c b/foo.c
index e69de29..1234567 100644
--- a/foo.c
+++ b/foo.c
@@ -2 +2 @@
-int b;
+int x;
@@ -3,0 +4 @@
+int d;
"""


def test_parse_unified_diff_marks_modified_and_added_lines() -> None:
    changed = parse_unified_diff(_SAMPLE_DIFF)
    assert changed == {"foo.c": {2, 4}}


def test_parse_unified_diff_ignores_deleted_lines() -> None:
    diff_text = """\
diff --git a/foo.c b/foo.c
--- a/foo.c
+++ b/foo.c
@@ -2 +1,0 @@
-int b;
"""
    changed = parse_unified_diff(diff_text)
    # A pure deletion introduces no new line for a finding to anchor to.
    assert changed == {"foo.c": set()}


def _finding(
    declaring_file: Path,
    declaring_line: int,
    isr_line: int,
    non_isr_line: int,
) -> Finding:
    return Finding(
        variable="v",
        declaring_file=declaring_file,
        declaring_line=declaring_line,
        type_text="int",
        isr_functions=["Some_IRQHandler"],
        isr_accesses=[
            Access(
                variable="v", file=declaring_file, line=isr_line,
                is_write=True, in_isr_context=True, function="Some_IRQHandler",
            )
        ],
        non_isr_accesses=[
            Access(
                variable="v", file=declaring_file, line=non_isr_line,
                is_write=False, in_isr_context=False, function="main_loop",
            )
        ],
    )


def test_filter_by_diff_keeps_finding_when_isr_write_is_new() -> None:
    repo_root = Path("/repo")
    f = _finding(repo_root / "shared.c", declaring_line=1, isr_line=10, non_isr_line=50)
    changed = {"shared.c": {10}}  # only the new ISR write is in the diff
    assert filter_by_diff([f], changed, repo_root) == [f]


def test_filter_by_diff_keeps_finding_when_non_isr_read_is_new() -> None:
    repo_root = Path("/repo")
    f = _finding(repo_root / "shared.c", declaring_line=1, isr_line=10, non_isr_line=50)
    changed = {"shared.c": {50}}  # only the new unguarded read is in the diff
    assert filter_by_diff([f], changed, repo_root) == [f]


def test_filter_by_diff_keeps_finding_when_declaration_changed() -> None:
    repo_root = Path("/repo")
    f = _finding(repo_root / "shared.c", declaring_line=1, isr_line=10, non_isr_line=50)
    changed = {"shared.c": {1}}  # e.g. 'volatile' was dropped this PR
    assert filter_by_diff([f], changed, repo_root) == [f]


def test_filter_by_diff_drops_pre_existing_finding() -> None:
    repo_root = Path("/repo")
    f = _finding(repo_root / "shared.c", declaring_line=1, isr_line=10, non_isr_line=50)
    changed = {"shared.c": {999}}  # PR touched an unrelated line
    assert filter_by_diff([f], changed, repo_root) == []


def test_git_diff_lines_against_real_repo(tmp_path: Path) -> None:
    """End-to-end check against a real `git diff` invocation, guarding
    against off-by-one errors in hunk-header parsing.
    """
    def run(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    run("init")
    run("config", "user.email", "test@example.com")
    run("config", "user.name", "Test")

    src = tmp_path / "foo.c"
    src.write_text("int a;\nint b;\nint c;\n")
    run("add", "foo.c")
    run("commit", "-m", "initial")

    src.write_text("int a;\nint x;\nint c;\nint d;\n")
    run("add", "foo.c")
    run("commit", "-m", "modify")

    changed = git_diff_lines(tmp_path, "HEAD~1", "HEAD")
    assert changed == {"foo.c": {2, 4}}


def test_git_diff_lines_when_repo_root_is_a_subdirectory(tmp_path: Path) -> None:
    """Regression test: git prints diff paths relative to the repo's top
    level, not the cwd it was run from. If the analyzed directory is a
    subdirectory of a larger repo (e.g. `firmware/` in a monorepo), paths
    must still come back relative to that subdirectory so they match
    ParsedFile.path — otherwise every finding is silently dropped.
    """
    def run(*args: str, cwd: Path = tmp_path) -> None:
        subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)

    firmware_dir = tmp_path / "firmware"
    firmware_dir.mkdir()

    run("init")
    run("config", "user.email", "test@example.com")
    run("config", "user.name", "Test")

    src = firmware_dir / "foo.c"
    src.write_text("int a;\nint b;\nint c;\n")
    run("add", "firmware/foo.c")
    run("commit", "-m", "initial")

    src.write_text("int a;\nint x;\nint c;\nint d;\n")
    run("add", "firmware/foo.c")
    run("commit", "-m", "modify")

    # repo_root passed to git_diff_lines is the SUBDIRECTORY, not the git
    # top level — this is what reentrant does when the user points it at a
    # subfolder rather than the repo root.
    changed = git_diff_lines(firmware_dir, "HEAD~1", "HEAD")
    assert changed == {"foo.c": {2, 4}}
