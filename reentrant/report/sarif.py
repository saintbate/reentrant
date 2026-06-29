"""Emit SARIF 2.1.0 output for GitHub code-scanning integration."""
from __future__ import annotations

from importlib.metadata import version

from reentrant.model.findings import Finding

TOOL_VERSION = version("reentrant")
RULE_ID = "reentrant/isr-shared-var"


def to_sarif(findings: list[Finding]) -> dict:
    results = []
    for f in findings:
        isr_list = ", ".join(f.isr_functions)
        msg = (
            f"Variable '{f.variable}' ({f.type_text}) is accessed in ISR context "
            f"({isr_list}) and in non-ISR code without 'volatile' or a critical-section guard. "
            f"This can cause a data race. Declare as 'volatile' or protect non-ISR accesses with "
            f"__disable_irq()/__enable_irq() (or equivalent)."
        )
        if f.explanation and not f.explanation.startswith("[suppressed]"):
            msg += f" {f.explanation}"
        results.append({
            "ruleId": RULE_ID,
            "level": "warning",
            "message": {"text": msg},
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

    return {
        "version": "2.1.0",
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "reentrant",
                    "version": TOOL_VERSION,
                    "informationUri": "https://github.com/your-org/reentrant",
                    "rules": [{
                        "id": RULE_ID,
                        "name": "IsrSharedVariable",
                        "shortDescription": {
                            "text": "Shared variable accessed in ISR without volatile or guard",
                        },
                        "fullDescription": {"text": (
                            "A global or static variable is read or written inside an ISR "
                            "(or a function transitively called from one) and also accessed "
                            "in non-ISR code, without the 'volatile' qualifier or a recognised "
                            "critical-section wrapper. This is a potential data race on Cortex-M."
                        )},
                        "defaultConfiguration": {"level": "warning"},
                        "helpUri": "https://github.com/your-org/reentrant/docs/rules/isr-shared-var.md",
                    }],
                }
            },
            "results": results,
        }],
    }
