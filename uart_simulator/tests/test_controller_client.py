from __future__ import annotations

from uart_simulator.protocol.ascii_modbus import encode_frame
from uart_simulator.tools.controller_client import ControllerClient


class FakeSerial:
    def __init__(self, response: bytes) -> None:
        self.response = response
        self.written = b""
        self.closed = False

    def reset_input_buffer(self) -> None:
        return None

    def write(self, data: bytes) -> int:
        self.written += data
        return len(data)

    def flush(self) -> None:
        return None

    def read_until(self, sep: bytes = b"\n") -> bytes:
        return self.response

    def close(self) -> None:
        self.closed = True


def test_write_single_sends_echo_request(monkeypatch) -> None:
    response = encode_frame(1, 0x06, b"\x10\x08\x00\x01")
    serial_obj = FakeSerial(response)

    monkeypatch.setattr(
        "uart_simulator.tools.controller_client.serial.serial_for_url",
        lambda *args, **kwargs: serial_obj,
    )

    client = ControllerClient("COM5", 115200, node_id=1)
    tx = client.write_single(0x1008, 0x0001)

    assert serial_obj.written.startswith(b":01061008")
    assert tx.request_frame.startswith(b":01061008")
    assert tx.response_frame == response
    assert serial_obj.closed is True


def test_read_holding_decodes_words(monkeypatch) -> None:
    response = encode_frame(1, 0x03, b"\x04\x00\x01\x00\x02")
    serial_obj = FakeSerial(response)

    monkeypatch.setattr(
        "uart_simulator.tools.controller_client.serial.serial_for_url",
        lambda *args, **kwargs: serial_obj,
    )

    client = ControllerClient("COM5", 115200, node_id=1)
    tx = client.read_holding(0x1008, 2)

    assert serial_obj.written.startswith(b":01031008")
    assert tx.words_u16 == [1, 2]
    assert serial_obj.closed is True