"""Integrity scenarios must be selected explicitly and cannot pass on exit zero."""
from pathlib import Path
import json
import sys
import xml.etree.ElementTree as ET
import pytest

sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
import verify_private as verifier


def test_integrity_suite_has_new_real_cases_and_all_original_boundary_cases():
    assert verifier.suite_targets('integrity')==('/app/tests/integration/test_edge_integrity.py',
        '/app/services/delta/tests/test_reliable_consistency.py',
        '/app/services/delta/tests/test_bench_slot_boundary.py'), 'integrity scope missing or broadened into long soak'


def test_integrity_suite_rejects_old_passing_xml_without_new_scenarios_or_proofs():
    xml=(Path(__file__).parent/'fixtures/faults-and-boundary.xml').read_text()
    assert not verifier.assess_integrity_report(xml,0,{})['passed'], 'old successful cases replaced new integrity scenarios'


def fixture():
    folder=Path(__file__).parent/'fixtures'
    return ET.parse(folder/'integrity-report.xml').getroot(),json.loads((folder/'integrity-proof.json').read_text())


def test_actual_integrity_report_and_complete_proof_pass():
    root,proof=fixture()
    assert verifier.assess_integrity_report(ET.tostring(root,encoding='unicode'),0,proof)['passed'], 'real complete evidence rejected'


@pytest.mark.parametrize('mutation',['missing-case','replaced-case','skipped','damaged-file-modified','not-rejected',
    'partial-write','fake-ack','parser-never-reached','duplicate-recovery','not-blocked','wait-ended-before-exit',
    'sigkill-instead-of-term','ledger-mismatch','projection-ids-changed','projection-values-changed','canonical-changed','missing-evidence'])
def test_integrity_gate_rejects_incomplete_or_false_evidence(mutation):
    root,proof=fixture();cases=list(root.iter('testcase'))
    if mutation=='missing-case':root.find('testsuite').remove(cases[0])
    elif mutation=='replaced-case':cases[0].set('name','unrelated_old_passing_case')
    elif mutation=='skipped':ET.SubElement(cases[0],'skipped')
    elif mutation=='damaged-file-modified':proof['logical-missing-audit']['after_sha256']='0'*64
    elif mutation=='not-rejected':proof['logical-missing-audit']['rejected']=False
    elif mutation=='partial-write':proof['malformed-bad-hash']['rows_before']=[1,0]
    elif mutation=='fake-ack':proof['malformed-duplicate-id']['acks_before_recovery']=1
    elif mutation=='parser-never-reached':proof['malformed-invalid-utf8']['actual_parser_observed']=False
    elif mutation=='duplicate-recovery':proof['malformed-excess-depth']['rows_after']=[2,1]
    elif mutation=='not-blocked':proof['sigterm-db-wait']['real_db_lock_observed']=False
    elif mutation=='wait-ended-before-exit':proof['sigterm-db-wait']['wait_still_active_at_exit']=False
    elif mutation=='sigkill-instead-of-term':proof['sigterm-db-wait']['first_exit']=-9
    elif mutation=='ledger-mismatch':proof['sigterm-db-wait']['ledger_hashes_match']=False
    elif mutation=='projection-ids-changed':proof['sigterm-db-wait']['projection_ids_match']=False
    elif mutation=='projection-values-changed':proof['sigterm-db-wait']['projection_values_match']=False
    elif mutation=='canonical-changed':proof['sigterm-db-wait']['original_canonical_unchanged']=False
    else:proof.pop('sigterm-db-wait')
    assert not verifier.assess_integrity_report(ET.tostring(root,encoding='unicode'),0,proof)['passed'], f'{mutation} falsely passed'
