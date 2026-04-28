"""Unit tests for _float_to_registers — a pure function with no I/O."""
import math
import struct

import pytest

from main import _float_to_registers


def _registers_to_float(regs: list[int], byte_order: str = "ABCD") -> float:
    """Inverse of _float_to_registers, used for round-trip verification."""
    hi = regs[0].to_bytes(2, "big")
    lo = regs[1].to_bytes(2, "big")
    if byte_order == "ABCD":
        buf = hi + lo
    elif byte_order == "CDAB":
        buf = lo + hi
    elif byte_order == "BADC":
        buf = bytes([hi[1], hi[0], lo[1], lo[0]])
    elif byte_order == "DCBA":
        buf = lo[::-1] + hi[::-1]
    else:
        raise ValueError(f"Unknown byte order: {byte_order}")
    return struct.unpack(">f", buf)[0]


class TestABCDByteOrder:
    def test_zero(self):
        assert _float_to_registers(0.0) == [0, 0]

    def test_positive_one(self):
        # 1.0 = 0x3F800000 → [0x3F80, 0x0000]
        assert _float_to_registers(1.0) == [0x3F80, 0x0000]

    def test_voltage_380(self):
        # 380.0 = 0x43BE0000 → [0x43BE, 0x0000]
        assert _float_to_registers(380.0) == [0x43BE, 0x0000]

    def test_negative_one(self):
        # -1.0 = 0xBF800000 → [0xBF80, 0x0000]
        assert _float_to_registers(-1.0) == [0xBF80, 0x0000]

    def test_returns_exactly_two_registers(self):
        regs = _float_to_registers(42.0)
        assert len(regs) == 2

    def test_registers_are_valid_uint16(self):
        for v in [0.0, 1.0, 380.0, 56.78, -999.99]:
            regs = _float_to_registers(v)
            assert all(isinstance(r, int) for r in regs)
            assert all(0 <= r <= 0xFFFF for r in regs)

    def test_round_trip_common_values(self):
        for v in [0.0, 1.0, -1.0, 380.0, 56.78, 1234.56, 25.0, 50.0, 1000.0]:
            regs = _float_to_registers(v, "ABCD")
            recovered = _registers_to_float(regs, "ABCD")
            assert math.isclose(v, recovered, rel_tol=1e-6), (
                f"Round-trip failed for {v}: got {recovered}"
            )


class TestOtherByteOrders:
    @pytest.mark.parametrize("order", ["CDAB", "BADC", "DCBA"])
    @pytest.mark.parametrize("value", [380.0, 56.78, -1.0, 25.0])
    def test_round_trip(self, order, value):
        regs = _float_to_registers(value, order)
        recovered = _registers_to_float(regs, order)
        assert math.isclose(value, recovered, rel_tol=1e-6), (
            f"Round-trip failed for {value} with byte_order={order}"
        )

    def test_different_orders_produce_different_bytes(self):
        # ABCD and CDAB differ for non-symmetric floats
        v = 380.0
        abcd = _float_to_registers(v, "ABCD")
        cdab = _float_to_registers(v, "CDAB")
        assert abcd != cdab

    def test_invalid_byte_order_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown byte order"):
            _float_to_registers(1.0, "WXYZ")


class TestEdgeCases:
    def test_positive_infinity_does_not_crash(self):
        regs = _float_to_registers(float("inf"))
        assert len(regs) == 2

    def test_negative_infinity_does_not_crash(self):
        regs = _float_to_registers(float("-inf"))
        assert len(regs) == 2

    def test_float32_max(self):
        v = 3.4028235e+38
        regs = _float_to_registers(v)
        recovered = _registers_to_float(regs)
        assert math.isclose(v, recovered, rel_tol=1e-6)

    def test_very_small_value(self):
        v = 1.175494e-38  # near float32 min
        regs = _float_to_registers(v)
        recovered = _registers_to_float(regs)
        assert math.isclose(v, recovered, rel_tol=1e-5)
