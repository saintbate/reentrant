"""Walk function bodies and record read/write accesses to global symbols."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tree_sitter import Node

from reentrant.model.findings import Access
from reentrant.model.symbols import SymbolTable
from reentrant.parse.loader import ParsedFile
from reentrant.parse.queries import (
    ASSIGNMENT_QUERY,
    FUNCTION_DEF_QUERY,
    IDENTIFIER_QUERY,
    UPDATE_EXPR_QUERY,
    node_text,
    qmatches,
)


@dataclass
class FunctionAccesses:
    function: str
    file: Path
    accesses: list[Access]


def _collect_write_byte_offsets(body: Node, source: bytes) -> set[int]:
    write_offsets: set[int] = set()
    for _idx, captures in qmatches(ASSIGNMENT_QUERY, body):
        lhs_nodes = captures.get("lhs", [])
        if lhs_nodes:
            _collect_ident_offsets(lhs_nodes[0], write_offsets)
    # x++, --x etc. are also writes
    for _idx, captures in qmatches(UPDATE_EXPR_QUERY, body):
        target_nodes = captures.get("target", [])
        if target_nodes:
            write_offsets.add(target_nodes[0].start_byte)
    return write_offsets


def _collect_ident_offsets(node: Node, out: set[int]) -> None:
    if node.type == "identifier":
        out.add(node.start_byte)
    for child in node.children:
        _collect_ident_offsets(child, out)


def _local_names_in_body(body: Node, source: bytes) -> set[str]:
    locals_: set[str] = set()
    _walk_locals(body, source, locals_)
    return locals_


def _walk_locals(node: Node, source: bytes, out: set[str]) -> None:
    if node.type == "function_definition":
        return
    if node.type in ("declaration", "parameter_declaration"):
        for child in node.children:
            _extract_decl_names(child, source, out)
    for child in node.children:
        _walk_locals(child, source, out)


def _extract_decl_names(node: Node, source: bytes, out: set[str]) -> None:
    if node.type == "identifier":
        out.add(node_text(node, source))
    elif node.type in ("pointer_declarator", "array_declarator", "init_declarator",
                       "function_declarator"):
        for child in node.children:
            _extract_decl_names(child, source, out)


def walk_file_accesses(
    pf: ParsedFile, table: SymbolTable, isr_context: set[str]
) -> list[FunctionAccesses]:
    source = pf.source
    results: list[FunctionAccesses] = []

    for _idx, captures in qmatches(FUNCTION_DEF_QUERY, pf.root):
        name_nodes = captures.get("name", [])
        body_nodes = captures.get("body", [])
        params_nodes = captures.get("params", [])
        if not name_nodes or not body_nodes:
            continue

        fn_name = node_text(name_nodes[0], source)
        body_node = body_nodes[0]
        in_isr = fn_name in isr_context

        write_offsets = _collect_write_byte_offsets(body_node, source)
        local_names = _local_names_in_body(body_node, source)
        if params_nodes:
            _walk_locals(params_nodes[0], source, local_names)

        accesses: list[Access] = []
        for _ii, id_captures in qmatches(IDENTIFIER_QUERY, body_node):
            ident_nodes = id_captures.get("ident", [])
            if not ident_nodes:
                continue
            ident_node = ident_nodes[0]
            name = node_text(ident_node, source)

            if name in local_names:
                continue
            if table.is_suppressed(name):
                continue
            if table.get(name, pf.path) is None:
                continue

            accesses.append(Access(
                variable=name,
                file=pf.path,
                line=ident_node.start_point[0] + 1,
                is_write=ident_node.start_byte in write_offsets,
                in_isr_context=in_isr,
                function=fn_name,
            ))

        if accesses:
            results.append(FunctionAccesses(function=fn_name, file=pf.path, accesses=accesses))

    return results
