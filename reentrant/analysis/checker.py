"""Core checker: cross-reference ISR accesses with non-ISR accesses."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from reentrant.analysis.access_walker import FunctionAccesses, walk_file_accesses
from reentrant.analysis.blocking_calls import find_blocking_calls
from reentrant.analysis.guards import build_guard_map
from reentrant.analysis.isr_roots import find_isr_roots
from reentrant.model.callgraph import build_call_graph
from reentrant.model.findings import Access, Confidence, Finding
from reentrant.model.rules import ISR_BLOCKING_CALL, ISR_SHARED_VAR
from reentrant.model.symbols import SymbolTable, build_symbol_table
from reentrant.parse.loader import ParsedFile

# Scoped variable identity:
#   (declaring_file_str, name) for static variables — two TUs may each have
#   their own `static int x` and they must not be conflated.
#   (None, name) for non-static (extern-linkage) globals.
_VarKey = tuple[str | None, str]


def _var_key(acc: Access, table: SymbolTable) -> _VarKey:
    sym = table.get(acc.variable, acc.file)
    if sym is not None and sym.is_static:
        return (str(sym.declaring_file), acc.variable)
    return (None, acc.variable)


def analyze(files: list[ParsedFile]) -> list[Finding]:
    """Full pipeline: parse → symbols → callgraph → ISR context → check."""
    table = build_symbol_table(files)
    cg = build_call_graph(files)

    roots = find_isr_roots(set(cg.defs.keys()))
    isr_context = cg.reachable_from(roots)

    all_accesses: list[FunctionAccesses] = []
    for pf in files:
        all_accesses.extend(walk_file_accesses(pf, table, isr_context))

    findings = _check_shared_vars(all_accesses, table, files, isr_context)
    findings += _check_blocking_calls(files, isr_context)
    return findings


def _check_blocking_calls(files: list[ParsedFile], isr_context: set[str]) -> list[Finding]:
    findings: list[Finding] = []
    for site in find_blocking_calls(files, isr_context):
        findings.append(Finding(
            variable=site.api_name,
            declaring_file=site.file,
            declaring_line=site.line,
            type_text=site.entry.category,
            isr_functions=[site.calling_function],
            non_isr_accesses=[],
            isr_accesses=[Access(
                variable=site.api_name,
                file=site.file,
                line=site.line,
                is_write=True,
                in_isr_context=True,
                function=site.calling_function,
            )],
            rule_id=ISR_BLOCKING_CALL.id,
            confidence=Confidence.HIGH,
            explanation=f"{site.entry.reason} Fix: {site.entry.fix}",
        ))
    return findings


def _check_shared_vars(
    all_accesses: list[FunctionAccesses],
    table: SymbolTable,
    files: list[ParsedFile],
    isr_context: set[str],
) -> list[Finding]:
    isr_by_var: dict[_VarKey, list[Access]] = defaultdict(list)
    non_isr_by_var: dict[_VarKey, list[Access]] = defaultdict(list)
    isr_fns_by_var: dict[_VarKey, set[str]] = defaultdict(set)

    for fa in all_accesses:
        for acc in fa.accesses:
            key = _var_key(acc, table)
            if acc.in_isr_context:
                isr_by_var[key].append(acc)
                isr_fns_by_var[key].add(acc.function)
            else:
                non_isr_by_var[key].append(acc)

    candidates = set(isr_by_var.keys()) & set(non_isr_by_var.keys())

    # Guard map only needs the raw variable names; over-checking is harmless.
    candidate_var_names = {name for _, name in candidates}
    guard_map = build_guard_map(files, isr_context, candidate_var_names)

    findings: list[Finding] = []
    for var_key in sorted(candidates, key=lambda k: (k[0] or "", k[1])):
        file_scope_str, var_name = var_key
        file_scope = Path(file_scope_str) if file_scope_str else None
        sym = table.get(var_name, file_scope)
        if sym is None:
            continue

        if sym.is_volatile:
            continue

        non_isr = non_isr_by_var[var_key]
        all_guarded = all(
            guard_map.get((str(acc.file), acc.line), False)
            for acc in non_isr
        )
        if all_guarded:
            continue

        isr_acc = isr_by_var[var_key]
        if not any(a.is_write for a in isr_acc):
            continue

        findings.append(Finding(
            variable=var_name,
            declaring_file=sym.declaring_file,
            declaring_line=sym.declaring_line,
            type_text=sym.type_text,
            isr_functions=sorted(isr_fns_by_var[var_key]),
            non_isr_accesses=non_isr,
            isr_accesses=isr_by_var[var_key],
            rule_id=ISR_SHARED_VAR.id,
            confidence=Confidence.HIGH,
        ))

    return findings
