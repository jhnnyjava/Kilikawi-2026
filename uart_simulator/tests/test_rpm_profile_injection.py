"""Deterministic RPM ramp profile and telemetry injection tests."""

from __future__ import annotations

from uart_simulator.emulator.model import DriveState
from uart_simulator.emulator.server import _build_real_format_words, _u16_to_i16


def _rpm_targets_up_then_down(max_rpm: int = 200) -> list[int]:
    up = list(range(0, max_rpm + 1))
    down = list(range(max_rpm - 1, -1, -1))
    return up + down


def test_rpm_profile_one_rpm_per_second_to_200_and_back_to_zero() -> None:
    """Target profile should follow +1/s to 200 then -1/s to 0."""
    state = DriveState(enabled=True)
    state.eco_mode = False
    state.force_feedback_to_target = True

    targets = _rpm_targets_up_then_down(200)
    observed: list[int] = []

    for target in targets:
        state.target_velocity_rpm = target
        state.step(1.0)
        observed.append(state.velocity_actual_rpm)

    assert observed == targets


def test_injection_words_follow_compat_registers_during_rpm_profile() -> None:
    """Push/injection words should stay aligned with compatibility registers."""
    state = DriveState(enabled=True)
    state.eco_mode = False
    state.force_feedback_to_target = True
    state.bus_voltage_tenth_v = 548
    state.driver_temp_c = 44

    for target in _rpm_targets_up_then_down(200):
        state.target_velocity_rpm = target
        state.step(1.0)

        words_u16 = _build_real_format_words(state)
        words_i16 = [_u16_to_i16(w) for w in words_u16]

        speed_ref = _u16_to_i16(state.read_register(0x100B))
        current_ref = _u16_to_i16(state.read_register(0x100C))
        voltage = _u16_to_i16(state.read_register(0x100D))
        driver_temp = _u16_to_i16(state.read_register(0x1015))

        assert words_i16[0] == speed_ref
        assert abs(words_i16[1] - current_ref) <= 1
        assert words_i16[2] == voltage
        assert words_i16[4] == driver_temp
        assert words_u16[7] == 0xF00B
