"""Single source of truth for every filesystem location llm_cli reads or writes."""

from contextlib import suppress
from pathlib import Path


def home() -> Path:
    """User home — one indirection so tests can monkeypatch a single spot."""
    return Path.home()


def install_root() -> Path:
    """Installed copy of the package + run.py, shared by both tools' hooks."""
    return home() / ".llm_cli"


def venv_dir() -> Path:
    """Managed virtualenv hosting the package and its console entry points."""
    return install_root() / ".venv"


def run_py() -> Path:
    """Installed launcher script — the stable path registered in hooks and profiles."""
    return install_root() / "run.py"


def logs_dir() -> Path:
    """Persistent log files (headroom proxy output, crash reports)."""
    return install_root() / "logs"


def config_dir() -> Path:
    """User configuration (Atlassian credentials, GHE domain...)."""
    return home() / ".config" / "llm_cli"


def config_env() -> Path:
    """The one file holding every llm_cli setting — Atlassian credentials, but
    also the provider choice and the Copilot/GLM model keys. It was named
    `atlassian.env` back when it only held the former; existing installs are
    migrated on first access, since the rename must not lose their tokens.
    """
    # ponytail: one-shot rename, drop it once no install predates llm_cli.env.
    current = config_dir() / "llm_cli.env"
    legacy = config_dir() / "atlassian.env"
    if legacy.is_file() and not current.is_file():
        with suppress(OSError):
            legacy.rename(current)
    return current


def package_root() -> Path:
    """Directory containing the `llm_cli` package (repo checkout or install root)."""
    return Path(__file__).resolve().parent.parent
