"""Function call graph and ISR-context reachability."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from tree_sitter import Node

from reentrant.parse.loader import ParsedFile
from reentrant.parse.queries import CALL_EXPR_QUERY, FUNCTION_DEF_QUERY, node_text, qmatches


@dataclass
class FunctionDef:
    name: str
    file: Path
    line: int
    body: Node


@dataclass
class CallGraph:
    defs: dict[str, FunctionDef] = field(default_factory=dict)
    edges: dict[str, set[str]] = field(default_factory=dict)

    def add_def(self, fn: FunctionDef) -> None:
        self.defs[fn.name] = fn
        self.edges.setdefault(fn.name, set())

    def add_edge(self, caller: str, callee: str) -> None:
        self.edges.setdefault(caller, set()).add(callee)

    def reachable_from(self, roots: set[str]) -> set[str]:
        visited: set[str] = set(roots)
        queue = list(roots)
        while queue:
            current = queue.pop()
            for callee in self.edges.get(current, set()):
                if callee not in visited:
                    visited.add(callee)
                    queue.append(callee)
        return visited


def build_call_graph(files: list[ParsedFile]) -> CallGraph:
    cg = CallGraph()

    for pf in files:
        source = pf.source
        for _idx, captures in qmatches(FUNCTION_DEF_QUERY, pf.root):
            name_nodes = captures.get("name", [])
            body_nodes = captures.get("body", [])
            if not name_nodes or not body_nodes:
                continue
            name = node_text(name_nodes[0], source)
            cg.add_def(FunctionDef(
                name=name,
                file=pf.path,
                line=name_nodes[0].start_point[0] + 1,
                body=body_nodes[0],
            ))

    for pf in files:
        source = pf.source
        for _idx, captures in qmatches(FUNCTION_DEF_QUERY, pf.root):
            name_nodes = captures.get("name", [])
            body_nodes = captures.get("body", [])
            if not name_nodes or not body_nodes:
                continue
            caller = node_text(name_nodes[0], source)
            for _ci, call_captures in qmatches(CALL_EXPR_QUERY, body_nodes[0]):
                callee_nodes = call_captures.get("callee", [])
                if callee_nodes:
                    cg.add_edge(caller, node_text(callee_nodes[0], source))

    return cg
