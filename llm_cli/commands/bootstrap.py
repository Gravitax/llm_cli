"""bootstrap — interactive wizard guiding a new machine/user through the full
llm_cli setup:

  1. installs any missing dependency automatically; aborts with per-dependency
     install commands when something stays missing (winget guidance on Windows)
  2. activates the optimization layer for Claude Code and/or Copilot CLI
  3. offers the one-time Atlassian + Bitbucket credentials setup + global MCP
  4. runs the diagnostics so you leave with a verified, working setup

Invoked by install.py after the package (and the `claude`/`copilot` console
entry points) are installed by pip.
"""

from __future__ import annotations

import argparse

from llm_cli import paths
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
        return 1  # The blocking banner (install commands) was already printed.
    deps.export_local_bin_path()

    # sync + PATH block are machine-global: only the first activation runs them.
    for index, tool in enumerate(selected):
        activate.run(argparse.Namespace(tool=tool, skip_global=index > 0))

    _offer_atlassian_setup()
    _offer_global_mcp()

    log.print_step("Verifying setup")
    for tool in selected:
        check.run(argparse.Namespace(tool=tool, project=None))

    log.print_step("Done")
    log.print_ok("Run 'claude' and/or 'copilot' from any project directory.")
    return 0


def _prompt_tool_selection() -> list[str]:
    log.print_step("Which agent(s) do you want to activate?")
    print("    1) Claude Code")
    print("    2) GitHub Copilot CLI")
    print("    3) Both")
    choice = input("  Choice [3]: ").strip() or "3"
    return {
        "1": ["claude"],
        "2": ["copilot"],
    }.get(choice, ["claude", "copilot"])


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
    )
