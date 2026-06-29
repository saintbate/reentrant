"""Prompt templates for the LLM explanation layer."""
from __future__ import annotations

from reentrant.explain.retriever import CodeContext
from reentrant.model.findings import Finding

SYSTEM = """\
You are an expert embedded-systems firmware reviewer specialising in STM32 interrupt safety.

A finding is raised when: a global variable is WRITTEN inside an ISR (or a function reachable
from one via the call graph) AND accessed in non-ISR code WITHOUT a volatile qualifier or a
critical-section guard.

You will receive code snippets. Respond with a JSON object — raw JSON only, no markdown fences,
no extra text. Required fields:

  "suppress"     : true  → false positive; false → real bug
  "reason"       : one sentence justifying your suppress decision
  "explanation"  : (only when suppress=false) 2–3 sentences describing the concrete race scenario
  "fix"          : (only when suppress=false) one-line description or code snippet for the fix

Common false-positive patterns (suppress these):
  • Variable written once before NVIC enabled (init-time write, no concurrent ISR possible)
  • Every non-ISR access site is already wrapped in a custom guard that disables interrupts
    (e.g. taskENTER_CRITICAL, __disable_irq, ENTER_CRITICAL_SECTION, PRIMASK write)
  • The ISR and the non-ISR accesses are in the same setup function that cannot overlap

Do NOT suppress a genuine race: if the ISR writes the variable and main-loop code reads or
writes it concurrently without protection, that is a real bug.\
"""


def build_prompt(finding: Finding, ctx: CodeContext) -> str:
    parts: list[str] = [
        f"VARIABLE: `{finding.variable}`  TYPE: {finding.type_text}",
        f"DECLARED AT: {finding.declaring_file.name}:{finding.declaring_line}",
        f"ISR FUNCTIONS: {', '.join(finding.isr_functions[:4])}",
    ]

    if ctx.custom_guards:
        parts.append(f"GUARD PATTERNS SEEN IN THESE FILES: {', '.join(ctx.custom_guards)}")

    parts.append("\n--- DECLARATION CONTEXT ---")
    parts.append(ctx.declaration_snippet)

    for fn_name, snippet in ctx.isr_snippets:
        parts.append(f"\n--- ISR ACCESS in `{fn_name}` ---")
        parts.append(snippet)

    for fn_name, snippet in ctx.non_isr_snippets:
        parts.append(f"\n--- NON-ISR ACCESS in `{fn_name}` ---")
        parts.append(snippet)

    return "\n".join(parts)
