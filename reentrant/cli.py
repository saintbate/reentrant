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
from reentrant.model.findings import Confidence, Finding
from reentrant.parse.loader import load_repo
from reentrant.report.sarif import to_sarif

console = Console()


@click.group()
def main() -> None:
    """Reentrant — ISR-safety static analysis for STM32 firmware."""


def _run_explain(findings: list[Finding]) -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print("[dim]LLM explanation skipped — set ANTHROPIC_API_KEY to enable.[/dim]")
        return
    from reentrant.explain.llm import explain_findings
    console.print(f"[dim]Running LLM on {len(findings)} finding(s)…[/dim]")
    explain_findings(findings)


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
        console.print("[yellow]No C/H files found.[/yellow]")
        raise SystemExit(0)

    console.print(f"[dim]Analyzing {len(files)} file(s)…[/dim]")
    findings = analyze(files)

    if diff_base is not None:
        try:
            changed_lines = git_diff_lines(root, diff_base)
        except subprocess.CalledProcessError as e:
            console.print(f"[red]Failed to diff against '{diff_base}': {e.stderr.strip()}[/red]")
            raise SystemExit(2) from e
        before = len(findings)
        findings = filter_by_diff(findings, changed_lines, root)
        console.print(
            f"[dim]Diff scope ({diff_base}): {len(findings)}/{before} finding(s) "
            "touch changed lines.[/dim]"
        )

    if findings and not no_explain:
        _run_explain(findings)

    active = [f for f in findings if f.confidence != Confidence.LOW]
    suppressed_count = len(findings) - len(active)

    if output_json:
        print(json.dumps([dataclasses.asdict(f) for f in findings], default=str, indent=2))
        raise SystemExit(1 if active else 0)

    if output_sarif:
        print(json.dumps(to_sarif(active), indent=2))
        raise SystemExit(1 if active else 0)

    if not active:
        if suppressed_count:
            n = suppressed_count
            console.print(
                f"[green]✓ LLM suppressed {n} finding(s) as likely false positive(s).[/green]"
            )
        else:
            console.print("[green]✓ No ISR-safety issues found.[/green]")
        raise SystemExit(0)

    has_explanations = any(f.explanation for f in active)
    table = Table(title=f"ISR-safety findings ({len(active)})", show_lines=True)
    table.add_column("Variable", style="bold red")
    table.add_column("Declared at")
    table.add_column("ISR context")
    table.add_column("Non-ISR access")
    if has_explanations:
        table.add_column("Race condition", max_width=60, no_wrap=False)

    for f in active:
        isr_names = ", ".join(f.isr_functions[:2]) + ("…" if len(f.isr_functions) > 2 else "")
        non_isr_loc = f"{f.sample_non_isr_file.name}:{f.sample_non_isr_line}"
        row: list[str] = [
            f.variable,
            f"{f.declaring_file.name}:{f.declaring_line}",
            isr_names,
            non_isr_loc,
        ]
        if has_explanations:
            row.append(f.explanation or "")
        table.add_row(*row)

    console.print(table)
    if suppressed_count:
        n = suppressed_count
        console.print(f"[dim]({n} finding(s) suppressed by LLM as likely false positives)[/dim]")
    console.print(
        f"[yellow]{len(active)} potential ISR-safety issue(s). "
        "Add 'volatile' or wrap non-ISR accesses in a critical section.[/yellow]"
    )
    raise SystemExit(1)


# Alias for ergonomics
main.add_command(analyze_cmd, name="analyze")
