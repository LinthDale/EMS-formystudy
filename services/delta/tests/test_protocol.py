import pytest
from delta_device.protocol import decode, pdu_address, scales

def fixture():
    r = {49152: 9000, 53248: 123, 53249: 1, 53252: 2, 53253: 1, 53256: 2}
    for a in (49153, 49157, 49161):
        r.update({a: 2300, a+1: 1300, a+2: 3000, a+3: 6000})
    return r

def test_literal_protocol_fixture():
    r = decode(fixture(), 1)
    assert r['voltage'] == 230
    assert r['current'] == 13
    assert r['power_kw'] == 9
    assert r['energy_kwh'] == 655.38
    assert r['today_energy_kwh'] == 656.59
    assert r['phases'][2]['frequency_hz'] == 60
    assert pdu_address(0xA023) == 40994
    assert pdu_address(49152, 0) == 49152

def test_scale_rules():
    assert scales(None).power == 1
    assert scales(0x0193).energy == 10
    assert decode(fixture(), 0x019C)['power_kw'] == 90
    assert decode(fixture(), 0x019C)['energy_kwh'] == 6553.8
    assert decode(fixture(), 0, model_code=42)['today_energy_kwh'] == 65.659
    assert decode(fixture(), 0, model_code=1000)['today_energy_kwh'] == 656.59
    assert decode(fixture(), None)['today_energy_kwh'] == 656.59
    with pytest.raises(ValueError):
        decode(fixture(), 0)

@pytest.mark.parametrize('word', [6 << 3, 8 << 6, 0x4000, -1, 65536])
def test_invalid_scale(word):
    with pytest.raises(ValueError):
        scales(word)

def test_missing_register_and_signed_temperature():
    r = fixture()
    r[53259] = 65531
    assert decode(r, 1)['temperature_c'] == -5
    del r[49153]
    with pytest.raises(ValueError):
        decode(r, 1)
    with pytest.raises(ValueError):
        pdu_address(0, 1)
