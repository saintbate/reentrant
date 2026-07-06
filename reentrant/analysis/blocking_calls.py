"""Detect calls to known ISR-unsafe APIs from ISR-reachable code."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from reentrant.model.api_table import UNSAFE_APIS, ApiEntry
from reentrant.parse.loader import ParsedFile
from reentrant.parse.queries import CALL_EXPR_QUERY, FUNCTION_DEF_QUERY, node_text, qmatches


@dataclass
class BlockingCallSite:
    api_name: str
    entry: ApiEntry
    file: Path
    line: int
    calling_function: str


def find_blocking_calls(
    files: list[ParsedFile], isr_context: set[str]
) -> list[BlockingCallSite]:
    """Walk every ISR-reachable function and flag calls to table-listed APIs."""
    sites: list[BlockingCallSite] = []

    for pf in files:
        source = pf.source
        for _idx, captures in qmatches(FUNCTION_DEF_QUERY, pf.root):
            name_nodes = captures.get("name", [])
            body_nodes = captures.get("body", [])
            if not name_nodes or not body_nodes:
                continue

            fn_name = node_text(name_nodes[0], source)
            if fn_name not in isr_context:
                continue

            body_node = body_nodes[0]
            calls = [
                (node_text(cn, source), cn)
                for _ci, cc in qmatches(CALL_EXPR_QUERY, body_node)
                for cn in cc.get("callee", [])
            ]
            callee_names = {name for name, _ in calls}

            for callee_name, callee_node in calls:
                entry = UNSAFE_APIS.get(callee_name)
                if entry is None:
                    continue
                if entry.safe_sibling is not None and entry.safe_sibling in callee_names:
                    # Same function also calls the ISR-safe counterpart —
                    # almost always a deliberate runtime dispatch, not a bug.
                    continue

                sites.append(BlockingCallSite(
                    api_name=callee_name,
                    entry=entry,
                    file=pf.path,
                    line=callee_node.start_point[0] + 1,
                    calling_function=fn_name,
                ))

    return sites
