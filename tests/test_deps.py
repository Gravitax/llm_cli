"""Self-check for DependencyInstaller.ensure_npm_deps.

A vendored tree deployed without its node_modules produces an
ERR_MODULE_NOT_FOUND at runtime, long after setup reported success, so the
skip/install branches get the one test they need.
Run it directly: `python tests/test_deps.py`.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from llm_cli.services import deps  # noqa: E402


@contextmanager
def _recorded_npm(succeeds: bool = True):
    """Captures the argv ensure_npm_deps would run instead of running it."""
    calls: list[list[str]] = []
    original = deps._run_ok
    deps._run_ok = lambda argv: (calls.append(argv), succeeds)[1]
    try:
        yield calls
    finally:
        deps._run_ok = original


def _installer() -> deps.DependencyInstaller:
    return deps.installer()


def test_installs_when_node_modules_missing():
    with TemporaryDirectory() as tmp:
        directory = Path(tmp)
        (directory / "package.json").write_text("{}\n")
        with _recorded_npm() as calls:
            assert _installer().ensure_npm_deps(directory)
        assert calls == [
            ["npm", "install", "--prefix", str(directory), "--omit=dev"]
        ], calls


def test_skips_when_node_modules_present():
    with TemporaryDirectory() as tmp:
        directory = Path(tmp)
        (directory / "package.json").write_text("{}\n")
        (directory / "node_modules").mkdir()
        with _recorded_npm() as calls:
            assert _installer().ensure_npm_deps(directory)
        assert calls == [], calls


def test_skips_the_registry_package_name():
    with _recorded_npm() as calls:
        assert _installer().ensure_npm_deps(Path("copilot-api"))
    assert calls == [], calls


def test_reports_npm_failure():
    with TemporaryDirectory() as tmp:
        directory = Path(tmp)
        (directory / "package.json").write_text("{}\n")
        with _recorded_npm(succeeds=False):
            assert not _installer().ensure_npm_deps(directory)


if __name__ == "__main__":
    test_installs_when_node_modules_missing()
    test_skips_when_node_modules_present()
    test_skips_the_registry_package_name()
    test_reports_npm_failure()
    print("deps.ensure_npm_deps: OK")
