"""Keep weak earlier evidence and mutations from becoming a passing release."""
import copy
import json
from pathlib import Path
import sys
from uuid import uuid4
import xml.etree.ElementTree as ET

import pytest

sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
from critical_report import assess
from private_critical import OPERATIONS
from verify_private import suite_targets,validate_secure_request


def fixture():
    folder=Path(__file__).parent/'fixtures'
    return (folder/'critical-report.xml').read_text(),json.loads((folder/'critical-proof.json').read_text())


def test_critical_suite_is_exactly_three_new_cases_and_fixed_boundary():
    assert suite_targets('critical')==('/app/tests/integration/test_edge_critical.py',
        '/app/services/delta/tests/test_bench_slot_boundary.py'), 'critical suite grew into long tests'


def test_real_critical_report_and_independent_proofs_pass():
    xml,proof=fixture()
    assert assess(xml,0,proof)['passed'], 'complete real critical evidence rejected'


def test_earlier_passing_report_without_backup_pickup_gap_proof_is_rejected():
    folder=Path(__file__).parent/'fixtures';xml=(folder/'critical-report.xml').read_text()
    old=json.loads((folder/'critical-before-gap-proof.json').read_text())
    assert not assess(xml,0,old)['passed'], 'earlier weak passing evidence admitted without chain PITR'


@pytest.mark.parametrize('kind',['missing-case','substitute','skip','not-real-full','wrong-quota','full-acked',
    'slot-not-lost','slot-still-valid','no-retryable','unverified-base','not-reserved','no-gap-checkpoint',
    'no-chain-pitr','wrong-marker','reused-lost-slot','tls-downgrade','not-rotated','duplicate',
    'same-timeline','wrong-pinned-branch','latest-allowed','no-counterexample','changed-inputs','missing-proof'])
def test_critical_gate_rejects_false_or_incomplete_evidence(kind):
    xml,proof=fixture();root=ET.fromstring(xml);cases=list(root.iter('testcase'))
    central=proof['central-data-full'];slot=proof['slot-reseed'];timeline=proof['timeline-pitr']
    if kind=='missing-case':root.find('testsuite').remove(cases[0])
    elif kind=='substitute':cases[0].set('name','unrelated_old_case')
    elif kind=='skip':ET.SubElement(cases[0],'skipped')
    elif kind=='not-real-full':central['freed']['actual_relation_enospc']=False
    elif kind=='wrong-quota':central['full']['limit_bytes']=256*1024**3
    elif kind=='full-acked':central['statuses_during_failure']=['committed']
    elif kind=='slot-not-lost':slot['lost']['lost']['wal_status']='reserved'
    elif kind=='slot-still-valid':slot['lost']['lost']['restart_lsn']='0/1000000'
    elif kind=='no-retryable':slot['statuses_during_failure']=[]
    elif kind=='unverified-base':slot['rebuilt']['base_verified']=False
    elif kind=='not-reserved':slot['rebuilt']['reserved_before_backup']=None
    elif kind=='no-gap-checkpoint':slot['rebuilt']['forced_gap_segments']=0
    elif kind=='no-chain-pitr':slot['rebuilt']['reseed_chain_pitr_verified']=False
    elif kind=='wrong-marker':slot['rebuilt']['recovered_gap_marker']='other'
    elif kind=='reused-lost-slot':slot['rebuilt']['replacement_slot']['slot']='ems_archive_slot'
    elif kind=='tls-downgrade':slot['rebuilt']['replacement_slot']['peer_tls']=False
    elif kind=='not-rotated':slot['generation_rotated']=False
    elif kind=='duplicate':slot['rows']=[1,2]
    elif kind=='same-timeline':timeline['branch_timelines']=[2,2]
    elif kind=='wrong-pinned-branch':timeline['pinned_rows']='branch-three'
    elif kind=='latest-allowed':timeline['latest_rejected']=False
    elif kind=='no-counterexample':timeline['unsafe_latest_rows']='branch-two'
    elif kind=='changed-inputs':timeline['pristine_inputs_unchanged']=False
    elif kind=='missing-proof':proof.clear()
    assert not assess(ET.tostring(root,encoding='unicode'),0,proof)['passed'], 'false evidence admitted: '+kind


@pytest.mark.parametrize('field',['cid','sql','path','timeline'])
def test_critical_control_rejects_worker_selected_resource_or_recovery_input(field):
    with pytest.raises(ValueError):
        validate_secure_request(dict(request_id=str(uuid4()),op='timeline_matrix',**{field:'untrusted'}),OPERATIONS)
