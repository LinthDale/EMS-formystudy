"""A checksum-valid foreign backup is still the wrong recovery input."""
import subprocess
from types import SimpleNamespace
import pytest


def test_backup_preflight_requires_external_expected_cluster_and_rejects_foreign_before_verify(tmp_path):
    from edge_receiver.backup_preflight import verify_backup
    calls=[]
    def run(args,**kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0,stdout='Database system identifier: 222\n',stderr='')
    with pytest.raises(ValueError,match='cluster'):verify_backup(tmp_path,'111',runner=run)
    assert len(calls)==1 and calls[0][0]=='pg_controldata', 'foreign cluster reached backup acceptance'


def test_backup_preflight_accepts_only_matching_cluster_and_successful_checksum(tmp_path):
    from edge_receiver.backup_preflight import verify_backup
    calls=[]
    def run(args,**kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0,stdout='Database system identifier: 111\n' if args[0]=='pg_controldata' else '',stderr='')
    assert verify_backup(tmp_path,'111',runner=run)['system_identifier']=='111', 'correct backup rejected'
    assert [a[0] for a in calls]==['pg_controldata','pg_verifybackup'], 'checksum not checked after identity'


@pytest.mark.parametrize('expected',['','0','-1','111; rm','2'*30,None])
def test_backup_preflight_rejects_invalid_external_identity_without_executing(tmp_path,expected):
    from edge_receiver.backup_preflight import verify_backup
    def run(*args,**kwargs):raise AssertionError('invalid ID reached subprocess')
    with pytest.raises(ValueError):verify_backup(tmp_path,expected,runner=run)
