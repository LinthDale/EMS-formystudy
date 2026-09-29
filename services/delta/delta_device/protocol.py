"""Delta V1.35 input registers. Addresses are vendor Base-1 references.

Temperature signedness is a profile assumption pending target-model acceptance.
Only the documented phase-1 compatibility subset is persisted by the EMS.
"""
from dataclasses import dataclass
from typing import Mapping, Optional


def u16(value: int) -> int:
    if type(value) is not int or not 0 <= value <= 65535:
        raise ValueError("invalid 16-bit register")
    return value


def pdu_address(reference: int, base: int = 1) -> int:
    if base not in (0, 1) or type(base) is not int:
        raise ValueError("address_base must be 0 or 1")
    return u16(reference - base)


@dataclass(frozen=True)
class Scales:
    dc_current: float = .01
    power: float = 1
    energy: float = 10
    ac_current: float = .01
    voltage: float = .1


def scales(word: Optional[int]) -> Scales:
    # None means an explicit Modbus Illegal Address response, not timeout.
    if word is None:
        return Scales()
    u16(word)
    if word & 1:
        return Scales()
    if word & 0xC000:
        raise ValueError("reserved scale bits")
    current = (.01, .01, .1, 1)
    power = (1, .1, 1, 10, 100, 1000)
    energy = (10, .001, .01, .1, 1, 10, 100, 1000)
    try:
        return Scales(current[(word >> 1) & 3], power[(word >> 3) & 7],
                      energy[(word >> 6) & 15], current[(word >> 10) & 3],
                      (.1, .01, .1, 1)[(word >> 12) & 3])
    except IndexError as exc:
        raise ValueError("reserved scale code") from exc


def decode(registers: Mapping[int, int], scale_word: Optional[int],
           model_code: Optional[int] = None) -> dict:
    factor = scales(scale_word)

    def value(address):
        try:
            return u16(registers[address])
        except KeyError as exc:
            raise ValueError("missing required input register") from exc

    def low_first(address):
        return value(address) | (value(address + 1) << 16)

    phases = []
    for address in (49153, 49157, 49161):
        phases.append({
            "voltage": value(address) * factor.voltage,
            "current": value(address + 1) * factor.ac_current,
            "power_kw": value(address + 2) * factor.power / 1000,
            "frequency_hz": value(address + 3) * .01,
        })
    today_factor = factor.energy
    if scale_word == 0:
        if type(model_code) is not int or not 0 <= model_code <= 9999:
            raise ValueError("scale=0 requires supported IR40962 model code")
        today_factor = 1 if model_code < 1000 else 10
    result = {
        "profile": "delta-three-phase-v1.35",
        "scale_word": scale_word,
        "voltage": phases[0]["voltage"],
        "current": phases[0]["current"],
        "power_kw": value(49152) * factor.power / 1000,
        "energy_kwh": low_first(53252) * factor.energy / 1000,
        "today_energy_kwh": low_first(53248) * today_factor / 1000,
        "state": value(53256),
        "phases": phases,
    }
    if 53259 in registers:
        raw = value(53259)
        result["temperature_c"] = raw - 65536 if raw & 0x8000 else raw
    return result
