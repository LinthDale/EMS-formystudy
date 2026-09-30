"""PRD-0022 retires unauthenticated meter writes; diagnostic reads remain."""
import pytest
from httpx import ASGITransport, AsyncClient
import main


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as ac:
        yield ac


async def test_health_and_config_remain_readable(client):
    assert (await client.get("/health")).json() == {"status": "ok"}
    assert (await client.get("/config")).json()["fault_mode"] == "none"


@pytest.mark.parametrize("path", ["/config?noise_voltage_v=9", "/inject-fault?mode=zero"])
async def test_legacy_writes_are_gone_and_cannot_mutate(client, path):
    before = main.get_config()
    assert (await client.post(path)).status_code == 410
    assert main.get_config() == before


@pytest.mark.parametrize("fc", [5, 6, 15, 16, 22, 23])
def test_network_modbus_writes_rejected(fc):
    assert not main._store.validate(fc, 0, 1)


def test_trusted_simulation_updates_are_still_readable():
    main._store.setValues(3, 0, [3800])
    assert main._store.validate(3, 0, 1)
    assert main._store.getValues(3, 0, 1) == [3800]
