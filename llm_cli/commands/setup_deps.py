"""setup-deps — installs every missing runtime dependency of the layer
(port of setup_dependencies.sh / setup_dependencies.ps1).

Fully automatic (no prompts) — called by bootstrap before tool activation.
Every dependency still gets its chance to install; anything left missing is
then reported in one blocking banner with the exact install command per
dependency, and the non-zero exit aborts the wizard.
"""

from __future__ import annotations

import argparse

from llm_cli.services import copilot_proxy, deps, log, vendored
from llm_cli.tool_profile import TOOL_NAMES

# Same recovery command on every platform: the proxy is vendored, not fetched
# from the registry, and its bundle needs its dependencies alongside it.
_COPILOT_API_DIR = vendored.target_dir(vendored.COPILOT_API)
_COPILOT_API_HINT = (
    f"npm install -g {_COPILOT_API_DIR} "
    f"&& npm install --prefix {_COPILOT_API_DIR} --omit=dev"
)

_TOOL_PACKAGES = {
    "claude": ("@anthropic-ai/claude-code", "claude"),
    "copilot": ("@github/copilot", "copilot"),
}

# Extra per-tool dependencies that are not a plain global npm package.
_TOOL_EXTRAS = {
    "claude": [("copilot-api", copilot_proxy.ensure_installed)],
}

_WINDOWS_INSTALL_HINTS = {
    "curl": "winget install cURL.cURL",
    "git": "winget install Git.Git",
    "node": "winget install OpenJS.NodeJS.LTS",
    "uv": "winget install astral-sh.uv",
    "rtk": (
        "download rtk.exe from https://github.com/rtk-ai/rtk/releases "
        "into %USERPROFILE%\\.local\\bin"
    ),
    "headroom": 'pip install --user --prefer-binary "headroom-ai[all]"',
    "claude": "npm install -g @anthropic-ai/claude-code",
    "copilot": "npm install -g @github/copilot",
    "copilot-api": _COPILOT_API_HINT,
}

_POSIX_INSTALL_HINTS = {
    "curl": "sudo apt-get install -y curl  (or: brew install curl)",
    "git": "sudo apt-get install -y git  (or: brew install git)",
    "node": f"install Node.js >= {deps.MIN_NODE_MAJOR} from https://nodejs.org",
    "uv": "curl -LsSf https://astral.sh/uv/install.sh | sh",
    "rtk": (
        "curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/"
        "refs/heads/master/install.sh | sh"
    ),
    "headroom": 'uv tool install "headroom-ai[all]"',
    "claude": "npm install -g @anthropic-ai/claude-code",
    "copilot": "npm install -g @github/copilot",
    "copilot-api": _COPILOT_API_HINT,
}


def configure(subparsers) -> None:
    parser = subparsers.add_parser(
        "setup-deps", help="install every missing runtime dependency"
    )
    parser.add_argument(
        "tools", nargs="*", choices=list(TOOL_NAMES),
        help="agent CLIs to install on top of the shared dependencies",
    )
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    log.print_step("Checking & installing dependencies")
    # Binaries installed since this terminal opened (winget writes PATH to the
    # registry only) would otherwise be invisible to every probe below.
    deps.export_configured_path()
    installer = deps.installer()

    steps = [
        ("curl", lambda: installer.ensure_system_tool("curl", "curl")),
        ("git", lambda: installer.ensure_system_tool(
            "git", "Git.Git" if _is_windows() else "git"
        )),
        ("node", installer.ensure_node),
        ("uv", installer.ensure_uv),
        ("rtk", installer.ensure_rtk),
        ("headroom", installer.ensure_headroom),
    ]
    for tool in args.tools:
        package, binary = _TOOL_PACKAGES[tool]
        steps.append(
            (binary, lambda pkg=package, exe=binary: installer.ensure_npm_cli(pkg, exe))
        )
        steps += _TOOL_EXTRAS.get(tool, [])

    missing = [name for name, step in steps if not step()]
    if missing:
        _print_missing_banner(missing)
        return 1
    log.print_ok("All dependencies present.")
    return 0


def _print_missing_banner(missing: list[str]) -> None:
    hints = _WINDOWS_INSTALL_HINTS if _is_windows() else _POSIX_INSTALL_HINTS
    lines = ["MISSING DEPENDENCIES — setup cannot continue.", ""]
    lines += [f"  {name}: {hints[name]}" for name in missing]
    lines += ["", "Install them, open a NEW terminal, then re-run: python install.py"]
    log.red_banner(lines)


def _is_windows() -> bool:
    from llm_cli import platforms

    return platforms.current().is_windows
