"""check — verifies that the token optimizations are correctly configured
(port of check_optimizations.sh / check_optimizations.ps1).

Checks: RTK (hook for claude, instructions for copilot), PostToolUse hooks,
headroom wrap, shell wrapper block, context cache, instructions entries, MCP.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from pathlib import Path

from llm_cli import paths, platforms, tool_profile
from llm_cli.commands import setup_shell_wrapper
from llm_cli.services import cache, fs, git, headroom, instructions, log, settings_editor
from llm_cli.services.log import Checker
from llm_cli.tool_profile import TOOL_NAMES, ToolProfile


def configure(subparsers) -> None:
    parser = subparsers.add_parser(
        "check", help="diagnose the optimization setup for a tool"
    )
    parser.add_argument("tool", nargs="?", default="claude", choices=list(TOOL_NAMES))
    parser.add_argument("project", nargs="?", help="project path (default: git root)")
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    profile = tool_profile.resolve(args.tool)
    project = Path(args.project).resolve() if args.project else git.toplevel()
    checker = Checker()
    repair = instructions.run_command_prefix()

    print(f"\nChecking {profile.name} optimizations...")
    if profile.has_rtk_hook:
        _check_rtk_binary(checker, repair)
        if shutil.which("rtk"):
            _check_rtk_hook(checker, profile, repair)
            _check_rtk_savings(checker)
    else:
        _check_rtk_instructions(checker, profile, repair)

    if profile.has_agent_hooks:
        _check_post_tool_use_hooks(checker, profile, repair)
    _check_headroom(checker, profile, repair)

    _check_shell_wrapper(checker, repair)
    _check_context_cache(checker, profile, project, repair)
    _check_instructions(checker, profile, project, repair)
    _check_global_mcp(checker, profile, repair)

    print("\n==============================")
    print(f"  Passed: {checker.passed}  Failed: {checker.failed}")
    print("==============================\n")
    return 0 if checker.failed == 0 else 1


def _check_rtk_binary(checker: Checker, repair: str) -> None:
    log.print_step("RTK dependencies")
    rtk_path = shutil.which("rtk")
    if rtk_path:
        checker.ok(f"rtk {_command_output(['rtk', '--version'])} at {rtk_path}")
    else:
        checker.fail("rtk not found in PATH")
        checker.warn(f"Fix: {repair} setup-rtk")


def _check_rtk_hook(checker: Checker, profile: ToolProfile, repair: str) -> None:
    log.print_step("RTK hook installation")
    # The hook rewrites bash commands transparently — the agent needs no RTK
    # instructions, so the hook registration is the only load-bearing check.
    hook_cmd = _find_pre_tool_use_command(profile.settings_json, "rtk")
    if hook_cmd:
        checker.ok(f"PreToolUse hook registered in settings.json: {hook_cmd}")
    else:
        checker.fail(f"RTK PreToolUse hook not found in {profile.settings_json}")
        checker.warn(f"Fix: {repair} setup-rtk")


def _check_rtk_savings(checker: Checker) -> None:
    log.print_step("RTK token savings")
    savings = _command_output(["rtk", "gain"])
    if not savings or "No tracking" in savings or "No data" in savings:
        checker.warn("No savings data yet — run a session first, then: rtk gain")
        return
    tokens_saved = _first_match(r"Tokens saved.*?([\d.]+[KM]?\s+\(\d+\.\d+%\))", savings)
    commands = _first_match(r"Total commands\D*(\d+)", savings)
    checker.ok(f"RTK savings — {commands} commands — saved {tokens_saved}")
    print("\n".join(f"       {line}" for line in savings.splitlines()))


def _check_rtk_instructions(checker: Checker, profile: ToolProfile, repair: str) -> None:
    """RTK without a hook system (copilot): the agent prefixes commands with rtk
    because its instructions tell it to — check the binary and that block."""
    log.print_step("RTK output compression (via instructions)")
    rtk_path = shutil.which("rtk")
    if rtk_path:
        checker.ok(f"rtk {_command_output(['rtk', '--version'])} at {rtk_path}")
    else:
        checker.fail("rtk not found in PATH — the agent's rtk-prefixed commands will fail")
        checker.warn(f"Fix: {repair} setup-deps {profile.name}")

    if settings_editor.contains(profile.instructions_global, "# CLI output compression (RTK)"):
        checker.ok(f"RTK usage block present in {profile.instructions_global.name}")
    else:
        checker.fail(f"RTK usage block missing from {profile.instructions_global}")
        checker.warn(f"Fix: {repair} setup-context --tool {profile.name}")


def _check_post_tool_use_hooks(checker: Checker, profile: ToolProfile, repair: str) -> None:
    log.print_step("Cache refresh hooks (PostToolUse)")
    for hook_arg in ("hook cache-refresh-git", "hook cache-refresh-write"):
        if settings_editor.contains(profile.settings_json, hook_arg):
            checker.ok(f"PostToolUse hook registered: {hook_arg}")
        else:
            checker.fail(f"PostToolUse hook missing: {hook_arg}")
            checker.warn(f"Fix: {repair} setup-env --tool {profile.name}")


def _check_headroom(checker: Checker, profile: ToolProfile, repair: str) -> None:
    log.print_step("Headroom compression proxy (optional)")
    if not headroom.is_installed():
        if headroom.is_wrapped(profile):
            checker.fail(
                "settings.json routes API calls through headroom but the binary "
                f"is missing — {profile.name} requests will fail"
            )
            checker.warn(
                f"Fix: {repair} setup-headroom --tool {profile.name} (reinstall) "
                f"or remove the wrap from {profile.settings_json}"
            )
        else:
            checker.info("headroom not installed — optional, ~15-20% extra token savings")
            checker.info(f"Enable if wanted: {profile.name} -u")
        return

    checker.ok(f"headroom present at {shutil.which('headroom')}")
    if profile.headroom_mode == "launcher":
        _check_headroom_launcher(checker, profile)
        return

    if not headroom.is_wrapped(profile):
        checker.info(f"{profile.name} not wrapped — enable with: {profile.name} -u")
        return
    checker.ok(f"{profile.name} wrapped — proxy routing active in settings.json")

    # doctor's exit code also covers unrelated tools (codex, shell env), so the
    # load-bearing check is done directly: wrapped + proxy reachability.
    if headroom.proxy_alive(profile.name):
        checker.ok(f"headroom proxy reachable on port {headroom.proxy_port(profile.name)}")
    else:
        checker.info(f"proxy not running — the shell wrapper starts it at {profile.name} launch")
        checker.info("Details anytime: headroom doctor")

    perf = headroom.perf_summary()
    if perf:
        print("\n".join(f"       {line}" for line in perf.splitlines()))


def _check_headroom_launcher(checker: Checker, profile: ToolProfile) -> None:
    """Launcher mode (copilot): routing happens inside `launch`, so the check is
    that the wrapper entry point is on PATH and credentials allow a routed launch."""
    entry_point = shutil.which(profile.name)
    entry_dir = str(platforms.current().entry_points_dir())
    if entry_point and entry_point.startswith(entry_dir):
        checker.ok(f"{profile.name} launches through headroom ({entry_point})")
    elif entry_point:
        checker.warn(
            f"{profile.name} resolves to {entry_point}, not the llm_cli entry point "
            f"in {entry_dir} — ensure that directory precedes it on PATH"
        )
    else:
        checker.fail(
            f"{profile.name} entry point not found on PATH — run `python install.py`"
        )

    if headroom.proxy_alive(profile.name):
        checker.ok(
            f"{profile.name} headroom proxy reachable on port {headroom.proxy_port(profile.name)}"
        )
    else:
        checker.info(
            f"proxy not running — `headroom wrap` starts it on port "
            f"{headroom.proxy_port(profile.name)} at {profile.name} launch"
        )

    headroom.export_ghe_env()
    mode = headroom.copilot_mode()
    if mode:
        checker.ok(f"routing credentials available (mode: {mode})")
    else:
        checker.info(
            "no ANTHROPIC_API_KEY and no Copilot OAuth — launches stay plain "
            "(compression idle)"
        )
        checker.info(f"Enable: export ANTHROPIC_API_KEY=... or {headroom.login_hint()}")


def _check_shell_wrapper(checker: Checker, repair: str) -> None:
    log.print_step("Shell wrapper")
    targets = platforms.current().shell_profile_targets()
    if not targets:
        checker.warn("No shell profile file found (skipped)")
        return
    from llm_cli.services import text_blocks

    for target in targets:
        if text_blocks.contains(target.path, setup_shell_wrapper.BLOCK_BEGIN):
            checker.ok(f"llm_cli PATH block present in {target.path}")
        else:
            checker.fail(f"llm_cli PATH block missing from {target.path}")
            checker.warn(f"Fix: {repair} setup-shell-wrapper")


def _check_context_cache(
    checker: Checker, profile: ToolProfile, project: Path, repair: str
) -> None:
    log.print_step("Context cache")
    cache_file = cache.cache_file_for(profile, project)
    checker.info(f"Project : {project}")
    checker.info(f"Cache   : {cache_file}")
    if not cache_file.is_file():
        checker.fail("No cache found")
        checker.warn(f"Fix: {repair} setup-context-cache {project} --tool {profile.name}")
        return
    content = fs.read_text(cache_file)
    generated = _first_match(r"Generated: ([^|]+)", content).strip()
    size_kb = cache_file.stat().st_size / 1024
    checker.ok(
        f"Cache exists ({content.count(chr(10))} lines, {size_kb:.0f}K, generated: {generated})"
    )


def _check_instructions(
    checker: Checker, profile: ToolProfile, project: Path, repair: str
) -> None:
    log.print_step("Instructions files")
    if profile.instructions_global.is_file():
        lines = fs.read_text(profile.instructions_global).count("\n")
        checker.ok(f"Global instructions: {profile.instructions_global} ({lines} lines)")
    else:
        checker.fail(f"{profile.instructions_global} not found")
        checker.warn(f"Fix: {repair} setup-context --tool {profile.name}")

    local_file = project / profile.instructions_local
    if settings_editor.contains(local_file, instructions.INDEX_ENTRY_MARKER):
        checker.ok(f"'{instructions.INDEX_ENTRY_MARKER}' entry present in {local_file}")
    else:
        checker.fail(f"'{instructions.INDEX_ENTRY_MARKER}' missing from {local_file}")
        checker.warn(f"Fix: {repair} setup-context-cache {project} --tool {profile.name}")


def _check_global_mcp(checker: Checker, profile: ToolProfile, repair: str) -> None:
    log.print_step("Global MCP (optional)")
    mcp_config = _mcp_config_path(profile)
    if settings_editor.contains(mcp_config, "io.github.b1ff/atlassian-dc-mcp-jira"):
        checker.ok(f"Atlassian/Bitbucket MCP registered globally ({mcp_config})")
    else:
        checker.info("MCP not registered globally — Jira/Confluence/Bitbucket tools unavailable")
        checker.info(f"Enable if needed: {repair} setup-mcp")


def _mcp_config_path(profile: ToolProfile) -> Path:
    if profile.name == "claude":
        return paths.home() / ".claude.json"
    return paths.home() / ".copilot" / "mcp-config.json"


def _find_pre_tool_use_command(settings_path: Path, needle: str) -> str:
    try:
        settings = settings_editor.load_json(settings_path)
    except ValueError:
        return ""
    for entry in settings.get("hooks", {}).get("PreToolUse", []):
        for hook in entry.get("hooks", []):
            command = hook.get("command", "")
            if needle in command:
                return command
    return ""


def _command_output(argv: list[str]) -> str:
    # Tool output is UTF-8 even when the Windows console codepage is cp1252;
    # decoding must not depend on the locale or stdout comes back None.
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
    except OSError:
        return ""
    return log.console_safe(result.stdout).strip()


def _first_match(pattern: str, text: str) -> str:
    match = re.search(pattern, text)
    return match.group(1) if match else ""
