from __future__ import annotations

import argparse
from datetime import datetime

import serial


def run(port: str, baud: int) -> None:
    ser = serial.serial_for_url(port, baudrate=baud, timeout=0.2)
    print(f"[sniffer] Listening on {port} @ {baud}")
    try:
        while True:
            line = ser.read_until(b"\n")
            if not line:
                continue
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            text = line.decode("ascii", errors="replace").strip()
            print(f"{ts} raw={line.hex(' ')} text={text}")
    except KeyboardInterrupt:
        print("[sniffer] Stopped")
    finally:
        ser.close()


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Simple UART line sniffer")
    p.add_argument("--port", default="COM9", help="Serial port or pyserial URL")
    p.add_argument("--baud", type=int, default=115200, help="Baud rate")
    return p


def main() -> None:
    args = _parser().parse_args()
    run(args.port, args.baud)


if __name__ == "__main__":
    main()
