"""New cutover cases and evidence cannot be replaced by older passing tests."""
from copy import deepcopy
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import pytest

sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
import verify_private as verifier


def test_cutover_suite_selects_new_cases_plus_original_boundary_only():
    assert verifier.suite_targets('cutover')==('/app/tests/integration/test_edge_cutover.py',
        '/app/services/delta/tests/test_bench_slot_boundary.py'), 'cutover suite is missing or broadens into soak'


def fixture():
    root=ET.Element('testsuite')
    for c in ET.parse(Path(__file__).parent/'fixtures/faults-and-boundary.xml').getroot():
        if c.get('classname','').endswith('test_bench_slot_boundary'):root.append(c)
    names=['test_field_mtls_limited_database_role_repairs_missing_projection_after_permission_recovery',
        'test_duplicate_mtls_client_id_disconnect_keeps_source_and_rejects_old_ack_after_reconnect']
    names += [f'test_v1_conversion_sigkill_preserves_source_and_publishes_only_complete_v2[{stage}]'
              for stage in ('after_first_row','before_publish','after_publish')]
    for name in names:ET.SubElement(root,'testcase',name=name,classname='test_edge_cutover')
    proofs={'field-limited-role':dict(passed=True,administrative_flags=dict(rolsuper=False,rolreplication=False,rolcreatedb=False,rolcreaterole=False),
        denied_operations=4,actual_exception='InsufficientPrivilegeError',source_preserved_during_denial=True,
        receipt_timestamp_unchanged=True,mqtt_mtls=True,ack_durability='sync_wal',rows=1,pending_end=0),
        'duplicate-client-id':dict(passed=True,actual_disconnect=True,inflight_at_collision=True,old_challenge='old',new_challenge='new',
            observed_disconnect=dict(ready=True,challenge='old',batch_id='inflight-batch'),
            old_ack_observed=True,old_ack_accepted=False,source_preserved=True,central_rows=[1,1],pending_end=0)}
    for stage in ('after_first_row','before_publish','after_publish'):
        proofs['conversion-'+stage]=dict(passed=True,stage=stage,child_exit=-9,published_at_crash=stage=='after_publish',
            original_sha256='a'*64,source_unchanged=True,rows=2,central_rows=[1,1],pending_end=0,stable_mapping=True)
    return root,proofs


def test_complete_cutover_proof_passes():
    root,proof=fixture()
    assert verifier.assess_cutover_report(ET.tostring(root,encoding='unicode'),0,proof)['passed'], 'complete evidence rejected'


@pytest.mark.parametrize('mutation',['missing-case','replaced-case','skipped','root-role','local-only',
    'no-permission-error','source-deleted','fake-crash','partial-published','migration-duplicates','source-modified',
    'no-disconnect','not-inflight','timeout-already-reset','different-live-session','no-new-challenge','old-ack-accepted','absent-evidence'])
def test_cutover_gate_rejects_incomplete_or_false_result(mutation):
    root,proof=fixture();proof=deepcopy(proof)
    if mutation=='missing-case':root.remove(root[-1])
    elif mutation=='replaced-case':root[-1].set('name','old_passing_case')
    elif mutation=='skipped':ET.SubElement(root[-1],'skipped')
    elif mutation=='root-role':proof['field-limited-role']['administrative_flags']['rolsuper']=True
    elif mutation=='local-only':proof['field-limited-role']['ack_durability']='local'
    elif mutation=='no-permission-error':proof['field-limited-role']['actual_exception']='TimeoutError'
    elif mutation=='source-deleted':proof['field-limited-role']['source_preserved_during_denial']=False
    elif mutation=='fake-crash':proof['conversion-before_publish']['child_exit']=0
    elif mutation=='partial-published':proof['conversion-after_first_row']['published_at_crash']=True
    elif mutation=='migration-duplicates':proof['conversion-after_publish']['central_rows']=[2,1]
    elif mutation=='source-modified':proof['conversion-before_publish']['source_unchanged']=False
    elif mutation=='no-disconnect':proof['duplicate-client-id']['actual_disconnect']=False
    elif mutation=='not-inflight':proof['duplicate-client-id']['inflight_at_collision']=False
    elif mutation=='timeout-already-reset':proof['duplicate-client-id']['observed_disconnect']['ready']=False
    elif mutation=='different-live-session':proof['duplicate-client-id']['observed_disconnect']['challenge']='already-reset'
    elif mutation=='no-new-challenge':proof['duplicate-client-id']['new_challenge']=None
    elif mutation=='old-ack-accepted':proof['duplicate-client-id']['old_ack_accepted']=True
    else:proof.pop('conversion-after_publish')
    assert not verifier.assess_cutover_report(ET.tostring(root,encoding='unicode'),0,proof)['passed'], f'{mutation} falsely passed'
