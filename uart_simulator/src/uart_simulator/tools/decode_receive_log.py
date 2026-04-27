from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from uart_simulator.tools.windcon_map import classify_marker
from uart_simulator.tools.windcon_map import label_stream_words
from uart_simulator.tools.windcon_map import STREAM_FIELD_NAMES


# Field aliases for convenient filtering (short names -> full field names)
FIELD_ALIASES = {
    "speed": "speed_feedback_rpm",
    "current": "current_feedback_da",
    "voltage": "bus_voltage_dv",
    "status": "status_latch",
    "temp": "driver_temp_c",
    "work_mode": "work_mode",
    "run_mode": "run_mode",
    "marker": "marker_word",
    "fault": "fault_code",
    "fault_active": "fault_active",
}

FRAME_RX = re.compile(r":(?P<hex>[0-9A-Fa-f]{8,})")


@dataclass(slots=True)
class DecodedFrame:
    line_no: int
    address: int
    function: int
    byte_count: int
    words_u16: list[int]

    @property
    def words_i16(self) -> list[int]:
        return [to_i16(v) for v in self.words_u16]


def to_i16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def calc_lrc(data: bytes) -> int:
    return (-sum(data)) & 0xFF


def parse_frames(path: Path, strict_lrc: bool = True) -> list[DecodedFrame]:
    frames: list[DecodedFrame] = []

    for idx, raw in enumerate(path.read_text(errors="ignore").splitlines(), start=1):
        m = FRAME_RX.search(raw)
        if not m:
            continue

        blob = m.group("hex")
        if len(blob) < 10 or len(blob) % 2 != 0:
            continue

        try:
            binary = bytes.fromhex(blob)
        except ValueError:
            continue

        if len(binary) < 5:
            continue

        body = binary[:-1]
        lrc = binary[-1]
        if strict_lrc and calc_lrc(body) != lrc:
            continue

        address = body[0]
        function = body[1]
        payload = body[2:]
        if not payload:
            continue

        byte_count = payload[0]
        data = payload[1:]
        if byte_count != len(data) or byte_count % 2 != 0:
            continue

        words_u16 = [int.from_bytes(data[i : i + 2], "big") for i in range(0, len(data), 2)]

        frames.append(
            DecodedFrame(
                line_no=idx,
                address=address,
                function=function,
                byte_count=byte_count,
                words_u16=words_u16,
            )
        )

    return frames


def classify(words: list[int]) -> str:
    if len(words) < 8:
        return "short"
    return classify_marker(words[7])


def resolve_field_names(field_spec: str) -> list[str]:
    """Resolve field names, handling aliases and validation."""
    if not field_spec.strip():
        return []
    
    requested = [f.strip() for f in field_spec.split(",") if f.strip()]
    resolved = []
    
    for f in requested:
        # Try alias lookup first, then use as-is if it's a valid readable field
        full_name = FIELD_ALIASES.get(f, f)
        resolved.append(full_name)
    
    return resolved


def infer_fields(words_i16: list[int]) -> dict[str, int]:
    # This inference is based on the decompiled emulator compatibility stream
    # and observed capture statistics. Keep as best-effort labels.
    fields: dict[str, int] = {}
    if len(words_i16) < 10:
        return fields

    fields["speed_feedback_est"] = words_i16[0]
    fields["current_feedback_est"] = words_i16[1]
    fields["ref_or_aux_hi"] = words_i16[2]
    fields["ref_or_aux_lo"] = words_i16[3]
    fields["status_or_delta"] = words_i16[4]
    fields["mode_word"] = words_i16[5]
    fields["fault_or_small_status"] = words_i16[6]
    fields["marker_word"] = words_i16[7]
    fields["temp_or_power_est"] = words_i16[8]
    fields["small_delta_2"] = words_i16[9]
    return fields


def build_readable_fields(words_i16: list[int]) -> dict[str, int]:
    return label_stream_words(words_i16)


def frame_to_record(fr: DecodedFrame) -> dict[str, object]:
    words_i16 = fr.words_i16
    record: dict[str, object] = {
        "line_no": fr.line_no,
        "address": fr.address,
        "function": fr.function,
        "byte_count": fr.byte_count,
        "class": classify(fr.words_u16),
        "words_i16": words_i16,
        "readable": build_readable_fields(words_i16),
        "inferred": infer_fields(words_i16),
    }
    return record


def write_csv(frames: list[DecodedFrame], out_path: Path, fields_filter: list[str] | None = None) -> None:
    all_fieldnames = [
        "line_no",
        "address",
        "function",
        "byte_count",
        "class",
        *STREAM_FIELD_NAMES,
        "w0_i16",
        "w1_i16",
        "w2_i16",
        "w3_i16",
        "w4_i16",
        "w5_i16",
        "w6_i16",
        "w7_i16",
        "w8_i16",
        "w9_i16",
        "speed_feedback_est",
        "current_feedback_est",
        "ref_or_aux_hi",
        "ref_or_aux_lo",
        "status_or_delta",
        "mode_word",
        "fault_or_small_status",
        "marker_word",
        "temp_or_power_est",
        "small_delta_2",
    ]
    
    # If fields_filter specified, use only those fields; otherwise use all
    if fields_filter:
        fieldnames = [f for f in all_fieldnames if f in fields_filter]
    else:
        fieldnames = all_fieldnames

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for fr in frames:
            words_i16 = fr.words_i16
            row = {
                "line_no": fr.line_no,
                "address": fr.address,
                "function": fr.function,
                "byte_count": fr.byte_count,
                "class": classify(fr.words_u16),
            }
            row.update(build_readable_fields(words_i16))
            for i in range(min(10, len(words_i16))):
                row[f"w{i}_i16"] = words_i16[i]

            inferred = infer_fields(words_i16)
            row.update(inferred)
            
            # Filter row to only requested fields
            if fields_filter:
                row = {k: v for k, v in row.items() if k in fields_filter}
            
            writer.writerow(row)


def write_json(frames: list[DecodedFrame], out_path: Path, fields_filter: list[str] | None = None) -> None:
    payload = {
        "frame_count": len(frames),
        "functions": dict(Counter(fr.function for fr in frames)),
        "byte_counts": dict(Counter(fr.byte_count for fr in frames)),
        "classes": dict(Counter(classify(fr.words_u16) for fr in frames)),
        "frames": [],
    }
    
    for fr in frames:
        record = frame_to_record(fr)
        
        # If fields_filter specified, keep only those readable fields
        if fields_filter:
            filtered_readable = {k: v for k, v in record["readable"].items() if k in fields_filter}
            record["readable"] = filtered_readable
        
        payload["frames"].append(record)

    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def print_summary(frames: list[DecodedFrame]) -> None:
    if not frames:
        print("No valid frames decoded.")
        return

    functions = Counter(fr.function for fr in frames)
    byte_counts = Counter(fr.byte_count for fr in frames)
    classes = Counter(classify(fr.words_u16) for fr in frames)

    print(f"frames_decoded={len(frames)}")
    print(f"functions={dict(functions)}")
    print(f"byte_counts={dict(byte_counts)}")
    print(f"classes={dict(classes)}")

    # Per-column quick stats for first 10 words.
    word_count = max(len(fr.words_u16) for fr in frames)
    for idx in range(min(10, word_count)):
        vals = [to_i16(fr.words_u16[idx]) for fr in frames if len(fr.words_u16) > idx]
        c = Counter(vals)
        top = c.most_common(5)
        print(
            f"w{idx}: min={min(vals)} max={max(vals)} "
            f"top={[(v, n) for v, n in top]}"
        )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Decode WINDCON receive capture into signed register words and inferred telemetry labels."
    )
    p.add_argument("input", help="Path to receive log file")
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
    p.add_argument(
        "--fields",
        default="",
        help="Comma-separated field names to include in output (e.g., 'speed,fault,voltage'). "
             "Supports aliases: speed, current, voltage, status, temp, fault, marker, mode, driver_temp, work_mode, run_mode, fault_active. "
             "Or use full field names from readable output. If omitted, includes all fields.",
    )
    p.add_argument(
        "--no-lrc-check",
        action="store_true",
        help="Accept frames without strict LRC validation",
    )
    return p


def main() -> None:
    args = build_parser().parse_args()
    frames = parse_frames(Path(args.input), strict_lrc=not args.no_lrc_check)
    print_summary(frames)

    # Resolve field names if specified
    fields_filter = resolve_field_names(args.fields) if args.fields else None
    if fields_filter and args.fields:
        print(f"fields_filter={fields_filter}")

    if args.output_csv:
        out = Path(args.output_csv)
        write_csv(frames, out, fields_filter=fields_filter)
        print(f"csv_written={out}")

    if args.output_json:
        out = Path(args.output_json)
        write_json(frames, out, fields_filter=fields_filter)
        print(f"json_written={out}")


if __name__ == "__main__":
    main()
