"""Discover and parse all C source files in a directory tree."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from tree_sitter import Node, Parser, Tree

from reentrant.parse.queries import C_LANGUAGE

_PARSER = Parser(C_LANGUAGE)

_SKIP_DIRS: frozenset[str] = frozenset({
    "build", "cmake-build-debug", "cmake-build-release",
    ".git", "third_party", "Drivers",
})


@dataclass
class ParsedFile:
    path: Path
    source: bytes
    tree: Tree
    root: Node = field(init=False)

    def __post_init__(self) -> None:
        self.root = self.tree.root_node

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.source).hexdigest()[:16]


def load_repo(root: Path) -> list[ParsedFile]:
    """Return a ParsedFile for every .c/.h under root, skipping build dirs."""
    results: list[ParsedFile] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix.lower() not in {".c", ".h"}:
            continue
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        source = p.read_bytes()
        results.append(ParsedFile(path=p, source=source, tree=_PARSER.parse(source)))
    return results
