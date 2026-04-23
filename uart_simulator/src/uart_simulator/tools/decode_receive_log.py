from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


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
    marker = words[7]
    if marker == 0xF00B:
        return "compat-marker"
    if marker == 0x4CCD:
        return "float-marker"
    if marker == 0x0000:
        return "zero-marker"
    return "mixed"


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


def write_csv(frames: list[DecodedFrame], out_path: Path) -> None:
    fieldnames = [
        "line_no",
        "address",
        "function",
        "byte_count",
        "class",
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
        "mode_word",
        "marker_word",
        "temp_or_power_est",
    ]

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
            for i in range(min(10, len(words_i16))):
                row[f"w{i}_i16"] = words_i16[i]

            inferred = infer_fields(words_i16)
            row.update(inferred)
            writer.writerow(row)


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
        "--no-lrc-check",
        action="store_true",
        help="Accept frames without strict LRC validation",
    )
    return p


def main() -> None:
    args = build_parser().parse_args()
    frames = parse_frames(Path(args.input), strict_lrc=not args.no_lrc_check)
    print_summary(frames)

    if args.output_csv:
        out = Path(args.output_csv)
        write_csv(frames, out)
        print(f"csv_written={out}")


if __name__ == "__main__":
    main()
