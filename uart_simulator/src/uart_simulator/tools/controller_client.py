from __future__ import annotations

from dataclasses import dataclass

import serial

from uart_simulator.protocol.ascii_modbus import ProtocolError
from uart_simulator.protocol.ascii_modbus import build_read_holding_request
from uart_simulator.protocol.ascii_modbus import build_write_single_request
from uart_simulator.protocol.ascii_modbus import decode_frame


class ControllerClientError(RuntimeError):
    pass


@dataclass(slots=True)
class ControllerTransaction:
    request_frame: bytes
    response_frame: bytes
    words_u16: list[int] | None = None


class ControllerClient:
    def __init__(self, port: str, baud: int, node_id: int = 1, timeout_s: float = 0.25) -> None:
        self.port = port.strip()
        self.baud = int(baud)
        self.node_id = int(node_id)
        self.timeout_s = float(timeout_s)

    def _open(self) -> serial.Serial:
        try:
            return serial.serial_for_url(
                self.port,
                baudrate=self.baud,
                timeout=self.timeout_s,
                write_timeout=self.timeout_s,
            )
        except Exception as exc:  # pragma: no cover - serial backend errors vary by platform
            raise ControllerClientError(f"Unable to open controller port {self.port!r}") from exc

    @staticmethod
    def _decode_words(payload: bytes) -> list[int]:
        if not payload:
            return []
        byte_count = payload[0]
        data = payload[1:]
        if byte_count != len(data) or byte_count % 2 != 0:
            raise ControllerClientError("Malformed Modbus read response")
        return [int.from_bytes(data[i : i + 2], "big") for i in range(0, len(data), 2)]

    def write_single(self, register: int, value: int) -> ControllerTransaction:
        request = build_write_single_request(self.node_id, register, value)
        request_frame = decode_frame(request)
        ser = self._open()
        try:
            ser.reset_input_buffer()
            ser.write(request)
            ser.flush()
            response = ser.read_until(b"\n")
        finally:
            ser.close()

        if not response:
            raise ControllerClientError("Timed out waiting for write response")

        try:
            frame = decode_frame(response)
        except ProtocolError as exc:
            raise ControllerClientError("Invalid write response") from exc

        if frame.address != self.node_id or frame.function != 0x06:
            raise ControllerClientError("Unexpected write response from controller")
        if frame.payload != request_frame.payload:
            # Modbus ASCII write-single usually echoes register/value payload.
            raise ControllerClientError("Controller returned a non-echo write response")

        return ControllerTransaction(request_frame=request, response_frame=response)

    def read_holding(self, start_register: int, count: int = 1) -> ControllerTransaction:
        request = build_read_holding_request(self.node_id, start_register, count)
        ser = self._open()
        try:
            ser.reset_input_buffer()
            ser.write(request)
            ser.flush()
            response = ser.read_until(b"\n")
        finally:
            ser.close()

        if not response:
            raise ControllerClientError("Timed out waiting for read response")

        try:
            frame = decode_frame(response)
        except ProtocolError as exc:
            raise ControllerClientError("Invalid read response") from exc

        if frame.address != self.node_id or frame.function != 0x03:
            raise ControllerClientError("Unexpected read response from controller")

        words = self._decode_words(frame.payload)
        return ControllerTransaction(request_frame=request, response_frame=response, words_u16=words)