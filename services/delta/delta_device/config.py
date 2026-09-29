"""Validated JSON configuration. Secrets are referenced by environment name."""
import json
import re
from pathlib import Path

ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
ENV = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def load_config(path):
    with open(path, encoding="utf-8") as stream:
        config = json.load(stream)
    validate(config)
    return config


def validate(config):
    allowed = {"mode", "device_id", "modbus", "mqtt", "outbox_path",
               "queue_limit", "poll_interval", "batch_size", "clock_sync_file"}
    if not isinstance(config, dict) or set(config) - allowed:
        raise ValueError("unknown configuration keys")
    if config.get("mode") not in ("demo", "field"):
        raise ValueError("explicit demo or field mode required")
    device_id = config.get("device_id", "")
    if not isinstance(device_id, str) or not ID.fullmatch(device_id):
        raise ValueError("invalid device_id")
    if config["mode"] == "field" and "sim" in device_id.lower():
        raise ValueError("field device_id must not identify a simulator")
    bounds = {"queue_limit": (10000, 1, 1000000),
              "poll_interval": (10, 1, 3600), "batch_size": (100, 1, 100)}
    for name, (default, low, high) in bounds.items():
        v = config.setdefault(name, default)
        if type(v) is not int or not low <= v <= high:
            raise ValueError("invalid " + name)
    modbus = config.get("modbus", {})
    if set(modbus) - {"transport", "host", "port", "serial_port", "baudrate",
                       "unit_id", "address_base", "timeout", "read_temperature"}:
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
        config.setdefault("clock_sync_file", "/run/systemd/timesync/synchronized")
    path = config.get("outbox_path")
    if not isinstance(path, str) or not Path(path).is_absolute():
        raise ValueError("absolute outbox_path required")
    return config
