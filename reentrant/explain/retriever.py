"""Extract code context from source files for LLM analysis."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from reentrant.model.findings import Finding

_CONTEXT_RADIUS = 6   # lines above/below each flagged access
_DECL_RADIUS = 8      # lines above/below declaration

# Recognise custom critical-section guard families so the LLM can weigh them
_GUARD_PATTERNS = re.compile(
    r"\b("
    r"ENTER_CRITICAL_SECTION|EXIT_CRITICAL_SECTION"
    r"|taskENTER_CRITICAL(?:_FROM_ISR)?|taskEXIT_CRITICAL(?:_FROM_ISR)?"
    r"|portDISABLE_INTERRUPTS|portENABLE_INTERRUPTS"
    r"|__disable_irq|__enable_irq"
    r"|__set_PRIMASK|__get_PRIMASK"
    r"|disable_interrupts?|enable_interrupts?"
    r"|CRITICAL_SECTION_(?:BEGIN|END)"
    r"|cpu_irq_disable|cpu_irq_enable"
    r"|vTaskSuspendAll|xTaskResumeAll"
    r")\b",
    re.IGNORECASE,
)


@dataclass
class CodeContext:
    declaration_snippet: str
    isr_snippets: list[tuple[str, str]] = field(default_factory=list)
    non_isr_snippets: list[tuple[str, str]] = field(default_factory=list)
    custom_guards: list[str] = field(default_factory=list)


def _read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def _snippet(lines: list[str], center: int, radius: int) -> str:
    lo = max(0, center - 1 - radius)
    hi = min(len(lines), center + radius)
    return "\n".join(f"{lo + i + 1:4d} | {lines[lo + i]}" for i in range(hi - lo))


def _scan_guards(lines: list[str]) -> list[str]:
    found: set[str] = set()
    for line in lines:
        for m in _GUARD_PATTERNS.finditer(line):
            found.add(m.group(0))
    return sorted(found)


def build_context(finding: Finding) -> CodeContext:
    decl_lines = _read_lines(finding.declaring_file)
    ctx = CodeContext(
        declaration_snippet=_snippet(decl_lines, finding.declaring_line, _DECL_RADIUS)
    )

    seen_isr: set[str] = set()
    for acc in finding.isr_accesses:
        if acc.function in seen_isr:
            continue
        seen_isr.add(acc.function)
        lines = _read_lines(acc.file)
        ctx.custom_guards.extend(_scan_guards(lines))
        ctx.isr_snippets.append((acc.function, _snippet(lines, acc.line, _CONTEXT_RADIUS)))
        if len(ctx.isr_snippets) >= 2:
            break

    seen_non_isr: set[str] = set()
    for acc in finding.non_isr_accesses:
        if acc.function in seen_non_isr:
            continue
        seen_non_isr.add(acc.function)
        lines = _read_lines(acc.file)
        ctx.custom_guards.extend(_scan_guards(lines))
        ctx.non_isr_snippets.append((acc.function, _snippet(lines, acc.line, _CONTEXT_RADIUS)))
        if len(ctx.non_isr_snippets) >= 3:
            break

    ctx.custom_guards = sorted(set(ctx.custom_guards))
    return ctx
