from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class AsciiFrame:
    address: int
    function: int
    payload: bytes
    lrc: int


class ProtocolError(ValueError):
    pass


def calc_lrc(data: bytes) -> int:
    """Modbus ASCII LRC over binary bytes before ASCII hex conversion."""
    return (-sum(data)) & 0xFF


def encode_frame(address: int, function: int, payload: bytes) -> bytes:
    if not (0 <= address <= 0xFF):
        raise ProtocolError("Address out of range")
    if not (0 <= function <= 0xFF):
        raise ProtocolError("Function out of range")

    body = bytes([address, function]) + payload
    lrc = calc_lrc(body)
    ascii_hex = (body + bytes([lrc])).hex().upper().encode("ascii")
    return b":" + ascii_hex + b"\r\n"


def decode_frame(raw: bytes) -> AsciiFrame:
    data = raw.strip()
    if not data.startswith(b":"):
        raise ProtocolError("Frame must start with ':'")

    hex_blob = data[1:]
    if len(hex_blob) < 6 or len(hex_blob) % 2 != 0:
        raise ProtocolError("Invalid ASCII frame length")

    try:
        binary = bytes.fromhex(hex_blob.decode("ascii"))
    except Exception as exc:
        raise ProtocolError("Invalid hex in frame") from exc

    body, lrc = binary[:-1], binary[-1]
    if calc_lrc(body) != lrc:
        raise ProtocolError("LRC mismatch")
    if len(body) < 2:
        raise ProtocolError("Frame too short")

    return AsciiFrame(
        address=body[0],
        function=body[1],
        payload=body[2:],
        lrc=lrc,
    )


def build_read_holding_request(address: int, start_register: int, count: int) -> bytes:
    payload = start_register.to_bytes(2, "big") + count.to_bytes(2, "big")
    return encode_frame(address, 0x03, payload)


def build_write_single_request(address: int, register: int, value: int) -> bytes:
    payload = register.to_bytes(2, "big") + value.to_bytes(2, "big")
    return encode_frame(address, 0x06, payload)
