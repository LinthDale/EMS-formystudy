"""Ops helper: generate an argon2id PHC hash for BFF_AUTH_USERS.

The hash embeds salt + cost params, so the output drops straight into the env
var record ``username:<phc>:role``. The plaintext password is NEVER printed,
logged, or persisted — only the PHC string is emitted.

Usage (password read interactively, not echoed — preferred for ops):
    python -m bff.hashpw

Usage (username + role, prints a ready-to-paste record):
    python -m bff.hashpw --user ops_user --role ops

Reading the password from a pipe (e.g. CI / scripted provisioning):
    printf '%s' "$PW" | python -m bff.hashpw --stdin --user ops_user --role ops

Then assemble (comma-separated) into:
    BFF_AUTH_USERS="ops_user:<phc>:ops,ing_user:<phc>:ingest"
"""
from __future__ import annotations

import argparse
import getpass
import sys

from argon2 import PasswordHasher

from .credentials import _USERNAME_RE
from .roles import Role


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        # read first line without the trailing newline; never echoed
        pw = sys.stdin.readline().rstrip("\n")
    else:
        pw = getpass.getpass("password: ")
        confirm = getpass.getpass("confirm : ")
        if pw != confirm:
            raise SystemExit("error: passwords did not match")
    if not pw:
        raise SystemExit("error: empty password")
    return pw


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m bff.hashpw",
        description="Generate an argon2id PHC hash for a BFF_AUTH_USERS record.",
    )
    parser.add_argument("--user", help="username; prints a full env record when given")
    parser.add_argument(
        "--role",
        choices=[r.value for r in Role],
        help="role for the printed record (required with --user)",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="read the password from stdin instead of an interactive prompt",
    )
    args = parser.parse_args(argv)

    if args.user is not None:
        if not _USERNAME_RE.fullmatch(args.user):
            raise SystemExit(f"error: invalid username {args.user!r}")
        if args.role is None:
            raise SystemExit("error: --role is required when --user is given")

    password = _read_password(args.stdin)
    phc = PasswordHasher().hash(password)
    del password  # drop the plaintext reference as soon as it is hashed

    if args.user is not None:
        print(f"{args.user}:{phc}:{args.role}")
    else:
        print(phc)
    return 0


if __name__ == "__main__":  # pragma: no cover - thin CLI entrypoint
    raise SystemExit(main())
