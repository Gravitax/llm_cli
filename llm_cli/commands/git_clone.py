"""git-clone — clones a Bitbucket Server repository from the configured host,
using the credentials stored in ~/.git-credentials by setup-atlassian
(port of git_clone.sh; now also available on Windows).
"""

from __future__ import annotations

import argparse
import subprocess

from llm_cli import paths
from llm_cli.services import config, fs, log


def configure(subparsers) -> None:
    parser = subparsers.add_parser(
        "git-clone", help="clone <PROJECT>/<repo> from the configured Bitbucket host"
    )
    parser.add_argument("repo", metavar="PROJECT/repo", help="e.g. PL/myservice")
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    try:
        settings = config.require()
    except config.ConfigMissingError as error:
        log.print_err(str(error))
        return 1

    bitbucket_url = settings["BITBUCKET_URL"]
    host = bitbucket_url.replace("https://", "", 1)
    credential = _find_credential(host)
    if credential is None:
        log.print_err(
            f"No credentials for {host} in ~/.git-credentials — run setup-atlassian first."
        )
        return 1

    username, token = credential
    # Inline helper keeps the token out of the remote URL stored in .git/config.
    helper = f"!f() {{ echo username={username}; echo password={token}; }}; f"
    result = subprocess.run(
        ["git", "-c", f"credential.helper={helper}",
         "clone", f"{bitbucket_url}/scm/{args.repo}.git"]
    )
    return result.returncode


def _find_credential(host: str) -> tuple[str, str] | None:
    """First https://user:token@host entry matching the configured host."""
    credentials_file = paths.home() / ".git-credentials"
    if not credentials_file.is_file():
        return None
    for line in fs.read_text(credentials_file).splitlines():
        if f"@{host}" not in line:
            continue
        account = line.replace("https://", "", 1).split("@", 1)[0]
        username, _, token = account.partition(":")
        if username and token:
            return username, token
    return None
