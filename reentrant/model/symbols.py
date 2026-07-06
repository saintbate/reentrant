"""Cross-translation-unit symbol table for global/static variables."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from tree_sitter import Node

from reentrant.parse.loader import ParsedFile
from reentrant.parse.queries import (
    GLOBAL_DECL_QUERY,
    node_text,
    qmatches,
)

_HAL_HANDLE_PREFIXES = re.compile(
    r"^(h(tim|uart|spi|i2c|adc|dac|can|rng|rtc|sd|nand|nor|pccard|sram|dma|"
    r"crc|iwdg|wwdg|eth|pcd|hcd|dcmi|cryp|hash|rcc|flash|gpio|exti|"
    r"syscfg|pwr|bkp|usb|fdcan|lptim|opamp|comp|sai|dfsdm|mdios|quadspi|swpmi|"
    r"smbus))[0-9]*$",
    re.IGNORECASE,
)

_PERIPHERAL_NAMES = re.compile(
    r"^(GPIOA?|GPIOB?|GPIOC?|GPIOD?|GPIOE?|GPIOF?|GPIOG?|GPIOH?|GPIOI?|"
    r"TIM[0-9]+|USART[0-9]+|UART[0-9]+|SPI[0-9]+|I2C[0-9]+|ADC[0-9]+|"
    r"DAC|DMA[0-9]*|CAN[0-9]*|RCC|FLASH|EXTI|SYSCFG|PWR|SCB|NVIC|SysTick|"
    r"FDCAN[0-9]*|LPTIM[0-9]*|SAI[0-9]*)$"
)

# CMSIS volatile type aliases — declarations using these are implicitly volatile
_CMSIS_VOLATILE_TYPES = re.compile(r"\b(__IO|__IOM|__IM|__OM)\b")

# CMSIS globals that are write-once during init before NVIC is enabled
_CMSIS_INIT_GLOBALS: frozenset[str] = frozenset({
    "SystemCoreClock",
    "SystemD2Clock",
    "SystemD3Clock",
})


@dataclass
class Symbol:
    name: str
    is_volatile: bool
    is_static: bool
    declaring_file: Path
    declaring_line: int
    type_text: str


@dataclass
class SymbolTable:
    # static variables are file-scoped: two TUs may each have `static int x`
    # and they are entirely separate variables.  Key: (abs_path_str, name).
    _static_syms: dict[tuple[str, str], Symbol] = field(init=False, default_factory=dict)
    # Non-static (extern linkage) globals share one definition across all TUs.
    _global_syms: dict[str, Symbol] = field(init=False, default_factory=dict)

    def add(self, sym: Symbol) -> None:
        if sym.is_static:
            self._static_syms[(str(sym.declaring_file), sym.name)] = sym
        else:
            self._global_syms[sym.name] = sym

    def get(self, name: str, file: Path | None = None) -> Symbol | None:
        """Look up a symbol by name, respecting static file scope.

        Pass ``file`` (the TU being walked) so that a static declared in that
        file is found before falling back to the global table.
        """
        if file is not None:
            sym = self._static_syms.get((str(file), name))
            if sym is not None:
                return sym
        return self._global_syms.get(name)

    def is_suppressed(self, name: str) -> bool:
        return bool(
            _HAL_HANDLE_PREFIXES.match(name)
            or _PERIPHERAL_NAMES.match(name)
            or name in _CMSIS_INIT_GLOBALS
        )


def _extract_declarator_names(node: Node, source: bytes) -> list[str]:
    names: list[str] = []
    if node.type == "identifier":
        names.append(node_text(node, source))
    elif node.type in ("pointer_declarator", "array_declarator", "init_declarator"):
        for child in node.children:
            names.extend(_extract_declarator_names(child, source))
    return names


def _declarator_has_volatile(node: Node, source: bytes) -> bool:
    """True if `volatile` qualifies the pointer itself rather than the base
    type, e.g. `List_t * volatile pxDelayedTaskList` (FreeRTOS's own idiom
    for several kernel-internal globals: pxCurrentTCB, pxDelayedTaskList,
    etc.). tree-sitter-c parses this as a `type_qualifier` child of the
    `pointer_declarator`, not a sibling of the base type field — the check
    in build_symbol_table only looks at the latter, so this catches the
    former, recursing through nested pointer/array declarators. Checks the
    qualifier's actual text since `const` is the same node type.
    """
    if node.type not in ("pointer_declarator", "array_declarator", "init_declarator"):
        return False
    return any(
        (child.type == "type_qualifier" and node_text(child, source) == "volatile")
        or _declarator_has_volatile(child, source)
        for child in node.children
    )


def build_symbol_table(files: list[ParsedFile]) -> SymbolTable:
    table = SymbolTable()

    for pf in files:
        source = pf.source

        for _idx, captures in qmatches(GLOBAL_DECL_QUERY, pf.root):
            type_nodes = captures.get("type", [])
            decl_nodes = captures.get("decl", [])
            if not type_nodes or not decl_nodes:
                continue

            type_node = type_nodes[0]
            decl_node = decl_nodes[0]

            type_text = node_text(type_node, source)
            # volatile and storage-class qualifiers are sibling nodes to the
            # type field in tree-sitter-c (e.g. `volatile int x` →
            # type_qualifier + primitive_type).
            decl_parent = type_node.parent
            qualifier_text = ""
            if decl_parent is not None:
                qualifier_text = " ".join(
                    node_text(c, source)
                    for c in decl_parent.children
                    if c.type == "type_qualifier" or c.type == "storage_class_specifier"
                )

            full_text = (qualifier_text + " " + type_text).strip()

            if "extern" in full_text:
                continue

            volatile = (
                "volatile" in full_text
                or bool(_CMSIS_VOLATILE_TYPES.search(full_text))
                or _declarator_has_volatile(decl_node, source)
            )
            is_static = "static" in full_text

            for name in _extract_declarator_names(decl_node, source):
                if not name:
                    continue
                table.add(Symbol(
                    name=name,
                    is_volatile=volatile,
                    is_static=is_static,
                    declaring_file=pf.path,
                    declaring_line=type_node.start_point[0] + 1,
                    type_text=full_text,
                ))

    return table
