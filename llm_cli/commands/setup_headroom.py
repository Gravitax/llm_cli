"""setup-headroom — installs Headroom and durably wraps the tool so its API
calls go through the local proxy (port of setup_headroom.sh / setup_headroom.ps1).

~15-20% token savings on coding agents, 60-95% on JSON-heavy tool output.
Stacks on top of RTK and the context cache — they optimize different layers.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess

from llm_cli import tool_profile
from llm_cli.services import deps, headroom, instructions, log, settings_editor
from llm_cli.tool_profile import TOOL_NAMES, ToolProfile


def configure(subparsers) -> None:
    parser = subparsers.add_parser(
        "setup-headroom",
        help="install + wrap the tool with the headroom proxy (-u to unwrap)",
    )
    parser.add_argument("--tool", required=True, choices=list(TOOL_NAMES))
    parser.add_argument(
        "--ensure", action="store_true",
        help="non-interactive repair: skip silently when headroom is not installed",
    )
    parser.add_argument(
        "-u", "--remove", action="store_true", help="unwrap the tool instead"
    )
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    profile = tool_profile.resolve(args.tool)
    if args.remove:
        return _remove_wrap(profile)
    if args.ensure and not headroom.is_installed():
        repair = instructions.run_command_prefix()
        log.print_info(
            f"[SKIP] headroom not installed — enable with: {repair} setup-headroom --tool {profile.name}"
        )
        return 0
    if not deps.installer().ensure_headroom():
        return 1
    if profile.headroom_mode == "launcher":
        return _report_launcher_mode(profile)
    if _apply_wrap(profile) != 0:
        return 1
    return _verify_wrap(profile)


def _report_launcher_mode(profile: ToolProfile) -> int:
    """Launcher mode (copilot): no durable settings routing exists — the launch
    itself goes through `headroom wrap` inside the `launch` command."""
    log.print_ok(f"{profile.name} routes through headroom at launch (llm_cli launch).")
    headroom.export_ghe_env()
    if headroom.copilot_mode() is None:
        headroom.print_login_warning()
    log.print_info(f"Opt out per session with: LLM_CLI_NO_HEADROOM=1 {profile.name}")
    return 0


def _apply_wrap(profile: ToolProfile) -> int:
    if headroom.is_wrapped(profile):
        log.print_ok(f"{profile.name} already wrapped.")
        return 0

    log.print_step(f"Wrapping {profile.name} with the headroom proxy")
    # Durable part 1 — `headroom wrap` registers the retrieve/compression MCP
    # servers and context tools. It also launches a session of the tool;
    # `-- --version` makes that child session exit immediately.
    result = subprocess.run(
        ["headroom", "wrap", profile.name, "--", "--version"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        log.print_err(f"headroom wrap {profile.name} failed: {result.stdout}{result.stderr}")
        return 1
    # Durable part 2 — proxy routing in settings.json (what `headroom doctor`
    # checks as "routed"); wrap alone only exports it transiently.
    _write_proxy_routing(profile, add=True)
    if not headroom.is_wrapped(profile):
        log.print_err(
            f"wrap ran but {profile.settings_json} shows no proxy routing."
        )
        return 1
    log.print_ok(f"{profile.name} wrapped — durable proxy routing in {profile.settings_json}.")
    return 0


def _verify_wrap(profile: ToolProfile) -> int:
    log.print_step("Verifying headroom health")
    headroom.ensure_proxy(profile)
    if not headroom.proxy_alive():
        repair = instructions.run_command_prefix()
        log.print_err(
            f"headroom proxy is not reachable — {profile.name} cannot call the API while wrapped."
        )
        log.print_err(f"Unwrap with: {repair} setup-headroom --tool {profile.name} -u")
        return 1
    # Doctor output is diagnostic: unrelated warnings (other tools, shell env)
    # must not fail the setup; the load-bearing checks above already did.
    # Codex rows are filtered out — doctor probes every tool it can wrap, and
    # the OpenAI Codex CLI is not part of this layer.
    doctor = subprocess.run(["headroom", "doctor"], capture_output=True, text=True)
    for line in (doctor.stdout + doctor.stderr).splitlines():
        if "codex" not in line.lower():
            print(f"    {line}")
    log.print_ok(f"headroom proxy reachable and {profile.name} routed.")
    return 0


def _remove_wrap(profile: ToolProfile) -> int:
    if not shutil.which("headroom"):
        log.print_err("headroom not installed — nothing to unwrap.")
        return 1
    if subprocess.run(["headroom", "unwrap", profile.name]).returncode != 0:
        log.print_err(f"headroom unwrap {profile.name} failed.")
        return 1
    if profile.headroom_mode == "settings":
        _write_proxy_routing(profile, add=False)
    log.print_ok(f"{profile.name} unwrapped — API calls go directly to the provider again.")
    return 0


def _write_proxy_routing(profile: ToolProfile, *, add: bool) -> None:
    """Writes or removes the durable proxy routing (env.ANTHROPIC_BASE_URL) in
    the tool settings — `headroom wrap` only sets it transiently."""
    settings = settings_editor.load_json(profile.settings_json)
    if add:
        env = settings.setdefault("env", {})
        env["ANTHROPIC_BASE_URL"] = f"http://127.0.0.1:{headroom.proxy_port()}"
    elif "env" in settings:
        settings["env"].pop("ANTHROPIC_BASE_URL", None)
    settings_editor.save_json(profile.settings_json, settings)
