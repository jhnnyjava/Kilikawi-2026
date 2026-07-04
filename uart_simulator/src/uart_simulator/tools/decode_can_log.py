"""CAN frame decoder for WINDCON motor driver captures.

Decodes CANopen CiA402 frames from CAN bus captures and provides
human-readable telemetry and command data.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from uart_simulator.tools.canopen_map import (
    CANopenFrame,
    parse_canopen_frame,
    decode_pdo_payload,
    od_register_name,
)


CAN_FRAME_RX = re.compile(
    r"CAN\d+\s+([0-9a-fA-F]+)\s+\[\d+\]\s+([0-9a-fA-F\s]*)",
    re.IGNORECASE,
)


@dataclass(slots=True)
class DecodedCANFrame:
    """Decoded CAN frame with parsed CANopen structure."""
    line_no: int
    raw_id: int
    dlc: int
    data_hex: str
    data_bytes: bytes
    canopen: CANopenFrame
    pdo_payload: dict[str, int]


def parse_can_frames(path: Path) -> list[DecodedCANFrame]:
    """Parse CAN frames from a capture file."""
    frames: list[DecodedCANFrame] = []

    for idx, line in enumerate(path.read_text(errors="ignore").splitlines(), start=1):
        m = CAN_FRAME_RX.search(line)
        if not m:
            continue

        can_id_str = m.group(1)
        data_str = m.group(2) or ""

        # Parse CAN ID
        try:
            can_id = int(can_id_str, 16)
        except ValueError:
            continue

        # Parse data bytes (space-separated hex)
        data_parts = data_str.split()
        data_hex = "".join(data_parts)
        
        if len(data_hex) % 2 != 0:
            continue

        try:
            data_bytes = bytes.fromhex(data_hex)
        except ValueError:
            continue

        dlc = len(data_bytes)
        if dlc > 8:
            continue

        # Parse as CANopen frame
        canopen = parse_canopen_frame(can_id, data_bytes)
        pdo_payload = decode_pdo_payload(canopen)

        frames.append(
            DecodedCANFrame(
                line_no=idx,
                raw_id=can_id,
                dlc=dlc,
                data_hex=data_hex,
                data_bytes=data_bytes,
                canopen=canopen,
                pdo_payload=pdo_payload,
            )
        )

    return frames


def frame_to_record(fr: DecodedCANFrame) -> dict[str, object]:
    """Convert a decoded frame to a record dict for CSV/JSON."""
    return {
        "line_no": fr.line_no,
        "can_id": fr.raw_id,
        "can_id_hex": f"0x{fr.raw_id:03X}",
        "dlc": fr.dlc,
        "data_hex": fr.data_hex,
        "cob_id": f"0x{fr.canopen.cob_id:03X}",
        "node_id": fr.canopen.node_id,
        "function": fr.canopen.function,
        "is_pdo": fr.canopen.is_pdo,
        "pdo_type": fr.canopen.pdo_name if fr.canopen.is_pdo else "",
        "payload": fr.pdo_payload,
    }


def write_csv(frames: list[DecodedCANFrame], out_path: Path) -> None:
    """Write decoded CAN frames to CSV."""
    base_fieldnames = [
        "line_no",
        "can_id",
        "can_id_hex",
        "dlc",
        "data_hex",
        "cob_id",
        "node_id",
        "function",
        "is_pdo",
        "pdo_type",
    ]
    payload_fieldnames = sorted({key for fr in frames for key in fr.pdo_payload})
    fieldnames = [*base_fieldnames, *payload_fieldnames]

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()

        for fr in frames:
            record = frame_to_record(fr)
            for key in payload_fieldnames:
                record[key] = fr.pdo_payload.get(key, "")
            writer.writerow(record)


def write_json(frames: list[DecodedCANFrame], out_path: Path) -> None:
    """Write decoded CAN frames to JSON."""
    payload = {
        "frame_count": len(frames),
        "functions": dict(Counter(fr.canopen.function for fr in frames)),
        "node_ids": dict(Counter(fr.canopen.node_id for fr in frames)),
        "frames": [frame_to_record(fr) for fr in frames],
    }

    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def print_summary(frames: list[DecodedCANFrame]) -> None:
    """Print a summary of decoded frames."""
    if not frames:
        print("No valid CAN frames decoded.")
        return

    functions = Counter(fr.canopen.function for fr in frames)
    node_ids = Counter(fr.canopen.node_id for fr in frames)
    dlcs = Counter(fr.dlc for fr in frames)
    pdo_types = Counter(
        fr.canopen.pdo_name for fr in frames if fr.canopen.is_pdo
    )

    print(f"can_frames_decoded={len(frames)}")
    print(f"functions={dict(functions)}")
    print(f"node_ids={dict(node_ids)}")
    print(f"dlcs={dict(dlcs)}")
    print(f"pdo_types={dict(pdo_types)}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Decode CAN bus captures with CANopen CiA402 frame parsing and telemetry labels."
    )
    p.add_argument("input", help="Path to CAN capture file")
    p.add_argument(
        "--output-csv",
        default="",
        help="Optional output CSV path",
    )
    p.add_argument(
        "--output-json",
        default="",
        help="Optional output JSON path",
    )
    return p


def main() -> None:
    args = build_parser().parse_args()
    frames = parse_can_frames(Path(args.input))
    print_summary(frames)

    if args.output_csv:
        out = Path(args.output_csv)
        write_csv(frames, out)
        print(f"csv_written={out}")

    if args.output_json:
        out = Path(args.output_json)
        write_json(frames, out)
        print(f"json_written={out}")


if __name__ == "__main__":
    main()
