"""What Claude Code's /model picker can be made to show on a third-party provider.

The picker is not a live list of the provider's catalog: Claude Code fills it
from its own model slots (`opus`, `sonnet`, `haiku`, ...), each remapped by an
`ANTHROPIC_DEFAULT_*_MODEL` variable. Two documented mechanisms widen it:

  * gateway discovery — with CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1 the
    CLI calls `GET /v1/models` on ANTHROPIC_BASE_URL at startup and adds the
    entries it gets back, but it drops every id that does not start with
    `claude` or `anthropic`. Useful for the Copilot proxy, useless for z.ai;
  * ANTHROPIC_CUSTOM_MODEL_OPTION — exactly one extra entry, any id, no
    validation. This is the only way to reach a non-Claude model from the
    picker, hence one config key per provider to choose which one it is.

Anything beyond those is reachable with `--model <id>` at launch only.
"""

from __future__ import annotations

DISCOVERY_VAR = "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY"
# Claude Code hides discovered models when nonessential traffic is off, so the
# two settings are mutually exclusive and discovery has to win when enabled.
NONESSENTIAL_TRAFFIC_VAR = "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"
_CUSTOM_OPTION_VAR = "ANTHROPIC_CUSTOM_MODEL_OPTION"
_ENABLED = "1"


def discovery_env(enabled: bool) -> dict[str, str]:
    """Startup catalog discovery against the provider's own /v1/models."""
    if not enabled:
        return {NONESSENTIAL_TRAFFIC_VAR: _ENABLED}
    return {DISCOVERY_VAR: _ENABLED}


def custom_option_env(model_id: str, label: str) -> dict[str, str]:
    """The single free-form picker entry, or nothing when unconfigured."""
    model_id = model_id.strip()
    if not model_id:
        return {}
    return {
        _CUSTOM_OPTION_VAR: model_id,
        f"{_CUSTOM_OPTION_VAR}_NAME": f"{model_id} ({label})",
        f"{_CUSTOM_OPTION_VAR}_DESCRIPTION": (
            f"Extra {label} model, selected through llm_cli"
        ),
    }
