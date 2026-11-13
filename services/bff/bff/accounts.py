"""Database-only local authentication (PRD-0023). No environment account table."""
from __future__ import annotations
import asyncio
import base64
import binascii
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID
import asyncpg
from argon2 import extract_parameters, Type
from argon2.exceptions import VerificationError
from .credentials import verify
from .roles import Role

class AccountUnavailable(Exception):
    """Safe error boundary: never include driver errors or credentials."""

@dataclass(frozen=True, slots=True)
class Account:
    id: UUID
    username: str
    password_hash: str = field(repr=False)
    role: Role
    enabled: bool
    auth_version: int

class AccountRepository(Protocol):
    async def by_username(self, username: str) -> Account | None: ...
    async def by_id(self, account_id: UUID) -> Account | None: ...

def validate_phc(phc: str) -> None:
    try:
        p = extract_parameters(phc)
        for segment in phc.split("$")[-2:]:
            decoded = base64.b64decode(segment + "=" * (-len(segment) % 4), validate=True)
            if base64.b64encode(decoded).decode().rstrip("=") != segment:
                raise ValueError("noncanonical PHC base64")
        valid = (len(phc) <= 512 and p.type == Type.ID and p.version == 19
                 and 1 <= p.time_cost <= 10 and 1 <= p.parallelism <= 16
                 and 8 * p.parallelism <= p.memory_cost <= 262144
                 and 8 <= p.salt_len <= 96 and 4 <= p.hash_len <= 96)
    except (ValueError, TypeError, binascii.Error):
        valid = False
    if not valid:
        raise ValueError("invalid or unbounded Argon2id hash")

class PostgresAccounts:
    def __init__(self, pool):
        self.pool = pool

    @classmethod
    async def connect(cls, dsn: str):
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5,
                                        timeout=5, command_timeout=5)
        repo = cls(pool)
        try:
            await repo.by_username("__startup_probe__")
        except BaseException:
            await pool.close()
            raise
        return repo

    async def close(self):
        try:
            await asyncio.wait_for(self.pool.close(), timeout=5)
        except TimeoutError:
            self.pool.terminate()

    async def _get(self, column: str, value):
        try:
            async with self.pool.acquire(timeout=5) as conn:
                row = await conn.fetchrow(
                    "SELECT id,username,password_hash,role,enabled,auth_version "
                    f"FROM bff_auth.accounts WHERE {column}=$1", value)
        except (asyncpg.PostgresError, OSError, TimeoutError) as exc:
            raise AccountUnavailable() from exc
        return (Account(row["id"], row["username"], row["password_hash"],
                        Role(row["role"]), row["enabled"], row["auth_version"])
                if row else None)

    async def by_username(self, username):
        return await self._get("username", username)

    async def by_id(self, account_id):
        return await self._get("id", account_id)

class AccountAuth:
    def __init__(self, repository: AccountRepository):
        self.repository = repository
        self._workers = asyncio.Semaphore(2)

    async def authenticate(self, username: str, password: str) -> Account | None:
        # Bound active Argon2 work and queue wait. A canceled HTTP request must
        # retain its slot until the underlying verification thread finishes.
        try:
            await asyncio.wait_for(self._workers.acquire(), timeout=5)
        except TimeoutError as exc:
            raise AccountUnavailable() from exc
        slot_owned = True
        try:
            account = await self.repository.by_username(username)
            users = {}
            if account and account.enabled:
                try:
                    validate_phc(account.password_hash)
                except ValueError:
                    raise AccountUnavailable() from None
                users[username] = (account.password_hash, account.role)
            task = asyncio.create_task(asyncio.to_thread(verify, users, username, password))
            def finished(done):
                self._workers.release()
                if not done.cancelled():
                    done.exception()  # consume errors after HTTP cancellation
            task.add_done_callback(finished)
            slot_owned = False
            try:
                role = await asyncio.shield(task)
            except VerificationError:
                raise AccountUnavailable() from None
            # Return the original immutable snapshot. Never attach a newer
            # credential version to a password verified using an older hash.
            return account if role is not None else None
        finally:
            if slot_owned:
                self._workers.release()

    async def valid_session(self, session) -> bool:
        if session.account_id is None:
            return False
        account = await self.repository.by_id(session.account_id)
        return bool(account and account.enabled and account.username == session.username
                    and account.auth_version == session.auth_version
                    and account.role == session.role)
