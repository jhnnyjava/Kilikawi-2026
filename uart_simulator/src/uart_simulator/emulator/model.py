from __future__ import annotations

import math
import os
import struct
import threading
from dataclasses import dataclass, field


REG_CONTROLWORD = 0x11DE
REG_STATUSWORD = 0x11DF
REG_TARGET_VELOCITY = 0x11E6
REG_VELOCITY_ACTUAL = 0x11EC
REG_TARGET_POSITION = 0x11F0
REG_POSITION_ACTUAL = 0x1256
REG_BUS_VOLTAGE = 0x2003
REG_MOTOR_TEMP = 0x2002
REG_DRIVER_TEMP = 0x22A2
REG_ERROR_CODE = 0x603F
REG_SPEED_FDB = 0x129E
REG_CURRENT_FDB = 0x129F
REG_SPEED_REF = 0x12B0
REG_CURRENT_REF = 0x12B1

COMPAT_REG_WORK_MODE = 0x1007
COMPAT_REG_RUN_MODE = 0x1008
COMPAT_REG_SPEED_REF = 0x100B
COMPAT_REG_CURRENT_REF = 0x100C
COMPAT_REG_FAULT_CODE = 0x101D

# WINDCON startup commonly polls this block; provide non-zero defaults so
# UI pages treat the simulated drive as present and initialized.
COMPAT_DEFAULT_REGS: dict[int, int] = {
    0x1000: 0x0100,
    0x1005: 0x0258,
    0x1006: 0x0BB8,
    0x1007: 0x0001,
    0x1009: 0x0000,
    0x100A: 0x0000,
    0x100B: 0x0000,
    0x100C: 0x0000,
    0x100D: 0x021C,
    0x100E: 0x001E,
    0x1010: 0x0001,
    0x1011: 0x0001,
    0x1013: 0x0001,
    0x1014: 0x0001,
    0x1015: 0x0001,
    0x1016: 0x0001,
    0x1018: 0x0000,
    0x1019: 0x0000,
    0x101A: 0x0000,
    0x101B: 0x0000,
    0x101C: 0x0001,
    0x101D: 0x0001,
}

IO_PIN_COUNT = 30
ENCODER_PIN_COUNT = 8

IO_PIN_FUNCTIONS = [
    "DI0_START_ENABLE",
    "DI1_STOP_DISABLE",
    "DI2_ESTOP",
    "DI3_FAULT_RESET",
    "DI4_FORWARD_CMD",
    "DI5_REVERSE_CMD",
    "DI6_BRAKE_CMD",
    "DI7_ECO_MODE_SEL",
    "DI8_SPORT_MODE_SEL",
    "DI9_HOME_TRIGGER",
    "DO0_SERVO_READY",
    "DO1_SERVO_RUNNING",
    "DO2_FAULT_ACTIVE",
    "DO3_BRAKE_OUT",
    "DO4_ZERO_SPEED",
    "DO5_TARGET_REACHED",
    "AI0_THROTTLE",
    "AI1_BRAKE_LEVEL",
    "AO0_SPEED_MON",
    "AO1_TORQUE_MON",
    "RS485_A",
    "RS485_B",
    "CAN_H",
    "CAN_L",
    "ENCODER_PWR_5V",
    "ENCODER_GND",
    "AUX_24V_OUT",
    "AUX_GND",
    "MOTOR_TEMP_IN",
    "HEARTBEAT_LED",
]

ENCODER_PIN_FUNCTIONS = [
    "MOTOR_TEMP_PLUS",
    "COS_PLUS",
    "SIN_PLUS",
    "REF_PLUS",
    "MOTOR_TEMP_MINUS",
    "COS_MINUS",
    "SIN_MINUS",
    "REF_MINUS",
]


@dataclass(slots=True)
class DriveState:
    enabled: bool = False
    mode: str = "SPEED"
    throttle_percent: int = 100
    brake: bool = False
    eco_mode: bool = True
    gear: str = "FORWARD"
    target_velocity_rpm: int = 0
    velocity_actual_rpm: int = 0
    target_position: int = 0
    position_actual: int = 0
    position_setpoint_reached: bool = False
    bus_voltage_tenth_v: int = 540
    motor_temp_c: int = 30
    driver_temp_c: int = 32
    error_code: int = 0
    rotor_angle_deg: float = 0.0
    io_pins: list[bool] = field(default_factory=lambda: [False] * IO_PIN_COUNT)
    encoder_pins: list[bool] = field(default_factory=lambda: [False] * ENCODER_PIN_COUNT)
    compat_registers: dict[int, int] = field(default_factory=lambda: dict(COMPAT_DEFAULT_REGS))
    compat_param_selector: int = 0
    manual_override_active: bool = False
    force_feedback_to_target: bool = False
    _heartbeat_phase: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    _compat_mode_map: dict[int, str] = field(
        default_factory=lambda: {
            0: "SPEED",
            1: "SPEED",
            2: "POSITION",
            3: "TORQUE",
            4: "CURRENT",
            5: "HOMING",
            6: "PARAM_ID",
        },
        init=False,
        repr=False,
    )

    def step(self, dt_s: float) -> None:
        with self._lock:
            # If manual override is active, skip auto-simulation and use manually-set values
            if self.manual_override_active:
                self.rotor_angle_deg = (self.rotor_angle_deg + (self.velocity_actual_rpm * 6.0 * dt_s)) % 360.0
                self._heartbeat_phase += dt_s * 2.0 * math.pi
                self._update_io_pins()
                self._update_encoder_pins()
                return

            if self.force_feedback_to_target:
                self.velocity_actual_rpm = self.target_velocity_rpm
            else:
                accel_rpm_per_s = 800
                max_step = int(accel_rpm_per_s * dt_s)

                if not self.enabled or self.brake:
                    target = 0
                else:
                    throttle_scale = max(0.0, min(self.throttle_percent / 100.0, 1.0))
                    gear_sign = -1 if self.gear == "REVERSE" else 1
                    eco_scale = 0.6 if self.eco_mode else 1.0
                    target = int(self.target_velocity_rpm * throttle_scale * gear_sign * eco_scale)

                delta = target - self.velocity_actual_rpm
                if delta > max_step:
                    delta = max_step
                elif delta < -max_step:
                    delta = -max_step
                self.velocity_actual_rpm += delta

            # Position integration is coarse but useful for UI and protocol testing.
            self.position_actual += int((self.velocity_actual_rpm / 60.0) * 1000.0 * dt_s)
            self.position_setpoint_reached = abs(self.position_actual - self.target_position) <= 30

            # Very simple thermal model tied to speed magnitude.
            abs_speed = abs(self.velocity_actual_rpm)
            self.driver_temp_c = min(120, 30 + abs_speed // 200)
            self.motor_temp_c = min(140, 28 + abs_speed // 180)

            # Motor angle for animation.
            self.rotor_angle_deg = (self.rotor_angle_deg + (self.velocity_actual_rpm * 6.0 * dt_s)) % 360.0

            self._heartbeat_phase += dt_s * 2.0 * math.pi
            self._update_io_pins()
            self._update_encoder_pins()

    @property
    def status_word(self) -> int:
        status = 0x0001  # Ready to switch on
        if self.enabled:
            status |= 0x0004  # Operation enabled
        if self.error_code:
            status |= 0x0008  # Fault bit for simple testing
        if self.velocity_actual_rpm == 0:
            status |= 0x0010
        return status

    def write_register(self, reg: int, value: int) -> None:
        with self._lock:
            value &= 0xFFFF
            if reg == 0x0000:
                # Legacy WINDCON parameter-table selector/command register.
                self.compat_param_selector = value
                self.compat_registers[reg] = value
                return
            if reg == REG_CONTROLWORD:
                # Basic CiA402-like enable/disable interpretation.
                self.enabled = bool(value & 0x000F)
            elif reg == REG_TARGET_VELOCITY:
                self.target_velocity_rpm = _to_i16(value)
            elif reg == REG_TARGET_POSITION:
                self.target_position = _to_i16(value)
            elif reg == REG_ERROR_CODE and value == 0:
                self.error_code = 0
            else:
                # Apply WINDCON compatibility writes to live state so UI actions
                # reflected through 0x100x registers influence simulation.
                if reg == COMPAT_REG_WORK_MODE:
                    self.mode = self._compat_mode_map.get(value, self.mode)
                elif reg == COMPAT_REG_RUN_MODE:
                    # Some variants use 0/1 while others use bitfields.
                    self.enabled = bool(value & 0x0001)
                elif reg == COMPAT_REG_SPEED_REF:
                    self.target_velocity_rpm = _to_i16(value)
                elif reg == COMPAT_REG_CURRENT_REF:
                    # Current reference is in deci-amps on compatibility pages;
                    # map to an approximate speed target so telemetry responds.
                    cur_da = _to_i16(value)
                    if self.mode == "CURRENT":
                        self.target_velocity_rpm = int(cur_da * 12)
                elif reg == COMPAT_REG_FAULT_CODE:
                    self.error_code = value if value != 0 else 0

                # Preserve app-specific configuration writes for unknown regs.
                self.compat_registers[reg] = value

    def read_register(self, reg: int) -> int:
        with self._lock:
            if reg == 0x0000:
                # Legacy parameter read-back value channel.
                sel = self.compat_param_selector
                if sel == 0:
                    return 0x0001
                # WINDCON frequently writes descending negative even values
                # (FFFE, FFFC, ...) then reads 0x0000 to stream table values.
                idx = abs(_to_i16(sel)) // 2
                if idx > 0:
                    return self._param_table_value_by_index(idx - 1)
                # Fallback: direct synthetic value for non-index selectors.
                return _compat_param_value(sel)

            # WINDCON-specific compatibility block (0x1000 range).
            if reg == 0x1000:
                # Observed WINDCON expects 0x0100-style status baseline.
                status = 0x0100
                if self.enabled and abs(self.velocity_actual_rpm) > 5:
                    status |= 0x0001
                return status & 0xFFFF
            if reg == 0x1004:
                # Legacy "table data ready"/online flag used by parameter pages.
                return 1
            if reg == 0x1005:
                # VSY config maps this as CurrentBase.
                return self._compat_current_base()
            if reg == 0x1006:
                # VSY config maps this as SpeedBase.
                return self._compat_speed_base()
            if reg == 0x1007:
                # Work mode: keep online/active.
                return 1
            if reg == 0x1008:
                # Run mode.
                return 1 if self.enabled else 0
            if reg == 0x1009:
                # Speed feedback (signed RPM).
                return _to_u16(self.velocity_actual_rpm)
            if reg == 0x100A:
                # Current feedback in deci-amps, signed with motion direction.
                return _to_u16(self._compat_current_feedback_dA())
            if reg == 0x100B:
                # Speed reference (signed RPM).
                return _to_u16(self.target_velocity_rpm)
            if reg == 0x100C:
                # Current reference in deci-amps, signed with target direction.
                return _to_u16(self._compat_current_ref_dA())
            if reg == 0x100D:
                return self.bus_voltage_tenth_v & 0xFFFF
            if reg == 0x100E:
                return self.motor_temp_c & 0xFFFF
            if reg == 0x1010:
                # Statusword projection for compatibility pages.
                return self.status_word & 0xFFFF
            if reg == 0x1011:
                # Non-zero when fault active; otherwise keep online marker.
                return (self.error_code & 0xFFFF) if self.error_code else 1
            if reg in (0x1018, 0x1019):
                mode = _windcon_compat_telemetry_mode()
                if mode == "FAULT_CODES":
                    # VSY_double maps FaultCode1/FaultCode2 to 0x1018/0x1019.
                    # Keep both non-zero on fault so alarm pages reliably latch.
                    if self.error_code:
                        return self.error_code & 0xFFFF
                    return 0
                # Some WINDCON builds label this pair as battery voltage, while
                # others use current. Default to voltage for better UI behavior.
                value = (
                    abs(self.velocity_actual_rpm) / 120.0
                    if mode == "CURRENT_SPEED"
                    else (self.bus_voltage_tenth_v / 10.0)
                )
                hi, lo = _f32_words(value)
                return hi if reg == 0x1018 else lo
            if reg in (0x101A, 0x101B):
                mode = _windcon_compat_telemetry_mode()
                if mode == "FAULT_CODES":
                    # Keep this pair aligned to status/speed words for variants
                    # that do not decode float telemetry on 0x101A/0x101B.
                    value = _compat_mode_code(self.mode) if reg == 0x101A else _to_u16(self.velocity_actual_rpm)
                    return value & 0xFFFF
                # Some WINDCON builds label this pair as motor temperature,
                # while others use speed. Default to temperature for UI labels.
                value = (
                    abs(self.velocity_actual_rpm) / 1000.0
                    if mode == "CURRENT_SPEED"
                    else float(self.motor_temp_c)
                )
                hi, lo = _f32_words(value)
                return hi if reg == 0x101A else lo
            if reg == 0x1013:
                return self.error_code & 0xFFFF
            if reg == 0x1014:
                return self.error_code & 0xFFFF
            if reg == 0x1015:
                return self.driver_temp_c & 0xFFFF
            if reg == 0x1016:
                # Compact run-state bitfield.
                bitfield = 0
                if self.enabled:
                    bitfield |= 0x0001
                if abs(self.velocity_actual_rpm) > 5:
                    bitfield |= 0x0002
                if self.brake:
                    bitfield |= 0x0004
                return bitfield
            if reg == 0x101C:
                return 1 if (self.error_code != 0) else 0
            if reg == 0x101D:
                return self.error_code & 0xFFFF
            if reg == REG_SPEED_FDB:
                return _to_u16(abs(self.velocity_actual_rpm))
            if reg == REG_CURRENT_FDB:
                return _to_u16(int(abs(self.velocity_actual_rpm) * 100 / 120))
            if reg == REG_SPEED_REF:
                return _to_u16(self.target_velocity_rpm)
            if reg == REG_CURRENT_REF:
                return _to_u16(int(abs(self.target_velocity_rpm) * 100 / 120))

            if reg == REG_CONTROLWORD:
                return 0x000F if self.enabled else 0x0006
            if reg == REG_STATUSWORD:
                return self.status_word
            if reg == REG_TARGET_VELOCITY:
                return _to_u16(self.target_velocity_rpm)
            if reg == REG_VELOCITY_ACTUAL:
                return _to_u16(self.velocity_actual_rpm)
            if reg == REG_TARGET_POSITION:
                return _to_u16(self.target_position)
            if reg == REG_POSITION_ACTUAL:
                return _to_u16(self.position_actual)
            if reg == REG_BUS_VOLTAGE:
                return self.bus_voltage_tenth_v & 0xFFFF
            if reg == REG_MOTOR_TEMP:
                return self.motor_temp_c & 0xFFFF
            if reg == REG_DRIVER_TEMP:
                return self.driver_temp_c & 0xFFFF
            if reg == REG_ERROR_CODE:
                return self.error_code & 0xFFFF
            return self.compat_registers.get(reg, 0)

    def _param_table_value_by_index(self, index: int) -> int:
        addresses = _param_table_addresses()
        if not addresses:
            return 0x0001
        reg = addresses[index % len(addresses)]
        # Lock-safe read path for selector-streamed table values.
        if reg == 0x1004:
            return 1
        if reg == 0x1005:
            return self._compat_current_base()
        if reg == 0x1006:
            return self._compat_speed_base()
        if reg == 0x1007:
            return 1
        if reg == 0x1008:
            return 1 if self.enabled else 0
        if reg == 0x1009:
            return _to_u16(self.velocity_actual_rpm)
        if reg == 0x100A:
            return _to_u16(self._compat_current_feedback_dA())
        if reg == 0x100B:
            return _to_u16(self.target_velocity_rpm)
        if reg == 0x100C:
            return _to_u16(self._compat_current_ref_dA())
        if reg == 0x100D:
            return self.bus_voltage_tenth_v & 0xFFFF
        if reg == 0x100E:
            return self.motor_temp_c & 0xFFFF
        if reg == 0x1010:
            return self.status_word & 0xFFFF
        if reg == 0x1011:
            return (self.error_code & 0xFFFF) if self.error_code else 1
        if reg == 0x1013:
            return self.error_code & 0xFFFF
        if reg == 0x1014:
            return self.error_code & 0xFFFF
        if reg == 0x1015:
            return self.driver_temp_c & 0xFFFF
        if reg == 0x1016:
            bitfield = 0
            if self.enabled:
                bitfield |= 0x0001
            if abs(self.velocity_actual_rpm) > 5:
                bitfield |= 0x0002
            if self.brake:
                bitfield |= 0x0004
            return bitfield
        if reg == 0x101C:
            return 1 if (self.error_code != 0) else 0
        if reg == 0x101D:
            return self.error_code & 0xFFFF
        if reg == REG_SPEED_FDB:
            return _to_u16(abs(self.velocity_actual_rpm))
        if reg == REG_CURRENT_FDB:
            return _to_u16(int(abs(self.velocity_actual_rpm) * 100 / 120))
        if reg == REG_SPEED_REF:
            return _to_u16(self.target_velocity_rpm)
        if reg == REG_CURRENT_REF:
            return _to_u16(int(abs(self.target_velocity_rpm) * 100 / 120))

        value = self.compat_registers.get(reg, 0)
        return value if value != 0 else ((reg ^ 0x5A5A) & 0xFFFF) or 0x0001

    def _compat_current_base(self) -> int:
        # Base in deci-amps. Default 60.0A -> 600.
        return max(1, min(0xFFFF, int(os.environ.get("WINDCON_CURRENT_BASE_DA", "600"))))

    def _compat_speed_base(self) -> int:
        # Base in RPM. Default 3000rpm.
        return max(1, min(0xFFFF, int(os.environ.get("WINDCON_SPEED_BASE_RPM", "3000"))))

    def _compat_current_feedback_dA(self) -> int:
        # Approximate phase current from speed magnitude, sign follows rotation.
        sign = -1 if self.velocity_actual_rpm < 0 else 1
        amps = abs(self.velocity_actual_rpm) / 120.0
        return int(sign * amps * 10.0)

    def _compat_current_ref_dA(self) -> int:
        sign = -1 if self.target_velocity_rpm < 0 else 1
        amps = abs(self.target_velocity_rpm) / 120.0
        return int(sign * amps * 10.0)

    def read_block(self, start: int, count: int) -> list[int]:
        return [self.read_register(start + i) for i in range(count)]

    def set_mode(self, mode: str) -> None:
        with self._lock:
            self.mode = mode

    def set_throttle(self, percent: int) -> None:
        with self._lock:
            self.throttle_percent = max(0, min(100, int(percent)))

    def set_brake(self, active: bool) -> None:
        with self._lock:
            self.brake = bool(active)

    def set_eco_mode(self, eco_mode: bool) -> None:
        with self._lock:
            self.eco_mode = bool(eco_mode)

    def set_gear(self, gear: str) -> None:
        with self._lock:
            self.gear = "REVERSE" if gear == "REVERSE" else "FORWARD"

    def set_target_position(self, value: int) -> None:
        with self._lock:
            self.target_position = int(value)

    def clear_fault(self) -> None:
        with self._lock:
            self.error_code = 0

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "enabled": self.enabled,
                "mode": self.mode,
                "throttle_percent": self.throttle_percent,
                "brake": self.brake,
                "eco_mode": self.eco_mode,
                "gear": self.gear,
                "target_velocity_rpm": self.target_velocity_rpm,
                "velocity_actual_rpm": self.velocity_actual_rpm,
                "target_position": self.target_position,
                "position_actual": self.position_actual,
                "bus_voltage_tenth_v": self.bus_voltage_tenth_v,
                "motor_temp_c": self.motor_temp_c,
                "driver_temp_c": self.driver_temp_c,
                "error_code": self.error_code,
                "rotor_angle_deg": self.rotor_angle_deg,
                "io_pins": list(self.io_pins),
                "encoder_pins": list(self.encoder_pins),
            }

    def _update_io_pins(self) -> None:
        pulse_fast = int(abs(math.sin(self._heartbeat_phase * 6.0)) > 0.2)
        pulse_slow = int(abs(math.sin(self._heartbeat_phase * 2.0)) > 0.2)

        base = [False] * IO_PIN_COUNT

        def set_pin(a_pin: int, level_high: bool) -> None:
            # A1..A30 maps to index 0..29.
            base[a_pin - 1] = bool(level_high)

        # Row 3 signals (A1, A4, A7, A10, A13, A16, A19, A22, A25, A28)
        set_pin(1, bool(pulse_fast and abs(self.velocity_actual_rpm) > 30))   # Wheel motion pulse
        set_pin(4, False)                                                      # Isolated GND
        set_pin(7, False)                                                      # Instrument GND
        set_pin(10, self.enabled or self.throttle_percent > 0)                 # Key switch power in
        set_pin(13, bool(self.error_code))                                     # Key switch alarm in
        set_pin(16, False)                                                     # Signal GND
        set_pin(19, False)                                                     # Signal GND
        set_pin(22, True)                                                      # 5V throttle supply
        set_pin(25, self.enabled)                                              # 12V+ output
        set_pin(28, self.enabled or self.throttle_percent > 0)                 # B+ output

        # Row 1 signals (A2, A3, A5, A6, A8, A9, A11, A12, A14, A15)
        set_pin(2, bool(pulse_slow))                                           # CAN L activity
        set_pin(3, not bool(pulse_slow))                                       # CAN H activity
        set_pin(5, True)                                                       # Isolated 5V
        set_pin(6, bool(pulse_fast and abs(self.velocity_actual_rpm) > 30))    # Speed pulse
        set_pin(8, bool(pulse_slow))                                           # RS485 T+
        set_pin(9, not bool(pulse_slow))                                       # RS485 T-
        set_pin(11, self.gear != "REVERSE")                                  # Active LOW reverse
        set_pin(12, not self.eco_mode)                                         # Active LOW mid/low speed
        set_pin(14, self.error_code == 0)                                      # Active LOW alarm/lock
        set_pin(15, not (self.eco_mode and self.throttle_percent < 65))        # Active LOW high speed

        # Row 2 signals (A17, A18, A20, A21, A23, A24, A26, A27, A29, A30)
        set_pin(17, not self.brake)                                            # Active LOW low brake
        set_pin(18, not self.brake)                                            # Active LOW P-gear
        set_pin(20, True)                                                      # Active LOW voltage select (not asserted)
        set_pin(21, not self.brake)                                            # Active LOW P-gear select
        set_pin(23, self.gear != "REVERSE")                                  # Active LOW direction select
        set_pin(24, self.brake)                                                # Active HIGH brake
        set_pin(26, self.enabled)                                              # READY output
        set_pin(27, False)                                                     # Signal GND
        set_pin(29, False)                                                     # Throttle GND
        set_pin(30, self.throttle_percent > 0)                                 # Throttle analog represented as digital high/low

        self.io_pins = base

    def _update_encoder_pins(self) -> None:
        # Connector B matches the resolver+temperature mapping from the manual.
        theta = math.radians(self.rotor_angle_deg)
        sin_plus = math.sin(theta) >= 0.0
        cos_plus = math.cos(theta) >= 0.0

        # Excitation reference is shown as an AC pair in the UI (phase-opposed).
        ref_plus = math.sin(self._heartbeat_phase * 8.0) >= 0.0

        temp_ok = (self.error_code == 0) and (self.motor_temp_c < 130)
        self.encoder_pins = [
            temp_ok,           # B1  Motor Temp (+)
            cos_plus,          # B2  COS+
            sin_plus,          # B3  SIN+
            ref_plus,          # B4  REF+
            temp_ok,           # B5  Motor Temp (-)
            not cos_plus,      # B6  COS-
            not sin_plus,      # B7  SIN-
            not ref_plus,      # B8  REF-
        ]


def _to_i16(value: int) -> int:
    value &= 0xFFFF
    if value & 0x8000:
        return value - 0x10000
    return value


def _to_u16(value: int) -> int:
    return value & 0xFFFF


def _split_i32_words(value: int) -> tuple[int, int]:
    v = value & 0xFFFFFFFF
    return (v >> 16) & 0xFFFF, v & 0xFFFF


def _param_table_addresses() -> list[int]:
    # Primary addresses from VSY_Single/CAN402 map sections that WINDCON pages poll.
    return [
        0x1004,
        0x1005,
        0x1006,
        0x1007,
        0x1008,
        0x1009,
        0x100A,
        0x100B,
        0x100C,
        0x100D,
        0x100E,
        0x1010,
        0x1011,
        0x1013,
        0x1014,
        0x1015,
        0x1016,
        0x1018,
        0x101A,
        0x101C,
        0x101D,
        REG_CONTROLWORD,
        REG_STATUSWORD,
        REG_TARGET_VELOCITY,
        REG_VELOCITY_ACTUAL,
        REG_TARGET_POSITION,
        REG_POSITION_ACTUAL,
        REG_SPEED_REF,
        REG_SPEED_FDB,
        REG_CURRENT_REF,
        REG_CURRENT_FDB,
        REG_BUS_VOLTAGE,
        REG_MOTOR_TEMP,
        REG_DRIVER_TEMP,
        REG_ERROR_CODE,
    ]


def _compat_param_value(selector_u16: int) -> int:
    # Deterministic, non-zero synthetic value for legacy selector-based reads.
    sel = abs(_to_i16(selector_u16))
    return ((sel ^ 0x55AA) & 0xFFFF) or 0x0001


def _f32_words(value: float) -> tuple[int, int]:
    packed = struct.pack(">f", float(value))
    hi = int.from_bytes(packed[0:2], "big")
    lo = int.from_bytes(packed[2:4], "big")

    # Many HMIs (including some WINDCON builds) decode 32-bit values as CDAB
    # (low-word first). Allow switching via env var without code changes.
    # Supported: ABCD (default Modbus), CDAB (word-swapped).
    order = os.environ.get("WINDCON_FLOAT_WORD_ORDER", "ABCD").strip().upper()
    if order == "ABCD":
        return hi, lo
    return lo, hi


def _windcon_compat_telemetry_mode() -> str:
    # `VOLT_TEMP` matches WINDCON variants that display battery+temperature on
    # 0x1018/0x101A.
    # `CURRENT_SPEED` keeps older current/speed float mapping.
    # `FAULT_CODES` matches VSY_double where FaultCode1/FaultCode2 are 0x1018/0x1019.
    mode = os.environ.get("WINDCON_1018_101A_MODE", "VOLT_TEMP").strip().upper()
    if mode == "CURRENT_SPEED":
        return "CURRENT_SPEED"
    if mode == "FAULT_CODES":
        return "FAULT_CODES"
    return "VOLT_TEMP"


def _compat_mode_code(mode_name: str) -> int:
    m = (mode_name or "").upper()
    if m == "POSITION":
        return 2
    if m == "TORQUE":
        return 3
    if m == "CURRENT":
        return 4
    if m == "HOMING":
        return 5
    if m == "PARAM_ID":
        return 6
    return 1


