"""Dependency installers (port of lib_deps.sh + the setup_dependencies.ps1 /
setup_prerequisites.ps1 install helpers).

Every ensure_* is idempotent: already present -> silent success; missing ->
automatic install where the platform allows it; impossible -> loud error
(False return, never swallowed). Windows policy: npm and pip installs are
scripted, everything else (git, node, python, rtk) is winget GUIDANCE ONLY —
in particular rtk is NEVER auto-installed on Windows (no Unix curl|sh there).
"""

from __future__ import annotations

import abc
import os
import shutil
import subprocess
import re

from llm_cli import paths, platforms
from llm_cli.services import log

MIN_NODE_MAJOR = 20


def local_bin() -> str:
    return str(paths.home() / ".local" / "bin")


def export_local_bin_path() -> None:
    """Installers drop binaries in ~/.local/bin; make them visible now."""
    _prepend_path(local_bin())


def export_configured_path() -> None:
    """Merges freshly configured PATH entries (Windows registry) into the live
    PATH so binaries installed mid-session are found without a new terminal."""
    current = os.environ.get("PATH", "")
    known = {_canonical(entry) for entry in current.split(os.pathsep) if entry}
    fresh: list[str] = []
    for entry in platforms.current().configured_path_entries():
        if _canonical(entry) not in known:
            known.add(_canonical(entry))
            fresh.append(entry)
    if fresh:
        # Appended, not prepended: deliberate in-process prepends (~/.local/bin,
        # npm prefix) and system32 must keep precedence over registry entries.
        os.environ["PATH"] = os.pathsep.join([current, *fresh] if current else fresh)


def _canonical(entry: str) -> str:
    return os.path.normcase(entry.rstrip("\\/"))


def export_npm_bin_path() -> None:
    """Puts npm's global bin dir on PATH for the current process."""
    prefix = _command_stdout(["npm", "config", "get", "prefix"])
    if not prefix:
        return
    # npm's global binaries live in <prefix>/bin on POSIX, <prefix> on Windows.
    suffix = "" if platforms.current().is_windows else "bin"
    _prepend_path(os.path.join(prefix, suffix) if suffix else prefix)


def node_major_version() -> int:
    match = re.match(r"v(\d+)", _command_stdout(["node", "--version"]))
    return int(match.group(1)) if match else 0


class DependencyInstaller(abc.ABC):
    """Platform strategy for obtaining the layer's runtime dependencies."""

    @abc.abstractmethod
    def ensure_system_tool(self, binary: str, package: str) -> bool:
        """git, curl... via the system package manager."""

    @abc.abstractmethod
    def ensure_node(self) -> bool:
        """Node.js >= 20 — required by the claude/copilot CLIs and MCP servers."""

    @abc.abstractmethod
    def ensure_uv(self) -> bool:
        """uv — package runner used by the MCP servers and the headroom install."""

    @abc.abstractmethod
    def ensure_rtk(self) -> bool:
        """RTK (CLI output compression) — shared by claude and copilot."""

    @abc.abstractmethod
    def ensure_headroom(self) -> bool:
        """Headroom (context-compression proxy)."""

    def ensure_npm_cli(self, package: str, binary: str) -> bool:
        """Installs a global npm CLI when its binary is missing."""
        export_npm_bin_path()
        if shutil.which(binary):
            return True
        log.print_info(f"Installing {package} via npm...")
        if not _run_ok(["npm", "install", "-g", package]):
            log.print_err(f"npm install -g {package} failed.")
            return False
        if not shutil.which(binary):
            log.print_err(
                f"{binary} not found after install — check `npm config get prefix` in PATH."
            )
            return False
        log.print_ok(f"{binary} installed.")
        return True


class PosixDepInstaller(DependencyInstaller):
    def ensure_system_tool(self, binary: str, package: str) -> bool:
        if shutil.which(binary):
            return True
        log.print_info(f"Installing {package}...")
        if shutil.which("apt-get"):
            installed = _run_ok(["sudo", "apt-get", "install", "-y", package])
        elif shutil.which("brew"):
            installed = _run_ok(["brew", "install", package])
        else:
            log.print_err(f"No package manager found — install {package} manually.")
            return False
        if not installed or not shutil.which(binary):
            log.print_err(f"{package} installation failed.")
            return False
        log.print_ok(f"{package} installed.")
        return True

    def ensure_node(self) -> bool:
        if node_major_version() >= MIN_NODE_MAJOR:
            return True
        log.print_info(f"Installing Node.js {MIN_NODE_MAJOR} (requires sudo)...")
        if not shutil.which("apt-get"):
            log.print_err(
                f"Cannot install Node.js automatically — install Node >= {MIN_NODE_MAJOR} manually."
            )
            return False
        setup_ok = _run_shell(
            f"curl -fsSL https://deb.nodesource.com/setup_{MIN_NODE_MAJOR}.x | sudo -E bash -"
        ) and _run_ok(["sudo", "apt-get", "install", "-y", "nodejs"])
        if not setup_ok or node_major_version() < MIN_NODE_MAJOR:
            log.print_err("Node.js installation failed.")
            return False
        log.print_ok("Node.js installed.")
        return True

    def ensure_uv(self) -> bool:
        if shutil.which("uv"):
            return True
        log.print_info("Installing uv...")
        _run_shell("curl -LsSf https://astral.sh/uv/install.sh | sh > /dev/null 2>&1")
        export_local_bin_path()
        if not shutil.which("uv"):
            log.print_err("uv installation failed. Install manually: https://docs.astral.sh/uv/")
            return False
        log.print_ok("uv installed.")
        return True

    def ensure_rtk(self) -> bool:
        if shutil.which("rtk"):
            return True
        log.print_info("Installing RTK...")
        if not _run_shell(
            "curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh"
        ):
            log.print_err("RTK installation failed.")
            return False
        export_local_bin_path()
        if not shutil.which("rtk"):
            log.print_err(f"RTK binary not found after install. Add {local_bin()} to PATH.")
            return False
        log.print_ok("RTK installed.")
        return True

    def ensure_headroom(self) -> bool:
        if shutil.which("headroom"):
            return True
        log.print_info("Installing headroom-ai (large: ML dependencies)...")
        if shutil.which("uv"):
            installed = _run_ok(["uv", "tool", "install", "headroom-ai[all]"])
        elif shutil.which("pip3"):
            installed = _run_ok(_pip_install_argv("pip3"))
        else:
            log.print_err("Neither uv nor pip3 found — cannot install headroom.")
            return False
        export_local_bin_path()
        if not installed or not shutil.which("headroom"):
            log.print_err("headroom missing from PATH after install.")
            return False
        log.print_ok("headroom installed.")
        return True


class WindowsDepInstaller(DependencyInstaller):
    """Scripted npm/pip installs only; binaries come with winget guidance."""

    def ensure_system_tool(self, binary: str, package: str) -> bool:
        if shutil.which(binary):
            return True
        log.print_err(f"{binary} not found — install it with: winget install {package}")
        return False

    def ensure_node(self) -> bool:
        if node_major_version() >= MIN_NODE_MAJOR:
            return True
        log.print_err(
            f"Node.js >= {MIN_NODE_MAJOR} not found — install it with: "
            "winget install OpenJS.NodeJS.LTS"
        )
        return False

    def ensure_uv(self) -> bool:
        if shutil.which("uv"):
            return True
        log.print_err("uv not found — install it with: winget install astral-sh.uv")
        return False

    def ensure_rtk(self) -> bool:
        if shutil.which("rtk") or self.rtk_executable():
            return True
        log.print_err(
            "rtk.exe not found. Install the Windows build from "
            "https://github.com/rtk-ai/rtk/releases into "
            f"{local_bin()} and add that directory to PATH."
        )
        return False

    def ensure_headroom(self) -> bool:
        # pip --user drops headroom.exe in the nt_user scripts dir, which the
        # shell profile block only adds to NEW terminals — export it now so
        # this process (and its child steps) can see the binary.
        _prepend_path(str(platforms.current().entry_points_dir()))
        if shutil.which("headroom"):
            return True
        log.print_info("Installing headroom-ai (large: ML dependencies)...")
        if not _run_ok(_pip_install_argv("pip")):
            log.print_err("pip install headroom-ai failed.")
            return False
        if not shutil.which("headroom"):
            log.print_err("headroom missing from PATH after install.")
            return False
        log.print_ok("headroom installed.")
        return True

    @staticmethod
    def rtk_executable() -> str | None:
        """rtk on PATH, or its default install location before PATH is set."""
        on_path = shutil.which("rtk")
        if on_path:
            return on_path
        default = paths.home() / ".local" / "bin" / "rtk.exe"
        return str(default) if default.is_file() else None


def _pip_install_argv(pip_binary: str) -> list[str]:
    """headroom pulls litellm, whose newest sdists compile Rust extensions —
    --prefer-binary keeps pip on wheel-only releases instead of a toolchain."""
    return [pip_binary, "install", "--user", "--prefer-binary", "headroom-ai[all]"]


def installer() -> DependencyInstaller:
    if platforms.current().is_windows:
        return WindowsDepInstaller()
    return PosixDepInstaller()


def _prepend_path(entry: str) -> None:
    current_path = os.environ.get("PATH", "")
    if entry not in current_path.split(os.pathsep):
        os.environ["PATH"] = entry + os.pathsep + current_path


def _resolve_binary(argv: list[str]) -> list[str] | None:
    """Resolves argv[0] through PATH, or None when absent. Windows CLIs like
    npm are .cmd shims that CreateProcess cannot launch from a bare name —
    subprocess needs the full resolved path, extension included."""
    binary = shutil.which(argv[0])
    if not binary:
        return None
    return [binary, *argv[1:]]


def _command_stdout(argv: list[str]) -> str:
    """Runs a command and returns its stripped stdout; '' when the binary is
    missing or cannot be launched — probes must degrade, never crash setup."""
    resolved = _resolve_binary(argv)
    if not resolved:
        return ""
    try:
        result = subprocess.run(resolved, capture_output=True, text=True)
    except OSError:
        return ""
    return result.stdout.strip()


def _run_ok(argv: list[str]) -> bool:
    resolved = _resolve_binary(argv)
    if not resolved:
        return False
    try:
        return subprocess.run(resolved).returncode == 0
    except OSError:
        return False


def _run_shell(command: str) -> bool:
    return subprocess.run(command, shell=True).returncode == 0
