"""Unit: request schema validation."""
import pytest
from pydantic import ValidationError

from device_service.models import DeviceCreate, SignalCreate


def test_valid_device_id():
    assert DeviceCreate(device_id="sim-001").device_id == "sim-001"


def test_invalid_device_id_rejected():
    with pytest.raises(ValidationError):
        DeviceCreate(device_id="bad id!")  # space + '!' not allowed


def test_device_id_too_long_rejected():
    with pytest.raises(ValidationError):
        DeviceCreate(device_id="x" * 65)


def test_signal_name_pattern():
    assert SignalCreate(signal_name="voltage").signal_name == "voltage"
    with pytest.raises(ValidationError):
        SignalCreate(signal_name="has space")