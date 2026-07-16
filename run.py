#!/usr/bin/env python3
"""llm_cli launcher — works from the repo checkout and from ~/.llm_cli alike.

Registered by absolute path in hooks and shell shims, so no PYTHONPATH games
are needed whatever interpreter (python3 / python / py -3) invokes it.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from llm_cli.cli import main  # noqa: E402 — needs the sys.path insert above.

sys.exit(main())
