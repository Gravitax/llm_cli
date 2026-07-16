"""Platform selection — the single os check of the codebase lives here."""

import os
from typing import Optional

from llm_cli.platforms.base import PlatformOps, ProfileTarget, WriteSpec  # noqa: F401

_current: Optional[PlatformOps] = None


def current() -> PlatformOps:
    """Returns the process-wide PlatformOps singleton."""
    global _current
    if _current is None:
        _current = _detect()
    return _current


def _detect() -> PlatformOps:
    if os.name == "nt":
        from llm_cli.platforms.windows import WindowsOps

        return WindowsOps()
    from llm_cli.platforms.posix import PosixOps

    return PosixOps()
