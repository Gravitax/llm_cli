"""Headroom proxy helpers (port of lib_headroom.sh / lib_headroom.ps1).

Shared by setup-headroom, check, prelaunch and launch. Behavior contract:
headroom is an optimization — every failure degrades to a visible warning,
never to a blocked tool launch.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request

from llm_cli import platforms
from llm_cli.services import config, fs, log
from llm_cli.tool_profile import ToolProfile

# Default port of `headroom proxy`. Override with: export HEADROOM_PROXY_PORT=8787
DEFAULT_PROXY_PORT = 8787
_PROXY_START_ATTEMPTS = 5
_WRAP_PATTERN = re.compile(r"headroom|ANTHROPIC_BASE_URL.*(localhost|127\.0\.0\.1)")


def proxy_port() -> int:
    return int(os.environ.get("HEADROOM_PROXY_PORT", DEFAULT_PROXY_PORT))


def is_installed() -> bool:
    return shutil.which("headroom") is not None


def export_ghe_env() -> None:
    """Exports the GitHub Enterprise Copilot domain from the llm_cli config, so
    the headroom auth module targets the enterprise instance instead of
    github.com. No-op when not configured."""
    domain = config.load().get("GITHUB_COPILOT_ENTERPRISE_DOMAIN", "")
    if domain:
        os.environ["GITHUB_COPILOT_ENTERPRISE_DOMAIN"] = domain


def login_hint() -> str:
    """The copilot OAuth login command, with --domain when GHE is configured."""
    domain = os.environ.get(
        "GITHUB_COPILOT_ENTERPRISE_DOMAIN",
        config.load().get("GITHUB_COPILOT_ENTERPRISE_DOMAIN", ""),
    )
    if domain:
        return f"headroom copilot-auth login --domain {domain}"
    return "headroom copilot-auth login"


def print_login_warning() -> None:
    """Highly visible banner shown whenever compression would stay idle for
    lack of credentials."""
    log.red_banner([
        "Headroom compression is IDLE — no credentials. Connect it with:",
        f"  {login_hint()}",
        "then verify with: headroom copilot-auth status",
    ])


def is_wrapped(profile: ToolProfile) -> bool:
    """True when the tool settings durably route API calls through the proxy."""
    settings = profile.settings_json
    if not settings.is_file():
        return False
    return bool(_WRAP_PATTERN.search(fs.read_text(settings)))


def proxy_alive() -> bool:
    """True when the local proxy answers on its port (any HTTP response counts)."""
    url = f"http://127.0.0.1:{proxy_port()}/"
    try:
        urllib.request.urlopen(url, timeout=1)
        return True
    except urllib.error.HTTPError:
        return True  # An HTTP error still proves something is listening.
    except (urllib.error.URLError, OSError):
        return False


def copilot_mode() -> str | None:
    """How headroom can route copilot: "byok" needs a provider key in the
    environment; otherwise a saved Copilot OAuth token enables "subscription".
    None when neither is available."""
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("COPILOT_PROVIDER_API_KEY"):
        return "byok"
    status = _auth_status()
    if "not logged in" in status:
        return None
    if "logged in" in status:
        return "subscription"
    return None


def ensure_proxy(profile: ToolProfile) -> None:
    """Starts the proxy if the tool is wrapped and the proxy is down.
    Never blocks the tool launch: a wrapped tool with a dead proxy cannot
    reach the API at all, so failures degrade to a visible warning."""
    if not is_installed() or not is_wrapped(profile):
        return
    # The shared proxy also serves copilot: it must carry the GHE routing
    # config whichever tool starts it.
    export_ghe_env()
    if proxy_alive():
        return

    print("Starting headroom proxy...")
    platforms.current().spawn_detached(["headroom", "proxy"])
    for _ in range(_PROXY_START_ATTEMPTS):
        time.sleep(1)
        if proxy_alive():
            return
    log.print_warn(
        f"headroom proxy failed to start — {profile.name} API calls may fail."
    )
    log.print_warn(f"Disable the wrap with: headroom unwrap {profile.name}")


# Copilot BYOK routing refuses to start without an explicit --model, so a
# default is injected at launch when the caller passed none. It is only a boot
# model: switch freely in-session with copilot's `/model` command. Override the
# default with COPILOT_DEFAULT_MODEL in the llm_cli config.
_DEFAULT_COPILOT_MODEL = "claude-sonnet-5"


def default_copilot_model() -> str:
    return config.load().get("COPILOT_DEFAULT_MODEL", "") or _DEFAULT_COPILOT_MODEL


def _with_default_model(arguments: list[str]) -> list[str]:
    """Prepends `--model <default>` unless the caller already set a model."""
    if any(arg == "--model" or arg.startswith("--model=") for arg in arguments):
        return arguments
    return ["--model", default_copilot_model(), *arguments]


def launch_argv(tool: str, binary: str, arguments: list[str]) -> list[str]:
    """Launcher-mode argv (copilot): routes through headroom when credentials
    allow it, plain launch otherwise. Opt out with LLM_CLI_NO_HEADROOM=1.

    `headroom wrap <tool>` takes the tool's Click subcommand name (headroom
    re-resolves and launches the tool itself); the plain fallback uses `binary`,
    the resolved real executable, to bypass our own same-named entry point."""
    if os.environ.get("LLM_CLI_NO_HEADROOM") or not is_installed():
        return [binary, *arguments]

    export_ghe_env()
    mode = copilot_mode()
    if mode is None:
        print_login_warning()
        return [binary, *arguments]
    headroom_bin = shutil.which("headroom") or "headroom"
    forwarded = _with_default_model(arguments)
    if mode == "subscription":
        return [headroom_bin, "wrap", tool, "--subscription", "--", *forwarded]
    return [headroom_bin, "wrap", tool, "--", *forwarded]


def perf_summary(max_lines: int = 5) -> str:
    """First lines of `headroom perf` for diagnostics ('' when unavailable)."""
    result = subprocess.run(["headroom", "perf"], capture_output=True, text=True)
    if result.returncode != 0:
        return ""
    return "\n".join(result.stdout.splitlines()[:max_lines])


def _auth_status() -> str:
    try:
        result = subprocess.run(
            ["headroom", "copilot-auth", "status"], capture_output=True, text=True
        )
    except OSError:
        return ""
    return result.stdout + result.stderr
