"""Single source of truth for every filesystem location llm_cli reads or writes."""

from pathlib import Path


def home() -> Path:
    """User home — one indirection so tests can monkeypatch a single spot."""
    return Path.home()


def install_root() -> Path:
    """Installed copy of the package + run.py, shared by both tools' hooks."""
    return home() / ".llm_cli"


def run_py() -> Path:
    """Installed launcher script — the stable path registered in hooks and profiles."""
    return install_root() / "run.py"


def config_dir() -> Path:
    """User configuration (Atlassian credentials, GHE domain...)."""
    return home() / ".config" / "llm_cli"


def atlassian_env() -> Path:
    return config_dir() / "atlassian.env"


def package_root() -> Path:
    """Directory containing the `llm_cli` package (repo checkout or install root)."""
    return Path(__file__).resolve().parent.parent
