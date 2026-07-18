"""Windows implementation of the platform primitives (PowerShell 5.1 compatible)."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import sysconfig
import winreg
from pathlib import Path

from llm_cli import paths
from llm_cli.platforms.base import (
    PlatformOps,
    ProfileTarget,
    WriteSpec,
    spawn_output_target,
)


class WindowsOps(PlatformOps):
    is_windows = True

    def shell_profile_targets(self) -> list[ProfileTarget]:
        profile = self._current_user_all_hosts_profile()
        if profile is None:
            return []
        return [ProfileTarget(profile, "powershell")]

    def profile_encoding(self) -> WriteSpec:
        # PS 5.1 parses BOM-less .ps1 as ANSI — the BOM is mandatory.
        return WriteSpec(newline="\r\n", bom=True)

    def hook_command(self, *cli_args: str) -> dict:
        command = " ".join(
            [f'"{sys.executable}"', f'"{paths.run_py()}"', *cli_args]
        )
        # "shell": "powershell" mirrors the hook entries rtk writes on Windows.
        return {"type": "command", "command": command, "shell": "powershell"}

    def spawn_detached(
        self,
        argv: list[str],
        log_path: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        # CREATE_NO_WINDOW (not DETACHED_PROCESS): the child gets an invisible
        # console its own children inherit — a .cmd shim or console subchild
        # can never pop a visible terminal window.
        flags = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        )
        output = spawn_output_target(log_path)
        try:
            subprocess.Popen(
                argv,
                stdout=output,
                stderr=output,
                stdin=subprocess.DEVNULL,
                env=env,
                creationflags=flags,
            )
        finally:
            if output is not subprocess.DEVNULL:
                output.close()

    def exec_or_run(self, argv: list[str]) -> int:
        # os.exec* on Windows detaches the console; run as a child instead and
        # let the tool own Ctrl+C (the parent ignores SIGINT until it exits).
        previous = signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            return subprocess.call(argv)
        finally:
            signal.signal(signal.SIGINT, previous)

    def make_private(self, path: Path) -> None:
        pass  # %USERPROFILE% is already user-scoped; chmod is meaningless here.

    def make_executable(self, path: Path) -> None:
        pass  # Execution is extension-based on Windows.

    def unblock(self, path: Path) -> None:
        # Dropping the Zone.Identifier alternate stream is what Unblock-File does;
        # without it RemoteSigned refuses downloaded/synced scripts.
        zone = Path(str(path) + ":Zone.Identifier")
        try:
            zone.unlink()
        except OSError:
            pass  # No stream present — nothing to unblock.

    def default_python_hint(self) -> str:
        return "python"

    def entry_points_dir(self) -> Path:
        # `pip install --user` uses the nt_user scheme for console scripts.
        scripts = sysconfig.get_path("scripts", "nt_user")
        return Path(scripts) if scripts else Path(sysconfig.get_path("scripts"))

    def configured_path_entries(self) -> list[str]:
        # Fresh-terminal PATH = HKLM system PATH + HKCU user PATH; re-reading
        # the registry sees entries winget added after this process started.
        return _registry_path_entries(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        ) + _registry_path_entries(winreg.HKEY_CURRENT_USER, "Environment")

    @staticmethod
    def _current_user_all_hosts_profile() -> Path | None:
        # $PROFILE is a PowerShell concept: only PowerShell itself can say where
        # CurrentUserAllHosts lives (OneDrive redirection, PS 5.1 vs 7 paths).
        query = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "$PROFILE.CurrentUserAllHosts"],
            capture_output=True,
            text=True,
        )
        location = query.stdout.strip()
        if query.returncode != 0 or not location:
            return None
        return Path(location)


def _registry_path_entries(root: int, subkey: str) -> list[str]:
    try:
        with winreg.OpenKey(root, subkey) as key:
            value, _kind = winreg.QueryValueEx(key, "Path")
    except OSError:
        return []  # Key/value absent or unreadable — degrade, never crash.
    # The system PATH is REG_EXPAND_SZ (%SystemRoot%...); expanding a plain
    # string is a harmless identity, so expand unconditionally before splitting.
    expanded = winreg.ExpandEnvironmentStrings(value)
    return [entry for entry in expanded.split(os.pathsep) if entry]
