"""copilot-models — prints the model catalog of the (enterprise) Copilot API.

Backs the `copilot --models` wrapper flag: under the headroom wrap the copilot
CLI cannot list models in-session, so users need the valid `--model` names.
"""

from __future__ import annotations

import argparse

from llm_cli import paths
from llm_cli.services import copilot_catalog, log


def configure(subparsers) -> None:
    parser = subparsers.add_parser(
        "copilot-models", help="list the models the Copilot API offers"
    )
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    try:
        models = copilot_catalog.list_models()
    except copilot_catalog.CatalogError as error:
        log.print_err(str(error))
        return 1
    if not models:
        log.print_warn("The Copilot API returned no picker-enabled models.")
        return 1
    print("Copilot models (picker-enabled):")
    for model_id, name in models:
        print(f"  {model_id:<28} {name}")
    print()
    print("Use one at launch:  copilot --model <id>")
    print(f"Set the default:    COPILOT_DEFAULT_MODEL=<id> in {paths.config_env()}")
    return 0
