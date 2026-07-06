"""Diff-aware scoping: filter whole-repo findings to what a PR touched."""
from reentrant.diffscope.gitdiff import git_diff_lines, parse_unified_diff
from reentrant.diffscope.scope import filter_by_diff

__all__ = ["git_diff_lines", "parse_unified_diff", "filter_by_diff"]
