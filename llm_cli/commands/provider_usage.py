"""provider-usage — reports the remaining quota of the active Claude provider.

Claude Code's built-in /usage only knows the Anthropic subscription: behind
ANTHROPIC_BASE_URL it reports session tokens, never what the provider has left.
Each provider exposes its own account API, so this command asks the right one.
Backs the /quota slash command shared by the three provider config homes.
"""

from __future__ import annotations

import argparse

from llm_cli.services import claude_provider, copilot_proxy, glm_api, log

_BAR_WIDTH = 20
_LABEL_COLUMN = 26
_BAR_FULL = "#"
_BAR_EMPTY = "."
_PERCENT_MAX = 100.0


def configure(subparsers) -> None:
    parser = subparsers.add_parser(
        "provider-usage", help="show the remaining quota of the active Claude provider"
    )
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    provider = claude_provider.active()
    if provider == claude_provider.COPILOT:
        return copilot_proxy.show_usage()
    if provider == claude_provider.GLM:
        return _print_glm()
    print("Provider: Anthropic — the built-in /usage command reports this plan.")
    return 0


def _print_glm() -> int:
    try:
        quota = glm_api.quota()
    except glm_api.GlmApiError as error:
        log.print_err(str(error))
        return 1
    print(f"GLM Coding Plan usage (plan: {quota.level})")
    if not quota.lines:
        log.print_warn("z.ai reported no quota window.")
        return 1
    for line in quota.lines:
        reset = f", resets {line.reset_at}" if line.reset_at else ""
        print(
            f"  {line.label:<{_LABEL_COLUMN}} {_bar(line.percent_used)} "
            f"{line.percent_used:5.1f}% used{reset}"
        )
    return 0


def _bar(percent_used: float) -> str:
    filled = round(min(max(percent_used, 0.0), _PERCENT_MAX) / _PERCENT_MAX * _BAR_WIDTH)
    return f"[{_BAR_FULL * filled}{_BAR_EMPTY * (_BAR_WIDTH - filled)}]"
