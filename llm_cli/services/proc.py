"""proc — captured subprocess calls whose timeout actually fires.

Setup runs unattended inside a wizard: any external CLI it shells out to must
either finish or die on a deadline, because a blocked child freezes the whole
install with no output and no way back. `subprocess.run(capture_output=True,
timeout=N)` does not give that guarantee on Windows, so every captured call in
the layer goes through `run_captured` instead.
"""

from __future__ import annotations

import subprocess
import tempfile

# Deliberately short: a CLI stuck on an invisible prompt (marketplace trust, git
# credentials, an "overwrite?" confirmation) must fail fast and let the setup
# move on. Every step guarded by this helper is an optimization layer, so a
# missed one is a warning, never a broken install.
DEFAULT_TIMEOUT_SECONDS = 30


def run_captured(
    argv: list[str],
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    *,
    merge_stderr: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Captured, non-interactive CLI call whose timeout actually fires.

    Output goes to a temporary file rather than an OS pipe. On Windows a child
    that spawns its own children keeps the pipe's write end open, so the pipe
    drain subprocess.run performs on timeout blocks forever and the timeout
    never takes effect — the freeze seen on both the plugin and the RTK step. A
    plain file has no such back-pressure, so the child can be killed and
    TimeoutExpired raised on schedule.

    stdin is closed so a CLI that asks for confirmation fails fast instead of
    waiting on a prompt nobody can see.

    stderr is folded into stdout by default, since callers that echo a step's
    output want the diagnostics too. Pass merge_stderr=False for value probes
    (`npm config get prefix`) where a warning line would corrupt the result;
    stderr is then discarded rather than piped, keeping the no-pipe guarantee.

    Raises subprocess.TimeoutExpired on deadline and OSError when the binary
    cannot be launched — both are the caller's to degrade into a warning.
    """
    with tempfile.TemporaryFile() as sink:
        try:
            completed = subprocess.run(
                argv,
                stdout=sink,
                stderr=subprocess.STDOUT if merge_stderr else subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                timeout=timeout,
            )
        finally:
            sink.seek(0)
            output = sink.read().decode("utf-8", "replace")
    return subprocess.CompletedProcess(argv, completed.returncode, output, "")
