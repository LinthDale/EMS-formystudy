"""Validated JSON configuration. Secrets are referenced by environment name."""
import json
import math
import os
import re
from pathlib import Path

ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
ENV = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def simulator_recovery_settings():
    """RTU listener lifecycle delays; env overrides apply only to the simulator."""
    values = []
    for name, default in (("DELTA_SIM_RTU_HEALTH_SECONDS", .5),
                          ("DELTA_SIM_RTU_RECONNECT_SECONDS", 2)):
        value = float(os.environ.get(name, default))
        if not math.isfinite(value) or not .01 <= value <= 60:
            raise ValueError("invalid " + name)
        values.append(value)
    return tuple(values)


def response_lifetime(config):
    """Operator-qualified last-byte lifetime, never inferred from read timeout."""
    value = config.get('response_lifetime_seconds')
    source = config.get('response_lifetime_source')
    if value is None:
        if source is not None:
            raise ValueError('response lifetime requires both bound and source')
        return None
    if config.get('transport') != 'rtu':
        raise ValueError('response lifetime applies only to RTU')
    if type(value) not in (int, float) or not math.isfinite(value) or not .01 <= value <= 120:
        raise ValueError('invalid response lifetime')
    if not isinstance(source, str) or not source.strip() or len(source) > 256:
        raise ValueError('response lifetime source required')
    return float(value)


def load_config(path):
    with open(path, encoding="utf-8") as stream:
        config = json.load(stream)
    validate(config)
    return config


def validate(config):
    allowed = {"mode", "device_id", "modbus", "mqtt", "outbox_path",
               "queue_limit", "poll_interval", "batch_size", "clock_sync_file", "delivery"}
    if not isinstance(config, dict) or set(config) - allowed:
        raise ValueError("unknown configuration keys")
    if config.get("mode") not in ("demo", "field"):
        raise ValueError("explicit demo or field mode required")
    device_id = config.get("device_id", "")
    if not isinstance(device_id, str) or not ID.fullmatch(device_id):
        raise ValueError("invalid device_id")
    if config["mode"] == "field" and "sim" in device_id.lower():
        raise ValueError("field device_id must not identify a simulator")
    reliable = 'delivery' in config
    if reliable:
        validate_delivery(config['delivery'])
    bounds = {"queue_limit": (10000, 1, 1000000),
              "poll_interval": (10, 1, 3600), "batch_size": (1 if reliable else 100, 1, 1 if reliable else 100)}
    for name, (default, low, high) in bounds.items():
        v = config.setdefault(name, default)
        if type(v) is not int or not low <= v <= high:
            raise ValueError("invalid " + name)
    modbus = config.get("modbus", {})
    if set(modbus) - {"transport", "host", "port", "serial_port", "baudrate",
                       "unit_id", "address_base", "timeout", "read_temperature",
                       "response_lifetime_seconds", "response_lifetime_source"}:
        raise ValueError("unknown modbus keys")
    if modbus.get("transport") not in ("tcp", "rtu"):
        raise ValueError("transport must be tcp or rtu")
    for name, default, low, high in (
        ("unit_id", 1, 1, 247), ("address_base", 1, 0, 1),
        ("port", 502, 1, 65535), ("timeout", 3, 1, 30)):
        v = modbus.setdefault(name, default)
        if type(v) is not int or not low <= v <= high:
            raise ValueError("invalid modbus " + name)
    if modbus["transport"] == "tcp":
        if not isinstance(modbus.get("host"), str) or not modbus["host"].strip():
            raise ValueError("modbus host required")
    else:
        if not isinstance(modbus.get("serial_port"), str) or not modbus["serial_port"]:
            raise ValueError("serial_port required")
        if modbus.setdefault("baudrate", 19200) not in (9600, 19200, 38400):
            raise ValueError("unsupported baudrate")
    if type(modbus.setdefault("read_temperature", False)) is not bool:
        raise ValueError("read_temperature must be boolean")
    lifetime = response_lifetime(modbus)
    if config['mode'] == 'field' and modbus['transport'] == 'rtu' and lifetime is None:
        raise ValueError('field RTU requires a qualified response lifetime')
    mqtt = config.get("mqtt", {})
    if set(mqtt) - {"host", "port", "client_id", "tls", "ca_file", "cert_file",
                     "key_file", "username_env", "password_env"}:
        raise ValueError("unknown mqtt keys")
    if not isinstance(mqtt.get("host"), str) or not mqtt["host"].strip():
        raise ValueError("mqtt host required")
    if not ID.fullmatch(mqtt.get("client_id", "")):
        raise ValueError("unique mqtt client_id required")
    v = mqtt.setdefault("port", 8883 if config["mode"] == "field" else 1883)
    if type(v) is not int or not 1 <= v <= 65535:
        raise ValueError("invalid mqtt port")
    if type(mqtt.setdefault("tls", False)) is not bool:
        raise ValueError("tls must be boolean")
    for key in ("username_env", "password_env"):
        if key in mqtt and not ENV.fullmatch(mqtt[key]):
            raise ValueError("invalid credential environment name")
    if bool(mqtt.get("username_env")) != bool(mqtt.get("password_env")):
        raise ValueError("both credential environment names required")
    if bool(mqtt.get("cert_file")) != bool(mqtt.get("key_file")):
        raise ValueError("both client certificate and key required")
    if config["mode"] == "field":
        if not mqtt["tls"]:
            raise ValueError("field requires verified TLS")
        if not (mqtt.get("username_env") or mqtt.get("cert_file")):
            raise ValueError("field requires credentials or mTLS")
        if reliable and not all(mqtt.get(k) for k in ('ca_file', 'cert_file', 'key_file')):
            raise ValueError('v2 field requires mTLS')
        config.setdefault("clock_sync_file", "/run/systemd/timesync/synchronized")
    path = config.get("outbox_path")
    if not isinstance(path, str) or not Path(path).is_absolute():
        raise ValueError("absolute outbox_path required")
    return config


def validate_delivery(delivery):
    from .reliable_wire import identifier, uuid_text
    allowed = {'protocol', 'gateway_id', 'stream_id', 'config_revision', 'profile_version',
               'queue_byte_limit', 'audit_limit', 'ack_timeout_seconds'}
    if not isinstance(delivery, dict) or set(delivery) - allowed or type(delivery.get('protocol')) is not int or delivery['protocol'] != 2:
        raise ValueError('explicit v2 delivery required')
    for name in ('gateway_id', 'config_revision', 'profile_version'):
        identifier(delivery.get(name))
    try:
        uuid_text(delivery.get('stream_id'))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError('registered stream_id required') from exc
    for name, default, low, high in [('queue_byte_limit', 4 * 1024**3, 65536, 64 * 1024**3),
                                     ('audit_limit', 600000, 1, 6000000),
                                     ('ack_timeout_seconds', 30, 1, 120)]:
        value = delivery.setdefault(name, default)
        if type(value) is not int or not low <= value <= high:
            raise ValueError('invalid delivery ' + name)
