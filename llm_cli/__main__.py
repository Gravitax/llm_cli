"""Module entry point: python3 -m llm_cli <command>."""

import sys

from llm_cli.cli import main
from llm_cli.services.crash_guard import guarded_main

sys.exit(guarded_main(main))
