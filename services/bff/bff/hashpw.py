"""Legacy standalone Argon2 hash utility, not account provisioning.

Use docker compose run --rm account-admin create USER --role ops --reason REASON
to create a database account. This utility only emits a hash or legacy import
record; it does not save a user. Never write its output to BFF_AUTH_USERS.
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
        description="Generate an Argon2id hash for legacy tooling; use account-admin for DB users.",
    )
    parser.add_argument("--user", help="username; prints a legacy import record when given")
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
