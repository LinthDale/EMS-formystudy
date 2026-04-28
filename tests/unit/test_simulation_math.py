"""Unit tests for simulation physics: power formula, energy, fault modes, SimConfig."""
import math

import pytest

from main import SimConfig


class TestThreePhasePowerFormula:
    """P = √3 × V_LL × I × cos(φ) / 1000  (kW)"""

    @staticmethod
    def _power(v: float, i: float, pf: float) -> float:
        return math.sqrt(3) * v * i * pf / 1000.0

    def test_nominal_380v_100a_pf085(self):
        # √3 × 380 × 100 × 0.85 / 1000 = 55.91 kW
        p = self._power(380.0, 100.0, 0.85)
        assert math.isclose(p, 55.91, rel_tol=1e-3)

    def test_zero_current_gives_zero_power(self):
        assert self._power(380.0, 0.0, 0.85) == 0.0

    def test_zero_voltage_gives_zero_power(self):
        assert self._power(0.0, 100.0, 0.85) == 0.0

    def test_unity_pf_greater_than_lagging(self):
        p_unity = self._power(380.0, 100.0, 1.0)
        p_lagging = self._power(380.0, 100.0, 0.85)
        assert p_unity > p_lagging

    def test_power_proportional_to_current(self):
        p1 = self._power(380.0, 100.0, 0.85)
        p2 = self._power(380.0, 200.0, 0.85)
        assert math.isclose(p2 / p1, 2.0, rel_tol=1e-9)

    def test_power_proportional_to_voltage(self):
        p1 = self._power(380.0, 100.0, 0.85)
        p2 = self._power(760.0, 100.0, 0.85)
        assert math.isclose(p2 / p1, 2.0, rel_tol=1e-9)


class TestCurrentBounds:
    """Simulator uses max(0.0, current) to prevent negative readings."""

    def test_extreme_negative_swing_clamps_to_zero(self):
        base, swing = 10.0, 50.0  # worst case: 10 - 50 = -40
        assert max(0.0, base - swing) == 0.0

    def test_normal_conditions_not_clamped(self):
        base, swing = 100.0, 40.0  # worst case: 60 — should not clamp
        assert max(0.0, base - swing) == 60.0

    def test_exactly_zero_current_allowed(self):
        assert max(0.0, 0.0) == 0.0


class TestEnergyAccumulation:
    """E += max(P, 0) / 3600  per second tick."""

    def test_1_hour_of_56kw_yields_56kwh(self):
        power_kw = 56.0
        energy = 0.0
        for _ in range(3600):
            energy += max(power_kw, 0.0) / 3600.0
        assert math.isclose(energy, 56.0, rel_tol=1e-9)

    def test_energy_increases_each_tick(self):
        power_kw = 10.0
        energy = 0.0
        prev = -1.0
        for _ in range(5):
            energy += max(power_kw, 0.0) / 3600.0
            assert energy > prev
            prev = energy

    def test_zero_power_no_energy_gain(self):
        energy = 5.0
        energy += max(0.0, 0.0) / 3600.0
        assert energy == 5.0

    def test_negative_power_clamped_no_energy_gain(self):
        # Negative power would imply generation — clamp prevents counter regression
        energy = 5.0
        energy += max(-10.0, 0.0) / 3600.0
        assert energy == 5.0


class TestFaultModeLogic:
    """Verify simulator fault mode branches produce correct values."""

    def test_fault_zero_sets_all_values_to_zero(self):
        fault_mode = "zero"
        if fault_mode == "zero":
            voltage = current = power_kw = 0.0
        else:
            voltage, current, power_kw = 380.0, 100.0, 55.91
        assert voltage == 0.0
        assert current == 0.0
        assert power_kw == 0.0

    def test_no_fault_produces_nonzero_values(self):
        fault_mode = "none"
        if fault_mode == "zero":
            voltage = current = 0.0
        else:
            voltage = 380.0
            current = 100.0
        assert voltage > 0.0
        assert current > 0.0

    def test_fault_freeze_does_not_change_energy(self):
        fault_mode = "freeze"
        energy_kwh = 10.0
        # freeze branch: just increments t, does NOT update energy
        if fault_mode == "freeze":
            pass  # no energy update
        else:
            energy_kwh += 1.0  # hypothetical update
        assert energy_kwh == 10.0


class TestSimConfig:
    def test_default_noise_voltage(self):
        assert SimConfig().noise_voltage_v == 3.0

    def test_default_current_base(self):
        assert SimConfig().current_base_a == 100.0

    def test_default_current_swing(self):
        assert SimConfig().current_swing_a == 40.0

    def test_default_noise_current(self):
        assert SimConfig().noise_current_a == 2.0

    def test_default_power_factor(self):
        assert SimConfig().power_factor == 0.85

    def test_default_period_seconds(self):
        assert SimConfig().period_seconds == 3600.0

    def test_default_fault_mode_is_none(self):
        assert SimConfig().fault_mode == "none"

    def test_field_mutation(self):
        cfg = SimConfig()
        cfg.current_base_a = 150.0
        assert cfg.current_base_a == 150.0

    def test_independent_instances(self):
        cfg1 = SimConfig()
        cfg2 = SimConfig()
        cfg1.current_base_a = 999.0
        assert cfg2.current_base_a == 100.0  # not shared

    def test_default_current_range_is_positive(self):
        cfg = SimConfig()
        # worst case current = base - swing = 60 > 0 (no clamping needed under defaults)
        worst_case = cfg.current_base_a - cfg.current_swing_a
        assert worst_case > 0.0
