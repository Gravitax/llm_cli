"""GitHub Copilot routing for Claude Code through the local copilot-api proxy."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import NamedTuple

from llm_cli import paths, platforms
from llm_cli.services import (
    claude_config,
    claude_provider,
    config,
    deps,
    headroom,
    log,
    model_picker,
    vendored,
)

_PACKAGE = "copilot-api"
_BINARY = "copilot-api"
# GitHub Enterprise tenants need a copilot-api build that derives its three
# hosts from the tenant root; the registry build is github.com-only. That build
# is vendored in this package and deployed under the install root.
_ENTERPRISE_FLAG = "--enterprise-url"
_DEFAULT_PORT = 4141
_EXTRA_MODEL_KEY = "CLAUDE_COPILOT_EXTRA_MODEL"
_DISCOVERY_KEY = "CLAUDE_COPILOT_MODEL_DISCOVERY"
_DISABLED_VALUES = {"0", "false", "no", "off"}
_PROXY_LOG_NAME = "copilot-api.log"
_PROXY_START_ATTEMPTS = 20
_ACCOUNT_TYPES = {"individual", "business", "enterprise"}
_MAIN_MODEL_PREFERENCES = (
    "gpt-5.6-terra",
    "gpt-5.5",
    "claude-sonnet-5",
    "claude-sonnet-4.6",
    "gpt-4.1",
)
# Claude Code's /model picker only offers its three built-in slots, so the Opus
# one gets its own model: mapping it to the main model too would show the same
# entry twice and leave the Copilot catalog unreachable from the picker.
_OPUS_MODEL_PREFERENCES = (
    "claude-opus-4.8",
    "claude-opus-4.6",
    "claude-opus-4.1",
)
_SMALL_MODEL_PREFERENCES = (
    "gpt-5.6-luna",
    "gpt-5-mini",
    "claude-haiku-4.5",
    "gpt-4.1",
)
_PROVIDER_OVERRIDE_VARS = (
    *claude_provider.ROUTING_ENV_VARS,
    "ANTHROPIC_API_KEY",
    "CLAUDE_CONFIG_DIR",
)


class ModelSlots(NamedTuple):
    """The Copilot models bound to Claude Code's three built-in model slots."""

    main: str
    opus: str
    small: str


def is_active() -> bool:
    return claude_provider.is_active(claude_provider.COPILOT)


def toggle() -> bool:
    return claude_provider.toggle(claude_provider.COPILOT)


def prepare() -> ModelSlots | None:
    """Ensures the proxy is usable and returns the models to route to."""
    if not _ensure_installed():
        return None
    binary = shutil.which(_BINARY)
    if binary is None:
        log.print_err("copilot-api is not available on PATH after installation.")
        return None
    if not _check_enterprise_support(binary) or not _ensure_authenticated(binary):
        return None
    try:
        port = proxy_port()
        account = account_type()
    except ValueError as error:
        log.print_err(str(error))
        return None
    models = _ensure_proxy(binary, port, account)
    if not models:
        return None
    slots = _select_models(models)
    if slots is None:
        return None
    export_env(port, slots)
    return slots


def proxy_port() -> int:
    raw = config.load().get("COPILOT_API_PORT", "") or str(_DEFAULT_PORT)
    try:
        port = int(raw)
    except ValueError as error:
        raise ValueError(
            f"COPILOT_API_PORT must be an integer, got {raw!r}."
        ) from error
    if not 1 <= port <= 65535:
        raise ValueError(f"COPILOT_API_PORT must be between 1 and 65535, got {port}.")
    return port


def account_type() -> str:
    value = config.load().get("COPILOT_API_ACCOUNT_TYPE", "") or "individual"
    if value not in _ACCOUNT_TYPES:
        choices = ", ".join(sorted(_ACCOUNT_TYPES))
        raise ValueError(
            f"COPILOT_API_ACCOUNT_TYPE must be one of {choices}, got {value!r}."
        )
    return value


def export_env(port: int, slots: ModelSlots) -> None:
    """Routes Claude Code to the proxy and fills its model slots, which is what
    the in-session /model picker lists."""
    values = config.load()
    os.environ.update({
        "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{port}",
        "ANTHROPIC_AUTH_TOKEN": "dummy",
        "ANTHROPIC_MODEL": slots.main,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": slots.opus,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": slots.main,
        "ANTHROPIC_SMALL_FAST_MODEL": slots.small,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": slots.small,
        "DISABLE_NON_ESSENTIAL_MODEL_CALLS": "1",
        # The proxy answers /v1/models, so the picker can list the Claude models
        # of the subscription instead of the three slots alone.
        **model_picker.discovery_env(_discovery_enabled(values)),
        **model_picker.custom_option_env(
            values.get(_EXTRA_MODEL_KEY, ""), "Copilot"
        ),
        "CLAUDE_CONFIG_DIR": str(
            claude_config.ensure(claude_provider.COPILOT, "Copilot")
        ),
    })
    os.environ.pop("ANTHROPIC_API_KEY", None)


def _discovery_enabled(values: dict[str, str]) -> bool:
    """Discovery costs one extra request per launch and is the only way to get
    more than three entries in the picker; opt out with the config key."""
    return values.get(_DISCOVERY_KEY, "").strip().lower() not in _DISABLED_VALUES


def catalog() -> list[str]:
    """Model IDs the running proxy exposes; empty when it is not up."""
    return _list_models(proxy_port())


def show_usage() -> int:
    """Prints the Copilot quota; returns the copilot-api exit code.

    Delegated rather than reimplemented: copilot-api already holds the GitHub
    token and knows the tenant endpoint, so llm_cli never has to read it.
    """
    binary = shutil.which(_BINARY)
    if binary is None:
        log.print_err("copilot-api is not installed — run `claude -copilot` first.")
        return 1
    return subprocess.call([binary, "check-usage", *_enterprise_args()])


def with_default_model(arguments: list[str], model: str) -> list[str]:
    if any(arg == "--model" or arg.startswith("--model=") for arg in arguments):
        return arguments
    return ["--model", model, *arguments]


def _enterprise_domain() -> str:
    """Configured GitHub Enterprise tenant root, scheme and trailing slash
    stripped. Empty when Copilot is served by github.com."""
    configured = config.load().get("GITHUB_COPILOT_ENTERPRISE_DOMAIN", "")
    return configured.split("://")[-1].strip("/")


def _enterprise_args() -> list[str]:
    """The copilot-api tenant flag, or nothing on github.com."""
    domain = _enterprise_domain()
    return [_ENTERPRISE_FLAG, domain] if domain else []


def _check_enterprise_support(binary: str) -> bool:
    """Refuses the launch when the tenant flag is configured but unsupported.

    A data-residency tenant serves Copilot from its own hosts (DOMAIN,
    api.DOMAIN, copilot-api.DOMAIN) and its tokens are valid nowhere else. The
    registry build of copilot-api hardcodes the github.com equivalents, so it
    would open a github.com device flow and link a personal account instead of
    the enterprise one — a silent wrong answer, hence the hard stop.
    """
    domain = _enterprise_domain()
    if not domain or _supports_enterprise(binary):
        return True
    log.red_banner([
        f"GitHub Enterprise Copilot is configured ({domain}), but the",
        "installed copilot-api only supports github.com: its device flow",
        "would link a personal account, not the enterprise one.",
        "",
        "Install the enterprise-capable build:",
        f"  npm install -g {_enterprise_source_dir()}",
        "Other enterprise-capable routes:",
        f"  copilot login --host {domain}      # official CLI, then: copilot",
        f"  {headroom.login_hint()}",
    ])
    return False


def _supports_enterprise(binary: str) -> bool:
    """True when the installed copilot-api understands the tenant flag."""
    try:
        result = subprocess.run(
            [binary, "start", "--help"], capture_output=True, text=True
        )
    except OSError:
        return False
    return _ENTERPRISE_FLAG in result.stdout


def _enterprise_source_dir() -> Path:
    """Where the vendored build lands once deployed."""
    return vendored.target_dir(vendored.COPILOT_API)


def _ensure_installed() -> bool:
    installer = deps.installer()
    if not installer.ensure_node():
        return False
    return installer.ensure_npm_cli(_install_source(), _BINARY)


def _install_source() -> str:
    """What to hand to `npm install -g`: the vendored build, deployed next to
    the install root. It wins over the registry package on github.com too, not
    only on enterprise tenants — the registry build binds to every interface
    and serves the Copilot token unauthenticated. The registry package stays as
    a fallback for installs whose package carries no vendored tree."""
    deployed = vendored.deploy(vendored.COPILOT_API)
    if deployed is not None:
        return str(deployed)
    return _PACKAGE


def _ensure_authenticated(binary: str) -> bool:
    if _token_exists(binary):
        return True
    auth_command = " ".join([_BINARY, "auth", *_enterprise_args()])
    if not sys.stdin.isatty():
        log.red_banner([
            "GitHub Copilot authentication is required.",
            "Run this command in an interactive terminal:",
            f"  {auth_command}",
        ])
        return False
    target = _enterprise_domain() or "GitHub"
    print(f"Authenticating copilot-api with {target}...")
    result = subprocess.call([binary, "auth", *_enterprise_args()])
    if result != 0 or not _token_exists(binary):
        log.print_err("GitHub authentication failed.")
        return False
    return True


def _token_exists(binary: str) -> bool:
    try:
        result = subprocess.run(
            [binary, "debug", "--json", *_enterprise_args()],
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    if result.returncode != 0:
        return False
    try:
        return bool(json.loads(result.stdout).get("tokenExists"))
    except (json.JSONDecodeError, AttributeError):
        return False


def _ensure_proxy(binary: str, port: int, account: str) -> list[str]:
    models = _list_models(port)
    if models:
        return models
    if _endpoint_alive(port):
        log.print_err(
            f"Port {port} is already used by a service that is not a ready "
            "copilot-api proxy."
        )
        log.print_err("Set COPILOT_API_PORT in the llm_cli config to another port.")
        return []

    log_file = paths.logs_dir() / _PROXY_LOG_NAME
    print(f"Starting copilot-api proxy (logs: {log_file})...")
    platforms.current().spawn_detached(
        [
            binary,
            "start",
            "--port",
            str(port),
            "--account-type",
            account,
            "--proxy-env",
            *_enterprise_args(),
        ],
        log_path=log_file,
        env=_proxy_env(),
    )
    for _ in range(_PROXY_START_ATTEMPTS):
        time.sleep(1)
        models = _list_models(port)
        if models:
            return models
    log.print_err("copilot-api failed to start or expose the Copilot model catalog.")
    log.print_err(f"Details in {log_file}")
    log.print_err(
        "Re-authenticate with: " + " ".join([_BINARY, "auth", *_enterprise_args()])
    )
    return []


def _proxy_env() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if key not in _PROVIDER_OVERRIDE_VARS
    }


def _endpoint_alive(port: int) -> bool:
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1)
        return True
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, OSError):
        return False


def _list_models(port: int) -> list[str]:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/v1/models", timeout=2
        ) as response:
            payload = json.load(response)
    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        OSError,
        ValueError,
    ):
        return []
    data = payload.get("data", []) if isinstance(payload, dict) else []
    return [
        item["id"]
        for item in data
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    ]


def _select_models(models: list[str]) -> ModelSlots | None:
    values = config.load()
    main = _select_model(
        "CLAUDE_COPILOT_MODEL",
        values.get("CLAUDE_COPILOT_MODEL", ""),
        models,
        _MAIN_MODEL_PREFERENCES,
        models[0],
    )
    if main is None:
        return None
    opus = _select_model(
        "CLAUDE_COPILOT_OPUS_MODEL",
        values.get("CLAUDE_COPILOT_OPUS_MODEL", ""),
        models,
        _OPUS_MODEL_PREFERENCES,
        main,
    )
    small = _select_model(
        "CLAUDE_COPILOT_SMALL_MODEL",
        values.get("CLAUDE_COPILOT_SMALL_MODEL", ""),
        models,
        _SMALL_MODEL_PREFERENCES,
        main,
    )
    if opus is None or small is None:
        return None
    return ModelSlots(main=main, opus=opus, small=small)


def _select_model(
    key: str,
    configured: str,
    models: list[str],
    preferences: tuple[str, ...],
    fallback: str,
) -> str | None:
    if configured:
        if configured in models:
            return configured
        log.print_err(f"{key}={configured} is not available from GitHub Copilot.")
        log.print_err(f"Available models: {', '.join(models)}")
        return None
    return next((model for model in preferences if model in models), fallback)
