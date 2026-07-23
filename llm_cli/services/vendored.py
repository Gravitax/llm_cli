"""Deployment of the third-party trees shipped inside the package.

copilot-api is vendored rather than pulled from npm: the registry build is
github.com-only, it binds to every interface and its unauthenticated /token
route answers with the live Copilot bearer. The patched copy under vendor/ is
what makes the Copilot provider usable, so a clone of this repository has to
carry it — hence a deploy step instead of an `npm install copilot-api`.

The bundle in dist/ is committed on purpose: deploying it as-is means the
target machine needs node and npm, but no Node build toolchain.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from llm_cli import paths

COPILOT_API = "copilot-api"
_VENDOR_DIR = "vendor"
_BUNDLE = Path("dist") / "main.js"


def source_dir(name: str = COPILOT_API) -> Path:
    """The vendored tree inside the installed package."""
    return Path(__file__).resolve().parent.parent / _VENDOR_DIR / name


def target_dir(name: str = COPILOT_API) -> Path:
    """Where the tree is deployed, and where npm installs it from."""
    return paths.install_root() / name


def deploy(name: str = COPILOT_API) -> Path | None:
    """Copies the vendored tree next to the install root; returns its path, or
    None when the package carries no such tree.

    Merged rather than replaced: the deployed copy grows a node_modules of a
    few hundred megabytes that must survive an upgrade.
    """
    source = source_dir(name)
    if not source.is_dir():
        return None
    target = target_dir(name)
    if _is_current(source, target):
        return target
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, dirs_exist_ok=True)
    return target


def _is_current(source: Path, target: Path) -> bool:
    """True when the deployed bundle is at least as recent as the vendored one.

    Comparing the bundle alone is enough: it is the only file npm installs, and
    it is regenerated whenever the sources change.
    """
    deployed = target / _BUNDLE
    if not deployed.is_file():
        return False
    try:
        return deployed.stat().st_mtime >= (source / _BUNDLE).stat().st_mtime
    except OSError:
        return False
