"""Finding dataclass — one per flagged variable."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class Confidence(str, Enum):
    HIGH = "high"      # emit by default
    MEDIUM = "medium"  # suppressed unless --verbose
    LOW = "low"        # suppressed by default


@dataclass(frozen=True)
class Access:
    variable: str
    file: Path
    line: int
    is_write: bool
    in_isr_context: bool
    function: str


@dataclass
class Finding:
    variable: str
    declaring_file: Path
    declaring_line: int
    type_text: str
    isr_functions: list[str]          # ISR-context functions that access this var
    non_isr_accesses: list[Access]
    isr_accesses: list[Access]
    confidence: Confidence = Confidence.HIGH
    explanation: str = ""             # filled in by LLM layer

    @property
    def primary_isr(self) -> str:
        return self.isr_functions[0] if self.isr_functions else "unknown"

    @property
    def sample_non_isr_file(self) -> Path:
        return self.non_isr_accesses[0].file if self.non_isr_accesses else self.declaring_file

    @property
    def sample_non_isr_line(self) -> int:
        return self.non_isr_accesses[0].line if self.non_isr_accesses else self.declaring_line
