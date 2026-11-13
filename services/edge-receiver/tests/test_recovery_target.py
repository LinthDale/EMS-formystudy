"""A physical cluster ID does not authorize an arbitrary recovery branch."""
import pytest
import json
import sys

from edge_receiver import backup_preflight


@pytest.mark.parametrize('timeline',['latest','current','0','-1','2;port=5432',2,True,'4294967296','02'])
def test_recovery_plan_rejects_unpinned_or_invalid_timeline(timeline):
    with pytest.raises(ValueError,match='timeline'):
        backup_preflight.recovery_settings(timeline,'ems_approved_target')


@pytest.mark.parametrize('target',['',"x'\nport=5432",'a'*64,None])
def test_recovery_plan_rejects_invalid_target(target):
    with pytest.raises(ValueError,match='target'):
        backup_preflight.recovery_settings('2',target)


def test_recovery_plan_pins_approved_timeline_and_named_target():
    assert backup_preflight.recovery_settings('2','ems_approved_target')=={
        'recovery_target_timeline':'2','recovery_target_name':'ems_approved_target',
        'recovery_target_action':'promote'}, 'approved recovery branch changed'


@pytest.mark.parametrize('extra',[[],['--expected-timeline','latest','--target-name','safe']])
def test_directory_cli_refuses_unpinned_target_before_backup_commands(monkeypatch,capsys,extra):
    monkeypatch.setattr(sys,'argv',['preflight','--directory','/untrusted','--expected-system-id','1',*extra])
    def forbidden(*args,**kwargs):raise AssertionError('unapproved branch reached backup commands')
    monkeypatch.setattr(backup_preflight,'verify_backup',forbidden)
    with pytest.raises(SystemExit) as stopped:backup_preflight.main()
    assert stopped.value.code==1 and json.loads(capsys.readouterr().out)['verified'] is False, 'CLI accepted unpinned target'


def test_directory_cli_returns_verified_backup_and_approved_settings(monkeypatch,capsys):
    monkeypatch.setattr(sys,'argv',['preflight','--directory','/restore','--expected-system-id','123',
        '--expected-timeline','2','--target-name','safe'])
    monkeypatch.setattr(backup_preflight,'verify_backup',lambda directory,expected:dict(verified=True,system_identifier=expected))
    backup_preflight.main();result=json.loads(capsys.readouterr().out)
    assert result['verified'] and result['system_identifier']=='123' and result['recovery_settings']['recovery_target_timeline']=='2', 'CLI lost approved branch'
