"""bootstrap — interactive wizard guiding a new machine/user through the full
llm_cli setup:

  1. installs any missing dependency automatically (no prompts)
  2. activates the optimization layer for Claude Code, Copilot CLI and/or OpenCode
  3. offers the one-time Atlassian + Bitbucket credentials setup + global MCP
  4. runs the diagnostics so you leave with a verified, working setup

Invoked by install.py after the package (and the `claude`/`copilot`/`opencode`
console entry points) are installed by pip.
"""

from __future__ import annotations

import argparse

from llm_cli import paths, tool_profile
from llm_cli.commands import activate, check, setup_atlassian, setup_deps, setup_mcp
from llm_cli.services import deps, log, settings_editor
from llm_cli.commands.setup_mcp import SERVER_JIRA


def configure(subparsers) -> None:
    parser = subparsers.add_parser("bootstrap", help="interactive first-time setup wizard")
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    log.print_step("llm_cli setup wizard")
    log.print_info(f"Root: {paths.package_root()}")

    selected = _prompt_tool_selection()
    if setup_deps.run(argparse.Namespace(tools=selected)) != 0:
        log.print_err(
            "Some dependencies could not be installed — the related steps may fail below."
        )
    deps.export_local_bin_path()

    for tool in selected:
        activate.run(argparse.Namespace(tool=tool))

    _offer_atlassian_setup()
    _offer_global_mcp()

    log.print_step("Verifying setup")
    for profile in tool_profile.ALL_PROFILES:
        if profile.home.is_dir():
            check.run(argparse.Namespace(tool=profile.name, project=None))

    log.print_step("Done")
    log.print_ok("Run 'claude', 'copilot' and/or 'opencode' from any project directory.")
    return 0


def _prompt_tool_selection() -> list[str]:
    log.print_step("Which agent(s) do you want to activate?")
    print("    1) Claude Code")
    print("    2) GitHub Copilot CLI")
    print("    3) OpenCode")
    print("    4) All three")
    choice = input("  Choice [4]: ").strip() or "4"
    return {
        "1": ["claude"],
        "2": ["copilot"],
        "3": ["opencode"],
    }.get(choice, ["claude", "copilot", "opencode"])


def _ask_yes_no(prompt: str, default: str = "n") -> bool:
    hint = "Y/n" if default == "y" else "y/N"
    reply = input(f"{prompt} [{hint}] ").strip() or default
    return reply.lower().startswith("y")


def _offer_atlassian_setup() -> None:
    log.print_step("Atlassian + Bitbucket credentials")
    credentials_file = paths.atlassian_env()
    if credentials_file.is_file():
        log.print_ok(f"credentials already configured ({credentials_file}).")
        if not _ask_yes_no("  Rotate/reconfigure tokens now?"):
            return
    else:
        log.print_info("No credentials found — needed for Jira/Confluence/Bitbucket MCP tools.")
        if not _ask_yes_no("  Configure them now?", default="y"):
            return
    if setup_atlassian.run(argparse.Namespace()) != 0:
        log.print_err("Atlassian setup failed.")


def _offer_global_mcp() -> None:
    log.print_step("Global MCP registration (user scope)")
    if not paths.atlassian_env().is_file():
        log.print_info("No credentials yet — configure them first (step above) to enable MCP.")
        return
    if _mcp_already_registered():
        log.print_ok("Atlassian/Bitbucket MCP already registered globally.")
        return
    log.print_info("Atlassian/Bitbucket MCP not yet registered globally.")
    if _ask_yes_no("  Register now (active in every session for this user)?", default="y"):
        if setup_mcp.run(argparse.Namespace(remove=False)) != 0:
            log.print_err("Global MCP setup failed.")
    else:
        from llm_cli.services import instructions

        log.print_info("Skipped — enable later with:")
        log.print_info(f"  {instructions.run_command_prefix()} setup-mcp")


def _mcp_already_registered() -> bool:
    return settings_editor.contains(
        paths.home() / ".claude.json", SERVER_JIRA
    ) or settings_editor.contains(
        paths.home() / ".copilot" / "mcp-config.json", SERVER_JIRA
    ) or settings_editor.contains(
        paths.home() / ".config" / "opencode" / "opencode.json", SERVER_JIRA
    )
