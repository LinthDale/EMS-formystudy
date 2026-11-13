"""Verified database/replication TLS, ENOSPC, and guarded physical restore."""
import asyncio
import copy
import json
import os
from pathlib import Path
import ssl
import threading
from uuid import uuid4

import pytest

import test_edge_receipts_mqtt as base
from test_edge_cutover import field_config
from edge_receiver.database_tls import verified_database_tls
from edge_receiver.store import ReceiptStore

pytestmark=pytest.mark.integration
VALUES=dict(voltage=230,current=5,power_kw=1,energy_kwh=100)


@pytest.fixture(autouse=True)
def private_gate():
    if os.environ.get('EDGE_V2_WAL_SECURITY')!='1':pytest.skip('explicit owned WAL security bench required')
    assert os.readlink('/proc/self/ns/net')==os.environ['EMS_V2_DEMO_NETNS'], 'wrong network namespace'
    assert {p.name for p in Path('/sys/class/net').iterdir()}=={'lo'}, 'unexpected network interface'


def emit(name,**value):
    Path(os.environ['EDGE_V2_EVIDENCE'],name+'.json').write_text(json.dumps(dict(passed=True,**value),indent=2))


def control(op):
    directory=Path(os.environ['EDGE_V2_EVIDENCE']);token=str(uuid4())
    path=directory/('control-'+token+'.request.json');temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(dict(request_id=token,op=op)));os.replace(temp,path)
    response=path.with_name(path.name.replace('.request.json','.response.json'))
    base.wait_for(response.exists,seconds=90 if op=='recovery_matrix' else 30)
    value=json.loads(response.read_text())
    assert value.get('passed') is True and value.get('request_id')==token and value.get('op')==op, 'owned WAL security operation failed'
    return value


def configured(tmp_path,monkeypatch):
    box,config,mqtt=field_config(tmp_path)
    root=Path(os.environ['EDGE_V2_TEST_PKI'])/'pg-client'
    config['db_tls']=dict(ca_file=str(root/'ca.crt'),cert_file=str(root/'receiver.crt'),key_file=str(root/'receiver.key'))
    monkeypatch.setenv('EDGE_V2_TLS_DSN','postgresql://qa_tls_receiver@127.0.0.1:5432/ems')
    config['dsn_env']='EDGE_V2_TLS_DSN';config['db_timeout_seconds']=2
    return box,config,mqtt


def test_verified_database_tls_and_dedicated_wal_role_deliver_original_once(tmp_path,monkeypatch):
    box,config,mqtt=configured(tmp_path,monkeypatch);sample=box.enqueue(base.source_time(),VALUES)
    async def tls_details():
        dsn=os.environ[config['dsn_env']]
        store=ReceiptStore(dsn,tls=verified_database_tls(dsn,config['db_tls']),standby_name='ems_archive')
        async with store.connection() as db:
            own=await db.fetchrow('SELECT ssl,version,client_dn FROM pg_stat_ssl WHERE pid=pg_backend_pid()')
            assert own['ssl'] is True and 'qa_tls_receiver' in own['client_dn'], 'DB TLS client certificate not authenticated'
            return dict(own)
    details=asyncio.run(tls_details())
    with base.running_receiver(config),base.running_sender(box,mqtt,mode='field') as sender:base.deliver(sender,box)
    assert len(base.db_rows(config,sample))==1 and box.pending_count()==0, 'verified TLS source did not reach central once'
    peer=control('wal_status')
    assert peer['peer_tls'] is True and peer['peer_role']=='ems_wal_archive' and 'ems_wal_archive' in peer['peer_client_dn'], 'WAL TLS identity missing'
    emit('db-wal-tls-positive',database_tls=details,wal_peer=peer,rows=1,pending_end=0,sync_wal=True)


@pytest.mark.parametrize('kind',['wrong_ca','wrong_host','expired','missing_client','untrusted_client','expired_client','wrong_user'])
def test_database_tls_failure_never_confirms_source_then_correct_identity_recovers(tmp_path,monkeypatch,kind):
    box,config,mqtt=configured(tmp_path,monkeypatch);sample=box.enqueue(base.source_time(),VALUES)
    with base.running_receiver(config) as receiver,base.running_sender(box,mqtt,mode='field') as sender:
        base.establish(sender);good=receiver.store;bad=copy.deepcopy(config['db_tls']);dsn=os.environ[config['dsn_env']]
        root=Path(os.environ['EDGE_V2_TEST_PKI'])/'pg-client'
        if kind=='wrong_ca':bad['ca_file']=str(root/'rogue-ca.crt')
        elif kind=='untrusted_client':bad['cert_file']=str(root/'rogue-receiver.crt')
        elif kind=='expired_client':bad['cert_file']=str(root/'expired-receiver.crt')
        elif kind=='wrong_user':dsn=dsn.replace('qa_tls_receiver@','qa_tls_other@')
        if kind=='missing_client':
            context=ssl.create_default_context(cafile=bad['ca_file'])  # Independent actual server-side rejection.
        else:context=verified_database_tls(dsn,bad)
        receiver.store=ReceiptStore(dsn,timeout=2,standby_name='ems_archive',tls=context)
        errors=[];commit=receiver.store.commit
        async def observe(item):
            try:return await commit(item)
            except Exception as exc:
                identity_rejected='certificate authentication failed' in str(exc)
                errors.append(dict(kind=type(exc).__name__,verify_code=getattr(exc,'verify_code',None),
                                   certificate_identity_rejected=identity_rejected,
                                   client_certificate_required='requires a valid client certificate' in str(exc)))
                raise
        receiver.store.commit=observe
        try:
            if kind in ('untrusted_client','expired_client'):control('db_client_probe_begin')
            if kind in ('wrong_host','expired'):control('db_cert_'+kind)
            assert not sender.step(threading.Event()), 'invalid DB TLS confirmed delivery'
            assert errors and box.pending()==[sample] and not base.db_rows(dict(dsn_env='EDGE_V2_TEST_DSN'),sample), 'DB TLS failure lost source or wrote partial data'
            if kind in ('wrong_ca','wrong_host','expired'):
                assert errors[0]['kind']=='SSLCertVerificationError', 'server certificate rejected for the wrong reason'
                allowed={'wrong_ca':{19,20,21},'wrong_host':{62,64},'expired':{10}}
                assert errors[0]['verify_code'] in allowed[kind], 'TLS rejection had an unexpected verify reason'
            elif kind=='wrong_user':
                assert errors[0]['certificate_identity_rejected'], 'valid wrong DB role was not rejected for certificate identity'
            elif kind=='missing_client':
                assert errors[0]['client_certificate_required'], 'missing client certificate failed for an unrelated cause'
            elif kind in ('untrusted_client','expired_client'):
                reason=control('db_client_probe_end_expired' if kind=='expired_client' else 'db_client_probe_end')
                errors[0].update({k:reason[k] for k in ('server_rejected_client_certificate','client_certificate_verify_code')})
        finally:
            if kind in ('wrong_host','expired'):control('db_cert_good')
            receiver.store=good
        base.deliver(sender,box,seconds=12)
    assert len(base.db_rows(config,sample))==1 and box.pending_count()==0, 'corrected DB TLS did not recover the original once'
    emit('db-tls-'+kind,kind=kind,actual_error=errors[0],source_preserved=True,no_partial_write=True,rows=1,pending_end=0)


@pytest.mark.parametrize('kind',['wrong_ca','wrong_host','expired','missing_client','untrusted_client','expired_client','wrong_user','plaintext'])
def test_replication_tls_failure_cannot_authorize_ack_then_same_slot_recovers(tmp_path,monkeypatch,kind):
    box,config,mqtt=configured(tmp_path,monkeypatch);sample=box.enqueue(base.source_time(),VALUES)
    with base.running_receiver(config),base.running_sender(box,mqtt,mode='field') as sender:
        base.establish(sender)
        try:
            probe=control('wal_probe_'+kind)
            assert not sender.step(threading.Event()) and box.pending()==[sample], 'failed WAL TLS produced a committed ACK'
        finally:resumed=control('wal_resume')
        assert not base.db_rows(config,sample), 'WAL TLS failure left a partial row'
        base.deliver(sender,box,seconds=12)
    assert len(base.db_rows(config,sample))==1 and box.pending_count()==0, 'WAL TLS recovery duplicated/lost the original'
    emit('wal-tls-'+kind,kind=kind,probe=probe,recovered_slot=resumed['slot'],source_preserved=True,rows=1,pending_end=0)


@pytest.mark.parametrize('kind',['plaintext','wrong_role'])
def test_connected_unsafe_replication_peer_is_rejected_by_ack_predicate(tmp_path,monkeypatch,kind):
    box,config,mqtt=configured(tmp_path,monkeypatch);sample=box.enqueue(base.source_time(),VALUES)
    with base.running_receiver(config),base.running_sender(box,mqtt,mode='field') as sender:
        base.establish(sender)
        try:
            rejected=control('wal_gate_'+kind)
            assert not sender.step(threading.Event()) and box.pending()==[sample], 'connected unsafe peer allowed a committed ACK'
            assert not base.db_rows(config,sample), 'unsafe replication gate partially committed source'
        finally:control('wal_resume')
        base.deliver(sender,box,seconds=12)
    assert len(base.db_rows(config,sample))==1 and box.pending_count()==0, 'safe peer did not recover once'
    emit('wal-gate-'+kind,kind=kind,gate=rejected,source_preserved=True,rows=1,pending_end=0)


def test_backup_corruption_later_wal_crc_and_cross_cluster_inputs_fail_closed():
    value=control('recovery_matrix')
    for key in ('good_promoted','postbackup_marker_recovered','corrupt_backup_checksum_rejected',
        'corrupt_later_wal_crc_rejected','foreign_wal_system_id_rejected',
        'valid_foreign_bundle_rejected_before_start','foreign_bundle_checksum_valid','pristine_inputs_unchanged'):
        assert value.get(key) is True, 'recovery evidence missing: '+key
    emit('recovery-inputs',**{k:v for k,v in value.items() if k!='passed'})


def test_real_wal_archive_enospc_keeps_source_and_original_slot_recovers(tmp_path,monkeypatch):
    box,config,mqtt=configured(tmp_path,monkeypatch);sample=box.enqueue(base.source_time(),VALUES)
    with base.running_receiver(config),base.running_sender(box,mqtt,mode='field') as sender:
        base.establish(sender)
        try:
            full=control('wal_full')
            assert not sender.step(threading.Event()) and box.pending()==[sample], 'full WAL archive acknowledged or deleted source'
            assert not base.db_rows(config,sample), 'full WAL archive partially committed source'
        finally:freed=control('wal_free')
        assert full['before']['slot']==freed['slot']['slot'] and freed['same_slot'], 'recovery skipped WAL by replacing the slot'
        base.deliver(sender,box,seconds=12)
        caught_up=control('wal_caught_up')
        assert caught_up['flush_fence_satisfied'], 'resumed archive did not flush through the fixed primary LSN'
    assert len(base.db_rows(config,sample))==1 and box.pending_count()==0, 'ENOSPC recovery lost or duplicated source'
    emit('wal-enospc',failure=full,recovered=freed,caught_up=caught_up,source_preserved=True,no_partial_write=True,rows=1,pending_end=0,
        scope='bounded owned tmpfs ENOSPC behavior; not nonvolatile/power-failure durability')
