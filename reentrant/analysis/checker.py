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
from reentrant.model.rules import ISR_BLOCKING_CALL, ISR_SHARED_VAR, ISR_STALE_READ
from reentrant.model.symbols import Symbol, SymbolTable, build_symbol_table
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

    buckets = _bucket_accesses(all_accesses, table, files, isr_context)

    findings = _check_shared_var_races(buckets, table)
    findings += _check_stale_reads(buckets, table)
    findings += _check_blocking_calls(files, isr_context)
    return findings


class _Buckets:
    """Accesses grouped by scoped variable identity, shared across the
    variable-based rules so accesses and the guard map are computed once."""

    def __init__(self) -> None:
        self.isr_by_var: dict[_VarKey, list[Access]] = defaultdict(list)
        self.non_isr_by_var: dict[_VarKey, list[Access]] = defaultdict(list)
        self.isr_fns_by_var: dict[_VarKey, set[str]] = defaultdict(set)
        self.candidates: set[_VarKey] = set()
        self.guard_map: dict[tuple[str, int], bool] = {}

    def all_guarded(self, accesses: list[Access]) -> bool:
        return all(self.guard_map.get((str(acc.file), acc.line), False) for acc in accesses)


def _bucket_accesses(
    all_accesses: list[FunctionAccesses],
    table: SymbolTable,
    files: list[ParsedFile],
    isr_context: set[str],
) -> _Buckets:
    buckets = _Buckets()

    for fa in all_accesses:
        for acc in fa.accesses:
            key = _var_key(acc, table)
            if acc.in_isr_context:
                buckets.isr_by_var[key].append(acc)
                buckets.isr_fns_by_var[key].add(acc.function)
            else:
                buckets.non_isr_by_var[key].append(acc)

    buckets.candidates = set(buckets.isr_by_var.keys()) & set(buckets.non_isr_by_var.keys())

    # Guard map only needs the raw variable names; over-checking is harmless.
    candidate_var_names = {name for _, name in buckets.candidates}
    buckets.guard_map = build_guard_map(files, isr_context, candidate_var_names)

    return buckets


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


def _sym_for(var_key: _VarKey, table: SymbolTable) -> tuple[str, Symbol | None]:
    file_scope_str, var_name = var_key
    file_scope = Path(file_scope_str) if file_scope_str else None
    return var_name, table.get(var_name, file_scope)


def _check_shared_var_races(buckets: _Buckets, table: SymbolTable) -> list[Finding]:
    """Tier 1: the ISR writes a variable that non-ISR code accesses without
    volatile or a guard — the classic race, high enough precision to block CI.
    """
    findings: list[Finding] = []
    for var_key in sorted(buckets.candidates, key=lambda k: (k[0] or "", k[1])):
        var_name, sym = _sym_for(var_key, table)
        if sym is None or sym.is_volatile:
            continue

        non_isr = buckets.non_isr_by_var[var_key]
        if buckets.all_guarded(non_isr):
            continue

        isr_acc = buckets.isr_by_var[var_key]
        if not any(a.is_write for a in isr_acc):
            continue

        findings.append(Finding(
            variable=var_name,
            declaring_file=sym.declaring_file,
            declaring_line=sym.declaring_line,
            type_text=sym.type_text,
            isr_functions=sorted(buckets.isr_fns_by_var[var_key]),
            non_isr_accesses=non_isr,
            isr_accesses=isr_acc,
            rule_id=ISR_SHARED_VAR.id,
            confidence=Confidence.HIGH,
        ))

    return findings


def _check_stale_reads(buckets: _Buckets, table: SymbolTable) -> list[Finding]:
    """Tier 2: the inverse of the race above — the ISR only reads a variable
    that non-ISR code writes without volatile or a guard. The ISR may see a
    stale or torn value, but this pattern is common and mostly benign for
    write-once-at-init config/threshold variables, so it's advisory only.
    """
    findings: list[Finding] = []
    for var_key in sorted(buckets.candidates, key=lambda k: (k[0] or "", k[1])):
        var_name, sym = _sym_for(var_key, table)
        if sym is None or sym.is_volatile:
            continue

        isr_acc = buckets.isr_by_var[var_key]
        if any(a.is_write for a in isr_acc):
            continue  # ISR writes it — that's isr-shared-var's job

        non_isr = buckets.non_isr_by_var[var_key]
        if not any(a.is_write for a in non_isr):
            continue  # no non-ISR write — nothing for the ISR to go stale on

        if buckets.all_guarded(non_isr):
            continue

        findings.append(Finding(
            variable=var_name,
            declaring_file=sym.declaring_file,
            declaring_line=sym.declaring_line,
            type_text=sym.type_text,
            isr_functions=sorted(buckets.isr_fns_by_var[var_key]),
            non_isr_accesses=non_isr,
            isr_accesses=isr_acc,
            rule_id=ISR_STALE_READ.id,
            confidence=Confidence.HIGH,
        ))

    return findings
