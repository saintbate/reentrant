"""Feedback loop: JSONL logging of human verdicts on findings."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from reentrant.cli import main
from reentrant.feedback import append_feedback, build_record
from reentrant.model.rules import ISR_SHARED_VAR, Tier


def test_build_record_captures_code_context(tmp_path: Path) -> None:
    src = tmp_path / "shared.c"
    src.write_text("int flag = 0;\n\nvoid EXTI0_IRQHandler(void) {\n    flag = 1;\n}\n")

    record = build_record(ISR_SHARED_VAR.id, src, 4, "tp", variable="flag", note="real bug")

    assert record.rule_id == ISR_SHARED_VAR.id
    assert record.tier == Tier.TIER_1.value
    assert record.verdict == "tp"
    assert record.variable == "flag"
    assert record.note == "real bug"
    assert "flag = 1;" in record.code_context
    assert record.timestamp  # non-empty ISO timestamp


def test_build_record_unknown_rule_raises(tmp_path: Path) -> None:
    src = tmp_path / "shared.c"
    src.write_text("int x;\n")
    with pytest.raises(KeyError):
        build_record("no/such/rule", src, 1, "fp")


def test_append_feedback_writes_jsonl(tmp_path: Path) -> None:
    src = tmp_path / "shared.c"
    src.write_text("int flag = 0;\n")
    out = tmp_path / "feedback.jsonl"

    r1 = build_record(ISR_SHARED_VAR.id, src, 1, "fp", note="first")
    r2 = build_record(ISR_SHARED_VAR.id, src, 1, "tp", note="second")
    append_feedback(r1, out)
    append_feedback(r2, out)

    lines = out.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["note"] == "first"
    assert json.loads(lines[1])["note"] == "second"


def test_append_feedback_creates_parent_dirs(tmp_path: Path) -> None:
    src = tmp_path / "shared.c"
    src.write_text("int flag = 0;\n")
    out = tmp_path / "nested" / "dir" / "feedback.jsonl"

    record = build_record(ISR_SHARED_VAR.id, src, 1, "fp")
    append_feedback(record, out)

    assert out.exists()


def test_cli_feedback_command(tmp_path: Path) -> None:
    src = tmp_path / "shared.c"
    src.write_text("int flag = 0;\n\nvoid EXTI0_IRQHandler(void) {\n    flag = 1;\n}\n")
    out = tmp_path / "feedback.jsonl"

    runner = CliRunner()
    result = runner.invoke(main, [
        "feedback",
        "--rule", ISR_SHARED_VAR.id,
        "--verdict", "fp",
        "--note", "init-time only",
        "--out", str(out),
        str(src), "4",
    ])

    assert result.exit_code == 0, result.output
    assert out.exists()
    record = json.loads(out.read_text().splitlines()[0])
    assert record["rule_id"] == ISR_SHARED_VAR.id
    assert record["verdict"] == "fp"
    assert record["note"] == "init-time only"


def test_cli_feedback_unknown_rule_errors(tmp_path: Path) -> None:
    src = tmp_path / "shared.c"
    src.write_text("int flag = 0;\n")

    runner = CliRunner()
    result = runner.invoke(main, [
        "feedback", "--rule", "no/such/rule", "--verdict", "fp", str(src), "1",
    ])

    assert result.exit_code == 2
