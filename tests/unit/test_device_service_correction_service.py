"""Unit: FR-344 mass-deactivate threshold (pure). No DB."""
import pytest

from device_service.correction_service import (
    DEACTIVATE_ALERT_1H,
    DEACTIVATE_ALERT_24H,
    mass_deactivate_suspicious,
)


@pytest.mark.parametrize("c1h,c24h,expected", [
    (1, 1, False),
    (DEACTIVATE_ALERT_1H - 1, DEACTIVATE_ALERT_24H - 1, False),   # just under both
    (DEACTIVATE_ALERT_1H, 5, True),                               # 1h threshold hit
    (2, DEACTIVATE_ALERT_24H, True),                              # 24h threshold hit
    (DEACTIVATE_ALERT_1H, DEACTIVATE_ALERT_24H, True),
])
def test_mass_deactivate_suspicious(c1h, c24h, expected):
    assert mass_deactivate_suspicious(c1h, c24h) is expected


def test_thresholds_match_fr344_spec():
    assert DEACTIVATE_ALERT_1H == 5 and DEACTIVATE_ALERT_24H == 20
