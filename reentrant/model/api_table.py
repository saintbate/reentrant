"""Curated table of ISR-unsafe APIs (libc, STM32 HAL, FreeRTOS).

This table is the real domain knowledge behind the isr-blocking-call rule —
kept as data (reentrant/data/isr_unsafe_apis.toml), not code, so it can grow
without touching the detector in reentrant/analysis/blocking_calls.py.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from importlib import resources


@dataclass(frozen=True)
class ApiEntry:
    name: str
    category: str
    blocking: bool
    reason: str
    fix: str
    # If the SAME calling function also calls this ISR-safe counterpart (e.g.
    # xSemaphoreGive's sibling is xSemaphoreGiveFromISR), the call is almost
    # always a deliberate runtime dispatch — e.g. CMSIS-RTOS's
    # `if (inHandlerMode()) { xFromISR(...) } else { x(...) }` wrappers, which
    # every STM32Cube + FreeRTOS project ships. We can't see the branch, but
    # the presence of both calls in one function is strong evidence it's
    # handled correctly, so we don't flag it.
    safe_sibling: str | None = None


def _load_unsafe_apis() -> dict[str, ApiEntry]:
    data_text = resources.files("reentrant").joinpath("data", "isr_unsafe_apis.toml").read_text()
    raw = tomllib.loads(data_text)
    return {
        name: ApiEntry(
            name=name,
            category=fields["category"],
            blocking=fields["blocking"],
            reason=fields["reason"],
            fix=fields["fix"],
            safe_sibling=fields.get("safe_sibling"),
        )
        for name, fields in raw.items()
    }


UNSAFE_APIS: dict[str, ApiEntry] = _load_unsafe_apis()
