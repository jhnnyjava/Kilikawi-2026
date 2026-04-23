"""Tests for emulator server frame classification."""

from uart_simulator.emulator.server import _looks_like_read_response_payload
from uart_simulator.emulator.server import _build_real_format_words
from uart_simulator.emulator.server import _build_response
from uart_simulator.emulator.server import _u16_to_i16
from uart_simulator.emulator.model import DriveState


def test_detects_read_response_payload_shape() -> None:
    """0x03 response payload uses byte_count + data bytes."""
    payload = bytes([0x14]) + bytes(range(0x14))
    assert _looks_like_read_response_payload(payload) is True


def test_rejects_read_request_payload_shape() -> None:
    """0x03 request payload is always 4 bytes and should not match response shape."""
    payload = b"\x10\x07\x00\x01"
    assert _looks_like_read_response_payload(payload) is False


def test_rejects_invalid_byte_count_mismatch() -> None:
    """Byte count mismatch should not be classified as a valid response payload."""
    payload = bytes([0x14]) + bytes(3)
    assert _looks_like_read_response_payload(payload) is False


def test_real_format_words_shape_and_marker() -> None:
    """Real-format simulated block must produce 10 words with 0xF00B marker."""
    words = _build_real_format_words(DriveState())
    assert len(words) == 10
    assert words[7] == 0xF00B
    assert all(0 <= w <= 0xFFFF for w in words)


def test_real_format_words_map_to_registers() -> None:
    """Stream word mapping should track compatibility register values."""
    state = DriveState()
    state.enabled = True
    state.target_velocity_rpm = 1200
    state.bus_voltage_tenth_v = 546
    state.driver_temp_c = 55
    state.error_code = 23

    words_u16 = _build_real_format_words(state)
    words_i16 = [_u16_to_i16(w) for w in words_u16]

    assert words_i16[0] == state.target_velocity_rpm  # speed
    assert words_i16[1] == _u16_to_i16(state.read_register(0x100C))  # current ref
    assert words_i16[2] == state.bus_voltage_tenth_v  # voltage
    assert words_i16[3] == 10000  # status latch when enabled
    assert words_i16[4] == state.driver_temp_c
    assert words_i16[5] == 1  # work mode
    assert words_i16[6] == 1  # run mode
    assert words_u16[7] == 0xF00B
    assert words_i16[8] == state.error_code
    assert words_i16[9] == 1  # fault active


def test_fc17_read_write_multiple_round_trip() -> None:
    """Function 0x17 should apply writes then return requested read block."""
    state = DriveState()

    # Write 0x1008=1 and 0x100B=1000, then read back 0x1008.
    read_start = 0x1008
    read_count = 1
    write_start = 0x1008
    write_values = [0x0001, 0x0000, 0x0000, 0x03E8]
    write_count = len(write_values)
    write_bytes = b"".join(v.to_bytes(2, "big") for v in write_values)

    payload = (
        read_start.to_bytes(2, "big")
        + read_count.to_bytes(2, "big")
        + write_start.to_bytes(2, "big")
        + write_count.to_bytes(2, "big")
        + bytes([len(write_bytes)])
        + write_bytes
    )

    resp = _build_response(state=state, function=0x17, payload=payload, node_id=1)
    assert resp[0] == 2  # read_count * 2

    r0 = int.from_bytes(resp[1:3], "big")
    assert r0 == state.read_register(0x1008)

    # Verify write side-effects also applied to live state.
    assert state.enabled is True
    assert state.target_velocity_rpm == 1000
