"""setup-atlassian — one-time Atlassian credentials setup (Confluence + Jira +
Bitbucket), shared by Claude Code and Copilot CLI (port of setup_atlassian.sh;
now also available on Windows).

Prompts the enterprise URLs, prompts and validates the tokens, then:
  - stores everything in ~/.config/llm_cli/atlassian.env (user-only access)
  - stores git credentials for the configured Bitbucket host
  - allows read-only git commands in Claude Code settings
  - registers the MCP servers globally (user scope), once, for both tools
"""

from __future__ import annotations

import argparse
import getpass
import shutil

from llm_cli import paths, platforms
from llm_cli.commands import setup_mcp
from llm_cli.services import atlassian_api, config, deps, fs, git, instructions, log
from llm_cli.tool_profile import ALL_PROFILES, CLAUDE

_GIT_READONLY_PERMISSIONS = (
    "Bash(git clone:*)", "Bash(git pull:*)", "Bash(git fetch:*)",
    "Bash(git checkout:*)", "Bash(git status:*)", "Bash(git log:*)",
    "Bash(git diff:*)", "Bash(git ls-remote:*)", "Bash(git branch:*)",
    "Bash(git push:*)",
)


def configure(subparsers) -> None:
    parser = subparsers.add_parser(
        "setup-atlassian", help="first-time credentials setup or token rotation"
    )
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    if not _check_prerequisites():
        return 1
    values = _prompt_urls(config.load())
    values.update(_prompt_credentials(values))

    if not _validate_tokens(values):
        log.print_err("One or more tokens are invalid. No changes made.")
        return 1

    log.print_step("Storing credentials")
    stored_at = config.store(values)
    log.print_ok(f"credentials stored in {stored_at} (user-only access).")
    _refresh_installed_instructions()

    log.print_step(f"Configuring git credentials for {values['BITBUCKET_URL']}")
    _configure_git_credentials(values)
    log.print_ok("git credentials stored in ~/.git-credentials.")

    if shutil.which("claude") or CLAUDE.home.is_dir():
        log.print_step("Configuring Claude Code git permissions")
        _configure_claude_permissions()
        log.print_ok(f"read-only git commands allowed in {CLAUDE.settings_json}.")

    log.print_step("Registering MCP servers globally (user scope)")
    setup_mcp.run(argparse.Namespace(remove=False))

    repair = instructions.run_command_prefix()
    print(
        "\nCredentials ready. Atlassian + Bitbucket MCP servers are registered"
        "\nGLOBALLY (user scope) for both Claude Code and Copilot CLI."
        f"\nTo remove the global registration later: {repair} setup-mcp -u\n"
    )
    return 0


def _check_prerequisites() -> bool:
    log.print_step("Checking prerequisites")
    installer = deps.installer()
    if not (installer.ensure_node() and installer.ensure_uv()):
        return False
    log.print_ok("Prerequisites met.")
    return True


def _prompt_value(label: str, hint: str = "", default: str = "") -> str:
    if hint:
        print(f"\n{hint}\n")
    suffix = f" [{default}]" if default else ""
    value = input(f"  {label}{suffix}: ").strip() or default
    if not value:
        raise SystemExit(f"    [ERROR] No value provided for {label}.")
    return value


def _prompt_secret(label: str, hint: str) -> str:
    """Token prompt without echo — tokens must never land on screen or in logs."""
    print(f"\n{hint}\n")
    value = getpass.getpass(f"  {label} (input hidden): ").strip()
    if not value:
        raise SystemExit(f"    [ERROR] No value provided for {label}.")
    return value


def _prompt_urls(existing: dict[str, str]) -> dict[str, str]:
    """Prompts the enterprise base URLs, pre-filled from an existing config so
    a token rotation never forces re-typing the URLs."""
    log.print_step("Enterprise service URLs")
    values = {
        "CONFLUENCE_URL": _prompt_value(
            "Confluence URL",
            "    Base URL of your Confluence instance, including any context path.\n"
            "    e.g. https://confluence.mycompany.com/c",
            existing.get("CONFLUENCE_URL", ""),
        ),
        "JIRA_URL": _prompt_value(
            "Jira URL", "    e.g. https://jira.mycompany.com/j", existing.get("JIRA_URL", "")
        ),
        "BITBUCKET_URL": _prompt_value(
            "Bitbucket URL", "    e.g. https://git.mycompany.com",
            existing.get("BITBUCKET_URL", ""),
        ),
    }
    registry = input(
        f"\n  MCP registry URL (optional, Enter to skip) [{existing.get('MCP_REGISTRY_URL', '')}]: "
    ).strip() or existing.get("MCP_REGISTRY_URL", "")
    ghe = input(
        "  GitHub Enterprise domain for Copilot (optional, e.g. mycompany.ghe.com) "
        f"[{existing.get('GITHUB_COPILOT_ENTERPRISE_DOMAIN', '')}]: "
    ).strip() or existing.get("GITHUB_COPILOT_ENTERPRISE_DOMAIN", "")
    if registry:
        values["MCP_REGISTRY_URL"] = registry
    if ghe:
        values["GITHUB_COPILOT_ENTERPRISE_DOMAIN"] = ghe
    return values


def _prompt_credentials(values: dict[str, str]) -> dict[str, str]:
    log.print_step("Account and Personal Access Tokens")
    return {
        "BITBUCKET_USERNAME": _prompt_value("Bitbucket username (your login or email)"),
        "CONFLUENCE_TOKEN": _prompt_secret(
            "Confluence token",
            f"    1. Open {values['CONFLUENCE_URL']}\n"
            "    2. Avatar (top right) > Settings\n"
            "    3. Personal Access Tokens > Create",
        ),
        "JIRA_TOKEN": _prompt_secret(
            "Jira token",
            f"    1. Open {values['JIRA_URL']}\n"
            "    2. Avatar (top right) > Profile\n"
            "    3. Personal Access Tokens > Create token",
        ),
        "BITBUCKET_TOKEN": _prompt_secret(
            "Bitbucket token",
            f"    1. Open {values['BITBUCKET_URL']}\n"
            "    2. Avatar (top right) > Manage account\n"
            "    3. HTTP access tokens > Create token",
        ),
    }


def _validate_tokens(values: dict[str, str]) -> bool:
    log.print_step("Validating tokens")
    checks = (
        ("Confluence", atlassian_api.validate_confluence,
         values["CONFLUENCE_URL"], values["CONFLUENCE_TOKEN"]),
        ("Jira", atlassian_api.validate_jira, values["JIRA_URL"], values["JIRA_TOKEN"]),
        ("Bitbucket", atlassian_api.validate_bitbucket,
         values["BITBUCKET_URL"], values["BITBUCKET_TOKEN"]),
    )
    for service, validate, url, token in checks:
        try:
            log.print_ok(f"{service}: {validate(url, token)}")
        except atlassian_api.TokenValidationError as error:
            log.print_err(f"{service}: {error}")
            return False
    return True


def _refresh_installed_instructions() -> None:
    """Regenerates the instructions so they carry the (new) Bitbucket URL."""
    for profile in ALL_PROFILES:
        if profile.home.is_dir():
            instructions.write_global_instructions(profile)


def _configure_git_credentials(values: dict[str, str]) -> None:
    host = values["BITBUCKET_URL"].replace("https://", "", 1)
    credentials_file = paths.home() / ".git-credentials"

    # Remove any existing entry for this host then append the updated one.
    lines = []
    if credentials_file.is_file():
        lines = [
            line for line in fs.read_text(credentials_file).splitlines()
            if f"@{host}" not in line
        ]
    lines.append(
        f"https://{values['BITBUCKET_USERNAME']}:{values['BITBUCKET_TOKEN']}@{host}"
    )
    fs.write_text_atomic(credentials_file, "\n".join(lines) + "\n")
    platforms.current().make_private(credentials_file)
    git.set_global_config("credential.helper", "store")


def _configure_claude_permissions() -> None:
    """Allows read-only git commands without permission prompts (Claude only)."""
    from llm_cli.services import settings_editor

    for rule in _GIT_READONLY_PERMISSIONS:
        settings_editor.ensure_permission_rule(CLAUDE.settings_json, rule)
