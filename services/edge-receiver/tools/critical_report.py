"""Require three exact scenarios and their independent failure/recovery proofs."""
from collections import Counter
import xml.etree.ElementTree as ET

NAMES=('test_central_receipt_data_enospc_keeps_source_and_recovers_once',
    'test_lost_physical_slot_keeps_pending_until_verified_new_base_and_wal_chain',
    'test_same_cluster_forks_require_explicit_timeline_for_second_pitr')


def assess(xml_text,exit_code,evidence):
    from verify_private import assess_boundary_report
    boundary=assess_boundary_report(xml_text,exit_code)
    if not boundary['passed']:return dict(passed=False,boundary=boundary)
    cases=list(ET.fromstring(xml_text).iter('testcase'));counts=Counter(c.get('name') for c in cases)
    data=evidence.get('central-data-full',{});slot=evidence.get('slot-reseed',{});timeline=evidence.get('timeline-pitr',{})
    full=data.get('full',{});freed=data.get('freed',{});lost=slot.get('lost',{});rebuilt=slot.get('rebuilt',{})
    checks=dict(
        central_enospc=(data.get('passed') is True and full.get('actual_enospc') is True and full.get('limit_bytes')==16*1024*1024
            and str(full.get('receipt_relation','')).startswith('pg_tblspc/') and freed.get('actual_relation_enospc') is True
            and freed.get('space_freed') is True and data.get('statuses_during_failure')==['retryable']
            and data.get('source_preserved') is True and data.get('rows')==1 and data.get('pending_end')==0
            and data.get('tablespace_removed') is True),
        lost_slot=(slot.get('passed') is True and lost.get('lost',{}).get('wal_status')=='lost'
            and lost.get('lost',{}).get('restart_lsn') is None and lost.get('child_exit')==1
            and lost.get('gate_rejected') is True and slot.get('ack_fenced_until_reseed') is True
            and slot.get('statuses_during_failure')==['retryable']
            and rebuilt.get('base_verified') is True and str(rebuilt.get('expected_system_id','')).isdecimal()
            and rebuilt.get('old_slot_preserved')=='ems_archive_slot'
            and rebuilt.get('replacement_slot',{}).get('slot')=='ems_archive_reseed'
            and rebuilt.get('replacement_slot',{}).get('active') is True
            and rebuilt.get('replacement_slot',{}).get('peer_tls') is True
            and rebuilt.get('flush_fence_satisfied') is True and bool(rebuilt.get('fixed_lsn'))
            and bool(rebuilt.get('reserved_before_backup')) and rebuilt.get('forced_gap_segments')==3
            and rebuilt.get('reseed_chain_pitr_verified') is True and rebuilt.get('recovered_gap_marker')=='reseed-gap'
            and slot.get('generation_rotated') is True and slot.get('source_preserved') is True
            and slot.get('rows')==[1,1] and slot.get('pending_end')==0),
        timeline=(timeline.get('passed') is True and timeline.get('branch_timelines')==[2,3]
            and timeline.get('approved_timeline')==2 and timeline.get('pinned_rows')=='branch-two'
            and timeline.get('unsafe_latest_rows')=='branch-three' and str(timeline.get('system_id','')).isdecimal()
            and all(timeline.get(k) is True for k in ('latest_rejected','second_pitr_promoted','backup_verified','pristine_inputs_unchanged'))))
    bad=any(c.find(t) is not None for c in cases for t in ('failure','error','skipped'))
    return dict(passed=exit_code==0 and len(cases)==38 and all(counts[n]==1 for n in NAMES) and not bad and all(checks.values()),
        boundary=boundary,expected_tests=38,observed_tests=len(cases),evidence_checks=checks)
