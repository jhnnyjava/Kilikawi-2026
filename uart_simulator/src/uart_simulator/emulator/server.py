from __future__ import annotations

import argparse
import math
import os
import time
from collections.abc import Callable
from typing import Any

import serial

from uart_simulator.emulator.model import DriveState
from uart_simulator.protocol.ascii_modbus import ProtocolError, decode_frame, encode_frame


_COMPAT_REG_NAMES: dict[int, str] = {
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
}


def _looks_like_read_response_payload(payload: bytes) -> bool:
    # Read response payload format is: [byte_count][data...], where
    # len(data) equals byte_count. This is different from read request payload
    # format [start_hi][start_lo][count_hi][count_lo].
    if len(payload) < 1:
        return False
    byte_count = payload[0]
    return len(payload) == byte_count + 1


def _to_u16_i16(value: int) -> int:
    return int(value) & 0xFFFF


def _u16_to_i16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if (value & 0x8000) else value


def _decode_read_response_words(payload: bytes) -> list[int] | None:
    if not payload:
        return None
    byte_count = payload[0]
    data = payload[1:]
    if byte_count != len(data) or (byte_count % 2) != 0:
        return None
    words: list[int] = []
    for i in range(0, len(data), 2):
        u16 = int.from_bytes(data[i : i + 2], "big")
        words.append(_u16_to_i16(u16))
    return words


def _format_words(words: list[int], limit: int = 10) -> str:
    show = words[:limit]
    body = " ".join(f"w{i}={v}" for i, v in enumerate(show))
    if len(words) > limit:
        return f"{body} ..."
    return body


def _format_read_request_detail(payload: bytes) -> str:
    if len(payload) != 4:
        return ""
    start = int.from_bytes(payload[0:2], "big")
    count = int.from_bytes(payload[2:4], "big")
    if count <= 0:
        return ""
    if count == 1:
        name = _COMPAT_REG_NAMES.get(start)
        if name:
            return f" [req_reg] 0x{start:04X} {name}"
        return f" [req_reg] 0x{start:04X}"
    names: list[str] = []
    for i in range(count):
        reg = start + i
        name = _COMPAT_REG_NAMES.get(reg)
        names.append(name if name else f"0x{reg:04X}")
    joined = ", ".join(names)
    return f" [req_regs] 0x{start:04X}+{count} ({joined})"


def _build_real_format_words(state: DriveState) -> list[int]:
    # Keep 10-word shape used by WINDCON's :010314.... path, but bind each
    # word to live compatibility telemetry/status so GUI/manual changes show up.
    t = time.perf_counter()

    # Use reference values so WINDCON displays the emulator's intended targets
    # instead of the scaled feedback values.
    speed = _u16_to_i16(state.read_register(0x100B))
    current = _u16_to_i16(state.read_register(0x100C))
    voltage = _u16_to_i16(state.read_register(0x100D))
    status = state.read_register(0x1010) & 0xFFFF
    driver_temp = _u16_to_i16(state.read_register(0x1015))
    mode_word = state.read_register(0x1007) & 0xFFFF
    run_word = state.read_register(0x1008) & 0xFFFF
    marker = 0xF00B
    fault_code = _u16_to_i16(state.read_register(0x101D))
    fault_active = 1 if (state.read_register(0x101C) & 0xFFFF) else 0

    # Add tiny deterministic jitter on current channel to avoid some UI pages
    # suppressing updates when values are perfectly static.
    w0 = speed
    w1 = current + int(1.0 * math.sin(t * 1.7))
    w2 = voltage
    w3 = 10000 if (status & 0x0004) else 0
    w4 = driver_temp
    w5 = mode_word
    w6 = run_word
    w7 = marker
    w8 = fault_code
    w9 = fault_active

    return [
        _to_u16_i16(w0),
        _to_u16_i16(w1),
        _to_u16_i16(w2),
        _to_u16_i16(w3),
        _to_u16_i16(w4),
        _to_u16_i16(w5),
        _to_u16_i16(w6),
        _to_u16_i16(w7),
        _to_u16_i16(w8),
        _to_u16_i16(w9),
    ]


def _build_stream_format_words(state: DriveState, marker_word: int) -> list[int]:
    words = _build_real_format_words(state)
    if len(words) >= 8:
        words[7] = marker_word & 0xFFFF
    return words


def _stream_marker_word(mode: str, tick_index: int) -> int:
    mode_norm = (mode or "compat").strip().lower()
    if mode_norm == "float":
        return 0x4CCD
    if mode_norm == "zero":
        return 0x0000
    if mode_norm == "auto":
        # Cycle through observed families from capture to mimic mixed streams.
        pattern = (0xF00B, 0x4CCD, 0x0000)
        return pattern[tick_index % len(pattern)]
    return 0xF00B


def _is_compat_poll_request(function: int, payload: bytes) -> bool:
    if function not in (0x03, 0x04) or len(payload) != 4:
        return False
    start = int.from_bytes(payload[0:2], "big")
    count = int.from_bytes(payload[2:4], "big")
    if count <= 0:
        return False
    end = start + count - 1
    # WINDCON compatibility pages poll this block heavily and expect a stable
    # frame schema. Switching marker families while this block is active causes
    # field remapping jitter in the UI.
    return not (end < 0x1000 or start > 0x101D)


def _build_response(state: DriveState, function: int, payload: bytes, node_id: int) -> bytes:
    if function in (0x03, 0x04):
        if len(payload) != 4:
            raise ProtocolError("Read request payload must be 4 bytes")
        start = int.from_bytes(payload[0:2], "big")
        count = int.from_bytes(payload[2:4], "big")
        if count <= 0 or count > 120:
            raise ProtocolError("Read count out of range")

        # Compatibility mode for controller-like 0x14-byte read responses.
        # Enabled by default and can be disabled with:
        # WINDCON_SIM_REAL_FORMAT=0
        use_real_like = os.environ.get("WINDCON_SIM_REAL_FORMAT", "1").strip() != "0"
        if use_real_like and start == 0x0000 and count == 10:
            values = _build_real_format_words(state)
        else:
            values = state.read_block(start, count)

        body = bytearray([count * 2])
        for value in values:
            body.extend(int(value & 0xFFFF).to_bytes(2, "big"))
        return bytes(body)

    if function == 0x06:
        if len(payload) != 4:
            raise ProtocolError("Write single payload must be 4 bytes")
        register = int.from_bytes(payload[0:2], "big")
        value = int.from_bytes(payload[2:4], "big")
        state.write_register(register, value)
        # Modbus convention: echo write request payload.
        return payload

    if function == 0x10:
        if len(payload) < 5:
            raise ProtocolError("Write multiple payload too short")
        start = int.from_bytes(payload[0:2], "big")
        count = int.from_bytes(payload[2:4], "big")
        byte_count = payload[4]
        data = payload[5:]
        if count <= 0 or count > 120:
            raise ProtocolError("Write multiple count out of range")
        if byte_count != len(data) or byte_count != count * 2:
            raise ProtocolError("Write multiple byte count mismatch")
        for i in range(count):
            off = i * 2
            value = int.from_bytes(data[off : off + 2], "big")
            state.write_register(start + i, value)
        return payload[:4]

    if function == 0x17:
        # Read/Write Multiple Registers (Modbus FC23)
        # Request: read_start(2) read_count(2) write_start(2) write_count(2) byte_count(1) write_data
        # Response: byte_count(1) read_data
        if len(payload) < 9:
            raise ProtocolError("Read/Write multiple payload too short")
        read_start = int.from_bytes(payload[0:2], "big")
        read_count = int.from_bytes(payload[2:4], "big")
        write_start = int.from_bytes(payload[4:6], "big")
        write_count = int.from_bytes(payload[6:8], "big")
        byte_count = payload[8]
        write_data = payload[9:]

        if read_count <= 0 or read_count > 120:
            raise ProtocolError("Read/Write multiple read-count out of range")
        if write_count <= 0 or write_count > 120:
            raise ProtocolError("Read/Write multiple write-count out of range")
        if byte_count != len(write_data) or byte_count != write_count * 2:
            raise ProtocolError("Read/Write multiple byte count mismatch")

        for i in range(write_count):
            off = i * 2
            value = int.from_bytes(write_data[off : off + 2], "big")
            state.write_register(write_start + i, value)

        values = state.read_block(read_start, read_count)
        body = bytearray([read_count * 2])
        for value in values:
            body.extend(int(value & 0xFFFF).to_bytes(2, "big"))
        return bytes(body)

    raise ProtocolError(f"Unsupported function 0x{function:02X}")


def run(
    port: str,
    baud: int,
    node_id: int,
    state: DriveState | None = None,
    step_state: bool = True,
    stop_predicate: Callable[[], bool] | None = None,
    trace_frames: bool = False,
    push_telemetry: bool = False,
    push_interval_ms: int = 20,
    push_marker_mode: str = "compat",
    push_when_idle_ms: int = 120,
    push_schema_lock_ms: int = 900,
    frame_event_cb: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    state = state or DriveState()
    ser = serial.serial_for_url(port, baudrate=baud, timeout=0.02)

    print(f"[emulator] Listening on {port} @ {baud}, node={node_id}")
    if push_telemetry:
        print(
            f"[emulator] Autonomous telemetry push enabled: "
            f"interval={push_interval_ms}ms marker={push_marker_mode} "
            f"idle-gate={push_when_idle_ms}ms schema-lock={push_schema_lock_ms}ms"
        )
    rx_buffer = bytearray()
    last_tick = time.perf_counter()
    last_push = last_tick
    push_tick = 0
    last_master_activity = last_tick
    compat_schema_lock_until = 0.0

    try:
        while True:
            if stop_predicate is not None and stop_predicate():
                break
            now = time.perf_counter()
            dt = now - last_tick
            if dt > 0 and step_state:
                state.step(dt)
            last_tick = now

            if push_telemetry:
                interval_s = max(1, push_interval_ms) / 1000.0
                idle_s = max(0, push_when_idle_ms) / 1000.0
                can_push = (now - last_master_activity) >= idle_s
                if can_push and (now - last_push) >= interval_s:
                    marker_word = _stream_marker_word(push_marker_mode, push_tick)
                    if now < compat_schema_lock_until:
                        marker_word = 0xF00B
                    values = _build_stream_format_words(state, marker_word=marker_word)
                    body = bytearray([len(values) * 2])
                    for value in values:
                        body.extend(int(value & 0xFFFF).to_bytes(2, "big"))
                    frame_out = encode_frame(node_id, 0x03, bytes(body))
                    ser.write(frame_out)
                    push_tick += 1
                    last_push = now
                    if trace_frames:
                        words_i16 = [_u16_to_i16(v) for v in values]
                        print(
                            f"[tx_push] {frame_out.strip().decode('ascii', errors='replace')} "
                            f"[tx_words] {_format_words(words_i16)}"
                        )
                    if frame_event_cb is not None:
                        words_i16 = [_u16_to_i16(v) for v in values]
                        frame_event_cb(
                            {
                                "event": "tx_push",
                                "function": 0x03,
                                "frame_ascii": frame_out.strip().decode("ascii", errors="replace"),
                                "words": words_i16,
                                "marker_word": marker_word & 0xFFFF,
                            }
                        )

            incoming = ser.read(256)
            if incoming:
                rx_buffer.extend(incoming)

            while b"\n" in rx_buffer:
                line_end = rx_buffer.index(0x0A)
                line = bytes(rx_buffer[: line_end + 1])
                del rx_buffer[: line_end + 1]

                # Real serial links can include noise or mixed traffic; only
                # parse probable Modbus ASCII frames starting with ':'.
                candidate = line.strip()
                if not candidate:
                    continue
                colon_idx = candidate.find(b":")
                if colon_idx < 0:
                    continue
                if colon_idx > 0:
                    candidate = candidate[colon_idx:]

                try:
                    frame = decode_frame(candidate)
                    if frame.address != node_id:
                        continue

                    last_master_activity = now
                    if _is_compat_poll_request(frame.function, frame.payload):
                        compat_schema_lock_until = now + (max(0, push_schema_lock_ms) / 1000.0)

                    # If this listener sees a function 0x03/0x04 response frame
                    # on a shared line, ignore it quietly instead of flagging a
                    # malformed request warning.
                    if frame.function in (0x03, 0x04) and _looks_like_read_response_payload(frame.payload):
                        continue

                    if frame_event_cb is not None:
                        frame_event_cb(
                            {
                                "event": "rx_request",
                                "function": frame.function,
                                "payload_hex": frame.payload.hex(),
                                "req_detail": _format_read_request_detail(frame.payload)
                                if frame.function in (0x03, 0x04)
                                else "",
                            }
                        )

                    resp_payload = _build_response(state, frame.function, frame.payload, node_id=node_id)
                    response = encode_frame(node_id, frame.function, resp_payload)
                    ser.write(response)
                    if frame_event_cb is not None:
                        words: list[int] | None = None
                        if frame.function in (0x03, 0x04):
                            words = _decode_read_response_words(resp_payload)
                        frame_event_cb(
                            {
                                "event": "tx_response",
                                "function": frame.function,
                                "frame_ascii": response.strip().decode("ascii", errors="replace"),
                                "payload_hex": resp_payload.hex(),
                                "words": words,
                            }
                        )
                    if trace_frames:
                        extra = ""
                        req_detail = ""
                        if frame.function in (0x03, 0x04):
                            req_detail = _format_read_request_detail(frame.payload)
                        if frame.function in (0x03, 0x04):
                            words = _decode_read_response_words(resp_payload)
                            if words is not None:
                                extra = f" [tx_words] {_format_words(words)}"
                        print(
                            f"[rx] fn=0x{frame.function:02X} payload={frame.payload.hex()} "
                            f"[tx] {response.strip().decode('ascii', errors='replace')}{extra}{req_detail}"
                        )
                except ProtocolError as exc:
                    print(f"[warn] dropped frame: {exc}")

            time.sleep(0.002)
    except KeyboardInterrupt:
        print("[emulator] Stopped")
    finally:
        ser.close()


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="UART/RS485 emulator scaffold")
    p.add_argument("--port", default="COM9", help="Serial port or pyserial URL")
    p.add_argument("--baud", type=int, default=115200, help="Baud rate")
    p.add_argument("--node", type=int, default=1, help="Device node/address")
    p.add_argument("--no-step", action="store_true", help="Disable internal state stepping")
    p.add_argument("--trace-frames", action="store_true", help="Print each processed RX/TX frame")
    p.add_argument(
        "--push-telemetry",
        action="store_true",
        help="Push unsolicited 10-word telemetry frames periodically",
    )
    p.add_argument(
        "--push-interval-ms",
        type=int,
        default=20,
        help="Telemetry push interval in milliseconds",
    )
    p.add_argument(
        "--push-marker-mode",
        choices=["compat", "float", "zero", "auto"],
        default="compat",
        help="Marker family for unsolicited telemetry frames",
    )
    p.add_argument(
        "--push-when-idle-ms",
        type=int,
        default=120,
        help="Only push unsolicited telemetry when no request was seen for this many milliseconds",
    )
    p.add_argument(
        "--push-schema-lock-ms",
        type=int,
        default=900,
        help="After compatibility-block polls, force push marker schema for this duration",
    )
    return p


def main() -> None:
    args = _parser().parse_args()
    run(
        args.port,
        args.baud,
        args.node,
        step_state=not args.no_step,
        trace_frames=args.trace_frames,
        push_telemetry=args.push_telemetry,
        push_interval_ms=args.push_interval_ms,
        push_marker_mode=args.push_marker_mode,
        push_when_idle_ms=args.push_when_idle_ms,
        push_schema_lock_ms=args.push_schema_lock_ms,
    )


if __name__ == "__main__":
    main()
