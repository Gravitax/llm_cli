"""setup-git-hooks — installs git hooks that refresh the context cache after
structural git operations (port of setup_git_hooks.sh + git_hook_refresh.ps1).

One POSIX sh hook serves both platforms: Git for Windows bundles sh.exe, and
the body converts paths with cygpath when available before delegating to run.py.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from llm_cli import paths, platforms
from llm_cli.services import fs, git, log, text_blocks

BLOCK_BEGIN = "# >>> llm_cli cache refresh >>>"
BLOCK_END = "# <<< llm_cli cache refresh <<<"

# Legacy bodies written by setup_git_hooks.sh / setup_git_hooks.ps1 — recognized
# so migration replaces them instead of appending a duplicate refresh.
_LEGACY_NEEDLES = ("setup_context_cache.sh", "git_hook_refresh.ps1")
_LEGACY_PATTERNS = (
    re.compile(r"\n?for tool_home in [^\n]*\n(?:.*\n)*?done\n?"),
    re.compile(r'\n?bash "\$HOME/\.(claude|copilot)/scripts/setup_context_cache\.sh".*\n?'),
    re.compile(r"\n?\[ \"\$3\" = \"1\" \] \|\| exit 0\n?"),
    re.compile(r"\n?project_dir=\$\(git rev-parse[^\n]*\n"),
    re.compile(r"\n?project_hash=\$\(echo -n[^\n]*\n"),
    re.compile(r"\n?[^\n]*git_hook_refresh\.ps1[^\n]*\n"),
)

# post-checkout receives: $1=prev HEAD, $2=new HEAD, $3=1 (branch) or 0 (file).
# Only branch checkouts change the structure, hence the guard variant.
_HOOK_BODY = """\
# Context cache refresh — only for projects already indexed by a previous session.
{guard_open}dir=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
run="$HOME/.llm_cli/run.py"
py="${{PYTHON_BIN:-}}"
[ -n "$py" ] || {{ command -v python3 >/dev/null 2>&1 && py=python3 || py=python; }}
if command -v cygpath >/dev/null 2>&1; then dir=$(cygpath -w "$dir"); run=$(cygpath -w "$run"); fi
[ -f "$run" ] && "$py" "$run" hook git-refresh "$dir" || true
{guard_close}"""

_HOOK_NAMES = ("post-merge", "post-checkout")


def configure(subparsers) -> None:
    parser = subparsers.add_parser(
        "setup-git-hooks",
        help="install cache-refresh git hooks (repo + global template)",
    )
    parser.add_argument("project", nargs="?", default=".", help="repository path")
    parser.add_argument(
        "-u", "--remove", action="store_true", help="remove the hooks instead"
    )
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve()
    if args.remove:
        print("Removing git hooks...")
        return remove_repo_hooks(project)
    print("Installing git hooks...")
    install_global_template()
    return install_repo_hooks(project)


def hook_body(hook_name: str) -> str:
    branch_only = hook_name == "post-checkout"
    return _HOOK_BODY.format(
        guard_open='if [ "$3" = "1" ]; then\n' if branch_only else "",
        guard_close="fi\n" if branch_only else "",
    )


def install_global_template() -> None:
    """Configures a git template dir so future clone/init inherit the hooks."""
    template_hooks = paths.home() / ".git-template" / "hooks"
    for name in _HOOK_NAMES:
        _install_hook(template_hooks / name, hook_body(name))
    git.set_global_config("init.templateDir", str(template_hooks.parent))
    log.print_ok(
        f"Git template configured at {template_hooks.parent} "
        "(applies to future git clone / git init)"
    )


def install_repo_hooks(project: Path) -> int:
    hooks_dir = _repo_hooks_dir(project)
    if hooks_dir is None:
        log.print_info(f"[SKIP] No .git/hooks found at {project} — not a git repository.")
        return 1
    for name in _HOOK_NAMES:
        _install_hook(hooks_dir / name, hook_body(name))
    log.print_ok(f"Git hooks installed in {hooks_dir}")
    return 0


def remove_repo_hooks(project: Path) -> int:
    hooks_dir = _repo_hooks_dir(project)
    if hooks_dir is None:
        log.print_info(f"[SKIP] No .git/hooks found at {project} — not a git repository.")
        return 1
    for name in _HOOK_NAMES:
        hook_path = hooks_dir / name
        if not hook_path.is_file():
            continue
        text_blocks.remove_block(hook_path, BLOCK_BEGIN, BLOCK_END)
        for pattern in _LEGACY_PATTERNS:
            text_blocks.remove_pattern(hook_path, pattern)
        log.print_ok(f"Context cache hook cleaned in {hook_path}")
    return 0


def _repo_hooks_dir(project: Path) -> Path | None:
    git_directory = git.git_dir(project)
    if git_directory is None:
        return None
    return git_directory / "hooks"


def _install_hook(hook_path: Path, body: str) -> None:
    """Writes the refresh block, appending when an unrelated hook already exists
    and replacing any legacy llm_cli body outright."""
    ops = platforms.current()
    if hook_path.is_file() and _is_legacy_hook(hook_path):
        fs.write_text_atomic(hook_path, "#!/bin/sh\n")
    if not hook_path.is_file():
        fs.write_text_atomic(hook_path, "#!/bin/sh\n")
    text_blocks.upsert_block(hook_path, BLOCK_BEGIN, BLOCK_END, body)
    ops.make_executable(hook_path)


def _is_legacy_hook(hook_path: Path) -> bool:
    content = fs.read_text(hook_path)
    return any(needle in content for needle in _LEGACY_NEEDLES)
