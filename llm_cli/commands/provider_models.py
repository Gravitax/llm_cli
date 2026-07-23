"""provider-models — lists the models the active Claude provider serves.

Claude Code's /model picker only ever shows its own slots plus whatever gateway
discovery could add, so it is never the full catalog on a third-party provider.
This command answers the other half: which ids `claude --model <id>` accepts.
Backs the /models slash command shared by the three provider config homes.
"""

from __future__ import annotations

import argparse

from llm_cli.services import (
    anthropic_catalog,
    claude_provider,
    copilot_proxy,
    glm_api,
    log,
)

_ID_COLUMN = 28


def configure(subparsers) -> None:
    parser = subparsers.add_parser(
        "provider-models", help="list the models the active Claude provider serves"
    )
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    provider = claude_provider.active()
    if provider == claude_provider.COPILOT:
        return _print_copilot()
    if provider == claude_provider.GLM:
        return _print_glm()
    return _print_anthropic()


def _print_copilot() -> int:
    models = copilot_proxy.catalog()
    if not models:
        log.print_err("The copilot-api proxy is not running or exposes no catalog.")
        log.print_err("Start a Copilot session first: claude -copilot")
        return 1
    _print_catalog("GitHub Copilot", [(model, "") for model in models])
    return 0


def _print_glm() -> int:
    try:
        models = glm_api.list_models()
    except glm_api.GlmApiError as error:
        log.print_err(str(error))
        return 1
    if not models:
        log.print_warn("z.ai returned no models.")
        return 1
    _print_catalog("GLM (z.ai)", models)
    return 0


def _print_anthropic() -> int:
    """The real catalog when a key is around, the aliases otherwise — a
    subscription login has no key and cannot enumerate models."""
    if not anthropic_catalog.has_api_key():
        print(f"Anthropic aliases ({len(anthropic_catalog.ALIASES)}):")
        for alias, description in anthropic_catalog.ALIASES:
            print(f"  {alias:<{_ID_COLUMN}} {description}")
        print()
        print("On a claude.ai subscription these aliases are the catalog;")
        print("/model resolves them to the current model versions.")
        return 0
    try:
        models = anthropic_catalog.list_models()
    except anthropic_catalog.AnthropicApiError as error:
        log.print_err(str(error))
        return 1
    _print_catalog("Anthropic", models)
    return 0


def _print_catalog(label: str, models: list[tuple[str, str]]) -> None:
    print(f"{label} models ({len(models)}):")
    for model_id, name in models:
        print(f"  {model_id:<{_ID_COLUMN}} {name}".rstrip())
    print()
    print("Use one for a session:  claude --model <id>")
    print("The /model picker only lists the slots and the discovered entries.")
