"""Tree-sitter symbol extraction and PageRank ranking for the context index.

Replaces the per-language regex extractors with tree-sitter tag queries
(vendored under llm_cli/queries) and ranks files by a PageRank over the
cross-file definition/reference graph. The index then leads with the code the
rest of the project depends on most, instead of ordering by directory depth.

The public entry point is extract_symbols(); everything else is internal.
Any tree-sitter failure degrades gracefully (returns nothing for that file) so
the indexer can fall back to its regex extractors.
"""

from __future__ import annotations

from collections import Counter, defaultdict, namedtuple
from pathlib import Path

import networkx as nx
import tree_sitter as ts
from grep_ast.parsers import filename_to_lang
from grep_ast.tsl import get_language, get_parser

QUERIES_DIR = Path(__file__).resolve().parent.parent / "queries"

# kind is "def" (a definition) or "ref" (a reference/call site).
Tag = namedtuple("Tag", "path name kind line")

# PageRank damping factor and iteration bounds (networkx defaults, named to
# avoid magic numbers per the project conventions).
_PAGERANK_ALPHA = 0.85
_PAGERANK_MAX_ITER = 100

_query_cache: dict[str, ts.Query | None] = {}


def _load_query(lang: str) -> ts.Query | None:
    """Compiles the vendored tags query for a language, cached, None if absent."""
    if lang in _query_cache:
        return _query_cache[lang]
    scm_file = QUERIES_DIR / f"{lang}-tags.scm"
    query: ts.Query | None = None
    if scm_file.is_file():
        try:
            query = ts.Query(get_language(lang), scm_file.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — a broken grammar/query just disables it.
            query = None
    _query_cache[lang] = query
    return query


def supported_lang(abs_path: Path) -> str | None:
    """Returns the tree-sitter language for a file when a tags query exists."""
    lang = filename_to_lang(str(abs_path))
    if lang and _load_query(lang) is not None:
        return lang
    return None


def get_tags(abs_path: Path, rel_path: str, lang: str) -> list[Tag]:
    """Extracts definition and reference tags from one file via tree-sitter."""
    query = _load_query(lang)
    if query is None:
        return []
    try:
        code = abs_path.read_text(encoding="utf-8", errors="ignore")
        tree = get_parser(lang).parse(bytes(code, "utf-8"))
    except Exception:  # noqa: BLE001 — unreadable/unparsable file: no tags.
        return []

    captures = ts.QueryCursor(query).captures(tree.root_node)
    tags: list[Tag] = []
    for cap_name, nodes in captures.items():
        if cap_name.startswith("name.definition."):
            kind = "def"
        elif cap_name.startswith("name.reference."):
            kind = "ref"
        else:
            continue
        for node in nodes:
            name = node.text.decode("utf-8", errors="ignore")
            tags.append(Tag(rel_path, name, kind, node.start_point[0] + 1))
    return tags


def _rank(all_tags: list[Tag]) -> tuple[dict[str, float], dict[tuple[str, str], int]]:
    """Ranks files and definitions from the full tag set.

    Returns (file_rank, symbol_refs):
      file_rank[path]          PageRank over the cross-file reference graph.
      symbol_refs[(path,name)] number of *other* files referencing that symbol.
    """
    defines: dict[str, set[str]] = defaultdict(set)      # ident -> files defining it
    referencers: dict[str, set[str]] = defaultdict(set)  # ident -> files referencing it
    ref_counts: Counter[tuple[str, str]] = Counter()     # (file, ident) -> ref count

    for tag in all_tags:
        if tag.kind == "def":
            defines[tag.name].add(tag.path)
        else:
            referencers[tag.name].add(tag.path)
            ref_counts[(tag.path, tag.name)] += 1

    # Edge referencer -> definer means "this file depends on that file"; PageRank
    # then flows toward the most depended-upon (core) files. Only cross-file
    # references matter, so identifiers defined nowhere in the tree are ignored.
    graph = nx.DiGraph()
    for ident, definer_files in defines.items():
        for referencer in referencers.get(ident, ()):
            for definer in definer_files:
                if referencer == definer:
                    continue
                weight = ref_counts[(referencer, ident)]
                if graph.has_edge(referencer, definer):
                    graph[referencer][definer]["weight"] += weight
                else:
                    graph.add_edge(referencer, definer, weight=weight)

    file_rank: dict[str, float] = {}
    if graph.number_of_edges():
        try:
            file_rank = nx.pagerank(
                graph, alpha=_PAGERANK_ALPHA, max_iter=_PAGERANK_MAX_ITER, weight="weight"
            )
        except nx.PowerIterationFailedConvergence:
            file_rank = {}

    symbol_refs: dict[tuple[str, str], int] = {}
    for ident, definer_files in defines.items():
        others = referencers.get(ident, set())
        for definer in definer_files:
            symbol_refs[(definer, ident)] = len(others - {definer})

    return file_rank, symbol_refs


def extract_symbols(
    files: list[tuple[str, Path]],
) -> tuple[dict[str, list[str]], dict[str, float]]:
    """Extracts and ranks symbols for every tree-sitter-supported file.

    Returns (symbols_by_path, file_rank):
      symbols_by_path[rel]  definition names, ordered by cross-file importance.
                            Present (possibly empty) for every supported file;
                            absent for files the indexer should regex-fallback.
      file_rank[rel]        PageRank score (absent => treat as 0.0).
    """
    all_tags: list[Tag] = []
    defs_by_file: dict[str, list[str]] = {}

    for rel, abs_path in files:
        lang = supported_lang(abs_path)
        if lang is None:
            continue
        tags = get_tags(abs_path, rel, lang)
        all_tags.extend(tags)
        defs_by_file[rel] = [tag.name for tag in tags if tag.kind == "def"]

    file_rank, symbol_refs = _rank(all_tags)

    symbols_by_path: dict[str, list[str]] = {}
    for rel, names in defs_by_file.items():
        # De-duplicate keeping the first occurrence, then order by how many other
        # files reference the symbol (API surface first), name as a stable tie.
        importance: dict[str, int] = {}
        for name in names:
            importance.setdefault(name, symbol_refs.get((rel, name), 0))
        symbols_by_path[rel] = sorted(
            importance, key=lambda name: (-importance[name], name)
        )

    return symbols_by_path, file_rank
