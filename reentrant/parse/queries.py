"""Tree-sitter S-expression queries and helpers for C analysis.

C_LANGUAGE is the canonical singleton for this package — import it from here,
not from loader.py.
"""
from __future__ import annotations

import warnings

import tree_sitter_c
from tree_sitter import Language, Node, Query, QueryCursor

C_LANGUAGE = Language(tree_sitter_c.language())


def _q(src: str) -> Query:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return C_LANGUAGE.query(src)


def qmatches(query: Query, node: Node) -> list[tuple[int, dict[str, list[Node]]]]:
    """Run a query via the 0.25.x QueryCursor API.

    Returns list of (pattern_index, {capture_name: [Node, ...]}).
    """
    cursor = QueryCursor(query)
    return cursor.matches(node)


def node_text(node: Node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


# All top-level / file-scope variable declarations
GLOBAL_DECL_QUERY = _q("""
(translation_unit
  (declaration
    type: (_) @type
    declarator: (_) @decl))
""")

# All function definitions
FUNCTION_DEF_QUERY = _q("""
(function_definition
  type: (_) @ret_type
  declarator: (function_declarator
    declarator: (identifier) @name
    parameters: (_) @params)
  body: (compound_statement) @body)
""")

# All call expressions inside a node
CALL_EXPR_QUERY = _q("""
(call_expression
  function: (identifier) @callee)
""")

# All identifier uses (post-filter by symbol table)
IDENTIFIER_QUERY = _q("""
(identifier) @ident
""")

# Assignment left-hand sides
ASSIGNMENT_QUERY = _q("""
(assignment_expression
  left: (_) @lhs
  right: (_) @rhs)
""")

# Increment / decrement — also writes (x++, ++x, x--, --x)
UPDATE_EXPR_QUERY = _q("""
(update_expression
  argument: (identifier) @target)
""")
