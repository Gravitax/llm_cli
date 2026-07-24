"""Self-check for the atlassian.env -> llm_cli.env migration in paths.config_env().

The branch moves a file holding live credentials, so it gets the one test this
repository has. Run it directly: `python tests/test_paths.py`.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from llm_cli import paths  # noqa: E402

_BODY = "JIRA_URL=https://example.invalid\n"


@contextmanager
def _fake_home():
    """A throwaway home with an empty ~/.config/llm_cli."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".config" / "llm_cli").mkdir(parents=True)
        original = paths.home
        paths.home = lambda: root
        try:
            yield root / ".config" / "llm_cli"
        finally:
            paths.home = original


def test_legacy_file_is_migrated():
    with _fake_home() as directory:
        (directory / "atlassian.env").write_text(_BODY)
        result = paths.config_env()
        assert result == directory / "llm_cli.env", result
        assert result.read_text() == _BODY
        assert not (directory / "atlassian.env").exists()


def test_current_file_wins_over_legacy():
    with _fake_home() as directory:
        (directory / "atlassian.env").write_text("STALE=1\n")
        (directory / "llm_cli.env").write_text(_BODY)
        result = paths.config_env()
        assert result.read_text() == _BODY
        assert (directory / "atlassian.env").read_text() == "STALE=1\n"


def test_missing_config_creates_nothing():
    with _fake_home() as directory:
        result = paths.config_env()
        assert result == directory / "llm_cli.env", result
        assert not result.exists()
        assert list(directory.iterdir()) == []


if __name__ == "__main__":
    test_legacy_file_is_migrated()
    test_current_file_wins_over_legacy()
    test_missing_config_creates_nothing()
    print("paths.config_env migration: OK")
