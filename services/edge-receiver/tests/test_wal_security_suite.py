"""Fixed real reports: TLS/error cause/storage/recovery proof is mandatory."""
import json
from pathlib import Path
import sys
from uuid import uuid4
import xml.etree.ElementTree as ET

import pytest

sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
from private_wal_security import SECURE_OPERATIONS
from verify_private import assess_wal_security_report,suite_targets,validate_secure_request


def fixture():
    folder=Path(__file__).parent/'fixtures'
    return ET.parse(folder/'wal-security-report.xml').getroot(),json.loads((folder/'wal-security-proof.json').read_text())


def test_wal_security_selects_only_new_short_scenarios_and_original_boundary():
    assert suite_targets('wal-security')==('/app/tests/integration/test_edge_wal_security.py',
        '/app/services/delta/tests/test_bench_slot_boundary.py'), 'suite broadened into baseline or long soak'


def test_real_wal_security_report_with_complete_proof_passes():
    root,proof=fixture()
    assert assess_wal_security_report(ET.tostring(root,encoding='unicode'),0,proof)['passed'], 'actual complete evidence rejected'


@pytest.mark.parametrize('mutation',['missing-case','substituted-case','skipped','db-cause-wrong','nonexistent-role',
    'no-client-required','no-server-client-reject','expired-client-wrong-cause','unverified-wal-expiry',
    'wrong-probe-kind','wal-positive-plaintext','wal-positive-wrong-role','fake-connected-peer','unsafe-peer-accepted',
    'not-enospc','child-not-failed','host-disk-instead-of-tmpfs','tmpfs-lost','no-slot-backlog','different-slot',
    'no-flush-fence','source-deleted','duplicate-row','same-cluster-as-foreign','missing-expected-cluster',
    'foreign-checksum-bad','corrupt-backup-accepted','corrupt-wal-accepted','foreign-wal-accepted',
    'foreign-bundle-accepted','pristine-overwritten','missing-evidence'])
def test_wal_security_gate_rejects_incomplete_or_false_evidence(mutation):
    root,proof=fixture();cases=list(root.iter('testcase'))
    if mutation=='missing-case':root.find('testsuite').remove(cases[0])
    elif mutation=='substituted-case':cases[0].set('name','unrelated_old_test')
    elif mutation=='skipped':ET.SubElement(cases[0],'skipped')
    elif mutation=='db-cause-wrong':proof['db-tls-expired']['actual_error']['verify_code']=19
    elif mutation=='nonexistent-role':proof['db-tls-wrong_user']['actual_error']['certificate_identity_rejected']=False
    elif mutation=='no-client-required':proof['db-tls-missing_client']['actual_error']['client_certificate_required']=False
    elif mutation=='no-server-client-reject':proof['db-tls-untrusted_client']['actual_error']['server_rejected_client_certificate']=False
    elif mutation=='expired-client-wrong-cause':proof['db-tls-expired_client']['actual_error']['client_certificate_verify_code']=20
    elif mutation=='unverified-wal-expiry':proof['wal-tls-expired']['probe']['tls_verify_code']=None
    elif mutation=='wrong-probe-kind':proof['wal-tls-wrong_user']['probe']['kind']='wrong_ca'
    elif mutation=='wal-positive-plaintext':proof['db-wal-tls-positive']['wal_peer']['peer_tls']=False
    elif mutation=='wal-positive-wrong-role':proof['db-wal-tls-positive']['wal_peer']['peer_role']='postgres'
    elif mutation=='fake-connected-peer':proof['wal-gate-plaintext']['gate']['peer_connected']=False
    elif mutation=='unsafe-peer-accepted':proof['wal-gate-plaintext']['gate']['observed']['guard']=True
    elif mutation=='not-enospc':proof['wal-enospc']['failure']['actual_enospc']=False
    elif mutation=='child-not-failed':proof['wal-enospc']['failure']['child_exit']=0
    elif mutation=='host-disk-instead-of-tmpfs':proof['wal-enospc']['failure']['archive_limit_bytes']=0
    elif mutation=='tmpfs-lost':proof['wal-enospc']['failure']['container_kept_running']=False
    elif mutation=='no-slot-backlog':proof['wal-enospc']['failure']['after']['lag_bytes']=0
    elif mutation=='different-slot':proof['wal-enospc']['recovered']['slot']['slot']='new-slot'
    elif mutation=='no-flush-fence':proof['wal-enospc']['caught_up']['flush_fence_satisfied']=False
    elif mutation=='source-deleted':proof['wal-enospc']['source_preserved']=False
    elif mutation=='duplicate-row':proof['wal-enospc']['rows']=2
    elif mutation=='same-cluster-as-foreign':proof['recovery-inputs']['foreign_system_id']=proof['recovery-inputs']['expected_system_id']
    elif mutation=='missing-expected-cluster':proof['recovery-inputs']['expected_system_id']=None
    elif mutation=='foreign-checksum-bad':proof['recovery-inputs']['foreign_bundle_checksum_valid']=False
    elif mutation=='corrupt-backup-accepted':proof['recovery-inputs']['corrupt_backup_checksum_rejected']=False
    elif mutation=='corrupt-wal-accepted':proof['recovery-inputs']['corrupt_later_wal_crc_rejected']=False
    elif mutation=='foreign-wal-accepted':proof['recovery-inputs']['foreign_wal_system_id_rejected']=False
    elif mutation=='foreign-bundle-accepted':proof['recovery-inputs']['valid_foreign_bundle_rejected_before_start']=False
    elif mutation=='pristine-overwritten':proof['recovery-inputs']['pristine_inputs_unchanged']=False
    else:proof.pop('wal-enospc')
    assert not assess_wal_security_report(ET.tostring(root,encoding='unicode'),0,proof)['passed'], f'{mutation} falsely passed'


@pytest.mark.parametrize('key',['cid','path','sql','expected_system_id'])
def test_secure_control_rejects_worker_selected_targets_commands_and_cluster_identity(key):
    request=dict(request_id=str(uuid4()),op='recovery_matrix')
    validate_secure_request(request,SECURE_OPERATIONS)
    with pytest.raises(ValueError):validate_secure_request(dict(request,**{key:'arbitrary'}),SECURE_OPERATIONS)
