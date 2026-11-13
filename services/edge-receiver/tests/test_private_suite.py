"""Private controller offers explicit bounded suites, never arbitrary paths."""
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import xml.etree.ElementTree as ET
from verify_private import suite_targets, assess_fault_report, assess_boundary_report


def test_resilience_suite_selects_only_new_short_cases_and_original_boundary():
    assert suite_targets('resilience')==('/app/tests/integration/test_edge_resilience.py',
        '/app/services/delta/tests/test_reliable_resilience.py',
        '/app/services/delta/tests/test_bench_slot_boundary.py'), 'resilience scope includes long tests or omits required cases'


def resilience_fixture():
    # Independent expected case identities and proof, not controller constants.
    root=ET.Element('testsuite')
    for c in ET.fromstring(valid_report()):
        if c.get('classname','').endswith('test_bench_slot_boundary'):
            root.append(c)
    evidence={}
    for stage in ['after_retire','before_commit','after_commit']:
        ET.SubElement(root,'testcase',classname='tests.test_reliable_resilience',
            name='test_sigkill_during_rotation_recovers_exact_transaction_boundary['+stage+']')
        after=stage=='after_commit'
        evidence['crash-'+stage]=dict(passed=True,child_exit=-9,observed=dict(stage=stage,journal_bytes=512,main_file_changed=True,
            baseline_stage='after_constructor',baseline_sha256='0'*64,observed_sha256='1'*64),
            recovered_sequence=2 if after else 1,next_sequence=3 if after else 2,
            retirement=dict(unconfirmed_evicted_total=1 if after else 0),integrity='ok',committed_identity_preserved=True if after else None)
    for name in ['test_sqlite_busy_retains_old_sample_and_recovers_without_false_retirement',
        'test_readonly_database_retains_old_sample_then_recovers',
        'test_online_backup_remains_coherent_while_rotation_commits_during_copy']:
        ET.SubElement(root,'testcase',classname='tests.test_reliable_resilience',name=name)
    evidence['sqlite-busy']=dict(passed=True,sqlite_error='SQLITE_BUSY',old_preserved=True,next_sequence=2)
    evidence['sqlite-readonly']=dict(passed=True,sqlite_error='SQLITE_READONLY',old_preserved=True,next_sequence=2)
    evidence['online-backup']=dict(passed=True,rotation_committed_during_copy=True,retained_sequences=[16,17,18,19,20],
        retirement=dict(unconfirmed_evicted_total=15),integrity='ok')
    for case,port,ca,code in [('untrusted-ca',8886,'rogue-ca.crt',19),('wrong-host',8887,'ca.crt',64),('expired',8888,'ca.crt',10)]:
        ET.SubElement(root,'testcase',classname='',name=f'test_v2_invalid_server_certificate_keeps_original_then_recovers_once[{case}-{port}-{ca}-{code}]')
        evidence['tls-server-'+case]=dict(passed=True,verify_code=code,real_client_rejection=True,
            source_preserved_during_failure=True,projections=1,pending_end=0)
    return root,evidence


def test_resilience_assessment_accepts_complete_independent_proof():
    from verify_private import assess_resilience_report
    root,evidence=resilience_fixture()
    assert assess_resilience_report(ET.tostring(root,encoding='unicode'),0,evidence)['passed'], 'valid 44-case evidence rejected'


@pytest.mark.parametrize('mutation',['skip','missing-case','duplicate-case','crash-was-not-sigkill','no-dirty-pages',
    'wrong-crash-recovery','no-real-lock','backup-not-concurrent','wrong-certificate-cause','no-real-client-rejection','missing-proof'])
def test_resilience_assessment_rejects_incomplete_or_wrong_fault_proof(mutation):
    from verify_private import assess_resilience_report
    root,evidence=resilience_fixture()
    if mutation=='skip':ET.SubElement(root[-1],'skipped')
    elif mutation=='missing-case':root.remove(root[-1])
    elif mutation=='duplicate-case':root.append(ET.fromstring(ET.tostring(root[-1])))
    elif mutation=='crash-was-not-sigkill':evidence['crash-after_retire']['child_exit']=0
    elif mutation=='no-dirty-pages':evidence['crash-before_commit']['observed']['main_file_changed']=False
    elif mutation=='wrong-crash-recovery':evidence['crash-before_commit']['recovered_sequence']=2
    elif mutation=='no-real-lock':evidence['sqlite-busy']['sqlite_error']='injected'
    elif mutation=='backup-not-concurrent':evidence['online-backup']['rotation_committed_during_copy']=False
    elif mutation=='wrong-certificate-cause':evidence['tls-server-expired']['verify_code']=64
    elif mutation=='no-real-client-rejection':evidence['tls-server-wrong-host']['real_client_rejection']=False
    elif mutation=='missing-proof':evidence.pop('online-backup')
    assert not assess_resilience_report(ET.tostring(root,encoding='unicode'),0,evidence)['passed'], f'{mutation} falsely passed'


@pytest.mark.parametrize('mutation',['constructor-only-change','wrong-baseline-stage','committed-identity-changed'])
def test_crash_evidence_cannot_relabel_constructor_writes_or_regenerated_identity(mutation):
    from verify_private import assess_resilience_report
    root,evidence=resilience_fixture()
    if mutation=='constructor-only-change':
        observed=evidence['crash-after_retire']['observed']
        observed['observed_sha256']=observed['baseline_sha256']
        # A claimed boolean alone is insufficient to prove any actual change.
        observed['main_file_changed']=True
    elif mutation=='wrong-baseline-stage':
        evidence['crash-before_commit']['observed']['baseline_stage']='before_constructor'
    else:
        evidence['crash-after_commit']['committed_identity_preserved']=False
    assert not assess_resilience_report(ET.tostring(root,encoding='unicode'),0,evidence)['passed'], f'{mutation} falsely passed'


def test_fault_suite_does_not_collect_baseline_or_soak():
    assert suite_targets('faults') == ('/app/tests/integration/test_edge_receipts_faults.py',
                                     '/app/services/delta/tests/test_bench_slot_boundary.py'), 'fault/boundary regression omitted'


def test_baseline_suite_remains_unchanged():
    assert suite_targets('baseline') == (
        '/app/tests/integration/test_edge_receipts.py',
        '/app/tests/integration/test_edge_receipts_mqtt.py',
        '/app/services/edge-receiver/tests', '/app/services/delta/tests'), 'baseline selection changed'


def test_unknown_suite_is_rejected():
    with pytest.raises(ValueError):
        suite_targets('arbitrary/path')


def valid_report():
    return (Path(__file__).parent/'fixtures/faults-and-boundary.xml').read_text()


def valid_timeout():
    return dict(passed=True,true_database_retryable_observed=True,database_exception_kinds=['TimeoutError'],
                after_failure=[0,0],receipts=1,projections=1,pending_end=0,
                received_statuses=[dict(status='retryable',error_code='database'),dict(status='committed')])


def test_complete_real_regression_fixture_and_database_proof_pass():
    assert assess_fault_report(valid_report(),0,valid_timeout())['passed'], 'complete 43-case proof rejected'


@pytest.mark.parametrize('mutation', ['skip', 'missing-boundary', 'duplicate-fault', 'nonzero-exit',
                                     'same-group-duplicate', 'same-group-unknown'])
def test_exit_zero_or_test_count_cannot_conceal_missing_regression(mutation):
    root = ET.fromstring(valid_report())
    if mutation == 'skip':
        ET.SubElement(list(root)[0],'skipped')
    elif mutation == 'missing-boundary':
        root.remove(next(c for c in root if c.get('name','').startswith('test_original_5109_boundary')))
    elif mutation == 'duplicate-fault':
        import copy
        root.append(copy.deepcopy(list(root)[0]))
    elif mutation in ('same-group-duplicate','same-group-unknown'):
        zero = next(c for c in root if c.get('name','').startswith('test_original_5109_boundary') and c.get('name').endswith('[0]'))
        negative = next(c for c in root if c.get('name','').startswith('test_original_5109_boundary') and c.get('name').endswith('[-0.015]'))
        zero.set('name',negative.get('name') if mutation=='same-group-duplicate' else zero.get('name').replace('[0]','[unverified]'))
    result = assess_fault_report(ET.tostring(root,encoding='unicode'),1 if mutation=='nonzero-exit' else 0,valid_timeout())
    assert not result['passed'], f'{mutation} falsely passed'


@pytest.mark.parametrize('change', [dict(database_exception_kinds=[]),dict(true_database_retryable_observed=False),
    dict(after_failure=[1,1]),dict(pending_end=1),dict(received_statuses=[dict(status='committed')])])
def test_sender_ack_timeout_cannot_be_relabelled_database_timeout(change):
    proof = valid_timeout()
    proof.update(change)
    assert not assess_fault_report(valid_report(),0,proof)['passed'], 'unproven DB timeout accepted'


def test_baseline_also_requires_original_boundary_regression():
    assert assess_boundary_report(valid_report(),0)['passed'], 'baseline boundary catalog rejected'
    root = ET.fromstring(valid_report())
    root.remove(next(c for c in root if c.get('name','').startswith('test_original_5109_boundary')))
    assert not assess_boundary_report(ET.tostring(root,encoding='unicode'),0)['passed'], 'baseline could omit original 15ms regression'
