"""Owned broker controls and strict lifecycle proof fail closed."""
import json
from pathlib import Path
import sys
from uuid import uuid4
import xml.etree.ElementTree as ET

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from verify_private import (assess_lifecycle_report,control_target,publish_control_response,
                            read_control_request,read_worker_file,atomic_host_text,suite_targets)


def test_lifecycle_scope_is_short_and_includes_original_boundary():
    assert suite_targets('lifecycle')==('/app/tests/integration/test_edge_lifecycle.py',
        '/app/services/delta/tests/test_reliable_corruption.py','/app/services/delta/tests/test_bench_slot_boundary.py'), 'unbounded lifecycle suite'


@pytest.mark.parametrize('op,expected',[('broker_stop','own-demo'),('broker_start','own-demo'),('revoke_old_client','own-tls')])
def test_control_targets_only_current_owned_container(op,expected):
    assert control_target(dict(request_id=str(uuid4()),op=op),[('broker','own-demo'),('tls-broker','own-tls')])==expected, 'wrong lifecycle target'


@pytest.mark.parametrize('control_request',[{},dict(request_id='not-uuid',op='broker_stop'),
    dict(request_id=str(uuid4()),op='docker_stop'),dict(request_id=str(uuid4()),op='broker_stop',container='shared'),
    dict(request_id=str(uuid4()),op=['broker_stop'])])
def test_control_rejects_untrusted_commands_ids_and_extra_fields(control_request):
    with pytest.raises((ValueError,TypeError)):
        control_target(control_request,[('broker','own-demo'),('tls-broker','own-tls')])


def test_control_never_falls_back_to_shared_when_owned_target_missing():
    with pytest.raises(ValueError):
        control_target(dict(request_id=str(uuid4()),op='broker_stop'),[])


def test_host_response_never_follows_worker_precreated_symlinks(tmp_path):
    outside=tmp_path/'host-file';outside.write_text('KEEP')
    response=tmp_path/'control.response.json'
    response.symlink_to(outside)
    response.with_suffix('.tmp').symlink_to(outside)
    publish_control_response(response,dict(passed=True))
    assert outside.read_text()=='KEEP', 'worker symlink allowed host file overwrite'
    assert not response.is_symlink() and json.loads(response.read_text())['passed'], 'response not atomically replaced'
    assert not list(tmp_path.glob('.host-control-*')), 'host temporary FD file leaked'


@pytest.mark.parametrize('name',['integration.log','worker.log','result.json','suite-assessment.json'])
def test_all_host_artifact_writes_replace_symlinks_without_touching_target(tmp_path,name):
    outside=tmp_path/'host-secret';outside.write_text('UNCHANGED')
    artifact=tmp_path/name;artifact.symlink_to(outside)
    atomic_host_text(artifact,'public-result')
    assert outside.read_text()=='UNCHANGED' and artifact.read_text()=='public-result', 'artifact write followed a worker symlink'


def test_host_artifact_reader_never_reads_worker_symlink_target(tmp_path):
    outside=tmp_path/'host-secret';outside.write_text('PRIVATE')
    artifact=tmp_path/'integration.xml';artifact.symlink_to(outside)
    with pytest.raises(OSError):read_worker_file(artifact,1024)


@pytest.mark.parametrize('kind',['symlink','oversize','directory'])
def test_request_reader_rejects_nonregular_or_unbounded_files(tmp_path,kind):
    path=tmp_path/'request.json'
    if kind=='symlink':
        target=tmp_path/'target';target.write_text('{}');path.symlink_to(target)
    elif kind=='oversize':path.write_text(' '*1025)
    else:path.mkdir()
    with pytest.raises((ValueError,OSError)):
        read_control_request(path)


def fixture():
    source=ET.parse(Path(__file__).parent/'fixtures/faults-and-boundary.xml').getroot()
    root=ET.Element('testsuite')
    for case in source:
        if case.get('classname','').endswith('test_bench_slot_boundary'):root.append(case)
    names=['test_real_broker_restart_keeps_tcp_acquisition_and_same_process_reconnects',
           'test_same_gateway_new_certificate_rotates_then_revoked_old_certificate_is_denied',
           'test_genuinely_new_path_still_initializes_and_sequences_from_one']
    proof={}
    for damage in ['header','truncated','zero-length','empty-sqlite']:
        names.append(f'test_damaged_existing_queue_fails_without_reset_or_modification[{damage}]')
        proof['corruption-'+damage]=dict(passed=True,damage=damage,empty_database_recreated=False,
                                         before_sha256='a'*64,after_sha256='a'*64)
    for name in names:ET.SubElement(root,'testcase',classname='tests.lifecycle',name=name)
    proof['broker-restart']=dict(passed=True,same_edge_process=True,tcp_samples_during_outage=3,
        projections_each=1,pending_end=0,broker_container_id='own',
        stopped=dict(passed=True,running=False,container_id='own',started_at='old'),
        started=dict(passed=True,running=True,container_id='own',started_at='new'))
    proof['certificate-rotation-revocation']=dict(passed=True,same_gateway='qa-edge',old_worked_before=True,
        new_worked_before=True,old_rejected_after=True,new_worked_after=True,active_old_session_disconnected=True,
        projections_each=1,pending_end=0,revocation=dict(passed=True,serial_revoked='01',crl_verified=True,revocation_verify_error=23))
    return root,proof


def test_lifecycle_assessment_accepts_complete_independent_fixture():
    root,proof=fixture()
    assert assess_lifecycle_report(ET.tostring(root,encoding='unicode'),0,proof)['passed'], 'complete evidence rejected'


@pytest.mark.parametrize('mutation',['skip','missing','duplicate','file-changed','broker-not-restarted',
    'no-tcp-collection','no-crl','wrong-revocation-cause','active-old-session-not-disconnected','new-cert-failed'])
def test_lifecycle_assessment_rejects_incomplete_or_unproven_result(mutation):
    root,proof=fixture()
    if mutation=='skip':ET.SubElement(root[-1],'skipped')
    elif mutation=='missing':root.remove(root[-1])
    elif mutation=='duplicate':root.append(ET.fromstring(ET.tostring(root[-1])))
    elif mutation=='file-changed':proof['corruption-header']['after_sha256']='b'*64
    elif mutation=='broker-not-restarted':proof['broker-restart']['started']['started_at']='old'
    elif mutation=='no-tcp-collection':proof['broker-restart']['tcp_samples_during_outage']=0
    elif mutation=='no-crl':proof['certificate-rotation-revocation']['revocation']['crl_verified']=False
    elif mutation=='wrong-revocation-cause':proof['certificate-rotation-revocation']['revocation']['revocation_verify_error']=10
    elif mutation=='active-old-session-not-disconnected':proof['certificate-rotation-revocation']['active_old_session_disconnected']=False
    else:proof['certificate-rotation-revocation']['new_worked_after']=False
    assert not assess_lifecycle_report(ET.tostring(root,encoding='unicode'),0,proof)['passed'], f'{mutation} falsely passed'
