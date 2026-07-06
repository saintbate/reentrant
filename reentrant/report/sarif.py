"""Emit SARIF 2.1.0 output for GitHub code-scanning integration."""
from __future__ import annotations

from importlib.metadata import version
from typing import Any

from reentrant.model.findings import Finding
from reentrant.model.rules import ISR_BLOCKING_CALL, ISR_SHARED_VAR, Tier, all_rules

TOOL_VERSION = version("reentrant")

# Tier 1 findings render as blocking errors in the Security tab; Tier 2 are
# advisory and never fail CI, so they render at a lower severity.
_LEVEL_BY_TIER = {Tier.TIER_1: "error", Tier.TIER_2: "warning"}


def _build_message(f: Finding) -> str:
    """Each rule needs its own message shape — a shared variable race and an
    ISR-unsafe call don't describe the same kind of problem."""
    if f.rule_id == ISR_SHARED_VAR.id:
        isr_list = ", ".join(f.isr_functions)
        msg = (
            f"Variable '{f.variable}' ({f.type_text}) is accessed in ISR context "
            f"({isr_list}) and in non-ISR code without 'volatile' or a critical-section guard. "
            f"This can cause a data race. Declare as 'volatile' or protect non-ISR accesses with "
            f"__disable_irq()/__enable_irq() (or equivalent)."
        )
    elif f.rule_id == ISR_BLOCKING_CALL.id:
        isr_list = ", ".join(f.isr_functions)
        msg = f"'{f.variable}' is called from ISR context ({isr_list}) but is not ISR-safe."
    else:
        msg = f"{f.rule.title}: '{f.variable}'."

    if f.explanation and not f.explanation.startswith("[suppressed]"):
        msg += f" {f.explanation}"
    return msg


def to_sarif(findings: list[Finding]) -> dict[str, Any]:
    results = []
    for f in findings:
        msg = _build_message(f)
        results.append({
            "ruleId": f.rule_id,
            "level": _LEVEL_BY_TIER[f.tier],
            "message": {"text": msg},
            "properties": {"tags": [f.tier.value]},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": str(f.declaring_file), "uriBaseId": "%SRCROOT%"},
                    "region": {"startLine": f.declaring_line},
                }
            }],
            "relatedLocations": [
                {
                    "id": i,
                    "message": {"text": f"Non-ISR access in {acc.function}"},
                    "physicalLocation": {
                        "artifactLocation": {"uri": str(acc.file), "uriBaseId": "%SRCROOT%"},
                        "region": {"startLine": acc.line},
                    },
                }
                for i, acc in enumerate(f.non_isr_accesses[:5])
            ],
        })

    # Declare every registered rule (not just ones that fired this run) so
    # GitHub Code Scanning has stable rule metadata across runs.
    rules = [
        {
            "id": rule.id,
            "name": rule.id.rsplit("/", 1)[-1],
            "shortDescription": {"text": rule.title},
            "fullDescription": {"text": rule.description},
            "defaultConfiguration": {"level": _LEVEL_BY_TIER[rule.tier]},
            "properties": {"tags": [rule.tier.value]},
        }
        for rule in all_rules()
    ]

    return {
        "version": "2.1.0",
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "reentrant",
                    "version": TOOL_VERSION,
                    "informationUri": "https://github.com/saintbate/reentrant",
                    "rules": rules,
                }
            },
            "results": results,
        }],
    }
