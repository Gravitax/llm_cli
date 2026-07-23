"""setup-shell-wrapper — ensures the pip-installed `claude`/`copilot` console
entry points are on PATH in every new shell.

The activation block only prepends the entry-point directory to PATH; all wrapper
logic lives in the Python core (the `claude`/`copilot` executables installed by
pip). Logic updates ship via `pip install` and never require a profile rewrite.
Legacy per-tool wrapper blocks and the old `functions.*` source line are removed
on sight.
"""

from __future__ import annotations

import argparse
import re

from llm_cli import platforms
from llm_cli.platforms.base import ProfileTarget
from llm_cli.services import log, text_blocks

BLOCK_BEGIN = "# >>> llm_cli >>>"
BLOCK_END = "# <<< llm_cli <<<"

_LEGACY_TOOLS = ("claude", "copilot")


def configure(subparsers) -> None:
    parser = subparsers.add_parser(
        "setup-shell-wrapper",
        help="ensure the llm_cli entry points are on PATH in new shells",
    )
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    targets = platforms.current().shell_profile_targets()
    if not targets:
        log.print_warn("No shell profile found — PATH entry not persisted.")
        return 1
    for target in targets:
        _remove_legacy_wrappers(target)
        _write_block(target)
        log.print_ok(
            f"llm_cli PATH block ready in {target.path} (takes effect in new terminals)"
        )
    return 0


def _posix_body() -> str:
    bin_dir = str(platforms.current().entry_points_dir())
    return f'export PATH="{bin_dir}:$PATH"'


def _powershell_body() -> str:
    scripts_dir = str(platforms.current().entry_points_dir())
    return (
        f"$llmCliBin = '{scripts_dir}'\n"
        "if ($env:PATH -notlike \"*$llmCliBin*\") "
        "{ $env:PATH = \"$llmCliBin;$env:PATH\" }"
    )


def _write_block(target: ProfileTarget) -> None:
    encoding = platforms.current().profile_encoding()
    body = _powershell_body() if target.kind == "powershell" else _posix_body()
    text_blocks.upsert_block(
        target.path, BLOCK_BEGIN, BLOCK_END, body,
        newline=encoding.newline, bom=encoding.bom,
    )


def _remove_legacy_wrappers(target: ProfileTarget) -> None:
    """Drops the per-tool wrapper blocks and the retired functions.* source
    line written by the removed bash/PS shims."""
    _remove_legacy_functions_source(target)
    for tool in _LEGACY_TOOLS:
        if target.kind == "powershell":
            removed = text_blocks.remove_block(
                target.path,
                f"# >>> {tool} context-cache wrapper (llm_cli) >>>",
                f"# <<< {tool} context-cache wrapper (llm_cli) <<<",
            )
        else:
            marker = f"# {tool} context-cache wrapper"
            pattern = re.compile(
                r"\n?" + re.escape(marker) + r"\n" + re.escape(tool) + r"\(\).*?\n\}",
                re.DOTALL,
            )
            removed = text_blocks.remove_pattern(target.path, pattern)
        if removed:
            log.print_ok(f"Outdated {tool} wrapper removed from {target.path}")


def _remove_legacy_functions_source(target: ProfileTarget) -> None:
    """Removes the `source .../shims/functions.*` line from older installs."""
    if target.kind == "powershell":
        pattern = re.compile(r"\n?[^\n]*\.llm_cli[\\/]shims[\\/]functions\.ps1[^\n]*\n")
    else:
        pattern = re.compile(r"\n?[^\n]*\.llm_cli/shims/functions\.sh[^\n]*\n")
    if text_blocks.remove_pattern(target.path, pattern):
        log.print_ok(f"Retired functions shim source removed from {target.path}")
