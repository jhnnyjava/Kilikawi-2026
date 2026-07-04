"""CANopen CiA402 protocol mapping for WINDCON motor driver.

This module provides COB-ID definitions, PDO mappings, and telemetry decoding
for the CANopen CiA402 device profile used by the WINDCON servo controller.

Reference:
- CANopen CiA301/CiA402 standards
- WINDCON Servo Assistant/config/quick_config/CAN402_MapConfig.ini
"""

from dataclasses import dataclass
from enum import IntEnum


class COBIDType(IntEnum):
    """CANopen standard COB-ID types."""
    NMT = 0x000
    SYNC = 0x080
    EMCY = 0x080  # Emergency (node specific)
    TPDO1 = 0x180
    RPDO1 = 0x200
    TPDO2 = 0x280
    RPDO2 = 0x300
    TPDO3 = 0x380
    RPDO3 = 0x400
    TPDO4 = 0x480
    RPDO4 = 0x500
    TX_NMT_ERROR = 0x580
    RX_NMT_ERROR = 0x600
    TX_PDO_NOT_VALID = 0x680
    RX_PDO_NOT_VALID = 0x700


# CANopen register (OD - Object Dictionary) to field name mapping
# Register addresses from CAN402_MapConfig.ini and WINDCON_RS485_CAN_DATA_MAP.md
OD_REGISTER_MAP = {
    0x1007: "work_mode",
    0x1008: "startup_mode",
    0x10B2: "rs485_address",
    0x10B3: "rs485_baudrate",
    0x10B4: "rs485_protocol",
    0x10B5: "can_node_id",
    0x10B6: "can_communication_method",
    0x10B7: "can_baudrate",
    0x10B9: "rs485_timeout_ms",
    0x10BA: "can_timeout_ms",
    0x10BB: "canopen_timeout_ms",
    0x10BC: "timeout_behavior",
    0x1027: "current_ref_method",
    0x1044: "speed_ref_method",
    0x1070: "position_ref_method",
    0x1071: "motor_pole_pairs_num",
    0x1074: "motor_pole_pairs_denom",
    0x1162: "rpdo1_trans_type",
    0x1163: "rpdo2_trans_type",
    0x1164: "rpdo3_trans_type",
    0x1165: "rpdo4_trans_type",
    0x1166: "rpdo1_number",
    0x1167: "rpdo2_number",
    0x1168: "rpdo3_number",
    0x1169: "rpdo4_number",
    0x119E: "rxpdo1_map_para_1",
    0x11A0: "rxpdo1_map_para_2",
    0x11A2: "rxpdo1_map_para_3",
    0x11A4: "rxpdo1_map_para_4",
    0x11A6: "rxpdo2_map_para_1",
    0x11A8: "rxpdo2_map_para_2",
    0x11AA: "rxpdo2_map_para_3",
    0x11AC: "rxpdo2_map_para_4",
    0x11AE: "rxpdo3_map_para_1",
    0x11B0: "rxpdo3_map_para_2",
    0x11B2: "rxpdo3_map_para_3",
    0x11B4: "rxpdo3_map_para_4",
    0x11B6: "rxpdo4_map_para_1",
    0x11B8: "rxpdo4_map_para_2",
    0x11BA: "rxpdo4_map_para_3",
    0x11BC: "rxpdo4_map_para_4",
    0x11BE: "txpdo1_map_para_1",
    0x11C0: "txpdo1_map_para_2",
    0x11C2: "txpdo1_map_para_3",
    0x11C4: "txpdo1_map_para_4",
    0x11C6: "txpdo2_map_para_1",
    0x11C8: "txpdo2_map_para_2",
    0x11CA: "txpdo2_map_para_3",
    0x11CC: "txpdo2_map_para_4",
    0x11CE: "txpdo3_map_para_1",
    0x11D0: "txpdo3_map_para_2",
    0x11D2: "txpdo3_map_para_3",
    0x11D4: "txpdo3_map_para_4",
    0x11D6: "txpdo4_map_para_1",
    0x11D8: "txpdo4_map_para_2",
    0x11DA: "txpdo4_map_para_3",
    0x11DC: "txpdo4_map_para_4",
    0x1191: "tpdo1_trans_type",
    0x1192: "tpdo2_trans_type",
    0x1193: "tpdo3_trans_type",
    0x1194: "tpdo4_trans_type",
    0x1195: "tpdo1_init_time_ms",
    0x1196: "tpdo2_init_time_ms",
    0x1197: "tpdo3_init_time_ms",
    0x1198: "tpdo4_init_time_ms",
    0x1199: "tpdo1_event_time_ms",
    0x119A: "tpdo2_event_time_ms",
    0x119B: "tpdo3_event_time_ms",
    0x119C: "tpdo4_event_time_ms",
    0x11DE: "control_word",
    0x11DF: "status_word",
    0x11E0: "operation_mode",
    0x11E1: "display_mode",
    0x11E4: "target_torque",
    0x11E5: "torque_actual_value",
    0x11E6: "target_velocity",
    0x11EC: "velocity_actual_value",
    0x11F0: "target_position",
    0x1238: "max_motor_speed",
    0x1256: "position_actual_value",
    0x118E: "product_heartbeat_time",
}


def od_register_name(address: int) -> str:
    """Get human-readable name for an OD register address."""
    return OD_REGISTER_MAP.get(address, f"0x{address:04X}")


@dataclass(slots=True)
class CANopenFrame:
    """Decoded CANopen frame."""
    cob_id: int
    node_id: int
    function: str
    dlc: int
    data: bytes
    raw_id: int = 0
    
    @property
    def is_pdo(self) -> bool:
        """Check if this is a PDO frame."""
        func_bits = (self.cob_id & 0x780)
        return func_bits in (
            int(COBIDType.TPDO1),
            int(COBIDType.RPDO1),
            int(COBIDType.TPDO2),
            int(COBIDType.RPDO2),
            int(COBIDType.TPDO3),
            int(COBIDType.RPDO3),
            int(COBIDType.TPDO4),
            int(COBIDType.RPDO4),
        )
    
    @property
    def pdo_name(self) -> str:
        """Get PDO type name (TPDO1, RPDO2, etc.)."""
        func_bits = self.cob_id & 0x780
        if func_bits == int(COBIDType.TPDO1):
            return "TPDO1"
        elif func_bits == int(COBIDType.RPDO1):
            return "RPDO1"
        elif func_bits == int(COBIDType.TPDO2):
            return "TPDO2"
        elif func_bits == int(COBIDType.RPDO2):
            return "RPDO2"
        elif func_bits == int(COBIDType.TPDO3):
            return "TPDO3"
        elif func_bits == int(COBIDType.RPDO3):
            return "RPDO3"
        elif func_bits == int(COBIDType.TPDO4):
            return "TPDO4"
        elif func_bits == int(COBIDType.RPDO4):
            return "RPDO4"
        return f"PDO_0x{func_bits:03X}"


# Common PDO payload structures (inferred from RS485 telemetry and CAN config)
TPDO1_FIELDS = [
    ("status_word", 0, 2, "u16"),  # Offset 0-1: Status word
    ("position_feedback", 2, 4, "i32"),  # Offset 2-5: Position feedback
]

TPDO2_FIELDS = [
    ("velocity_feedback", 0, 2, "i16"),  # Offset 0-1: Velocity feedback (speed_feedback_rpm)
    ("current_feedback", 2, 2, "i16"),  # Offset 2-3: Current feedback (current_feedback_da)
    ("torque_actual", 4, 2, "i16"),  # Offset 4-5: Torque actual
]

TPDO3_FIELDS = [
    ("bus_voltage", 0, 2, "i16"),  # Offset 0-1: Bus voltage (bus_voltage_dv)
    ("driver_temp", 2, 2, "i16"),  # Offset 2-3: Driver temperature (driver_temp_c)
    ("motor_temp", 4, 2, "i16"),  # Offset 4-5: Motor temperature
]

RPDO1_FIELDS = [
    ("control_word", 0, 2, "u16"),  # Offset 0-1: Control word
    ("target_torque", 2, 2, "i16"),  # Offset 2-3: Target torque
]

RPDO2_FIELDS = [
    ("target_velocity", 0, 2, "i16"),  # Offset 0-1: Target velocity
    ("target_position", 2, 4, "i32"),  # Offset 2-5: Target position
]


def parse_canopen_frame(can_id: int, data: bytes) -> CANopenFrame:
    """Parse a raw CAN frame into a CANopen frame structure."""
    # Extract function bits (upper 7 bits excluding RTR)
    cob_id = can_id & 0x7FF
    function_bits = cob_id & 0x780
    node_id = cob_id & 0x7F
    dlc = len(data)
    
    # Determine function name
    function = _get_function_name(function_bits, cob_id)
    
    return CANopenFrame(
        cob_id=cob_id,
        node_id=node_id,
        function=function,
        dlc=dlc,
        data=data,
        raw_id=can_id,
    )


def _get_function_name(function_bits: int, cob_id: int) -> str:
    """Get human-readable function name from COB-ID."""
    if cob_id == 0x000:
        return "NMT"
    if cob_id == int(COBIDType.SYNC):
        return "SYNC"
    if int(COBIDType.EMCY) < cob_id <= 0x0FF:
        return "EMCY"

    if function_bits == int(COBIDType.NMT):
        return "NMT" if cob_id == 0x000 else "NMT_ERROR"
    elif function_bits == int(COBIDType.TPDO1):
        return "TPDO1"
    elif function_bits == int(COBIDType.RPDO1):
        return "RPDO1"
    elif function_bits == int(COBIDType.TPDO2):
        return "TPDO2"
    elif function_bits == int(COBIDType.RPDO2):
        return "RPDO2"
    elif function_bits == int(COBIDType.TPDO3):
        return "TPDO3"
    elif function_bits == int(COBIDType.RPDO3):
        return "RPDO3"
    elif function_bits == int(COBIDType.TPDO4):
        return "TPDO4"
    elif function_bits == int(COBIDType.RPDO4):
        return "RPDO4"
    elif function_bits == int(COBIDType.TX_NMT_ERROR):
        return "TX_NMT_ERROR"
    elif function_bits == int(COBIDType.RX_NMT_ERROR):
        return "RX_NMT_ERROR"
    else:
        return f"UNKNOWN_0x{cob_id:03X}"


def decode_tpdo1(data: bytes) -> dict[str, int]:
    """Decode TPDO1 (transmit PDO 1) payload."""
    result = {}
    if len(data) >= 2:
        result["status_word"] = int.from_bytes(data[0:2], "little", signed=False)
    if len(data) >= 6:
        result["position_feedback"] = int.from_bytes(data[2:6], "little", signed=True)
    return result


def decode_tpdo2(data: bytes) -> dict[str, int]:
    """Decode TPDO2 (transmit PDO 2) payload - telemetry."""
    result = {}
    if len(data) >= 2:
        result["velocity_feedback_rpm"] = int.from_bytes(data[0:2], "little", signed=True)
    if len(data) >= 4:
        result["current_feedback_da"] = int.from_bytes(data[2:4], "little", signed=True)
    if len(data) >= 6:
        result["torque_actual"] = int.from_bytes(data[4:6], "little", signed=True)
    return result


def decode_tpdo3(data: bytes) -> dict[str, int]:
    """Decode TPDO3 (transmit PDO 3) payload - environmental."""
    result = {}
    if len(data) >= 2:
        result["bus_voltage_dv"] = int.from_bytes(data[0:2], "little", signed=True)
    if len(data) >= 4:
        result["driver_temp_c"] = int.from_bytes(data[2:4], "little", signed=True)
    if len(data) >= 6:
        result["motor_temp_c"] = int.from_bytes(data[4:6], "little", signed=True)
    return result


def decode_rpdo1(data: bytes) -> dict[str, int]:
    """Decode RPDO1 (receive PDO 1) payload - control."""
    result = {}
    if len(data) >= 2:
        result["control_word"] = int.from_bytes(data[0:2], "little", signed=False)
    if len(data) >= 4:
        result["target_torque"] = int.from_bytes(data[2:4], "little", signed=True)
    return result


def decode_rpdo2(data: bytes) -> dict[str, int]:
    """Decode RPDO2 (receive PDO 2) payload - reference commands."""
    result = {}
    if len(data) >= 2:
        result["target_velocity_rpm"] = int.from_bytes(data[0:2], "little", signed=True)
    if len(data) >= 6:
        result["target_position"] = int.from_bytes(data[2:6], "little", signed=True)
    return result


def decode_pdo_payload(frame: CANopenFrame) -> dict[str, int]:
    """Decode PDO payload based on PDO type."""
    if not frame.is_pdo:
        return {}
    
    func_bits = frame.cob_id & 0x780
    
    if func_bits == int(COBIDType.TPDO1):
        return decode_tpdo1(frame.data)
    elif func_bits == int(COBIDType.TPDO2):
        return decode_tpdo2(frame.data)
    elif func_bits == int(COBIDType.TPDO3):
        return decode_tpdo3(frame.data)
    elif func_bits == int(COBIDType.RPDO1):
        return decode_rpdo1(frame.data)
    elif func_bits == int(COBIDType.RPDO2):
        return decode_rpdo2(frame.data)
    else:
        return {}
