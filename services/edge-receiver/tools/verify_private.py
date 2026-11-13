"""Provision only owned network-none resources for committed-delivery tests."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from uuid import UUID, uuid4


def cleanup_owned(owned, output, runner=subprocess.run):
    results = []
    for name, cid in reversed(owned):
        item = dict(name=name, container=cid, passed=False, logs_passed=False)
        try:
            logs = runner(['docker', 'logs', cid], text=True, capture_output=True, timeout=15)
            atomic_host_text(output / (name + '.log'),logs.stdout + logs.stderr)
            item['logs_passed'] = logs.returncode == 0
        except (OSError, subprocess.TimeoutExpired) as exc:
            item['logs_error_kind'] = type(exc).__name__
        try:
            removed = runner(['docker', 'rm', '-f', cid], capture_output=True, text=True, timeout=15)
            item['passed'] = removed.returncode == 0
        except (OSError, subprocess.TimeoutExpired) as exc:
            item['remove_error_kind'] = type(exc).__name__
        results.append(item)
    return results


def record_owned_command(output, commands, name, cmd, cid):
    commands.append(dict(name=name, command=cmd, container=cid))
    publish_control_response(output/'commands.json',commands)


def suite_targets(suite):
    suites = {
        'baseline': ('/app/tests/integration/test_edge_receipts.py',
                     '/app/tests/integration/test_edge_receipts_mqtt.py',
                     '/app/services/edge-receiver/tests', '/app/services/delta/tests'),
        'faults': ('/app/tests/integration/test_edge_receipts_faults.py',
                   '/app/services/delta/tests/test_bench_slot_boundary.py'),
        'resilience': ('/app/tests/integration/test_edge_resilience.py',
                       '/app/services/delta/tests/test_reliable_resilience.py',
                       '/app/services/delta/tests/test_bench_slot_boundary.py'),
        'lifecycle': ('/app/tests/integration/test_edge_lifecycle.py',
                      '/app/services/delta/tests/test_reliable_corruption.py',
                      '/app/services/delta/tests/test_bench_slot_boundary.py'),
        'restore-load': ('/app/tests/integration/test_edge_restore_load.py',
                         '/app/services/delta/tests/test_bench_slot_boundary.py'),
        'wal-pitr': ('/app/tests/integration/test_edge_wal_pitr.py',
                     '/app/services/delta/tests/test_bench_slot_boundary.py'),
        'cutover': ('/app/tests/integration/test_edge_cutover.py',
                    '/app/services/delta/tests/test_bench_slot_boundary.py'),
        'integrity': ('/app/tests/integration/test_edge_integrity.py',
                      '/app/services/delta/tests/test_reliable_consistency.py',
                      '/app/services/delta/tests/test_bench_slot_boundary.py'),
        'critical': ('/app/tests/integration/test_edge_critical.py',
                     '/app/services/delta/tests/test_bench_slot_boundary.py'),
        'wal-security': ('/app/tests/integration/test_edge_wal_security.py',
                         '/app/services/delta/tests/test_bench_slot_boundary.py'),
    }
    if suite not in suites:
        raise ValueError('unknown private suite')
    return suites[suite]


def assess_boundary_report(xml_text, exit_code):
    required = {
        'test_original_5109_boundary_uses_scheduled_identity_and_signed_delay': 3,
        'test_adjacent_representable_times_around_boundary_keep_scheduled_slot': 15,
        'test_real_skip_stays_missing_instead_of_renumbering_successes': 1,
        'test_repeated_same_deadline_still_has_duplicate_slot_identity': 1,
        'test_end_boundary_never_creates_extra_sample': 4,
        'test_invalid_or_off_grid_schedule_is_not_rounded_into_success': 9,
        'test_observer_wiring_keeps_deadline_values_and_real_gaps': 2,
    }
    try:
        cases = list(ET.fromstring(xml_text).iter('testcase'))
    except ET.ParseError:
        return dict(passed=False, reason='invalid_junit')
    counts = Counter(case.get('name','').split('[',1)[0] for case in cases)
    missing = {name: dict(expected=count, observed=counts[name]) for name,count in required.items() if counts[name] != count}
    boundary_cases = [case for case in cases if case.get('name','').split('[',1)[0] in required]
    catalog = json.loads(Path(__file__).with_name('boundary-cases.json').read_text())
    expected_ids = {(c['module'],c['name']) for c in catalog['case_ids']}
    actual_ids = Counter((c.get('classname','').rsplit('.',1)[-1],c.get('name','')) for c in boundary_cases)
    missing_ids = sorted(expected_ids - actual_ids.keys())
    unexpected_ids = sorted(actual_ids.keys() - expected_ids)
    duplicate_ids = sorted(identity for identity,count in actual_ids.items() if count > 1)
    identity_ok = (len(catalog['case_ids'])==len(expected_ids)==35
                   and not missing_ids and not unexpected_ids and not duplicate_ids)
    bad = any(case.find(tag) is not None for case in boundary_cases for tag in ('skipped','failure','error'))
    return dict(passed=exit_code == 0 and not missing and not bad and identity_ok, observed_tests=len(cases),
                boundary_cases=len(boundary_cases), missing_groups=missing, boundary_failed_or_skipped=bad,
                missing_case_ids=missing_ids,unexpected_case_ids=unexpected_ids,duplicate_case_ids=duplicate_ids)


def assess_fault_report(xml_text, exit_code, database_proof):
    boundary = assess_boundary_report(xml_text,exit_code)
    if not boundary['passed']:
        return dict(passed=False,boundary=boundary)
    required = (
        'test_database_timeout_keeps_source_then_recovers_once',
        'test_terminated_backend_rolls_back_partial_receipt_then_retry_commits_once',
        'test_duplicate_projection_is_rejected_and_source_quarantined_without_deletion',
        'test_two_live_receivers_commit_same_mqtt_sample_once',
        'test_generation_rotation_and_real_old_ack_replay_cannot_delete_pending',
        'test_sqlite_full_retires_oldest_and_preserves_newest_after_reopen',
        'test_audit_capacity_after_ack_recycles_oldest_and_accepts_new_sample',
        'test_untrusted_client_certificate_rejected_by_real_mtls_broker_and_keeps_queue',
    )
    cases = list(ET.fromstring(xml_text).iter('testcase'))
    counts = Counter(case.get('name') for case in cases)
    bad = any(case.find(tag) is not None for case in cases for tag in ('skipped','failure','error'))
    proof = database_proof if isinstance(database_proof,dict) else {}
    statuses = proof.get('received_statuses',[])
    real_timeout = (proof.get('passed') is True and proof.get('true_database_retryable_observed') is True
        and 'TimeoutError' in proof.get('database_exception_kinds',[])
        and proof.get('after_failure') == [0,0] and proof.get('receipts') == proof.get('projections') == 1
        and proof.get('pending_end') == 0
        and any(r.get('status')=='retryable' and r.get('error_code')=='database' for r in statuses))
    return dict(passed=len(cases)==43 and all(counts[name]==1 for name in required) and not bad and real_timeout,
                boundary=boundary,expected_tests=43,observed_tests=len(cases),database_timeout_evidence_valid=real_timeout)


def main(output, suite='baseline'):
    suite_targets(suite)  # Fail before creating directories, PKI or containers.
    # Includes PKI generation, provisioning and every failure/cleanup path.
    with tempfile.TemporaryDirectory(prefix='ems-committed-pki-') as temp:
        return run_private(output, Path(temp), suite)


WAL_OPERATIONS=frozenset(('wal_stop','wal_start','wal_basebackup','wal_restorepoint',
                         'wal_primary_loss','wal_recover','wal_missing'))


def validate_wal_request(request):
    if (not isinstance(request,dict) or set(request)!={'request_id','op'}
            or not isinstance(request['request_id'],str)
            or str(UUID(request['request_id']))!=request['request_id']
            or not isinstance(request['op'],str) or request['op'] not in WAL_OPERATIONS):
        raise ValueError('invalid fixed WAL request')


def assess_wal_report(xml_text,exit_code,proof):
    boundary=assess_boundary_report(xml_text,exit_code)
    cases=list(ET.fromstring(xml_text).iter('testcase'))
    name='test_acknowledged_postbackup_sample_recovers_from_independent_wal_after_primary_loss'
    checks={key:proof.get(key) is True for key in ('wal_outage_kept_source','postcommit_wal_loss_kept_source','migration_least_privilege',
        'postbackup_acked_payload_absent','original_primary_stopped','original_pgdata_not_used',
        'backup_and_wal_identity_match','pitr_excluded_after_target','old_ack_rejected',
        'missing_wal_failed_closed','recovered_sync_wal_ready')}
    checks['recovered_once']=proof.get('final_rows')==[1,1,1,1] and proof.get('pending_end')==0
    bad=any(c.find(t) is not None for c in cases for t in ('failure','error','skipped'))
    return dict(passed=boundary['passed'] and exit_code==0 and len(cases)==36
        and sum(c.get('name')==name for c in cases)==1 and not bad and all(checks.values()),
        boundary=boundary,expected_tests=36,observed_tests=len(cases),evidence_checks=checks)


def assess_cutover_report(xml_text,exit_code,evidence):
    boundary=assess_boundary_report(xml_text,exit_code)
    if not boundary['passed']:return dict(passed=False,boundary=boundary)
    cases=list(ET.fromstring(xml_text).iter('testcase'));counts=Counter(c.get('name') for c in cases)
    required=['test_field_mtls_limited_database_role_repairs_missing_projection_after_permission_recovery',
        'test_duplicate_mtls_client_id_disconnect_keeps_source_and_rejects_old_ack_after_reconnect']
    required += [f'test_v1_conversion_sigkill_preserves_source_and_publishes_only_complete_v2[{stage}]'
                 for stage in ('after_first_row','before_publish','after_publish')]
    def proof(name):
        p=evidence.get(name) if isinstance(evidence,dict) else None
        return p if isinstance(p,dict) else {}
    p=proof('field-limited-role')
    checks={'field-limited-role':p.get('passed') is True
        and p.get('administrative_flags')==dict(rolsuper=False,rolreplication=False,rolcreatedb=False,rolcreaterole=False)
        and p.get('denied_operations')==4 and p.get('actual_exception')=='InsufficientPrivilegeError'
        and all(p.get(k) is True for k in ('source_preserved_during_denial','receipt_timestamp_unchanged','mqtt_mtls'))
        and p.get('ack_durability')=='sync_wal' and p.get('rows')==1 and p.get('pending_end')==0}
    for stage in ('after_first_row','before_publish','after_publish'):
        p=proof('conversion-'+stage);digest=p.get('original_sha256')
        checks['conversion-'+stage]=(p.get('passed') is True and p.get('stage')==stage
            and p.get('child_exit')==-9 and p.get('published_at_crash') is (stage=='after_publish')
            and p.get('source_unchanged') is True and p.get('stable_mapping') is True
            and isinstance(digest,str) and len(digest)==64 and all(c in '0123456789abcdef' for c in digest)
            and p.get('rows')==2 and p.get('central_rows')==[1,1] and p.get('pending_end')==0)
    p=proof('duplicate-client-id')
    observed=p.get('observed_disconnect',{})
    checks['duplicate-client-id']=(p.get('passed') is True and p.get('actual_disconnect') is True
        and p.get('inflight_at_collision') is True
        and isinstance(observed,dict) and observed.get('ready') is True
        and observed.get('challenge')==p.get('old_challenge')
        and isinstance(observed.get('batch_id'),str) and bool(observed['batch_id'])
        and p.get('old_ack_observed') is True and p.get('old_ack_accepted') is False and p.get('source_preserved') is True
        and isinstance(p.get('old_challenge'),str) and bool(p['old_challenge'])
        and isinstance(p.get('new_challenge'),str) and bool(p['new_challenge']) and p['new_challenge']!=p['old_challenge']
        and p.get('central_rows')==[1,1] and p.get('pending_end')==0)
    bad=any(c.find(tag) is not None for c in cases for tag in ('failure','error','skipped'))
    return dict(passed=exit_code==0 and len(cases)==40 and all(counts[n]==1 for n in required)
        and not bad and all(checks.values()),boundary=boundary,expected_tests=40,observed_tests=len(cases),evidence_checks=checks)


def control_target(request, owned):
    """Worker cannot choose a Docker ID, path, command, or a shared target."""
    if not isinstance(request,dict) or set(request)!={'request_id','op'}:
        raise ValueError('invalid lifecycle request')
    if not isinstance(request['request_id'],str) or str(UUID(request['request_id']))!=request['request_id']:
        raise ValueError('invalid control request UUID')
    operations={'broker_stop':'broker','broker_start':'broker','revoke_old_client':'tls-broker',
                'db_backup':'database','db_restore':'database'}
    if not isinstance(request['op'],str) or request['op'] not in operations:
        raise ValueError('invalid lifecycle operation')
    name=operations[request['op']]
    targets=[cid for role,cid in owned if role==name]
    if len(targets)!=1:
        raise ValueError('owned lifecycle target unavailable')
    return targets[0]


def read_control_request(path):
    return json.loads(read_worker_file(path,1024))


def read_worker_file(path, limit):
    return read_worker_bytes(path,limit).decode('utf-8')


def read_worker_bytes(path, limit):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        metadata=os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size>limit:
            raise ValueError('invalid control file')
        raw=stream.read(limit+1)
    if len(raw)>limit:
        raise ValueError('oversized control file')
    return raw


def publish_control_response(path, result):
    atomic_host_text(path,json.dumps(result,indent=2))


def atomic_host_text(path, value):
    # Worker can precreate arbitrary names/symlinks in the evidence directory.
    # Write through a new exclusive random FD; rename replaces, never follows,
    # a pre-existing response symlink. No predictable .tmp is ever opened.
    fd,name=tempfile.mkstemp(prefix='.host-control-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb' if isinstance(value,bytes) else 'w') as stream:
            stream.write(value)
        os.replace(name,path)
    finally:
        if os.path.lexists(name):os.unlink(name)


def lifecycle_control(request, owned, call, private, output=None):
    cid=control_target(request,owned)
    op=request['op']
    if op in ('db_backup','db_restore'):
        # Fixed source/target DB names and backup path; no worker-supplied SQL,
        # filename, DSN, container, or drop/overwrite operation is accepted.
        prefix=['docker','exec',cid]
        if op=='db_backup':
            call(prefix+['pg_dump','-U','postgres','-d','ems','-Fc','-f','/tmp/ems-private-backup.dump'],timeout=60)
            digest=call(prefix+['sha256sum','/tmp/ems-private-backup.dump']).split()[0]
            # docker cp may preserve a container symlink: never open the copied
            # path normally. Fresh private copy directory + bounded NOFOLLOW FD.
            with tempfile.TemporaryDirectory(prefix='dump-copy-',dir=private) as copy_dir:
                copied=Path(copy_dir)/'central-backup.dump'
                call(['docker','cp',cid+':/tmp/ems-private-backup.dump',str(copied)])
                payload=read_worker_bytes(copied,16*1024*1024)
            if hashlib.sha256(payload).hexdigest()!=digest:
                raise ValueError('private database dump hash mismatch')
            if output is not None:atomic_host_text(output/'central-backup.dump',payload)
            return dict(passed=True,**request,container_id=cid,format='pg_dump-custom',
                        backup_sha256=digest,backup_bytes=len(payload),source_database='ems')
        call(prefix+['createdb','-U','postgres','ems_restore'])  # Refuses existing destination.
        call(prefix+['psql','-U','postgres','-d','ems_restore','-v','ON_ERROR_STOP=1','-c',
                     'CREATE EXTENSION IF NOT EXISTS timescaledb; SELECT timescaledb_pre_restore();'])
        call(prefix+['pg_restore','-U','postgres','-d','ems_restore','--no-owner','--exit-on-error',
                     '/tmp/ems-private-backup.dump'],timeout=60)
        call(prefix+['psql','-U','postgres','-d','ems_restore','-v','ON_ERROR_STOP=1','-c',
                     'SELECT timescaledb_post_restore();'])
        rows=call(prefix+['psql','-U','postgres','-d','ems_restore','-At','-c',
                         'SELECT (SELECT count(*) FROM edge_ingest.receipts),(SELECT count(*) FROM electricity_measurements);'])
        return dict(passed=True,**request,container_id=cid,target_database='ems_restore',
                    source_database_preserved=True,restore_method='pg_restore-to-new-database',counts=rows)
    before=json.loads(call(['docker','inspect',cid,'--format','{{json .State}}']))
    extra={}
    if op=='broker_stop':
        call(['docker','stop','--time','2',cid])
    elif op=='broker_start':
        call(['docker','start',cid])
    else:
        call(['openssl','ca','-batch','-config',str(private/'ca.conf'),'-revoke',str(private/'client.crt')])
        call(['openssl','ca','-gencrl','-config',str(private/'ca.conf'),'-crldays','1','-out',str(private/'revocations.pem')])
        serial=call(['openssl','x509','-in',str(private/'client.crt'),'-noout','-serial']).split('=',1)[1]
        metadata=call(['openssl','crl','-in',str(private/'revocations.pem'),'-noout','-text'])
        verify=call(['openssl','crl','-in',str(private/'revocations.pem'),'-noout','-verify','-CAfile',str(private/'ca.crt')])
        if serial.lower() not in metadata.lower():
            raise ValueError('revoked serial missing from CRL')
        revoked=subprocess.run(['openssl','verify','-CAfile',str(private/'ca.crt'),'-CRLfile',
            str(private/'revocations.pem'),'-crl_check',str(private/'client.crt')],capture_output=True,text=True,timeout=10)
        if revoked.returncode==0 or 'error 23 at' not in revoked.stdout+revoked.stderr:
            raise ValueError('certificate revocation was not independently verified')
        extra=dict(serial_revoked=serial,crl_verified=True,revocation_verify_error=23,
                   crl_sha256=hashlib.sha256((private/'revocations.pem').read_bytes()).hexdigest())
        call(['docker','restart','--time','2',cid])  # Force existing TLS sessions to reauthenticate.
    after=json.loads(call(['docker','inspect',cid,'--format','{{json .State}}']))
    if after['Running']!=(op!='broker_stop'):
        raise ValueError('owned broker lifecycle state mismatch')
    return dict(passed=True,**request,container_id=cid,started_at=after['StartedAt'],
                before_started_at=before['StartedAt'],running=after['Running'],**extra)


def assess_resilience_report(xml_text, exit_code, evidence):
    """Require actual crash/storage/TLS evidence as well as all fixed cases."""
    boundary=assess_boundary_report(xml_text,exit_code)
    if not boundary['passed']:
        return dict(passed=False,boundary=boundary)
    cases=list(ET.fromstring(xml_text).iter('testcase'))
    counts=Counter(c.get('name') for c in cases)
    required=[f'test_sigkill_during_rotation_recovers_exact_transaction_boundary[{stage}]'
              for stage in ('after_retire','before_commit','after_commit')]
    required += ['test_sqlite_busy_retains_old_sample_and_recovers_without_false_retirement',
                 'test_readonly_database_retains_old_sample_then_recovers',
                 'test_online_backup_remains_coherent_while_rotation_commits_during_copy']
    tls=(('untrusted-ca',8886,'rogue-ca.crt',19),('wrong-host',8887,'ca.crt',64),('expired',8888,'ca.crt',10))
    required += [f'test_v2_invalid_server_certificate_keeps_original_then_recovers_once[{case}-{port}-{ca}-{code}]'
                 for case,port,ca,code in tls]
    def proof(name):
        value=evidence.get(name) if isinstance(evidence,dict) else None
        return value if isinstance(value,dict) else {}
    verified={}
    for stage in ('after_retire','before_commit','after_commit'):
        p=proof('crash-'+stage)
        observed=p.get('observed',{})
        after=stage=='after_commit'
        baseline=observed.get('baseline_sha256') if isinstance(observed,dict) else None
        changed=observed.get('observed_sha256') if isinstance(observed,dict) else None
        hash_proof=(isinstance(baseline,str) and isinstance(changed,str) and len(baseline)==len(changed)==64
                    and all(c in '0123456789abcdef' for c in baseline+changed) and baseline!=changed)
        verified['crash-'+stage]=(p.get('passed') is True and p.get('child_exit')==-9
            and isinstance(observed,dict) and observed.get('stage')==stage
            and observed.get('baseline_stage')=='after_constructor' and hash_proof
            and (after or (observed.get('journal_bytes',0)>0 and observed.get('main_file_changed') is True))
            and (not after or p.get('committed_identity_preserved') is True)
            and p.get('recovered_sequence')==(2 if after else 1) and p.get('next_sequence')==(3 if after else 2)
            and isinstance(p.get('retirement'),dict)
            and p['retirement'].get('unconfirmed_evicted_total')==(1 if after else 0) and p.get('integrity')=='ok')
    for name,code in (('sqlite-busy','SQLITE_BUSY'),('sqlite-readonly','SQLITE_READONLY')):
        p=proof(name)
        verified[name]=(p.get('passed') is True and p.get('sqlite_error')==code
                        and p.get('old_preserved') is True and p.get('next_sequence')==2)
    p=proof('online-backup')
    verified['online-backup']=(p.get('passed') is True and p.get('rotation_committed_during_copy') is True
        and p.get('retained_sequences')==[16,17,18,19,20] and p.get('integrity')=='ok'
        and isinstance(p.get('retirement'),dict) and p['retirement'].get('unconfirmed_evicted_total')==15)
    for case,port,ca,code in tls:
        p=proof('tls-server-'+case)
        verified['tls-server-'+case]=(p.get('passed') is True and p.get('verify_code')==code
            and p.get('real_client_rejection') is True and p.get('source_preserved_during_failure') is True
            and p.get('projections')==1 and p.get('pending_end')==0)
    bad=any(c.find(tag) is not None for c in cases for tag in ('skipped','failure','error'))
    return dict(passed=exit_code==0 and len(cases)==44 and all(counts[n]==1 for n in required)
                and not bad and all(verified.values()),boundary=boundary,expected_tests=44,
                observed_tests=len(cases),evidence_checks=verified)


def assess_lifecycle_report(xml_text, exit_code, evidence):
    boundary=assess_boundary_report(xml_text,exit_code)
    if not boundary['passed']:
        return dict(passed=False,boundary=boundary)
    required=['test_real_broker_restart_keeps_tcp_acquisition_and_same_process_reconnects',
              'test_same_gateway_new_certificate_rotates_then_revoked_old_certificate_is_denied',
              'test_genuinely_new_path_still_initializes_and_sequences_from_one']
    required += [f'test_damaged_existing_queue_fails_without_reset_or_modification[{kind}]'
                 for kind in ('header','truncated','zero-length','empty-sqlite')]
    cases=list(ET.fromstring(xml_text).iter('testcase'));counts=Counter(c.get('name') for c in cases)
    def proof(name):
        value=evidence.get(name) if isinstance(evidence,dict) else None
        return value if isinstance(value,dict) else {}
    checks={}
    for kind in ('header','truncated','zero-length','empty-sqlite'):
        p=proof('corruption-'+kind)
        checks[kind]=(p.get('passed') is True and p.get('damage')==kind and p.get('empty_database_recreated') is False
                      and isinstance(p.get('before_sha256'),str) and len(p['before_sha256'])==64
                      and p.get('before_sha256')==p.get('after_sha256'))
    p=proof('broker-restart');start=p.get('started',{});stop=p.get('stopped',{})
    checks['broker-restart']=(p.get('passed') is True and p.get('same_edge_process') is True
        and p.get('tcp_samples_during_outage',0)>=3 and p.get('projections_each')==1 and p.get('pending_end')==0
        and start.get('passed') is True and stop.get('passed') is True
        and start.get('running') is True and stop.get('running') is False
        and start.get('container_id')==stop.get('container_id')==p.get('broker_container_id')
        and start.get('started_at')!=stop.get('started_at'))
    p=proof('certificate-rotation-revocation');revoked=p.get('revocation',{})
    checks['certificate-rotation-revocation']=(p.get('passed') is True and p.get('same_gateway')=='qa-edge'
        and all(p.get(key) is True for key in ('old_worked_before','new_worked_before','old_rejected_after','new_worked_after'))
        and p.get('active_old_session_disconnected') is True and revoked.get('passed') is True
        and revoked.get('serial_revoked') and revoked.get('crl_verified') is True and revoked.get('revocation_verify_error')==23
        and p.get('projections_each')==1 and p.get('pending_end')==0)
    bad=any(c.find(tag) is not None for c in cases for tag in ('skipped','failure','error'))
    return dict(passed=exit_code==0 and len(cases)==42 and all(counts[name]==1 for name in required)
                and not bad and all(checks.values()),boundary=boundary,expected_tests=42,observed_tests=len(cases),evidence_checks=checks)


def assess_restore_load_report(xml_text, exit_code, evidence):
    boundary=assess_boundary_report(xml_text,exit_code)
    if not boundary['passed']:return dict(passed=False,boundary=boundary)
    cases=list(ET.fromstring(xml_text).iter('testcase'));counts=Counter(c.get('name') for c in cases)
    required=('test_real_database_backup_restore_new_generation_recovers_pending_and_exposes_acked_loss',
        'test_real_mqtt_burst_fills_bounded_receiver_queue_then_recovers_original_once',
        'test_thousand_old_samples_do_not_block_new_samples_at_production_sender_cadence')
    def proof(name):
        p=evidence.get(name) if isinstance(evidence,dict) else None
        return p if isinstance(p,dict) else {}
    p=proof('database-restore');backup=p.get('backup',{});restore=p.get('restore',{})
    restored=(p.get('passed') is True and backup.get('passed') is True and backup.get('format')=='pg_dump-custom'
        and isinstance(backup.get('backup_sha256'),str) and len(backup['backup_sha256'])==64 and backup.get('backup_bytes',0)>0
        and restore.get('passed') is True and restore.get('target_database')=='ems_restore'
        and restore.get('restore_method')=='pg_restore-to-new-database' and p.get('original_db_preserved') is True
        and p.get('backup_identity_and_projection_matched') is True and p.get('recovered_original_identity_and_projection_matched') is True
        and p.get('restored_counts_before_replay')==[1,0,0] and p.get('old_ack_replayed') is True
        and p.get('old_ack_accepted') is False and p.get('old_generation')!=p.get('new_generation')
        and p.get('recovered_pending_rows')==p.get('fresh_rows')==1 and p.get('pending_end')==0
        and isinstance(p.get('unrecoverable_acked_after_backup'),list) and len(p['unrecoverable_acked_after_backup'])==1)
    p=proof('receiver-overload')
    overload=(p.get('passed') is True and p.get('mqtt_messages')==p.get('messages')==200
        and p.get('unique_source_samples')==1 and p.get('peak')==p.get('receiver_capacity')==64
        and p.get('dropped',0)>0 and p.get('rate_denied',0)>0 and p.get('actual_db_lock_observed') is True
        and p.get('no_committed_ack_while_locked') is True and p.get('original_rows')==p.get('fresh_rows')==1 and p.get('pending_end')==0)
    p=proof('live-backlog-delay');latencies=p.get('enqueue_to_commit_seconds',[]);ranks=p.get('completion_ranks_after_enqueue',[])
    delay=(p.get('passed') is True and p.get('old_samples')==1000 and p.get('new_samples')==3 and p.get('sender_wait_seconds')==1
        and isinstance(latencies,list) and len(latencies)==3 and all(type(n) in (int,float) and 0<=n<4 for n in latencies)
        and isinstance(ranks,list) and len(ranks)==3 and all(type(n) is int and 1<=n<=3 for n in ranks)
        and p.get('oldest_backlog_advanced') is True and p.get('retained_total')==1003
        and p.get('pending_history_retained',0)>900
        and p.get('pending_history_retained',0)+p.get('confirmed_samples',0)==1003)
    checks=dict(database_restore=restored,receiver_overload=overload,live_backlog_delay=delay)
    bad=any(c.find(tag) is not None for c in cases for tag in ('failure','error','skipped'))
    return dict(passed=exit_code==0 and len(cases)==38 and all(counts[name]==1 for name in required)
        and not bad and all(checks.values()),boundary=boundary,expected_tests=38,observed_tests=len(cases),evidence_checks=checks)


def integrity_case_names():
    groups={
        'test_existing_logically_inconsistent_queue_is_rejected_without_modifying_evidence':
            ['sequence-rollback','clock-rollback','missing-audit','audit-hash','audit-state','orphan-audit','audit-sequence'],
        'test_selected_pending_payload_must_match_persisted_identity_before_sending':
            ['hash-mismatch','valid-different-id','valid-different-sequence','valid-different-device','wrong-window','invalid-json'],
        'test_ack_after_live_audit_damage_cannot_delete_pending_or_fabricate_audit':
            ['missing-audit','audit-hash','audit-state','audit-sequence'],
        'test_live_high_water_rollback_cannot_retire_source_or_reuse_sequence':
            [f'{done}-{kind}' for done in ('False','True') for kind in ('sequence-rollback','clock-rollback')],
        'test_malformed_mqtt_batch_writes_nothing_then_valid_originals_recover_once':
            ['bad-hash','duplicate-id','duplicate-key','invalid-utf8','excess-depth'],
    }
    names=[name+'['+param+']' for name,params in groups.items() for param in params]
    names += ['test_valid_committed_and_quarantined_rows_survive_reopen_and_continue_sequence',
        'test_duplicate_retained_audit_sequence_is_rejected_on_reopen',
        'test_retention_counter_overflow_rolls_back_entire_replacement',
        'test_pending_uses_one_read_snapshot_during_real_capacity_rotation',
        'test_sigterm_during_real_database_wait_exits_cleanly_and_full_edge_restart_recovers']
    return names


def validate_secure_request(request,operations):
    if (not isinstance(request,dict) or set(request)!={'request_id','op'}
            or not isinstance(request['request_id'],str) or str(UUID(request['request_id']))!=request['request_id']
            or not isinstance(request['op'],str) or request['op'] not in operations):
        raise ValueError('invalid fixed WAL security request')


def assess_wal_security_report(xml_text,exit_code,evidence):
    boundary=assess_boundary_report(xml_text,exit_code)
    if not boundary['passed']:return dict(passed=False,boundary=boundary)
    cases=list(ET.fromstring(xml_text).iter('testcase'));counts=Counter(c.get('name') for c in cases)
    db_cases=('wrong_ca','wrong_host','expired','missing_client','untrusted_client','expired_client','wrong_user')
    wal_cases=(*db_cases,'plaintext')
    names=['test_verified_database_tls_and_dedicated_wal_role_deliver_original_once',
        'test_backup_corruption_later_wal_crc_and_cross_cluster_inputs_fail_closed',
        'test_real_wal_archive_enospc_keeps_source_and_original_slot_recovers']
    names += [f'test_database_tls_failure_never_confirms_source_then_correct_identity_recovers[{c}]' for c in db_cases]
    names += [f'test_replication_tls_failure_cannot_authorize_ack_then_same_slot_recovers[{c}]' for c in wal_cases]
    names += [f'test_connected_unsafe_replication_peer_is_rejected_by_ack_predicate[{c}]' for c in ('plaintext','wrong_role')]
    def proof(name):
        p=evidence.get(name) if isinstance(evidence,dict) else None
        return p if isinstance(p,dict) else {}
    checks={}
    p=proof('db-wal-tls-positive');tls=p.get('database_tls',{});peer=p.get('wal_peer',{})
    checks['positive']=(p.get('passed') is True and isinstance(tls,dict) and tls.get('ssl') is True
        and 'qa_tls_receiver' in str(tls.get('client_dn')) and p.get('sync_wal') is True and p.get('rows')==1 and p.get('pending_end')==0
        and isinstance(peer,dict) and peer.get('peer_tls') is True and peer.get('peer_role')=='ems_wal_archive'
        and 'ems_wal_archive' in str(peer.get('peer_client_dn')))
    for c in db_cases:
        p=proof('db-tls-'+c)
        checks['db-'+c]=(p.get('passed') is True and p.get('kind')==c and bool(p.get('actual_error'))
            and p.get('source_preserved') is True and p.get('no_partial_write') is True and p.get('rows')==1 and p.get('pending_end')==0)
        if c=='wrong_user':checks['db-'+c]=checks['db-'+c] and p.get('actual_error',{}).get('certificate_identity_rejected') is True
        if c=='missing_client':checks['db-'+c]=checks['db-'+c] and p.get('actual_error',{}).get('client_certificate_required') is True
        if c in ('wrong_ca','wrong_host','expired'):
            error=p.get('actual_error',{})
            checks['db-'+c]=checks['db-'+c] and error.get('kind')=='SSLCertVerificationError' and error.get('verify_code') in {'wrong_ca':(19,20,21),'wrong_host':(62,64),'expired':(10,)}[c]
        if c in ('untrusted_client','expired_client'):
            error=p.get('actual_error',{})
            checks['db-'+c]=(checks['db-'+c] and error.get('server_rejected_client_certificate') is True
                and error.get('client_certificate_verify_code') in ((10,) if c=='expired_client' else (19,20,21)))
    for c in wal_cases:
        p=proof('wal-tls-'+c);probe=p.get('probe',{})
        checks['wal-'+c]=(p.get('passed') is True and p.get('kind')==c and isinstance(probe,dict) and probe.get('kind')==c and probe.get('exit_code')==1
            and probe.get('reason_verified') is True and probe.get('replication_peer_absent') is True
            and p.get('source_preserved') is True and p.get('rows')==1 and p.get('pending_end')==0)
        if c in ('wrong_ca','wrong_host','expired'):
            checks['wal-'+c]=checks['wal-'+c] and probe.get('tls_verify_code') in {'wrong_ca':(19,20,21),'wrong_host':(62,64),'expired':(10,)}[c]
        if c=='expired_client':checks['wal-'+c]=checks['wal-'+c] and probe.get('client_verify_code')==10
    for c in ('plaintext','wrong_role'):
        p=proof('wal-gate-'+c);gate=p.get('gate',{})
        checks['gate-'+c]=(p.get('passed') is True and isinstance(gate,dict) and gate.get('peer_connected') is True
            and gate.get('gate_rejected') is True and gate.get('observed',{}).get('guard') is False
            and p.get('source_preserved') is True and p.get('rows')==1 and p.get('pending_end')==0)
    p=proof('recovery-inputs')
    checks['recovery']=(p.get('passed') is True and isinstance(p.get('expected_system_id'),str) and p['expected_system_id'].isdigit()
        and isinstance(p.get('foreign_system_id'),str) and p['foreign_system_id'].isdigit() and p['expected_system_id']!=p['foreign_system_id']
        and all(p.get(k) is True for k in ('good_promoted','postbackup_marker_recovered','corrupt_backup_checksum_rejected',
            'corrupt_later_wal_crc_rejected','foreign_wal_system_id_rejected','valid_foreign_bundle_rejected_before_start',
            'foreign_bundle_checksum_valid','pristine_inputs_unchanged')))
    p=proof('wal-enospc');failure=p.get('failure',{});recovered=p.get('recovered',{});caught=p.get('caught_up',{})
    checks['enospc']=(p.get('passed') is True and isinstance(failure,dict) and failure.get('actual_enospc') is True
        and failure.get('child_exit')==1 and failure.get('archive_limit_bytes')==128*1024*1024
        and failure.get('container_kept_running') is True and failure.get('after',{}).get('active') is False
        and failure.get('after',{}).get('lag_bytes',0)>failure.get('before',{}).get('lag_bytes',0)
        and isinstance(recovered,dict) and recovered.get('same_slot') is True and recovered.get('synchronous') is True
        and failure.get('before',{}).get('slot')==recovered.get('slot',{}).get('slot')=='ems_archive_slot'
        and isinstance(caught,dict) and caught.get('flush_fence_satisfied') is True and bool(caught.get('fixed_lsn'))
        and p.get('source_preserved') is True and p.get('no_partial_write') is True and p.get('rows')==1 and p.get('pending_end')==0)
    bad=any(c.find(t) is not None for c in cases for t in ('failure','error','skipped'))
    return dict(passed=exit_code==0 and len(cases)==55 and all(counts[n]==1 for n in names)
        and not bad and all(checks.values()),boundary=boundary,expected_tests=55,observed_tests=len(cases),evidence_checks=checks)


def assess_integrity_report(xml_text,exit_code,evidence):
    boundary=assess_boundary_report(xml_text,exit_code)
    if not boundary['passed']:return dict(passed=False,boundary=boundary)
    cases=list(ET.fromstring(xml_text).iter('testcase'));counts=Counter(c.get('name') for c in cases)
    def proof(name):
        p=evidence.get(name) if isinstance(evidence,dict) else None
        return p if isinstance(p,dict) else {}
    checks={}
    for kind in ('sequence-rollback','clock-rollback','missing-audit','audit-hash','audit-state','orphan-audit','audit-sequence'):
        p=proof('logical-'+kind);digest=p.get('before_sha256')
        checks['logical-'+kind]=(p.get('passed') is True and p.get('damage')==kind and p.get('quick_check')=='ok'
            and p.get('rejected') is True and isinstance(digest,str) and len(digest)==64 and p.get('after_sha256')==digest)
    for kind in ('bad-hash','duplicate-id','duplicate-key','invalid-utf8','excess-depth'):
        p=proof('malformed-'+kind)
        checks['malformed-'+kind]=(p.get('passed') is True and p.get('kind')==kind
            and p.get('actual_parser_observed') is True and p.get('acks_before_recovery')==0
            and p.get('rows_before')==[0,0] and p.get('rows_after')==[1,1]
            and p.get('receiver_survived') is True and p.get('pending_end')==0)
    p=proof('sigterm-db-wait');total=p.get('total_acquired',0)
    checks['sigterm-db-wait']=(p.get('passed') is True and p.get('real_db_lock_observed') is True
        and p.get('wait_still_active_at_exit') is True and p.get('first_exit')==p.get('restart_exit')==0
        and type(p.get('graceful_exit_seconds')) in (int,float) and 0<=p['graceful_exit_seconds']<4
        and isinstance(p.get('saved_before_restart'),list) and len(p['saved_before_restart'])>=1
        and type(total) is int and total>=2 and p.get('receipts')==p.get('projections')==total
        and all(p.get(k) is True for k in ('all_projection_counts_one','projection_ids_match','projection_values_match',
                                         'original_canonical_unchanged','ledger_hashes_match'))
        and p.get('pending_end')==0)
    bad=any(c.find(t) is not None for c in cases for t in ('failure','error','skipped'))
    return dict(passed=exit_code==0 and len(cases)==66 and all(counts[n]==1 for n in integrity_case_names())
        and not bad and all(checks.values()),boundary=boundary,expected_tests=66,observed_tests=len(cases),evidence_checks=checks)


def run_private(output, private, suite='baseline'):
    root = Path(__file__).resolve().parents[3]
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    owned, cleanup, commands = [], [], []
    label = 'committed-' + uuid4().hex

    def call(args, timeout=30, input_text=None):
        result = subprocess.run(args, text=True, input=input_text, capture_output=True, timeout=timeout)
        if result.returncode:
            raise RuntimeError('private command failed: ' + str(args[:3]))
        return result.stdout.strip()

    images = {name: call(['docker', 'image', 'inspect', name, '--format', '{{.Id}}'])
              for name in ('alpine', 'eclipse-mosquitto:2', 'timescale/timescaledb:latest-pg15',
                           'ems-receipts-test-20261112')}
    (output / 'images.json').write_text(json.dumps(images, indent=2))
    (output / 'containers-before.jsonl').write_text(call(['docker', 'ps', '--format', '{{json .}}']))
    source = output / 'source'
    for rel in ('services/delta', 'services/edge-receiver'):
        shutil.copytree(root / rel, source / rel, ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache', '.coverage'))
    for rel in ('infra/timescaledb/init.sql', 'infra/timescaledb/migrations/019_edge_committed_receipts.sql',
                'tests/integration/test_edge_receipts.py', 'tests/integration/test_edge_receipts_mqtt.py',
                'tests/integration/test_edge_receipts_faults.py','tests/integration/test_edge_resilience.py',
                'tests/integration/test_edge_lifecycle.py','tests/integration/test_edge_restore_load.py',
                'tests/integration/test_edge_wal_pitr.py','tests/integration/test_edge_cutover.py','tests/integration/test_edge_integrity.py',
                'tests/integration/test_edge_wal_security.py','tests/integration/test_edge_critical.py',
                'infra/timescaledb/migrations/020_edge_synchronous_wal.sql','infra/timescaledb/migrations/021_edge_tls_wal.sql'):
        path = root / rel
        if path.exists():
            (source / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, source / rel)
    hashes = {p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in source.rglob('*') if p.is_file()}
    (output / 'source-sha256.json').write_text(json.dumps(hashes, indent=2))
    (output / 'mosquitto.conf').write_text('listener 1883 127.0.0.1\nallow_anonymous true\npersistence false\nlog_dest stdout\nlog_type all\n')
    sys.path.insert(0, str(root / 'services/delta/tools'))
    from bench_field_checks import pki
    pki(private)
    from private_pg_tls import prepare as prepare_pg_tls,provision as provision_pg_tls
    prepare_pg_tls(private,call)
    for name in ('edge-receiver', 'qa-observer','rotated-client'):
        principal='qa-edge' if name=='rotated-client' else name
        call(['openssl', 'req', '-new', '-newkey', 'rsa:2048', '-nodes', '-subj', '/CN=' + principal,
              '-keyout', str(private / (name + '.key')), '-out', str(private / (name + '.csr'))])
        call(['openssl', 'x509', '-req', '-in', str(private / (name + '.csr')), '-CA', str(private / 'ca.crt'),
              '-CAkey', str(private / 'ca.key'), '-CAcreateserial', '-days', '2', '-sha256',
              '-extfile', str(private / 'client.ext'), '-out', str(private / (name + '.crt'))])
    for key in private.glob('*.key'):
        key.chmod(0o600)
    if suite=='lifecycle':
        ca_config=(private/'ca.conf').read_text()
        for key,name in (('database','index.txt'),('serial','serial'),('new_certs_dir','newcerts'),
                         ('certificate','ca.crt'),('private_key','ca.key')):
            ca_config=ca_config.replace(key+'='+name,key+'='+str(private/name))
        (private/'ca.conf').write_text(ca_config)
        call(['openssl','ca','-gencrl','-config',str(private/'ca.conf'),'-crldays','1','-out',str(private/'revocations.pem')])
    acl = (root / 'services/edge-receiver/deploy/edge-v2.acl.example').read_text()
    acl += '\n# Private QA observer only, never in the deployment ACL.\nuser qa-observer\ntopic read ems/v2/#\n'
    (private / 'acl').write_text(acl)
    tls = ('per_listener_settings true\nmessage_size_limit 65536\n'
           'persistence false\nlog_dest stdout\nlog_type all\n')
    for port,cert in ((8886,'server'),(8887,'wrong-host'),(8888,'expired')):
        tls += (f'listener {port} 127.0.0.1\nallow_anonymous false\nrequire_certificate true\n'
                f'use_identity_as_username true\ncafile /qa/ca.crt\ncertfile /qa/{cert}.crt\n'
                f'keyfile /qa/{cert}.key\nacl_file /qa/acl\n')
        if suite=='lifecycle':
            tls+='crlfile /qa/revocations.pem\n'
    (private / 'tls.conf').write_text(tls)
    (output / 'tls-broker-config.txt').write_text(tls)
    (output / 'tls-acl.txt').write_text(acl)
    (output / 'certificate-metadata.json').write_text(json.dumps({p.name: call(['openssl','x509','-in',str(p),
        '-noout','-fingerprint','-sha256','-subject','-issuer','-dates']) for p in private.glob('*.crt')}, indent=2))

    def create(name, image, args, command):
        cmd = ['docker', 'create', '--label', 'ems.qa.run=' + label, '--cpus', '.5',
               '--memory', '512m', '--pids-limit', '128'] + args + [images[image]] + command
        cid = call(cmd)
        owned.append((name, cid))
        record_owned_command(output,commands,name,cmd,cid)
        call(['docker', 'start', cid])
        return cid

    result = dict(passed=False, suite=suite, scope='private real MQTT/PostgreSQL; no shared fault injection')
    try:
        anchor = create('anchor', 'alpine', ['--network', 'none'], ['sleep', '1800'])
        namespace = call(['docker', 'exec', anchor, 'readlink', '/proc/self/ns/net'])
        network = ['--network', 'container:' + anchor]
        uid = f'{os.getuid()}:{os.getgid()}'
        create('broker', 'eclipse-mosquitto:2', network + ['--user', uid,
               '-v', str(output / 'mosquitto.conf') + ':/qa.conf:ro'], ['mosquitto', '-c', '/qa.conf'])
        # A separate broker process prevents the demo anonymous listener from
        # bypassing mTLS ACLs through a shared topic plane.
        create('tls-broker', 'eclipse-mosquitto:2', network + ['--user', uid,
               '-v', str(private) + ':/qa:ro'], ['mosquitto', '-c', '/qa/tls.conf'])
        db = create('database', 'timescale/timescaledb:latest-pg15', network + [
            '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', '-e', 'POSTGRES_DB=ems',
            '-e', 'PGDATA=/var/lib/postgresql/data/pgdata', '-e', 'TIMESCALEDB_TELEMETRY=off',
            '--tmpfs', '/var/lib/postgresql/data:rw,size=256m',
            '--tmpfs', '/qa-db-quota:rw,size=16m',
            '--tmpfs', '/run/pg-tls:rw,size=1m', '-v',str(private/'pg-server')+':/qa-pg:ro',
            '-v', str(source / 'infra/timescaledb/init.sql') + ':/docker-entrypoint-initdb.d/01.sql:ro'],
            ['postgres', '-c', 'shared_buffers=32MB', '-c', 'max_connections=20'])
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            ready = subprocess.run(['docker', 'exec', db, 'psql', '-h', '127.0.0.1', '-U', 'postgres', '-d', 'ems', '-At', '-c',
                                    "SELECT to_regclass('public.electricity_measurements') IS NOT NULL"],
                                   capture_output=True, text=True, timeout=5)
            if ready.returncode == 0 and ready.stdout.strip() == 't':
                break
            time.sleep(.2)
        else:
            raise TimeoutError('private database startup')
        migration = (source / 'infra/timescaledb/migrations/019_edge_committed_receipts.sql').read_text()
        for index in range(2):
            text = call(['docker', 'exec', '-i', db, 'psql', '-U', 'postgres', '-d', 'ems', '-v', 'ON_ERROR_STOP=1'],
                        input_text=migration)
            (output / f'migration-{index + 1}.log').write_text(text)
        for index in range(2):
            text=call(['docker','exec','-i',db,'psql','-U','postgres','-d','ems','-v','ON_ERROR_STOP=1'],
                      input_text=(source/'infra/timescaledb/migrations/020_edge_synchronous_wal.sql').read_text())
            (output/f'migration020-{index+1}.log').write_text(text)
        for index in range(2):
            text=call(['docker','exec','-i',db,'psql','-U','postgres','-d','ems','-v','ON_ERROR_STOP=1'],
                      input_text=(source/'infra/timescaledb/migrations/021_edge_tls_wal.sql').read_text())
            (output/f'migration021-{index+1}.log').write_text(text)
        provision_pg_tls(db,call)
        from private_wal import PrivateWal
        if suite=='critical':
            from private_critical import PrivateCritical,OPERATIONS
            wal_class=PrivateCritical
        elif suite=='wal-security':
            from private_wal_security import PrivateWalSecurity,SECURE_OPERATIONS
            wal_class=PrivateWalSecurity
        else:wal_class=PrivateWal
        wal=wal_class(private,output,owned,call,create,network,'timescale/timescaledb:latest-pg15',uid,
                       atomic_host_text,read_worker_bytes,tls=True)
        wal.provision(db)
        worker = create('worker', 'ems-receipts-test-20261112', network + [
            '--user', uid, '-e', 'PYTHONDONTWRITEBYTECODE=1', '-e', 'EMS_V2_DEMO_NETNS=' + namespace,
            '-e', 'EDGE_V2_TEST_DSN=postgresql://postgres@127.0.0.1:5432/ems',
            '-e', 'PYTHONPATH=/app/services/delta:/app/services/edge-receiver',
            '-e', 'COVERAGE_FILE=/evidence/receiver.coverage',
            '-e', 'EDGE_V2_EVIDENCE=/evidence',
            '-e', 'EDGE_V2_TEST_PKI=/qa', '-v', str(private) + ':/qa:ro',
            '-e', 'EDGE_V2_LIFECYCLE='+('1' if suite=='lifecycle' else '0'),
            '-e', 'EDGE_V2_RESTORE_LOAD='+('1' if suite=='restore-load' else '0'),
            '-e', 'EDGE_V2_RESTORED_DSN=postgresql://postgres@127.0.0.1:5432/ems_restore',
            '-e', 'EDGE_V2_WAL_PITR='+('1' if suite=='wal-pitr' else '0'),
            '-e', 'EDGE_V2_CUTOVER='+('1' if suite=='cutover' else '0'),
            '-e', 'EDGE_V2_INTEGRITY='+('1' if suite=='integrity' else '0'),
            '-e', 'EDGE_V2_CRITICAL='+('1' if suite=='critical' else '0'),
            '-e', 'EDGE_V2_WAL_SECURITY='+('1' if suite=='wal-security' else '0'),
            '-e', 'EDGE_V2_PITR_DSN=postgresql://postgres@127.0.0.1:5433/ems',
            '-v', str(source) + ':/app:ro', '-v', str(output) + ':/evidence', '-w', '/app'], ['sleep', '1800'])
        tests = suite_targets(suite)
        # Snapshot contains no shared-stack conftest. Preserve Delta's private
        # field fixtures so their dedicated environment gate can skip safely.
        cmd = ['docker', 'exec', worker, 'python', '-m', 'pytest', '-c', '/app/services/delta/pytest.ini', *tests,
               '-q', '-p', 'no:cacheprovider', '--cov=edge_receiver', '--cov=delta_device',
               '--cov-report=term-missing', '--cov-report=json:/evidence/receiver-coverage.json',
               '--junitxml=/evidence/integration.xml']
        if suite == 'baseline':
            cmd.append('--cov-fail-under=80')
        # A targeted fault suite reports exercised paths, not full-regression coverage.
        if suite in ('lifecycle','restore-load','wal-pitr','wal-security','critical'):
            receipts=[]
            # Read the held FD, never a path the worker can swap to a symlink.
            with tempfile.TemporaryFile(mode='w+',dir=output) as log:
                process=subprocess.Popen(cmd,text=True,stdout=log,stderr=subprocess.STDOUT)
                try:
                    deadline=time.monotonic()+300
                    handled=set()
                    while process.poll() is None:
                        if time.monotonic()>deadline:
                            raise TimeoutError('private lifecycle suite timeout')
                        for path in output.glob('control-*.request.json'):
                            if path.name in handled:
                                continue
                            request=read_control_request(path)
                            expected='control-'+request.get('request_id','')+'.request.json'
                            if path.name!=expected:
                                raise ValueError('control filename mismatch')
                            if suite=='critical':
                                validate_secure_request(request,OPERATIONS)
                                result_control=wal.control(request)
                            elif suite=='wal-security':
                                validate_secure_request(request,SECURE_OPERATIONS)
                                result_control=wal.control(request)
                            elif suite=='wal-pitr' and request.get('op') in WAL_OPERATIONS:
                                validate_wal_request(request)
                                result_control=wal.control(request)
                            else:
                                result_control=lifecycle_control(request,owned,call,private,output)
                            response=path.with_name(path.name.replace('.request.json','.response.json'))
                            publish_control_response(response,result_control)
                            receipts.append(result_control);handled.add(path.name)
                            publish_control_response(output/'lifecycle-control.json',receipts)
                        time.sleep(.03)
                    log.flush();log.seek(0)
                    done=subprocess.CompletedProcess(cmd,process.returncode,log.read(),'')
                finally:
                    if process.poll() is None:
                        process.terminate()
                        try:process.wait(timeout=3)
                        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
                    log.flush();log.seek(0)
                    atomic_host_text(output/'integration.log',log.read())
        else:
            done = subprocess.run(cmd, text=True, capture_output=True, timeout=600)
        atomic_host_text(output / 'integration.log',done.stdout + done.stderr)
        publish_control_response(output / 'test-command.json',cmd)
        xml = read_worker_file(output/'integration.xml',8*1024*1024)
        if suite == 'faults':
            proof_path = output/'database-timeout.json'
            assessment = assess_fault_report(xml,done.returncode,json.loads(read_worker_file(proof_path,65536)) if proof_path.exists() else {})
        elif suite == 'resilience':
            names=('crash-after_retire','crash-before_commit','crash-after_commit','sqlite-busy',
                   'sqlite-readonly','online-backup','tls-server-untrusted-ca','tls-server-wrong-host','tls-server-expired')
            proof={name:json.loads(read_worker_file(output/(name+'.json'),65536)) for name in names if (output/(name+'.json')).exists()}
            assessment=assess_resilience_report(xml,done.returncode,proof)
        elif suite == 'lifecycle':
            names=('corruption-header','corruption-truncated','corruption-zero-length','corruption-empty-sqlite',
                   'broker-restart','certificate-rotation-revocation')
            proof={name:json.loads(read_worker_file(output/(name+'.json'),65536)) for name in names if (output/(name+'.json')).exists()}
            assessment=assess_lifecycle_report(xml,done.returncode,proof)
        elif suite == 'restore-load':
            names=('database-restore','receiver-overload','live-backlog-delay')
            proof={name:json.loads(read_worker_file(output/(name+'.json'),65536)) for name in names if (output/(name+'.json')).exists()}
            assessment=assess_restore_load_report(xml,done.returncode,proof)
        elif suite=='wal-pitr':
            proof=json.loads(read_worker_file(output/'wal-pitr.json',131072)) if (output/'wal-pitr.json').exists() else {}
            assessment=assess_wal_report(xml,done.returncode,proof)
        elif suite=='cutover':
            names=['field-limited-role','duplicate-client-id']+['conversion-'+s for s in ('after_first_row','before_publish','after_publish')]
            proof={name:json.loads(read_worker_file(output/(name+'.json'),65536)) for name in names if (output/(name+'.json')).exists()}
            assessment=assess_cutover_report(xml,done.returncode,proof)
        elif suite=='integrity':
            names=['logical-'+k for k in ('sequence-rollback','clock-rollback','missing-audit','audit-hash','audit-state','orphan-audit','audit-sequence')]
            names += ['malformed-'+k for k in ('bad-hash','duplicate-id','duplicate-key','invalid-utf8','excess-depth')]+['sigterm-db-wait']
            proof={name:json.loads(read_worker_file(output/(name+'.json'),65536)) for name in names if (output/(name+'.json')).exists()}
            assessment=assess_integrity_report(xml,done.returncode,proof)
        elif suite=='critical':
            from critical_report import assess
            names=['central-data-full','slot-reseed','timeline-pitr']
            proof={name:json.loads(read_worker_file(output/(name+'.json'),131072)) for name in names if (output/(name+'.json')).exists()}
            assessment=assess(xml,done.returncode,proof)
        elif suite=='wal-security':
            names=['db-wal-tls-positive','recovery-inputs','wal-enospc']
            names += ['wal-gate-'+c for c in ('plaintext','wrong_role')]
            names += ['db-tls-'+c for c in ('wrong_ca','wrong_host','expired','missing_client','untrusted_client','expired_client','wrong_user')]
            names += ['wal-tls-'+c for c in ('wrong_ca','wrong_host','expired','missing_client','untrusted_client','expired_client','wrong_user','plaintext')]
            proof={name:json.loads(read_worker_file(output/(name+'.json'),131072)) for name in names if (output/(name+'.json')).exists()}
            assessment=assess_wal_security_report(xml,done.returncode,proof)
            atomic_host_text(output/'wal-job.log',call(['docker','exec',wal.wal,'cat','/tmp/wal.log']))
        else:
            assessment = assess_boundary_report(xml,done.returncode)
        publish_control_response(output/'suite-assessment.json',assessment)
        result.update(passed=assessment['passed'],exit_code=done.returncode,namespace=namespace,suite_assessment=assessment)
        print(done.stdout + done.stderr, flush=True)
    except Exception as exc:
        result['error_kind'] = type(exc).__name__
        raise
    finally:
        if suite in ('wal-security','critical') and 'wal' in locals() and wal.wal:
            try:atomic_host_text(output/'wal-job.log',call(['docker','exec',wal.wal,'cat','/tmp/wal.log'],timeout=5))
            except Exception as exc:result['wal_job_log_error_kind']=type(exc).__name__
        cleanup = cleanup_owned(owned, output)
        result['cleanup'] = cleanup
        result['sources_unchanged'] = all(hashlib.sha256((root / p).read_bytes()).hexdigest() == value
                                         for p, value in hashes.items())
        try:
            certificates={p.relative_to(private).as_posix():call(['openssl','x509','-in',str(p),'-noout',
                '-fingerprint','-sha256','-subject','-issuer','-dates']) for p in (private/'pg-client').glob('*.crt')}
            publish_control_response(output/'pg-certificate-metadata.json',certificates)
        except Exception as exc:result['certificate_metadata_error_kind']=type(exc).__name__
        result['passed'] = result['passed'] and all(x['passed'] and x['logs_passed'] for x in cleanup) and result['sources_unchanged']
        publish_control_response(output / 'result.json',result)
    return result['passed']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--suite', choices=('baseline', 'faults','resilience','lifecycle','restore-load','wal-pitr','cutover','integrity','wal-security','critical'), default='baseline')
    args = parser.parse_args()
    raise SystemExit(0 if main(args.output, args.suite) else 1)
