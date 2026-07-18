"""YAML-backed text templates.

Every text body llm_cli writes into user-facing files (CLAUDE.md,
copilot-instructions.md, AGENTS.md entries, ignore files) lives in
llm_cli/templates/*.yaml — the wording is data, editable without touching code.
"""

from __future__ import annotations

import functools
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


@functools.lru_cache(maxsize=None)
def load(name: str) -> dict:
    """Parses llm_cli/templates/<name>.yaml into a dict (cached per process)."""
    try:
        import yaml
    except ImportError as error:  # pragma: no cover — dependency of the package.
        raise RuntimeError(
            "PyYAML is required to load the llm_cli templates — "
            "install it with: pip install --user pyyaml"
        ) from error
    template_file = TEMPLATES_DIR / f"{name}.yaml"
    if not template_file.is_file():
        raise FileNotFoundError(f"template file missing: {template_file}")
    data = yaml.safe_load(template_file.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{template_file} must contain a YAML mapping at top level")
    return data


def text(name: str, key: str) -> str:
    """One text block out of <name>.yaml; fails loudly on a missing key."""
    data = load(name)
    if key not in data:
        raise KeyError(f"{TEMPLATES_DIR / (name + '.yaml')}: missing key '{key}'")
    return data[key]
