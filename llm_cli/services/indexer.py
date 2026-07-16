#!/usr/bin/env python3
"""Compact project context index generation (formerly gen_context_cache.py).

Instead of having the LLM read every file linearly (high token cost),
this module builds a symbol index (functions, classes) grouped by directory.
The LLM reads this index first and then targets only the files it needs.

Output format (one line per file):
    rel/path/file.py | 120 LOC | ClassName.method1, ClassName.method2, top_level_func

Exclusions:
    Reads the tool ignore files at project root (gitignore-style patterns,
    union across all profiles) so one index serves every tool.
"""

from __future__ import annotations

import ast
import fnmatch
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from llm_cli import tool_profile

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv",
    "venv", "dist", "build",
    ".next", ".nuxt", "coverage", ".pytest_cache", ".mypy_cache",
    ".tox", "eggs", ".eggs", "*.egg-info", ".cache", ".idea", ".vscode",
    "CMakeFiles", ".cmake",
    # Windows / WSL user-profile noise
    "AppData", "Application Data", "Local Settings",
    "D3DSCache", "ConnectedDevicesPlatform", "Packages",
    "WindowsApps", "WpSystem", "GameBarPresenceWriter",
}

SKIP_EXTENSIONS = {
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".exe", ".bin",
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".ico", ".webp",
    ".mp4", ".mp3", ".wav", ".pdf", ".zip", ".tar", ".gz",
    ".lock", ".sum", ".map", ".min.js", ".min.css",
    ".o", ".a", ".d", ".obj", ".lib", ".pch", ".gch",
    # Windows system / cache artefacts
    ".dxcache", ".blf", ".cdp", ".cdpresource",
    ".db-shm", ".db-wal", ".db-journal",
    ".edb", ".winmd", ".pak", ".uca", ".jcp", ".jfm",
    ".pb", ".sst",
}

_CPP_SKIP_KEYWORDS: frozenset[str] = frozenset({
    "if", "for", "while", "switch", "catch", "return", "else", "do",
    "try", "case", "sizeof", "alignof", "decltype", "delete", "new",
    "throw", "static_assert", "static_cast", "dynamic_cast",
    "reinterpret_cast", "const_cast",
})

MAX_FILE_SIZE_KB = 200
MAX_FILES = 200
MAX_SYMBOLS = 12
# Collect up to SCAN_LIMIT candidates before sorting and truncating to MAX_FILES.
# Large enough to give the sort meaningful input, bounded to prevent hangs on huge trees.
SCAN_LIMIT = MAX_FILES * 5


def extract_python_symbols(path: Path) -> list[str]:
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source)
    except SyntaxError:
        return []

    symbols = []
    # iter_child_nodes visits only direct module-level children — no double-counting of methods.
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            methods = [
                n.name for n in ast.iter_child_nodes(node)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            if methods:
                for method in methods[:6]:
                    symbols.append(f"{node.name}.{method}")
                if len(methods) > 6:
                    symbols.append(f"{node.name}...")
            else:
                symbols.append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(node.name)

    return symbols


def extract_js_ts_symbols(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8", errors="ignore")
    symbols = []

    class_pattern = re.compile(r'^(?:export\s+)?class\s+(\w+)', re.MULTILINE)
    func_pattern = re.compile(
        r'^(?:export\s+)?(?:async\s+)?function\s+(\w+)|'
        r'^(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s+)?\(',
        re.MULTILINE
    )
    interface_pattern = re.compile(r'^(?:export\s+)?(?:interface|type)\s+(\w+)', re.MULTILINE)

    for match in class_pattern.finditer(source):
        symbols.append(match.group(1))
    for match in func_pattern.finditer(source):
        name = match.group(1) or match.group(2)
        if name:
            symbols.append(name)
    for match in interface_pattern.finditer(source):
        symbols.append(match.group(1))

    return symbols[:20]


def extract_go_symbols(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8", errors="ignore")
    pattern = re.compile(r'^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\(', re.MULTILINE)
    return [m.group(1) for m in pattern.finditer(source)][:20]


def extract_rust_symbols(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8", errors="ignore")
    struct_pattern = re.compile(r'^pub\s+struct\s+(\w+)|^struct\s+(\w+)', re.MULTILINE)
    fn_pattern = re.compile(r'^(?:pub\s+)?(?:async\s+)?fn\s+(\w+)', re.MULTILINE)
    symbols = []
    for m in struct_pattern.finditer(source):
        symbols.append(m.group(1) or m.group(2))
    for m in fn_pattern.finditer(source):
        symbols.append(m.group(1))
    return symbols[:20]


def extract_bash_symbols(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8", errors="ignore")
    funcs = re.compile(r'^(\w+)\s*\(\s*\)', re.MULTILINE)
    # Exported vars (export FOO=) and plain uppercase constants (FOO=).
    exports = re.compile(r'^export\s+([A-Z_][A-Z0-9_]*)=', re.MULTILINE)
    constants = re.compile(r'^([A-Z_][A-Z0-9_]{2,})=', re.MULTILINE)
    symbols = [m.group(1) for m in funcs.finditer(source)]
    symbols += [m.group(1) for m in exports.finditer(source)]
    symbols += [m.group(1) for m in constants.finditer(source)]
    return symbols[:10]


def extract_c_symbols(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8", errors="ignore")
    symbols: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        if name not in seen and name not in _CPP_SKIP_KEYWORDS and len(name) > 1:
            seen.add(name)
            symbols.append(name)

    for m in re.finditer(r'^\s*(?:typedef\s+)?struct\s+(\w+)', source, re.MULTILINE):
        add(m.group(1))
    for m in re.finditer(r'^\s*enum\s+(\w+)', source, re.MULTILINE):
        add(m.group(1))
    for m in re.finditer(r'}\s*(\w+)\s*;', source):
        add(m.group(1))
    for m in re.finditer(r'^\s*typedef\s+\w[\w\s*]+\s+(\w+)\s*;', source, re.MULTILINE):
        add(m.group(1))

    func_re = re.compile(
        r'^(?:static\s+|extern\s+|inline\s+)*'
        r'(?:const\s+)?[\w*][\w\s*]*\s+'
        r'(\w+)\s*\(',
        re.MULTILINE,
    )
    for m in func_re.finditer(source):
        add(m.group(1))

    return symbols[:25]


def extract_cpp_symbols(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8", errors="ignore")
    symbols: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        if name not in seen and name not in _CPP_SKIP_KEYWORDS and len(name) > 1:
            seen.add(name)
            symbols.append(name)

    for m in re.finditer(r'^\s*namespace\s+(\w+)\s*[{;]', source, re.MULTILINE):
        add(f"ns:{m.group(1)}")
    for m in re.finditer(
        r'^(?:\s*template\s*<[^>]*>\s*)?\s*(?:class|struct)\s+(\w+)',
        source, re.MULTILINE,
    ):
        add(m.group(1))
    for m in re.finditer(r'^\s*enum(?:\s+class)?\s+(\w+)', source, re.MULTILINE):
        add(m.group(1))
    for m in re.finditer(r'}\s*(\w+)\s*;', source):
        add(m.group(1))
    for m in re.finditer(r'^\s*typedef\s+\w[\w\s*]+\s+(\w+)\s*;', source, re.MULTILINE):
        add(m.group(1))
    for m in re.finditer(r'(\w+)(?:<[^>]*>)?::(\w+)\s*\(', source):
        class_name, method = m.group(1), m.group(2)
        if method not in _CPP_SKIP_KEYWORDS:
            add(f"{class_name}::{method}")
    func_re = re.compile(
        r'^(?:(?:static|inline|virtual|explicit|constexpr|friend)\s+)*'
        r'(?:const\s+)?[\w:*&<>]+\s+'
        r'(\w+)\s*\(',
        re.MULTILINE,
    )
    for m in func_re.finditer(source):
        add(m.group(1))

    return symbols[:30]


def extract_proto_symbols(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8", errors="ignore")
    pattern = re.compile(r'^\s*(?:message|service|enum|rpc)\s+(\w+)', re.MULTILINE)
    return [m.group(1) for m in pattern.finditer(source)][:20]


EXTRACTORS = {
    ".py":    extract_python_symbols,
    ".js":    extract_js_ts_symbols,
    ".ts":    extract_js_ts_symbols,
    ".tsx":   extract_js_ts_symbols,
    ".jsx":   extract_js_ts_symbols,
    ".go":    extract_go_symbols,
    ".rs":    extract_rust_symbols,
    ".sh":    extract_bash_symbols,
    ".bash":  extract_bash_symbols,
    ".c":     extract_c_symbols,
    ".h":     extract_cpp_symbols,
    ".cpp":   extract_cpp_symbols,
    ".cc":    extract_cpp_symbols,
    ".cxx":   extract_cpp_symbols,
    ".hpp":   extract_cpp_symbols,
    ".hxx":   extract_cpp_symbols,
    ".hh":    extract_cpp_symbols,
    ".proto": extract_proto_symbols,
}


def count_lines(path: Path) -> int:
    try:
        return sum(1 for _ in path.open(encoding="utf-8", errors="ignore"))
    except OSError:
        return 0


def should_skip(path: Path) -> bool:
    if path.suffix in SKIP_EXTENSIONS:
        return True
    try:
        if path.stat().st_size > MAX_FILE_SIZE_KB * 1024:
            return True
    except (FileNotFoundError, OSError):
        # Broken symlink or unreadable file — skip it
        return True
    return False


# Built once from the tool profiles so adding a tool extends the index scope
# without editing the indexer (e.g. ".opencodeignore" comes for free).
IGNORE_FILE_NAMES = tuple(
    profile.ignore_file
    for profile in tool_profile.ALL_PROFILES
    if profile.ignore_file
)


def load_ignore_patterns(project_root: Path) -> list[str]:
    """Reads the tool ignore files at project root and returns their glob patterns."""
    patterns = []
    for name in IGNORE_FILE_NAMES:
        ignore_file = project_root / name
        if not ignore_file.exists():
            continue
        for line in ignore_file.read_text(encoding="utf-8").splitlines():
            line = line.strip().rstrip("/")
            if line and not line.startswith("#"):
                patterns.append(line)
    return patterns


def is_ignored(rel_path: str, patterns: list[str]) -> bool:
    """Returns True if rel_path matches any ignore pattern."""
    parts = Path(rel_path).parts
    for pattern in patterns:
        if fnmatch.fnmatch(rel_path, pattern):
            return True
        for part in parts:
            if fnmatch.fnmatch(part, pattern):
                return True
    return False


def collect_files(project_root: Path, ignore_patterns: list[str]) -> list[tuple[str, Path]]:
    """Returns (relative_path_str, absolute_path) pairs sorted by relevance, capped at MAX_FILES.

    Collects up to SCAN_LIMIT candidates, then sorts by relevance (source files first,
    shallower depth first) before truncating to MAX_FILES. This prevents deep directories
    with many noise files from crowding out important top-level source files, while
    bounding traversal time on large trees.
    """
    results: list[tuple[str, Path]] = []

    for dirpath, dirnames, filenames in os.walk(project_root):
        if len(results) >= SCAN_LIMIT:
            break

        current_dir = Path(dirpath)
        rel_dir = current_dir.relative_to(project_root)

        dirnames[:] = [
            d for d in sorted(dirnames)
            if d not in SKIP_DIRS
            and not d.startswith(".")
            and not is_ignored(str(rel_dir / d), ignore_patterns)
        ]

        for filename in sorted(filenames):
            if len(results) >= SCAN_LIMIT:
                break
            file_path = current_dir / filename
            rel_file = str(rel_dir / filename) if str(rel_dir) != "." else filename
            if should_skip(file_path):
                continue
            if is_ignored(rel_file, ignore_patterns):
                continue
            results.append((rel_file, file_path))

    # Sort: source files first (have an extractor), then by directory depth ascending.
    results.sort(key=lambda item: (
        0 if item[1].suffix.lower() in EXTRACTORS else 1,
        len(Path(item[0]).parts),
    ))
    return results[:MAX_FILES]


def is_cache_fresh(output_file: Path, project_root: Path, ignore_patterns: list[str]) -> bool:
    """Returns True if the cache is newer than every file in the project tree.

    Walks the tree independently of collect_files and exits as soon as one
    newer file is found — O(1) in the common case where something changed,
    O(n) only when the cache is truly up to date.
    """
    if not output_file.exists():
        return False
    cache_mtime = output_file.stat().st_mtime

    for dirpath, dirnames, filenames in os.walk(project_root):
        current_dir = Path(dirpath)
        rel_dir = current_dir.relative_to(project_root)

        dirnames[:] = [
            d for d in dirnames
            if d not in SKIP_DIRS
            and not d.startswith(".")
            and not is_ignored(str(rel_dir / d), ignore_patterns)
        ]

        for filename in filenames:
            try:
                if (current_dir / filename).stat().st_mtime > cache_mtime:
                    return False
            except OSError:
                pass

    return True


def format_symbols(symbols: list[str]) -> str:
    if not symbols:
        return ""
    truncated = symbols[:MAX_SYMBOLS]
    suffix = "..." if len(symbols) > MAX_SYMBOLS else ""
    return ", ".join(truncated) + suffix


def detect_project_type(project_root: Path) -> str:
    markers = {
        "Python":             ["setup.py", "pyproject.toml", "requirements.txt"],
        "Node.js/TypeScript": ["package.json", "tsconfig.json"],
        "Go":                 ["go.mod"],
        "Rust":               ["Cargo.toml"],
        "CMake/C++":          ["CMakeLists.txt"],
    }
    detected = [lang for lang, files in markers.items()
                if any((project_root / f).exists() for f in files)]
    return ", ".join(detected) if detected else "Unknown"


_PROGRESS_BAR_WIDTH = 32


def _render_progress(current: int, total: int) -> None:
    """Writes a progress bar to stderr, overwriting the current line."""
    filled = int(_PROGRESS_BAR_WIDTH * current / total)
    arrow = ">" if filled < _PROGRESS_BAR_WIDTH else ""
    bar = "=" * filled + arrow + " " * (_PROGRESS_BAR_WIDTH - filled - len(arrow))
    sys.stderr.write(f"\r  [{bar}] {current}/{total}")
    sys.stderr.flush()


def generate_index(project_root: Path, files: list[tuple[str, Path]]) -> str:
    """Builds the markdown index from a pre-collected file list."""
    total = len(files)
    show_progress = sys.stderr.isatty() and total > 0

    total_loc = 0
    ext_counts: dict[str, int] = {}
    file_rows: list[str] = []

    for i, (rel_path, abs_path) in enumerate(files):
        if show_progress:
            _render_progress(i + 1, total)

        ext = abs_path.suffix.lower()
        ext_counts[ext] = ext_counts.get(ext, 0) + 1
        loc = count_lines(abs_path)
        total_loc += loc

        extractor = EXTRACTORS.get(ext)
        symbols = extractor(abs_path) if extractor else []
        sym_str = format_symbols(symbols)

        row = f"{rel_path} | {loc} LOC"
        if sym_str:
            row += f" | {sym_str}"
        file_rows.append(row)

    if show_progress:
        # Clear the progress line before printing the final status.
        sys.stderr.write(f"\r{' ' * (_PROGRESS_BAR_WIDTH + 20)}\r")
        sys.stderr.flush()

    ext_summary = ", ".join(
        f"{ext or 'no-ext'}: {count}"
        for ext, count in sorted(ext_counts.items(), key=lambda x: -x[1])
        if count > 0
    )

    lines: list[str] = [
        "# Project Context Index",
        (f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} | "
         f"Root: {project_root} | "
         f"{len(files)} files | ~{total_loc:,} LOC | "
         f"Type: {detect_project_type(project_root)}"),
        f"Extensions: {ext_summary}",
        "",
        "> Read this index first. Target specific files instead of scanning broadly.",
        "> Format: path | LOC | symbols (Class.method for class members)",
        "",
    ]
    lines.extend(file_rows)

    return "\n".join(lines)


def build_index(project_root: Path, output_file: Path) -> None:
    """Generates the index into output_file, skipping when already fresh.

    Raises NotADirectoryError on a bad project root; any other failure
    propagates so callers can restore a previous cache.
    """
    project_root = Path(project_root).resolve()
    if not project_root.is_dir():
        raise NotADirectoryError(f"{project_root} is not a directory")

    ignore_patterns = load_ignore_patterns(project_root)

    # Check freshness before collecting files — returns immediately if nothing changed.
    if is_cache_fresh(output_file, project_root, ignore_patterns):
        lines = output_file.read_text(encoding="utf-8").count("\n")
        print(f"[OK] Context index up to date ({lines} lines)")
        return

    files = collect_files(project_root, ignore_patterns)
    print(f"Indexing {project_root}...")
    index = generate_index(project_root, files)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(index, encoding="utf-8")

    lines = index.count("\n")
    print(f"[OK] Context index written to {output_file} ({lines} lines)")
