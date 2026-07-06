"""Parse unified diff output into per-file sets of changed line numbers.

Line numbers are in the *new* (post-diff) file version, matching what
tree-sitter reports for the checked-out working tree.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
_NEW_FILE_HEADER = re.compile(r"^\+\+\+ b/(.+)$")


def parse_unified_diff(diff_text: str) -> dict[str, set[int]]:
    """Return {relative_path: {changed line numbers in the new file}}.

    Only added/modified lines ('+' lines) count as changed — a pure deletion
    doesn't introduce a new line for a finding to anchor to. Context lines
    (present in both old and new file) advance the line counter but are not
    themselves marked changed, so this is safe to use with any context width
    (-U0 or the default -U3).
    """
    changed: dict[str, set[int]] = {}
    current_file: str | None = None
    new_line_no = 0

    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            # New file block starting. Reset so a binary file or pure rename
            # (neither emits a '+++ b/...' header) can't leak the previous
            # file's identity onto stray lines in this block.
            current_file = None
            continue

        file_match = _NEW_FILE_HEADER.match(line)
        if file_match:
            current_file = file_match.group(1)
            changed.setdefault(current_file, set())
            continue

        hunk_match = _HUNK_HEADER.match(line)
        if hunk_match:
            new_line_no = int(hunk_match.group(1))
            continue

        if current_file is None:
            continue

        if line.startswith("+") and not line.startswith("+++"):
            changed[current_file].add(new_line_no)
            new_line_no += 1
        elif line.startswith("-") and not line.startswith("---"):
            pass  # deleted line — doesn't exist in the new file
        elif line.startswith("\\"):
            pass  # "\ No newline at end of file"
        else:
            new_line_no += 1  # unchanged context line

    return changed


def git_diff_lines(repo_root: Path, base: str, head: str = "HEAD") -> dict[str, set[int]]:
    """Run `git diff base...head` scoped to C sources and parse changed lines.

    `--relative` is required: git normally prints paths relative to the repo's
    top level, not the cwd it was invoked from. If `repo_root` is a
    subdirectory of a larger repo (a common monorepo firmware layout), the
    un-prefixed paths would silently fail to match `ParsedFile.path` values
    (which are relative to `repo_root`), and every finding would be dropped.
    """
    result = subprocess.run(
        ["git", "diff", "--relative", "--unified=0", f"{base}...{head}", "--", "*.c", "*.h"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return parse_unified_diff(result.stdout)
