"""Tests for the Modbus ASCII protocol codec."""

import pytest

from uart_simulator.protocol.ascii_modbus import (
    AsciiFrame,
    build_read_holding_request,
    build_write_single_request,
    calc_lrc,
    decode_frame,
    encode_frame,
    ProtocolError,
)


def test_lrc_calculation():
    """Test LRC checksum calculation."""
    data = b"\x01\x03\x00\x00\x00\x08"
    expected_lrc = 0xF4  # -12 & 0xFF = 244
    assert calc_lrc(data) == expected_lrc


def test_encode_frame():
    """Test frame encoding to ASCII format."""
    frame = encode_frame(address=1, function=3, payload=b"\x00\x00\x00\x08")
    # Format: :address_function_payload_lrc\r\n
    assert frame.startswith(b":")
    assert frame.endswith(b"\r\n")
    assert b"0103" in frame  # Should contain address=01, function=03


def test_decode_frame():
    """Test frame decoding from ASCII format."""
    raw = b":010300000008F4\r\n"
    frame = decode_frame(raw)
    assert frame.address == 1
    assert frame.function == 3
    assert frame.payload == b"\x00\x00\x00\x08"
    assert frame.lrc == 0xF4


def test_decode_frame_invalid_lrc():
    """Test that invalid LRC is rejected."""
    raw = b":010300000008FF\r\n"  # Wrong LRC
    with pytest.raises(ProtocolError, match="LRC mismatch"):
        decode_frame(raw)


def test_decode_frame_no_start_marker():
    """Test that missing start marker is detected."""
    raw = b"010300000008F4\r\n"  # Missing ':'
    with pytest.raises(ProtocolError, match="must start with"):
        decode_frame(raw)


def test_round_trip():
    """Test encoding then decoding produces original values."""
    address, function, payload = 1, 3, b"\x00\x10\x00\x04"
    encoded = encode_frame(address, function, payload)
    decoded = decode_frame(encoded)
    assert decoded.address == address
    assert decoded.function == function
    assert decoded.payload == payload


def test_build_read_holding_request():
    """Test building a read holding registers request."""
    request = build_read_holding_request(address=1, start_register=0, count=8)
    frame = decode_frame(request)
    assert frame.address == 1
    assert frame.function == 0x03
    assert frame.payload[:4] == b"\x00\x00\x00\x08"


def test_build_write_single_request():
    """Test building a write single register request."""
    request = build_write_single_request(address=1, register=0x11DE, value=0x000F)
    frame = decode_frame(request)
    assert frame.address == 1
    assert frame.function == 0x06
    assert frame.payload == b"\x11\xDE\x00\x0F"


def test_address_range_validation():
    """Test that invalid address is rejected on encode."""
    with pytest.raises(ProtocolError, match="Address"):
        encode_frame(address=256, function=3, payload=b"")


def test_function_range_validation():
    """Test that invalid function code is rejected on encode."""
    with pytest.raises(ProtocolError, match="Function"):
        encode_frame(address=1, function=256, payload=b"")
