"""Detect critical-section guards around non-ISR accesses."""
from __future__ import annotations

import re

from tree_sitter import Node

from reentrant.parse.loader import ParsedFile
from reentrant.parse.queries import FUNCTION_DEF_QUERY, IDENTIFIER_QUERY, node_text, qmatches

_GUARD_ENTER = re.compile(
    r"^(__disable_irq"
    r"|taskENTER_CRITICAL|portENTER_CRITICAL|portDISABLE_INTERRUPTS"
    r"|CRITICAL_SECTION_ENTER|ENTER_CRITICAL|IRQ_DISABLE|hal_disable_irq)$"
)
# __set_PRIMASK restores the PRIMASK register to a saved value, serving as the
# exit of a save/disable/restore critical section (ARM idiom).
_GUARD_EXIT = re.compile(
    r"^(__enable_irq|__set_PRIMASK"
    r"|taskEXIT_CRITICAL|portEXIT_CRITICAL|portENABLE_INTERRUPTS"
    r"|CRITICAL_SECTION_EXIT|EXIT_CRITICAL|IRQ_ENABLE|hal_enable_irq)$"
)


def _is_guarded_access(ident_node: Node, body: Node, source: bytes) -> bool:
    """Return True if the ident falls inside a lexical disable/enable bracket."""
    calls: list[tuple[str, int]] = []

    def _walk(node: Node) -> None:
        if node.type == "call_expression":
            fn = node.child_by_field_name("function")
            if fn and fn.type == "identifier":
                calls.append((node_text(fn, source), node.start_byte))
        for child in node.children:
            _walk(child)

    _walk(body)

    target = ident_node.start_byte
    depth = 0
    for fn_name, byte_pos in calls:
        if byte_pos >= target:
            break
        if _GUARD_ENTER.match(fn_name):
            depth += 1
        elif _GUARD_EXIT.match(fn_name):
            depth -= 1

    return depth > 0


def build_guard_map(
    files: list[ParsedFile],
    isr_context: set[str],
    candidate_vars: set[str],
) -> dict[tuple[str, int], bool]:
    guard_map: dict[tuple[str, int], bool] = {}

    for pf in files:
        source = pf.source
        for _idx, captures in qmatches(FUNCTION_DEF_QUERY, pf.root):
            name_nodes = captures.get("name", [])
            body_nodes = captures.get("body", [])
            if not name_nodes or not body_nodes:
                continue

            fn_name = node_text(name_nodes[0], source)
            if fn_name in isr_context:
                continue

            body_node = body_nodes[0]
            for _ii, id_captures in qmatches(IDENTIFIER_QUERY, body_node):
                ident_nodes = id_captures.get("ident", [])
                if not ident_nodes:
                    continue
                ident_node = ident_nodes[0]
                var_name = node_text(ident_node, source)

                if var_name not in candidate_vars:
                    continue

                line = ident_node.start_point[0] + 1
                key = (str(pf.path), line)
                guard_map[key] = _is_guarded_access(ident_node, body_node, source)

    return guard_map
