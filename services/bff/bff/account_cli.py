"""Host-only account management. Invoke using the account-admin Compose service."""
from __future__ import annotations
import argparse
import asyncio
from getpass import getpass
import json
import os
import re
import sys
import warnings
from uuid import UUID, uuid4
import asyncpg
from argon2 import PasswordHasher
from .accounts import validate_phc
from .credentials import parse_auth_users

def parser():
    p = argparse.ArgumentParser(description="EMS database accounts (PRD-0023)")
    commands = p.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List accounts without password hashes")
    history = commands.add_parser("history")
    history.add_argument("--username")
    history.add_argument("--request-id", type=UUID)
    history.add_argument("--limit", type=int, default=50, choices=range(1, 1001), metavar="1..1000")
    for action in ("create", "enable", "disable", "set-role", "reset-password"):
        cmd = commands.add_parser(action)
        cmd.add_argument("username")
        if action in ("create", "set-role"):
            cmd.add_argument("--role", required=True, choices=("ops", "ingest", "readonly"))
        cmd.add_argument("--reason", required=True)
        cmd.add_argument("--request-id", type=UUID)
    legacy = commands.add_parser("import-env", help="One-time legacy records on stdin")
    legacy.add_argument("--reason", required=True)
    return p

def read_password():
    # Never fall back to echoing stdin when a terminal is absent.
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        first = getpass("New EMS password: ")
        second = getpass("Confirm password: ")
    if first != second or not 12 <= len(first) <= 256:
        raise ValueError("passwords must match and contain 12–256 characters")
    return first

def legacy_records(raw):
    users = parse_auth_users(raw)
    if not users or not any(role.value == "ops" for _,role in users.values()):
        raise ValueError("legacy import requires an OPS account")
    result = []
    for username, (encoded, role) in users.items():
        validate_phc(encoded)
        result.append({"username":username,"password_hash":encoded,"role":role.value})
    return result

def print_json(value):
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))

async def execute(args, dsn):
    # Server errors, DSN and imported hashes never enter stdout/stderr.
    conn = await asyncpg.connect(dsn, timeout=5, command_timeout=10,
        server_settings={"application_name":"ems-account-admin",
                         "default_transaction_isolation":"read committed",
                         "idle_in_transaction_session_timeout":"15000"})
    try:
        if args.command == "list":
            rows = await conn.fetch("SELECT * FROM bff_auth.account_summary ORDER BY username")
            return {"items":[dict(r) for r in rows]}
        if args.command == "history":
            rows = await conn.fetch(
                "SELECT * FROM bff_auth.account_audit "
                "WHERE ($1::text IS NULL OR username=$1) "
                "AND ($2::uuid IS NULL OR request_id=$2) "
                "ORDER BY created_at DESC,request_id LIMIT $3",
                args.username, args.request_id, args.limit)
            result = []
            for row in rows:
                item = dict(row)
                for key in ("before_state","after_state"):
                    if item[key] is not None:
                        item[key] = json.loads(item[key])
                result.append(item)
            return {"items":result}
        if args.command == "import-env":
            raw = sys.stdin.read(1024 * 1024 + 1)
            if len(raw)>1024 * 1024:
                raise ValueError("legacy input too large")
            records = legacy_records(raw)
            return json.loads(await conn.fetchval(
                "SELECT bff_auth.import_legacy($1::jsonb,$2)",json.dumps(records),args.reason))
        encoded = None
        existing = await conn.fetchval(
            "SELECT after_state FROM bff_auth.account_audit WHERE request_id=$1",
            args.request_id)
        if args.command in ("create","reset-password") and existing is None:
            encoded = PasswordHasher().hash(read_password())
        result = await conn.fetchval(
            "SELECT bff_auth.manage_account($1,$2,$3,$4,$5,$6)",
            args.request_id,args.command,args.username,encoded,
            getattr(args,"role",None),args.reason)
        return json.loads(result)
    finally:
        await conn.close(timeout=5)

def main(argv=None):
    args = parser().parse_args(argv)
    if getattr(args,"username",None) and not re.fullmatch(r"[a-zA-Z0-9_.-]{1,64}",args.username):
        print("Invalid username (use 1–64 letters, digits, _, . or -).",file=sys.stderr)
        return 2
    if hasattr(args,"reason") and not 1 <= len(args.reason.strip()) <= 500:
        print("A reason of 1–500 characters is required.",file=sys.stderr)
        return 2
    dsn = os.environ.get("BFF_AUTH_ADMIN_DSN","")
    if not dsn:
        print("BFF_AUTH_ADMIN_DSN is required.",file=sys.stderr)
        return 2
    if args.command not in ("list","history","import-env"):
        args.request_id = args.request_id or uuid4()
        print("request_id="+str(args.request_id),file=sys.stderr,flush=True)
    try:
        result = asyncio.run(execute(args,dsn))
    except (ValueError, EOFError):
        print("Invalid input; passwords must match (12–256 characters); import requires valid OPS records.",
              file=sys.stderr)
        return 2
    except Warning:
        print("A private interactive terminal is required for password entry.",file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Canceled. Check history by request_id before retrying a write.",file=sys.stderr)
        return 130
    except (asyncpg.PostgresError,OSError,TimeoutError):
        print("Operation not confirmed. Check history by request_id; verify account, last OPS, "
              "database permissions and connectivity. Do not retry with a new ID.",file=sys.stderr)
        return 1
    print_json(result)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
