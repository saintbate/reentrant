"""CLI entrypoint: reentrant analyze <path>"""
from __future__ import annotations

import dataclasses
import json
import os
import subprocess
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from reentrant.analysis.checker import analyze
from reentrant.diffscope import filter_by_diff, git_diff_lines
from reentrant.feedback import DEFAULT_FEEDBACK_PATH, append_feedback, build_record
from reentrant.model.findings import Confidence, Finding
from reentrant.parse.loader import load_repo
from reentrant.report.sarif import to_sarif

# Human-readable results (tables, final status) — the only thing on stdout
# in --json/--sarif mode is the bare print() payload built from that data.
console = Console()
# Progress/diagnostic messages always go to stderr so `--json`/`--sarif`
# output can be piped straight to a file without being corrupted by them.
err_console = Console(stderr=True)


@click.group()
def main() -> None:
    """Reentrant — ISR-safety static analysis for STM32 firmware."""


def _run_explain(findings: list[Finding]) -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        err_console.print("[dim]LLM explanation skipped — set ANTHROPIC_API_KEY to enable.[/dim]")
        return
    from reentrant.explain.llm import explain_findings
    err_console.print(f"[dim]Running LLM on {len(findings)} finding(s)…[/dim]")
    explain_findings(findings)


def _print_findings_table(findings: list[Finding], title: str) -> None:
    # Column set is rule-neutral: "Non-ISR access" only makes sense for the
    # shared-variable race rule (a blocking-call finding has no such thing),
    # and "Explanation" covers both LLM-generated and table-driven text.
    has_non_isr = any(f.non_isr_accesses for f in findings)
    has_explanations = any(f.explanation for f in findings)

    table = Table(title=title, show_lines=True)
    table.add_column("Subject", style="bold red")
    table.add_column("Location")
    table.add_column("ISR context")
    if has_non_isr:
        table.add_column("Non-ISR access")
    if has_explanations:
        table.add_column("Explanation", max_width=60, no_wrap=False)

    for f in findings:
        isr_names = ", ".join(f.isr_functions[:2]) + ("…" if len(f.isr_functions) > 2 else "")
        row: list[str] = [
            f.variable,
            f"{f.declaring_file.name}:{f.declaring_line}",
            isr_names,
        ]
        if has_non_isr:
            non_isr_loc = ""
            if f.non_isr_accesses:
                non_isr_loc = f"{f.sample_non_isr_file.name}:{f.sample_non_isr_line}"
            row.append(non_isr_loc)
        if has_explanations:
            row.append(f.explanation or "")
        table.add_row(*row)

    console.print(table)


@main.command()
@click.argument("path", type=click.Path(exists=True, file_okay=True, dir_okay=True, path_type=Path))
@click.option("--json", "output_json", is_flag=True, help="Output findings as JSON.")
@click.option("--sarif", "output_sarif", is_flag=True, help="Output findings as SARIF.")
@click.option("--no-explain", is_flag=True, help="Skip the LLM explanation layer.")
@click.option(
    "--diff-base",
    default=None,
    help="Git ref to diff against (e.g. origin/main). Scopes findings to lines "
         "touched between this ref and HEAD; pre-existing findings are suppressed.",
)
def analyze_cmd(
    path: Path, output_json: bool, output_sarif: bool, no_explain: bool, diff_base: str | None
) -> None:
    """Analyze a file or directory for ISR-safety bugs."""
    root = path if path.is_dir() else path.parent
    files = load_repo(root)
    if path.is_file():
        files = [f for f in files if f.path == path.resolve()]

    if not files:
        err_console.print("[yellow]No C/H files found.[/yellow]")
        raise SystemExit(0)

    err_console.print(f"[dim]Analyzing {len(files)} file(s)…[/dim]")
    findings = analyze(files)

    if diff_base is not None:
        try:
            changed_lines = git_diff_lines(root, diff_base)
        except subprocess.CalledProcessError as e:
            err_console.print(
                f"[red]Failed to diff against '{diff_base}': {e.stderr.strip()}[/red]"
            )
            raise SystemExit(2) from e
        before = len(findings)
        findings = filter_by_diff(findings, changed_lines, root)
        err_console.print(
            f"[dim]Diff scope ({diff_base}): {len(findings)}/{before} finding(s) "
            "touch changed lines.[/dim]"
        )

    if findings and not no_explain:
        _run_explain(findings)

    active = [f for f in findings if f.confidence != Confidence.LOW]
    suppressed_count = len(findings) - len(active)

    # Tier 1 findings can fail CI; Tier 2 are advisory-only, always, regardless
    # of confidence — this is the whole point of the tier split.
    blocking = [f for f in active if f.can_block]
    advisory = [f for f in active if not f.can_block]

    if output_json:
        print(json.dumps([dataclasses.asdict(f) for f in findings], default=str, indent=2))
        raise SystemExit(1 if blocking else 0)

    if output_sarif:
        print(json.dumps(to_sarif(active), indent=2))
        raise SystemExit(1 if blocking else 0)

    if not active:
        if suppressed_count:
            n = suppressed_count
            console.print(
                f"[green]✓ LLM suppressed {n} finding(s) as likely false positive(s).[/green]"
            )
        else:
            console.print("[green]✓ No ISR-safety issues found.[/green]")
        raise SystemExit(0)

    if blocking:
        _print_findings_table(blocking, f"Blocking ISR-safety issues ({len(blocking)})")
    if advisory:
        _print_findings_table(
            advisory, f"Advisory heuristics — does not fail CI ({len(advisory)})"
        )

    if suppressed_count:
        n = suppressed_count
        console.print(f"[dim]({n} finding(s) suppressed by LLM as likely false positives)[/dim]")

    if blocking:
        console.print(f"[yellow]{len(blocking)} blocking ISR-safety issue(s) found.[/yellow]")
        raise SystemExit(1)

    console.print(f"[dim]{len(advisory)} advisory finding(s) — review at your discretion.[/dim]")
    raise SystemExit(0)


@main.command()
@click.option("--rule", "rule_id", required=True, help="Rule id, e.g. reentrant/isr-shared-var.")
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("line", type=int)
@click.option(
    "--verdict",
    type=click.Choice(["fp", "tp", "unsure"]),
    required=True,
    help="fp = false positive, tp = true positive (real bug), unsure = can't tell.",
)
@click.option("--variable", default="", help="The flagged variable or call name, for readability.")
@click.option("--note", default="", help="Free-text context for why you gave this verdict.")
@click.option(
    "--out", "out_path", type=click.Path(path_type=Path), default=DEFAULT_FEEDBACK_PATH,
    help=f"JSONL log to append to (default: {DEFAULT_FEEDBACK_PATH}).",
)
def feedback_cmd(
    rule_id: str, file: Path, line: int, verdict: str, variable: str, note: str, out_path: Path
) -> None:
    """Record a human verdict on a finding: reentrant feedback --rule ID --verdict fp FILE LINE.

    Appends one record (rule, tier, code context, verdict) to a JSONL log —
    the labeled dataset the reframe spec calls for. This is what a
    '/false-positive' PR comment resolves to under the hood; see
    .github/workflows/false-positive.yml for the automated trigger.
    """
    try:
        record = build_record(rule_id, file, line, verdict, variable=variable, note=note)
    except KeyError as e:
        err_console.print(f"[red]{e}[/red]")
        raise SystemExit(2) from e

    append_feedback(record, out_path)
    console.print(f"[green]✓ Recorded {verdict} verdict for '{rule_id}' → {out_path}[/green]")


# Aliases for ergonomics
main.add_command(analyze_cmd, name="analyze")
main.add_command(feedback_cmd, name="feedback")
