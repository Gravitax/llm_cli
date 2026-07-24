"""setup-rtk — installs RTK and configures the Claude Code PreToolUse hook
(port of setup_rtk.sh / setup_rtk.ps1).

RTK intercepts bash commands (git, ls, tests...) and compresses output before
it reaches the LLM context (~70-80% token savings on CLI output).
"""

from __future__ import annotations

import argparse
import subprocess

from llm_cli import platforms
from llm_cli.services import deps, fs, log, proc, settings_editor, text_blocks
from llm_cli.tool_profile import CLAUDE

_PATH_EXPORT_LINE = 'export PATH="$HOME/.local/bin:$PATH"'
# `rtk init` rewrites settings.json and, depending on the build, may ask before
# overwriting an existing hook entry. A prompt nobody can see would freeze the
# whole wizard on this step, so the call gets a hard deadline and the direct
# registration below takes over when it expires.
_INIT_TIMEOUT_SECONDS = 30


def configure(subparsers) -> None:
    parser = subparsers.add_parser(
        "setup-rtk", help="install RTK and its Claude PreToolUse hook (-u to remove)"
    )
    parser.add_argument(
        "-u", "--remove", action="store_true", help="remove the hook instead"
    )
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    if args.remove:
        return _remove_hook()
    return _install()


def _install() -> int:
    print("Setting up RTK output compression...")
    installer = deps.installer()
    if not installer.ensure_rtk():
        return 1
    _ensure_local_bin_in_profile()
    deps.export_local_bin_path()

    _rtk_init()
    if not _hook_registered():
        # Fallback: write the hook entry ourselves, mirroring rtk's own shape.
        _register_hook_directly()
    print("RTK ready. Restart Claude Code to activate the hook.")
    print("Check savings after a session with: rtk gain")
    return 0


def _remove_hook() -> int:
    print("Removing RTK hook...")
    deps.export_local_bin_path()
    rtk = _rtk_binary()
    if rtk:
        _run_indented([rtk, "init", "-g", "--uninstall"])
    else:
        log.print_warn("rtk not found in PATH, skipping uninstall.")
    print("RTK hook removed. Restart Claude Code to apply.")
    return 0


def _rtk_binary() -> str | None:
    import shutil

    if platforms.current().is_windows:
        return deps.WindowsDepInstaller.rtk_executable()
    return shutil.which("rtk")


def _rtk_init() -> None:
    """Best-effort: lets rtk register its own hook. Never load-bearing — the
    caller checks the result and registers the entry itself when this did
    nothing, so a missing, failing or hanging rtk only costs the deadline."""
    rtk = _rtk_binary()
    if rtk is None:
        return
    # --auto-patch lets rtk adjust its own hook entry format across versions;
    # unsupported on the Windows build, where plain init is used.
    argv = [rtk, "init", "-g"]
    if not platforms.current().is_windows:
        argv.append("--auto-patch")
    print(f"    Running rtk init (up to {_INIT_TIMEOUT_SECONDS}s)...")
    _run_indented(argv)


def _hook_registered() -> bool:
    return settings_editor.contains(CLAUDE.settings_json, f"hook {CLAUDE.name}")


def _register_hook_directly() -> None:
    rtk = _rtk_binary()
    if rtk is None:
        return
    entry = {"type": "command", "command": f'"{rtk}" hook {CLAUDE.name}'}
    if platforms.current().is_windows:
        entry["shell"] = "powershell"
    settings_editor.register_hook(CLAUDE.settings_json, "PreToolUse", "Bash", entry)
    log.print_ok("RTK PreToolUse hook registered directly in settings.json.")


def _ensure_local_bin_in_profile() -> None:
    """Persists ~/.local/bin on PATH in the first available POSIX profile."""
    if platforms.current().is_windows:
        return  # rtk.exe placement is manual on Windows; PATH guidance covers it.
    from llm_cli import paths

    profiles = [paths.home() / name for name in (".bashrc", ".zshrc", ".profile")]
    if any(text_blocks.contains(p, ".local/bin") for p in profiles):
        return
    for profile in profiles:
        if profile.is_file():
            fs.write_text_atomic(
                profile, fs.read_text(profile) + f"{_PATH_EXPORT_LINE}\n"
            )
            log.print_ok(f"PATH updated in {profile}")
            return


def _run_indented(argv: list[str]) -> None:
    """Echoes an rtk call indented under the current step, and degrades every
    failure to a warning: rtk is an optional compression layer, so nothing it
    does may block the install."""
    try:
        result = proc.run_captured(argv, timeout=_INIT_TIMEOUT_SECONDS)
    except OSError as error:
        log.print_warn(f"could not run {' '.join(argv)}: {error}")
        return
    except subprocess.TimeoutExpired:
        log.print_warn(
            f"rtk did not answer within {_INIT_TIMEOUT_SECONDS}s — "
            "registering the hook directly instead."
        )
        return
    for line in result.stdout.splitlines():
        print(f"    {log.console_safe(line)}")
