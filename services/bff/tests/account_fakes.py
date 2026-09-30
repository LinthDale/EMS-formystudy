"""In-memory repository for explicit app-factory injection, never runtime config."""
from dataclasses import replace
from uuid import uuid4
from bff.accounts import Account, AccountUnavailable
from bff.credentials import parse_auth_users

class FakeAccounts:
    def __init__(self, raw=""):
        self.rows = {name: Account(uuid4(), name, phc, role, True, 1)
                     for name, (phc, role) in parse_auth_users(raw).items()}
        self.unavailable = False
    async def by_username(self, name):
        if self.unavailable:
            raise AccountUnavailable()
        return self.rows.get(name)
    async def by_id(self, account_id):
        if self.unavailable:
            raise AccountUnavailable()
        return next((r for r in self.rows.values() if r.id == account_id), None)
    def change(self, name, **fields):
        old = self.rows[name]
        self.rows[name] = replace(old, auth_version=old.auth_version + 1, **fields)
