"""Field DB connections must not rely on an optional libpq-style preference."""
import asyncio
import json
from pathlib import Path
import ssl
from unittest.mock import Mock,AsyncMock

import pytest
from edge_receiver.receiver import validate_config


def config(tmp_path):
    value=json.loads((Path(__file__).parents[1]/'deploy/receiver.example.json').read_text())
    path=tmp_path/'generation';path.write_text('77a7e12a-f5af-4025-b172-309cfbb5f082')
    value['generation_file']=str(path)
    return value


def test_field_refuses_missing_database_tls_configuration(tmp_path):
    value=config(tmp_path);value.pop('db_tls',None)
    with pytest.raises(ValueError):validate_config(value)


@pytest.mark.parametrize('dsn',['postgresql:///ems','postgresql://user@%2Ftmp/ems',
    'postgresql://user@localhost/ems?host=/tmp','postgresql://user@localhost/ems?sslmode=disable',
    'postgresql://user@localhost/ems?sslmode=prefer','postgresql://user@localhost/ems?sslmode=verify-ca',
    'postgresql://user@localhost/ems?sslmode=verify-full&sslmode=disable'])
def test_database_tls_cannot_be_bypassed_by_socket_host_override_or_downgrade(dsn):
    from edge_receiver.database_tls import verified_database_tls
    with pytest.raises(ValueError):verified_database_tls(dsn,dict(ca_file='ca',cert_file='cert',key_file='key'))


def test_database_tls_builds_verified_context_and_loads_client_certificate(monkeypatch):
    from edge_receiver.database_tls import verified_database_tls
    context=Mock(spec=ssl.SSLContext)
    create=Mock(return_value=context);monkeypatch.setattr(ssl,'create_default_context',create)
    result=verified_database_tls('postgresql://user@database/ems',dict(ca_file='ca',cert_file='cert',key_file='key'))
    assert result is context and context.check_hostname is True and context.verify_mode==ssl.CERT_REQUIRED, 'field DB does not verify server identity'
    create.assert_called_once_with(cafile='ca');context.load_cert_chain.assert_called_once_with('cert','key')


def test_current_store_requires_versioned_tls_predicate_without_legacy_fallback():
    import asyncpg
    from edge_receiver.store import ReceiptStore
    db=AsyncMock();db.fetchval.side_effect=asyncpg.UndefinedFunctionError('migration missing')
    with pytest.raises(asyncpg.UndefinedFunctionError):asyncio.run(ReceiptStore('private',standby_name='ems_archive').require_wal(db))
    assert db.fetchval.call_count==1 and 'edge_ingest.sync_tls_wal_flushed' in db.fetchval.call_args.args[0], 'old permissive predicate used as fallback'
