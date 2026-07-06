"""Tier system: rule metadata and the CI-blocking contract.

Core invariant being tested: Tier 1 findings can fail CI, Tier 2 findings
never do, regardless of confidence. This is the entire reason the tier
split exists — a noisy heuristic must never be able to block a merge.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from reentrant.cli import main
from reentrant.model.findings import Access, Finding
from reentrant.model.rules import ISR_SHARED_VAR, Rule, Tier, get_rule, register

# A synthetic Tier 2 rule standing in for a future dataflow/API-misuse
# heuristic (none exist yet — those land with the API tables). Registered
# here, not in production code, since nothing produces it today.
_FAKE_TIER_2 = register(Rule(
    id="test/fake-tier2-heuristic",
    tier=Tier.TIER_2,
    title="Fake advisory heuristic (test-only)",
    description="Stand-in for a future Tier 2 dataflow candidate.",
))


def test_tier1_rule_can_block() -> None:
    assert ISR_SHARED_VAR.tier is Tier.TIER_1
    assert ISR_SHARED_VAR.can_block is True


def test_tier2_rule_cannot_block() -> None:
    assert _FAKE_TIER_2.tier is Tier.TIER_2
    assert _FAKE_TIER_2.can_block is False


def test_get_rule_unknown_id_raises() -> None:
    with pytest.raises(KeyError):
        get_rule("no/such/rule")


def test_register_duplicate_id_raises() -> None:
    with pytest.raises(ValueError):
        register(Rule(id=ISR_SHARED_VAR.id, tier=Tier.TIER_1, title="x", description="x"))


def _finding(rule_id: str, file: Path) -> Finding:
    return Finding(
        variable="v",
        declaring_file=file,
        declaring_line=1,
        type_text="int",
        isr_functions=["Some_IRQHandler"],
        isr_accesses=[
            Access(variable="v", file=file, line=1, is_write=True,
                   in_isr_context=True, function="Some_IRQHandler"),
        ],
        non_isr_accesses=[
            Access(variable="v", file=file, line=2, is_write=False,
                   in_isr_context=False, function="main_loop"),
        ],
        rule_id=rule_id,
    )


def test_finding_can_block_follows_its_rule(tmp_path: Path) -> None:
    f = tmp_path / "x.c"
    tier1_finding = _finding(ISR_SHARED_VAR.id, f)
    tier2_finding = _finding(_FAKE_TIER_2.id, f)

    assert tier1_finding.tier is Tier.TIER_1
    assert tier1_finding.can_block is True
    assert tier2_finding.tier is Tier.TIER_2
    assert tier2_finding.can_block is False


def test_cli_exit_code_depends_only_on_tier1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The exit code is the whole point of the tier split: a Tier 2-only
    result set must exit 0 (never blocks CI) even though findings exist,
    while any Tier 1 finding must exit 1.
    """
    src = tmp_path / "shared.c"
    src.write_text("int v;\n")

    f = tmp_path / "shared.c"
    tier2_only = [_finding(_FAKE_TIER_2.id, f)]
    mixed = [_finding(_FAKE_TIER_2.id, f), _finding(ISR_SHARED_VAR.id, f)]

    runner = CliRunner()

    monkeypatch.setattr("reentrant.cli.analyze", lambda files: tier2_only)
    result = runner.invoke(main, ["analyze", str(tmp_path), "--no-explain"])
    assert result.exit_code == 0, result.output
    assert "Advisory heuristics" in result.output

    monkeypatch.setattr("reentrant.cli.analyze", lambda files: mixed)
    result = runner.invoke(main, ["analyze", str(tmp_path), "--no-explain"])
    assert result.exit_code == 1, result.output
    assert "Blocking ISR-safety issues" in result.output
    assert "Advisory heuristics" in result.output
