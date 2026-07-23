"""OS divergence layer — the only place allowed to branch on the operating system.

Every method is a narrow primitive; domain logic (what to install, what to write)
stays in services/ and commands/ which call these primitives blindly.
"""

from __future__ import annotations

import abc
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProfileTarget:
    """A shell profile file llm_cli may write its activation block into."""

    path: Path
    kind: str  # "posix" | "powershell"


@dataclass(frozen=True)
class WriteSpec:
    """Encoding contract for files parsed by the platform shell."""

    newline: str
    bom: bool


def spawn_output_target(log_path: Path | None):
    """stdout/stderr target for spawn_detached: an append handle on the log
    file when given (creating its directory), DEVNULL otherwise. Callers close
    the handle after Popen — the child keeps its inherited copy."""
    if log_path is None:
        return subprocess.DEVNULL
    log_path.parent.mkdir(parents=True, exist_ok=True)
    return open(log_path, "ab")


class PlatformOps(abc.ABC):
    """Narrow OS primitives; selected once via platforms.current()."""

    is_windows: bool
    python_exe_name: str  # File name of the interpreter inside the managed venv.

    def venv_python(self) -> Path:
        """Managed venv interpreter — the one docs and generated templates must
        use, since the package and its dependencies live only in that venv."""
        return self.entry_points_dir() / self.python_exe_name

    @abc.abstractmethod
    def shell_profile_targets(self) -> list[ProfileTarget]:
        """Profile files to receive the activation block (existing files only)."""

    @abc.abstractmethod
    def profile_encoding(self) -> WriteSpec:
        """How profile files must be encoded (PS 5.1 needs BOM + CRLF)."""

    @abc.abstractmethod
    def hook_command(self, *cli_args: str) -> dict:
        """settings.json hook entry invoking `run.py <cli_args>` with an
        absolute interpreter path (immune to PATH and Store-alias issues)."""

    @abc.abstractmethod
    def spawn_detached(
        self,
        argv: list[str],
        log_path: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        """Starts a long-lived background process detached from this one.
        Its output is appended to log_path when given, discarded otherwise."""

    @abc.abstractmethod
    def exec_or_run(self, argv: list[str]) -> int:
        """Hands the foreground over to an interactive tool; returns its exit
        code on platforms where the process cannot be replaced."""

    @abc.abstractmethod
    def make_private(self, path: Path) -> None:
        """Restricts a credentials file to the current user."""

    @abc.abstractmethod
    def make_executable(self, path: Path) -> None:
        """Marks a script as executable (no-op where irrelevant)."""

    @abc.abstractmethod
    def unblock(self, path: Path) -> None:
        """Clears download quarantine metadata (Zone.Identifier on Windows)."""

    @abc.abstractmethod
    def entry_points_dir(self) -> Path:
        """Directory where the managed venv drops the claude/copilot console
        executables — must be on PATH for the wrappers to resolve."""

    @abc.abstractmethod
    def configured_path_entries(self) -> list[str]:
        """PATH entries a brand-new terminal would see (machine + user registry
        PATH on Windows); [] where the inherited PATH is already authoritative."""
