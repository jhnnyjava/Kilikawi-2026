from __future__ import annotations

import argparse
import configparser
import re
import sys
import time
from pathlib import Path

import serial


FRAME_RE = re.compile(r"^:[0-9A-Fa-f]{8,}$")


def load_serial_settings(settings_path: Path) -> dict[str, str]:
    cfg = configparser.ConfigParser()
    if not settings_path.exists():
        return {}
    try:
        raw = settings_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {}
    cfg.read_string(raw)
    if "General" not in cfg:
        return {}
    return {k: v for k, v in cfg["General"].items()}


def parity_from_text(value: str) -> str:
    v = (value or "none").strip().lower()
    if v in {"none", "n"}:
        return serial.PARITY_NONE
    if v in {"odd", "o"}:
        return serial.PARITY_ODD
    if v in {"even", "e"}:
        return serial.PARITY_EVEN
    return serial.PARITY_NONE


def stopbits_from_text(value: str) -> float:
    v = (value or "1").strip()
    if v == "1.5":
        return serial.STOPBITS_ONE_POINT_FIVE
    if v == "2":
        return serial.STOPBITS_TWO
    return serial.STOPBITS_ONE


def bytesize_from_text(value: str) -> int:
    v = (value or "8").strip()
    if v == "5":
        return serial.FIVEBITS
    if v == "6":
        return serial.SIXBITS
    if v == "7":
        return serial.SEVENBITS
    return serial.EIGHTBITS


def parse_frames(capture_path: Path) -> list[bytes]:
    frames: list[bytes] = []
    with capture_path.open("r", encoding="utf-8", errors="ignore") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            if FRAME_RE.match(line):
                frames.append((line + "\r\n").encode("ascii"))
    return frames


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Replay captured Modbus ASCII frames to a COM port (virtual or real)."
    )
    p.add_argument(
        "--file",
        default="../data/Receive_20260326164249.txt",
        help="Path to capture text file containing :.... Modbus ASCII lines",
    )
    p.add_argument("--port", default=None, help="COM port to write to (e.g. COM10)")
    p.add_argument("--baud", type=int, default=None, help="Baud rate")
    p.add_argument("--data-bits", type=int, default=None, choices=[5, 6, 7, 8], help="Data bits")
    p.add_argument("--parity", default=None, choices=["None", "Even", "Odd", "N", "E", "O"], help="Parity")
    p.add_argument("--stop-bits", default=None, choices=["1", "1.5", "2"], help="Stop bits")
    p.add_argument("--delay-ms", type=int, default=20, help="Delay between frames (ms)")
    p.add_argument("--loop", action="store_true", help="Loop replay forever")
    p.add_argument(
        "--settings",
        default="../WINDCON Servo Assistant/serial_settings.ini",
        help="Path to WINDCON serial_settings.ini",
    )
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    capture_path = Path(args.file).resolve()
    settings_path = Path(args.settings).resolve()

    settings = load_serial_settings(settings_path)

    port = args.port or settings.get("com")
    if not port:
        print("[error] COM port not provided and not found in serial settings.")
        return 2

    baud = args.baud or int(settings.get("baudrate", "115200"))
    data_bits = args.data_bits or int(settings.get("databit", "8"))
    parity = args.parity or settings.get("parity", "None")
    stop_bits = args.stop_bits or settings.get("stopbit", "1")

    frames = parse_frames(capture_path)
    if not frames:
        print(f"[error] No Modbus ASCII frames found in {capture_path}")
        return 2

    print(f"[info] Capture file: {capture_path}")
    print(f"[info] Frames loaded: {len(frames)}")
    print(f"[info] Port settings: {port} {baud} {data_bits}{parity[0].upper()}{stop_bits}")
    print("[info] Press Ctrl+C to stop.")

    try:
        ser = serial.Serial(
            port=port,
            baudrate=baud,
            bytesize=bytesize_from_text(str(data_bits)),
            parity=parity_from_text(parity),
            stopbits=stopbits_from_text(stop_bits),
            timeout=0.1,
            write_timeout=0.5,
        )
    except Exception as exc:
        print(f"[error] Failed to open {port}: {exc}")
        return 3

    sent = 0
    delay_s = max(0, args.delay_ms) / 1000.0

    try:
        while True:
            for frame in frames:
                ser.write(frame)
                sent += 1
                if sent % 50 == 0:
                    print(f"[tx] Sent {sent} frames")
                if delay_s:
                    time.sleep(delay_s)
            if not args.loop:
                break
    except KeyboardInterrupt:
        print("\n[info] Stopped by user.")
    finally:
        ser.close()

    print(f"[done] Total frames sent: {sent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
