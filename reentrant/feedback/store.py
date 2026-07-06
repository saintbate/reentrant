"""Append-only JSONL feedback log: rule, code context, and a human verdict.

This is the "labeled dataset" the reframe spec calls for — a durable record
of which findings a developer confirmed as real bugs vs false positives,
meant to grow over time and eventually inform rule tuning.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from reentrant.model.rules import Tier, get_rule

DEFAULT_FEEDBACK_PATH = Path(".reentrant/feedback.jsonl")

_CONTEXT_RADIUS = 5  # lines above/below the flagged line to snapshot


@dataclass(frozen=True)
class FeedbackRecord:
    timestamp: str
    rule_id: str
    tier: str
    file: str
    line: int
    variable: str
    verdict: str  # "fp" | "tp" | "unsure"
    note: str
    code_context: str


def _read_snippet(file: Path, line: int, radius: int = _CONTEXT_RADIUS) -> str:
    try:
        lines = file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    lo = max(0, line - 1 - radius)
    hi = min(len(lines), line + radius)
    return "\n".join(f"{lo + i + 1:4d} | {lines[lo + i]}" for i in range(hi - lo))


def build_record(
    rule_id: str,
    file: Path,
    line: int,
    verdict: str,
    variable: str = "",
    note: str = "",
) -> FeedbackRecord:
    """Validates rule_id against the registry and snapshots code context.

    Raises KeyError via reentrant.model.rules.get_rule if rule_id is unknown.
    """
    rule = get_rule(rule_id)  # raises KeyError for an unknown rule id
    tier: Tier = rule.tier
    return FeedbackRecord(
        timestamp=datetime.now(UTC).isoformat(),
        rule_id=rule_id,
        tier=tier.value,
        file=str(file),
        line=line,
        variable=variable,
        verdict=verdict,
        note=note,
        code_context=_read_snippet(file, line),
    )


def append_feedback(record: FeedbackRecord, out_path: Path = DEFAULT_FEEDBACK_PATH) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(record)) + "\n")
