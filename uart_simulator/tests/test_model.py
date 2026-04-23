"""Tests for the drive state model."""

import pytest

from uart_simulator.emulator.model import (
    DriveState,
    REG_CONTROLWORD,
    REG_STATUSWORD,
    REG_TARGET_VELOCITY,
    REG_VELOCITY_ACTUAL,
    REG_TARGET_POSITION,
    REG_POSITION_ACTUAL,
    REG_BUS_VOLTAGE,
    REG_MOTOR_TEMP,
    REG_DRIVER_TEMP,
    REG_ERROR_CODE,
    _to_i16,
    _to_u16,
)


def test_initial_state():
    """Test that drive starts in disabled state."""
    state = DriveState()
    assert state.enabled is False
    assert state.velocity_actual_rpm == 0
    assert state.target_velocity_rpm == 0
    assert state.error_code == 0


def test_step_acceleration():
    """Test that velocity ramps toward target."""
    state = DriveState()
    state.enabled = True
    state.target_velocity_rpm = 1000

    state.step(0.01)  # 10ms step
    assert 0 < state.velocity_actual_rpm < 1000

    state.step(0.01)
    assert state.velocity_actual_rpm > 0  # Should be increasing


def test_step_deceleration_when_disabled():
    """Test that velocity goes to zero when disabled."""
    state = DriveState()
    state.enabled = True
    state.target_velocity_rpm = 1000
    state.step(0.1)  # Let it accelerate partway

    state.enabled = False
    state.step(0.01)
    assert state.velocity_actual_rpm < 80  # Should be decelerating


def test_position_integration():
    """Test that position integrates with velocity."""
    state = DriveState()
    state.enabled = True
    state.target_velocity_rpm = 600  # 10 rev/sec
    initial_pos = state.position_actual

    state.step(0.1)  # 100ms at high velocity
    assert state.position_actual > initial_pos


def test_thermal_model():
    """Test that temperature rises with velocity."""
    state = DriveState()
    initial_motor_temp = state.motor_temp_c
    initial_driver_temp = state.driver_temp_c

    state.enabled = True
    state.target_velocity_rpm = 3000  # Higher target to reach higher speeds
    for _ in range(150):  # Run longer (1.5 seconds)
        state.step(0.01)

    assert state.motor_temp_c > initial_motor_temp
    assert state.driver_temp_c > initial_driver_temp


def test_status_word_when_enabled():
    """Test status word reflects enabled state."""
    state = DriveState()
    state.enabled = False
    status = state.status_word
    assert status & 0x0004 == 0  # Operation NOT enabled

    state.enabled = True
    status = state.status_word
    assert status & 0x0004 != 0  # Operation enabled


def test_status_word_fault_bit():
    """Test status word reflects fault state."""
    state = DriveState()
    state.error_code = 0
    status = state.status_word
    assert status & 0x0008 == 0  # No fault

    state.error_code = 1
    status = state.status_word
    assert status & 0x0008 != 0  # Fault bit set


def test_write_control_word():
    """Test control word interpretation."""
    state = DriveState()
    state.write_register(REG_CONTROLWORD, 0x000F)
    assert state.enabled is True

    state.write_register(REG_CONTROLWORD, 0x0000)
    assert state.enabled is False


def test_write_target_velocity():
    """Test target velocity write."""
    state = DriveState()
    state.write_register(REG_TARGET_VELOCITY, 0x03E8)  # 1000
    assert state.target_velocity_rpm == 1000


def test_write_target_velocity_negative():
    """Test negative target velocity (signed 16-bit)."""
    state = DriveState()
    state.write_register(REG_TARGET_VELOCITY, 0xFC18)  # -1000 as u16
    assert state.target_velocity_rpm == -1000


def test_write_clear_error():
    """Test clearing error by writing 0."""
    state = DriveState()
    state.error_code = 123
    state.write_register(REG_ERROR_CODE, 0)
    assert state.error_code == 0


def test_read_control_word():
    """Test control word read."""
    state = DriveState()
    state.enabled = True
    value = state.read_register(REG_CONTROLWORD)
    assert value == 0x000F

    state.enabled = False
    value = state.read_register(REG_CONTROLWORD)
    assert value == 0x0006


def test_read_status_word():
    """Test status word read."""
    state = DriveState()
    state.enabled = True
    value = state.read_register(REG_STATUSWORD)
    assert value & 0x0004 != 0  # Operation enabled


def test_read_temperatures():
    """Test temperature register reads."""
    state = DriveState()
    state.motor_temp_c = 85
    state.driver_temp_c = 92
    assert state.read_register(REG_MOTOR_TEMP) == 85
    assert state.read_register(REG_DRIVER_TEMP) == 92


def test_read_block():
    """Test reading a block of consecutive registers."""
    state = DriveState()
    state.enabled = True
    state.target_velocity_rpm = 100

    # Read multiple registers at once
    block = state.read_block(REG_CONTROLWORD, 2)
    assert len(block) == 2
    assert block[0] == state.read_register(REG_CONTROLWORD)
    assert block[1] == state.read_register(REG_STATUSWORD)


def test_to_i16_positive():
    """Test unsigned to signed 16-bit conversion for positive."""
    assert _to_i16(0x7FFF) == 32767


def test_to_i16_negative():
    """Test unsigned to signed 16-bit conversion for negative."""
    assert _to_i16(0x8000) == -32768
    assert _to_i16(0xFFFF) == -1


def test_to_u16():
    """Test unsigned 16-bit masking."""
    assert _to_u16(0x10000) == 0
    assert _to_u16(0x1FFFF) == 0xFFFF


def test_compat_register_defaults_and_persistence():
    """WINDCON-polled compatibility registers should be non-zero and writable."""
    state = DriveState()

    # Startup poll block values should indicate initialized device state.
    assert state.read_register(0x1000) == 0x0100
    assert state.read_register(0x1005) > 0
    assert state.read_register(0x1007) == 1

    # Unknown/app-specific writes should round-trip.
    state.write_register(0x1144, 0x1234)
    assert state.read_register(0x1144) == 0x1234


def test_compat_voltage_and_temp_registers_follow_state():
    """Compatibility voltage/temp registers should mirror simulator state."""
    state = DriveState()
    state.bus_voltage_tenth_v = 537
    state.motor_temp_c = 42

    assert state.read_register(0x100D) == 537
    assert state.read_register(0x100E) == 42


def test_compat_telemetry_regs_change_with_speed():
    """Compatibility telemetry registers should change when speed changes."""
    state = DriveState()
    state.enabled = True
    state.target_velocity_rpm = 1500
    for _ in range(60):
        state.step(0.01)

    current_w0 = state.read_register(0x1018)
    current_w1 = state.read_register(0x1019)
    speed_w0 = state.read_register(0x101A)
    speed_w1 = state.read_register(0x101B)

    # Float32 word pairs should not be all zero when moving.
    assert (current_w0, current_w1) != (0, 0)
    assert (speed_w0, speed_w1) != (0, 0)


def test_legacy_parameter_selector_path_is_non_zero_and_ready():
    """Legacy parameter-page flow should get ready flags and non-zero readback."""
    state = DriveState()
    state.write_register(0x0000, 0xFF00)

    assert state.read_register(0x1004) == 1
    assert state.read_register(0x1007) == 1
    assert state.read_register(0x0000) != 0


def test_legacy_parameter_selector_index_walk_changes_values():
    """Selector writes FFFE/FFFC... should stream non-zero table values."""
    state = DriveState()
    state.write_register(0x0000, 0xFFFE)
    v1 = state.read_register(0x0000)
    state.write_register(0x0000, 0xFFFC)
    v2 = state.read_register(0x0000)

    assert v1 != 0
    assert v2 != 0
    assert v1 != v2


def test_rpm_ramp_loop_matches_feedback_and_ref():
    """Target RPM loop should match feedback/reference when locked."""
    state = DriveState()
    state.enabled = True
    state.force_feedback_to_target = True

    observed: list[int] = []
    expected: list[int] = list(range(0, 201)) + list(range(199, -1, -1))

    for rpm in expected:
        state.target_velocity_rpm = rpm
        state.step(1.0)
        observed.append(state.read_register(0x1009))  # Speed feedback compat
        assert state.read_register(0x100B) == rpm  # Speed reference compat

    assert observed == expected


def test_compat_write_speed_ref_updates_target_velocity() -> None:
    """WINDCON 0x100B write should drive simulator target speed."""
    state = DriveState()
    state.write_register(0x100B, 0x03E8)  # +1000 rpm
    assert state.target_velocity_rpm == 1000

    state.write_register(0x100B, 0xFC18)  # -1000 rpm as signed u16
    assert state.target_velocity_rpm == -1000


def test_compat_write_run_mode_updates_enabled_state() -> None:
    """WINDCON 0x1008 write should control enable/disable state."""
    state = DriveState()
    state.write_register(0x1008, 0x0001)
    assert state.enabled is True

    state.write_register(0x1008, 0x0000)
    assert state.enabled is False


def test_compat_write_work_mode_updates_mode_name() -> None:
    """WINDCON 0x1007 should remap to known simulator mode names."""
    state = DriveState()
    state.write_register(0x1007, 2)
    assert state.mode == "POSITION"

    state.write_register(0x1007, 4)
    assert state.mode == "CURRENT"


def test_manual_override_preserves_values() -> None:
    """When manual override is active, step() should preserve manually-set values."""
    state = DriveState()
    state.manual_override_active = True
    state.velocity_actual_rpm = 2000
    state.motor_temp_c = 85
    state.driver_temp_c = 90
    state.bus_voltage_tenth_v = 600

    # Step should NOT change these values when manual override is active
    state.step(0.1)

    assert state.velocity_actual_rpm == 2000
    assert state.motor_temp_c == 85
    assert state.driver_temp_c == 90
    assert state.bus_voltage_tenth_v == 600


def test_manual_override_disabled_uses_auto_simulation() -> None:
    """When manual override is disabled, step() should use normal auto-simulation."""
    state = DriveState()
    state.manual_override_active = False
    state.enabled = True
    state.target_velocity_rpm = 1000
    state.velocity_actual_rpm = 0
    
    state.step(0.01)
    
    # With auto-simulation, should accelerate toward target
    assert state.velocity_actual_rpm > 0
    assert state.velocity_actual_rpm < state.target_velocity_rpm
