"""OS divergence layer — the only place allowed to branch on the operating system.

Every method is a narrow primitive; domain logic (what to install, what to write)
stays in services/ and commands/ which call these primitives blindly.
"""

from __future__ import annotations

import abc
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


class PlatformOps(abc.ABC):
    """Narrow OS primitives; selected once via platforms.current()."""

    is_windows: bool

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
    def spawn_detached(self, argv: list[str]) -> None:
        """Starts a long-lived background process detached from this one."""

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
    def default_python_hint(self) -> str:
        """Interpreter name to show in docs and generated templates."""

    @abc.abstractmethod
    def entry_points_dir(self) -> Path:
        """Directory where `pip install --user` drops the claude/copilot
        console executables — must be on PATH for the wrappers to resolve."""
