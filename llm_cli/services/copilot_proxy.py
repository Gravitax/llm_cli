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

from llm_cli import paths, platforms
from llm_cli.services import (
    claude_config,
    claude_provider,
    config,
    deps,
    log,
)

_PACKAGE = "copilot-api"
_BINARY = "copilot-api"
_DEFAULT_PORT = 4141
_PROXY_LOG_NAME = "copilot-api.log"
_PROXY_START_ATTEMPTS = 20
_ACCOUNT_TYPES = {"individual", "business", "enterprise"}
_MAIN_MODEL_PREFERENCES = (
    "claude-sonnet-5",
    "claude-opus-4.1",
    "gpt-5",
    "claude-sonnet-4",
    "gpt-4.1",
)
_SMALL_MODEL_PREFERENCES = (
    "gpt-5-mini",
    "claude-haiku-4.5",
    "claude-3.5-haiku",
    "gpt-4.1",
)
_PROVIDER_OVERRIDE_VARS = (
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_SMALL_FAST_MODEL",
    "CLAUDE_CONFIG_DIR",
)


def is_active() -> bool:
    return claude_provider.is_active(claude_provider.COPILOT)


def toggle() -> bool:
    return claude_provider.toggle(claude_provider.COPILOT)


def prepare() -> tuple[str, str] | None:
    """Ensures the proxy is usable and returns its main and small model IDs."""
    if not _ensure_installed() or not _ensure_authenticated():
        return None
    try:
        port = proxy_port()
        account = account_type()
    except ValueError as error:
        log.print_err(str(error))
        return None
    models = _ensure_proxy(port, account)
    if not models:
        return None
    selected = _select_models(models)
    if selected is None:
        return None
    main_model, small_model = selected
    export_env(port, main_model, small_model)
    return selected


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


def export_env(port: int, main_model: str, small_model: str) -> None:
    os.environ.update({
        "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{port}",
        "ANTHROPIC_AUTH_TOKEN": "dummy",
        "ANTHROPIC_MODEL": main_model,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": main_model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": main_model,
        "ANTHROPIC_SMALL_FAST_MODEL": small_model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": small_model,
        "DISABLE_NON_ESSENTIAL_MODEL_CALLS": "1",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "CLAUDE_CONFIG_DIR": str(
            claude_config.ensure(claude_provider.COPILOT, "Copilot")
        ),
    })
    os.environ.pop("ANTHROPIC_API_KEY", None)


def with_default_model(arguments: list[str], model: str) -> list[str]:
    if any(arg == "--model" or arg.startswith("--model=") for arg in arguments):
        return arguments
    return ["--model", model, *arguments]


def _ensure_installed() -> bool:
    installer = deps.installer()
    if not installer.ensure_node():
        return False
    return installer.ensure_npm_cli(_PACKAGE, _BINARY)


def _ensure_authenticated() -> bool:
    binary = shutil.which(_BINARY)
    if binary is None:
        log.print_err("copilot-api is not available on PATH after installation.")
        return False
    if _token_exists(binary):
        return True
    if not sys.stdin.isatty():
        log.red_banner([
            "GitHub Copilot authentication is required.",
            "Run this command in an interactive terminal:",
            "  copilot-api auth",
        ])
        return False
    print("Authenticating copilot-api with GitHub...")
    result = subprocess.call([binary, "auth"])
    if result != 0 or not _token_exists(binary):
        log.print_err("GitHub authentication failed.")
        return False
    return True


def _token_exists(binary: str) -> bool:
    try:
        result = subprocess.run(
            [binary, "debug", "--json"],
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


def _ensure_proxy(port: int, account: str) -> list[str]:
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

    binary = shutil.which(_BINARY)
    if binary is None:
        log.print_err("copilot-api is not available on PATH.")
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
    log.print_err("Re-authenticate with: copilot-api auth")
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


def _select_models(models: list[str]) -> tuple[str, str] | None:
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
    small = _select_model(
        "CLAUDE_COPILOT_SMALL_MODEL",
        values.get("CLAUDE_COPILOT_SMALL_MODEL", ""),
        models,
        _SMALL_MODEL_PREFERENCES,
        main,
    )
    return (main, small) if small is not None else None


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
