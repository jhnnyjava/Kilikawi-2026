from __future__ import annotations

STREAM_FIELD_NAMES = [
    "speed_feedback_rpm",
    "current_feedback_da",
    "bus_voltage_dv",
    "status_latch",
    "driver_temp_c",
    "work_mode",
    "run_mode",
    "marker_word",
    "fault_code",
    "fault_active",
]

MARKER_CLASSES = {
    0xF00B: "compat-marker",
    0x4CCD: "float-marker",
    0x0000: "zero-marker",
}

READABLE_REGISTERS = {
    0x0000: "ParamSelector",
    0x1000: "CompatStatus",
    0x1005: "CurrentBase",
    0x1006: "SpeedBase",
    0x1007: "WorkMode",
    0x1008: "RunMode",
    0x1009: "SpeedFdbCompat",
    0x100A: "CurrentFdbCompat",
    0x100B: "SpeedRefCompat",
    0x100C: "CurrentRefCompat",
    0x100D: "BusVoltage_dV",
    0x100E: "MotorTemp_C",
    0x1010: "StatusWordCompat",
    0x1011: "FaultOrOnline",
    0x1013: "FaultCode1",
    0x1014: "FaultCode2",
    0x1015: "DriverTemp_C",
    0x1016: "RunStateBits",
    0x1018: "TelemetryPair1_Hi",
    0x1019: "TelemetryPair1_Lo",
    0x101A: "TelemetryPair2_Hi",
    0x101B: "TelemetryPair2_Lo",
    0x101C: "FaultActive",
    0x101D: "FaultCode",
    0x11DE: "Controlword",
    0x11DF: "Statusword",
    0x11E6: "TargetVelocity",
    0x11EC: "VelocityActual",
    0x11F0: "TargetPosition",
    0x1256: "PositionActual",
    0x129E: "SpeedFeedback",
    0x129F: "CurrentFeedback",
    0x12B0: "SpeedReference",
    0x12B1: "CurrentReference",
    0x2002: "MotorTemp",
    0x2003: "BusVoltage",
    0x22A2: "DriverTemp",
    0x603F: "ErrorCode",
    0x6040: "Controlword",
    0x6041: "Statusword",
    0x6060: "ModesOfOperation",
    0x6061: "ModesOfOperationDisplay",
    0x6064: "PositionActualValue",
    0x606B: "VelocityDemand",
    0x606C: "VelocityActualValue",
    0x6071: "TargetTorque",
    0x6077: "TorqueActual",
    0x607A: "TargetPositionCiA402",
    0x60FF: "TargetVelocityCiA402",
}


def classify_marker(marker_word: int) -> str:
    return MARKER_CLASSES.get(marker_word & 0xFFFF, "mixed")


def label_stream_words(words_i16: list[int]) -> dict[str, int]:
    if len(words_i16) < len(STREAM_FIELD_NAMES):
        return {}
    return {
        name: words_i16[idx]
        for idx, name in enumerate(STREAM_FIELD_NAMES)
    }


def register_name(register: int) -> str:
    return READABLE_REGISTERS.get(register & 0xFFFF, f"0x{register & 0xFFFF:04X}")