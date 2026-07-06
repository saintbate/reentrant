"""Rule registry: every detector registers itself here with a tier.

Tier 1 rules are precise enough to fail CI — gated at <15% false-positive
rate on the diff benchmark (see tests/measure_fp.py). If a rule can't hold
that bar, it belongs in Tier 2 or should be deleted.

Tier 2 rules are advisory only: they always render as PR comments and never
affect the CLI exit code, regardless of confidence. This is what lets the
tool add heuristic/dataflow candidates without risking a false alarm ever
blocking someone's merge.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Tier(str, Enum):
    TIER_1 = "tier_1"  # precise enough to fail CI
    TIER_2 = "tier_2"  # advisory only, never blocks


@dataclass(frozen=True)
class Rule:
    id: str
    tier: Tier
    title: str
    description: str

    @property
    def can_block(self) -> bool:
        return self.tier is Tier.TIER_1


_RULES: dict[str, Rule] = {}


def register(rule: Rule) -> Rule:
    if rule.id in _RULES:
        raise ValueError(f"Rule id already registered: {rule.id!r}")
    _RULES[rule.id] = rule
    return rule


def get_rule(rule_id: str) -> Rule:
    try:
        return _RULES[rule_id]
    except KeyError:
        raise KeyError(
            f"Unknown rule id: {rule_id!r}. Register it via reentrant.model.rules.register()."
        ) from None


def all_rules() -> list[Rule]:
    return list(_RULES.values())


ISR_SHARED_VAR = register(Rule(
    id="reentrant/isr-shared-var",
    tier=Tier.TIER_1,
    title="Shared variable accessed in ISR without volatile or guard",
    description=(
        "A global or static variable is written inside an ISR (or a function "
        "transitively reachable from one) and also accessed in non-ISR code "
        "without the 'volatile' qualifier or a recognised critical-section "
        "guard. This is a potential data race on Cortex-M."
    ),
))
