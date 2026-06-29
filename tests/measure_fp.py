"""
Measure false-positive rate on real-world STM32 repos.

Run: .venv/bin/python tests/measure_fp.py [--verbose]

Each finding is printed for manual triage.  For each finding, classify:
  T = true positive  (real bug or plausible bug)
  F = false positive (suppressed by context we don't yet model)
  U = unknown        (can't tell without running the code)

Edit the MANUAL_LABELS dict below after first run.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make sure local package is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from reentrant.analysis.checker import analyze
from reentrant.model.findings import Finding
from reentrant.parse.loader import load_repo

VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv

REPOS = list((Path(__file__).parent / "real_world").iterdir())


def run_repo(repo: Path) -> list[Finding]:
    try:
        files = load_repo(repo)
        return analyze(files)
    except Exception as e:
        print(f"  ERROR: {e}")
        return []


def print_finding(f: Finding, idx: int) -> None:
    isr_list = ", ".join(f.isr_functions[:3])
    if len(f.isr_functions) > 3:
        isr_list += f" (+{len(f.isr_functions) - 3} more)"
    non_isr_locs = [f"{a.file.name}:{a.line}" for a in f.non_isr_accesses[:3]]
    print(f"  [{idx}] var={f.variable!r:20s}  type={f.type_text!r:20s}")
    print(f"       decl={f.declaring_file.name}:{f.declaring_line}")
    print(f"       isr_fns={isr_list}")
    print(f"       non_isr={', '.join(non_isr_locs)}")
    if VERBOSE:
        for a in f.non_isr_accesses:
            guard = "(no guard)"
            rw = "W" if a.is_write else "R"
            print(f"         {rw} {a.file.name}:{a.line} in {a.function} {guard}")


def main() -> None:
    total_findings = 0
    repo_summary: list[tuple[str, int, list[Finding]]] = []

    for repo in sorted(REPOS):
        if not repo.is_dir() or repo.name.startswith("."):
            continue
        print(f"\n{'='*60}")
        print(f"REPO: {repo.name}")
        findings = run_repo(repo)
        print(f"  {len(findings)} finding(s)")
        for i, f in enumerate(findings):
            print_finding(f, i)
        total_findings += len(findings)
        repo_summary.append((repo.name, len(findings), findings))

    print(f"\n{'='*60}")
    print(f"TOTAL: {total_findings} findings across {len(repo_summary)} repos")
    print()
    print("Summary:")
    for name, n, _ in repo_summary:
        print(f"  {n:3d}  {name}")

    print()
    print("Manual triage steps:")
    print("  1. For each finding above, read the flagged variable's context in the repo.")
    print("  2. Classify: T=true positive  F=false positive  U=unknown")
    print("  3. Record FP rate = F / (T + F + U)")
    print("  Target: FP rate < 30% before LLM layer, < 15% after.")


if __name__ == "__main__":
    main()
