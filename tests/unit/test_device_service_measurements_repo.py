"""Unit: measurements_repo table mapping + table allowlist guard (no DB)."""
import pytest

from device_service.repositories.measurements_repo import recent_samples, table_for_gateway


def test_table_for_gateway_mapping():
    assert table_for_gateway("ems-gateway") == "electricity_measurements"
    assert table_for_gateway("kc-gateway") == "factory_measurements"
    assert table_for_gateway("kc-ingest") == "factory_measurements"
    assert table_for_gateway(None) is None
    assert table_for_gateway("something-else") is None


async def test_recent_samples_rejects_unknown_table():
    # the allowlist guard fires before any DB use (conn unused) -> blocks table-name injection
    with pytest.raises(ValueError):
        await recent_samples(None, table="devices; DROP TABLE x", device_id="d1")
