from unittest.mock import patch
import pytest
from bff.account_cli import parser, read_password, legacy_records

def test_password_not_accepted_as_argument():
    with pytest.raises(SystemExit):
        parser().parse_args(["create","alice","--role","ops","--reason","test","--password","bad"])

@pytest.mark.parametrize("answers", [("short","short"),("a"*12,"b"*12),("a"*257,"a"*257)])
def test_password_validation(answers):
    with patch("bff.account_cli.getpass",side_effect=answers):
        with pytest.raises(ValueError):
            read_password()

def test_valid_password():
    with patch("bff.account_cli.getpass",side_effect=["long-password","long-password"]):
        assert read_password()=="long-password"

def test_import_requires_ops():
    from tests.conftest import phc
    with pytest.raises(ValueError):
        legacy_records(f"reader:{phc('pw')}:readonly")

def test_import_preserves_hash():
    from tests.conftest import phc
    encoded=phc("pw")
    assert legacy_records(f"ops:{encoded}:ops")[0]["password_hash"]==encoded

def test_reason_required():
    with pytest.raises(SystemExit):
        parser().parse_args(["disable","alice"])
