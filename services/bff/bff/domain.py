"""Device -> measurement-domain resolution (ADR-025).

A device record carries a `gateway_id`; the gateway determines which measurement
hypertable (and therefore which PostgREST view) holds that device's samples. This
mirrors device-service's own `measurements_repo.table_for_gateway` mapping so the
BFF and device-service agree on the electricity/factory split — the single
authoritative signal is the gateway, NOT a free-text device_type.

Pure function, no I/O: the caller fetches the device record and passes gateway_id.
"""
from __future__ import annotations

# gateway_id -> PostgREST measurement resource (api.* views, §1.5 D2).
# Same split as services/device-service .../repositories/measurements_repo.py.
_GATEWAY_RESOURCE: dict[str, str] = {
    "ems-gateway": "/electricity_measurements",
    "kc-gateway": "/factory_measurements",
    "kc-ingest": "/factory_measurements",
}


def resource_for_gateway(gateway_id: str | None) -> str | None:
    """Resolve the PostgREST measurement resource for a device's gateway.

    Returns None when the gateway is unknown/absent — the caller must then refuse
    to serve a measurement view (404), never guess a domain.
    """
    if gateway_id is None:
        return None
    return _GATEWAY_RESOURCE.get(gateway_id)
