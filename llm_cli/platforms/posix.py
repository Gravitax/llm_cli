"""Linux / macOS implementation of the platform primitives."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from llm_cli import paths
from llm_cli.platforms.base import (
    PlatformOps,
    ProfileTarget,
    WriteSpec,
    spawn_output_target,
)


class PosixOps(PlatformOps):
    is_windows = False

    def shell_profile_targets(self) -> list[ProfileTarget]:
        candidates = (paths.home() / ".zshrc", paths.home() / ".bashrc")
        return [ProfileTarget(p, "posix") for p in candidates if p.is_file()]

    def profile_encoding(self) -> WriteSpec:
        return WriteSpec(newline="\n", bom=False)

    def hook_command(self, *cli_args: str) -> dict:
        command = " ".join(
            [f'"{sys.executable}"', f'"{paths.run_py()}"', *cli_args]
        )
        return {"type": "command", "command": command}

    def spawn_detached(
        self,
        argv: list[str],
        log_path: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        # start_new_session detaches from this process group (replaces nohup &).
        output = spawn_output_target(log_path)
        try:
            subprocess.Popen(
                argv,
                stdout=output,
                stderr=output,
                stdin=subprocess.DEVNULL,
                env=env,
                start_new_session=True,
            )
        finally:
            if output is not subprocess.DEVNULL:
                output.close()

    def exec_or_run(self, argv: list[str]) -> int:
        # The shim's foreground process becomes the tool: signals, TTY and exit
        # code all belong to it directly.
        os.execvp(argv[0], argv)

    def make_private(self, path: Path) -> None:
        os.chmod(path, 0o600)

    def make_executable(self, path: Path) -> None:
        os.chmod(path, os.stat(path).st_mode | 0o755)

    def unblock(self, path: Path) -> None:
        pass  # No download quarantine on POSIX.

    def default_python_hint(self) -> str:
        return "python3"

    def entry_points_dir(self) -> Path:
        # `pip install --user` uses the posix_user scheme → ~/.local/bin.
        return paths.home() / ".local" / "bin"

    def configured_path_entries(self) -> list[str]:
        return []  # Login shells rebuild PATH; the inherited value is current.
