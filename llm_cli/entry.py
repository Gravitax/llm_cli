"""Console entry points for the `claude` and `copilot` wrapper commands.

Installed by pip as executables on the PATH (a real binary on Windows, an
executable script on Unix — no shell shim needed). Each forwards to the tested
`launch` command, which runs the pre-launch steps then hands the foreground to
the real tool. Replaces the retired claude()/copilot() shell functions.
"""

from __future__ import annotations

import sys

from llm_cli.cli import main
from llm_cli.services.crash_guard import guarded_main


def claude_main() -> int:
    return guarded_main(lambda: main(["launch", "claude", "--", *sys.argv[1:]]))


def copilot_main() -> int:
    return guarded_main(lambda: main(["launch", "copilot", "--", *sys.argv[1:]]))
