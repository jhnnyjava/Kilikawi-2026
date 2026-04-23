from __future__ import annotations

import argparse
import binascii
import pathlib
import re
import time
from dataclasses import dataclass
from typing import Iterable


COMMON_ENCODINGS = [
    "utf-8",
    "gb18030",
    "gbk",
    "big5",
    "utf-16le",
    "utf-16be",
    "latin-1",
]


@dataclass(slots=True)
class DecodeCandidate:
    encoding: str
    text: str
    score: float
    cjk_count: int
    control_count: int


def is_cjk_char(ch: str) -> bool:
    cp = ord(ch)
    return (
        0x4E00 <= cp <= 0x9FFF
        or 0x3400 <= cp <= 0x4DBF
        or 0x20000 <= cp <= 0x2A6DF
        or 0x2A700 <= cp <= 0x2B73F
        or 0x2B740 <= cp <= 0x2B81F
        or 0x2B820 <= cp <= 0x2CEAF
        or 0xF900 <= cp <= 0xFAFF
    )


def _score_text(text: str) -> tuple[float, int, int]:
    if not text:
        return (0.0, 0, 0)

    total = len(text)
    cjk_count = sum(1 for ch in text if is_cjk_char(ch))
    printable = sum(1 for ch in text if ch.isprintable() and ch not in "\x00\x0b\x0c")
    control_count = sum(1 for ch in text if ord(ch) < 32 and ch not in "\r\n\t")

    printable_ratio = printable / total
    cjk_ratio = cjk_count / total
    control_ratio = control_count / total

    score = printable_ratio + (0.45 * cjk_ratio) - (1.2 * control_ratio)
    return (score, cjk_count, control_count)


def decode_candidates(raw: bytes, encodings: Iterable[str] | None = None) -> list[DecodeCandidate]:
    options = list(encodings or COMMON_ENCODINGS)
    out: list[DecodeCandidate] = []

    for enc in options:
        try:
            text = raw.decode(enc, errors="strict")
        except UnicodeDecodeError:
            continue
        score, cjk_count, control_count = _score_text(text)
        out.append(
            DecodeCandidate(
                encoding=enc,
                text=text,
                score=score,
                cjk_count=cjk_count,
                control_count=control_count,
            )
        )

    out.sort(key=lambda x: x.score, reverse=True)
    return out


def best_decode(raw: bytes, encodings: Iterable[str] | None = None) -> DecodeCandidate | None:
    cand = decode_candidates(raw, encodings)
    return cand[0] if cand else None


def encode_variants(text: str, encodings: Iterable[str] | None = None) -> dict[str, bytes]:
    options = list(encodings or COMMON_ENCODINGS)
    out: dict[str, bytes] = {}
    for enc in options:
        try:
            out[enc] = text.encode(enc, errors="strict")
        except UnicodeEncodeError:
            continue
    return out


def looks_like_hex(payload: str) -> bool:
    s = re.sub(r"\s+", "", payload)
    return bool(re.fullmatch(r"[0-9A-Fa-f]+", s)) and len(s) % 2 == 0


def parse_bytes_arg(text: str) -> bytes:
    if looks_like_hex(text):
        return binascii.unhexlify(re.sub(r"\s+", "", text))
    return text.encode("utf-8", errors="replace")


def _print_candidates(raw: bytes, top: int, encodings: list[str] | None = None) -> None:
    candidates = decode_candidates(raw, encodings)
    if not candidates:
        print("No strict decode candidate found for configured encodings.")
        return

    print(f"Input bytes: {len(raw)}")
    print(f"Input hex: {raw.hex()}")
    print("Decode candidates:")
    for c in candidates[:top]:
        print(
            f"  - {c.encoding:8s} score={c.score:.3f} cjk={c.cjk_count} ctrl={c.control_count} text={c.text!r}"
        )


def _print_encodings(text: str, encodings: list[str] | None = None) -> None:
    variants = encode_variants(text, encodings)
    if not variants:
        print("No encoding variant could encode this text.")
        return

    print(f"Input text: {text!r}")
    print("Encodings:")
    for enc, data in variants.items():
        print(f"  - {enc:8s} bytes={len(data):3d} hex={data.hex()}")


def _serial_send(port: str, baud: int, text: str, encodings: list[str], gap_ms: int) -> None:
    try:
        import serial
    except Exception as exc:  # pragma: no cover - import failure path
        raise RuntimeError("pyserial is required for serial-send") from exc

    variants = encode_variants(text, encodings)
    if not variants:
        raise RuntimeError("Text could not be encoded with requested encodings")

    with serial.Serial(port, baudrate=baud, timeout=0.2) as ser:
        for enc, payload in variants.items():
            # ASCII marker helps identify which variant arrived at receiver.
            marker = f"[ENC:{enc}] ".encode("ascii")
            frame = marker + payload + b"\r\n"
            ser.write(frame)
            ser.flush()
            print(f"sent {enc}: {frame.hex()}")
            time.sleep(max(gap_ms, 0) / 1000.0)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Encoding reference/probe tool for UART payloads (includes Chinese/CJK-aware scoring)."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    probe = sub.add_parser("probe", help="Probe decode candidates from bytes or hex")
    probe.add_argument("--bytes", dest="bytes_arg", default="", help="Raw text or hex bytes")
    probe.add_argument("--file", dest="file_path", default="", help="Read bytes from file")
    probe.add_argument("--top", type=int, default=5, help="Number of top decode candidates")
    probe.add_argument(
        "--encodings",
        default=",".join(COMMON_ENCODINGS),
        help="Comma-separated encoding list",
    )

    enc = sub.add_parser("encode", help="Show encoded variants for input text")
    enc.add_argument("--text", required=True, help="Input text")
    enc.add_argument(
        "--encodings",
        default=",".join(COMMON_ENCODINGS),
        help="Comma-separated encoding list",
    )

    send = sub.add_parser("serial-send", help="Send text in multiple encodings over serial")
    send.add_argument("--port", required=True, help="Serial port")
    send.add_argument("--baud", type=int, default=115200, help="Baud rate")
    send.add_argument("--text", required=True, help="Text to send")
    send.add_argument(
        "--encodings",
        default="utf-8,gb18030,gbk,big5",
        help="Comma-separated encodings to send",
    )
    send.add_argument("--gap-ms", type=int, default=150, help="Gap between variants")

    return p


def main() -> None:
    args = _build_parser().parse_args()

    if args.cmd == "probe":
        encs = [x.strip() for x in args.encodings.split(",") if x.strip()]
        raw = b""
        if args.file_path:
            raw = pathlib.Path(args.file_path).read_bytes()
        elif args.bytes_arg:
            raw = parse_bytes_arg(args.bytes_arg)
        else:
            raise SystemExit("probe requires --bytes or --file")
        _print_candidates(raw, top=max(1, args.top), encodings=encs)
        return

    if args.cmd == "encode":
        encs = [x.strip() for x in args.encodings.split(",") if x.strip()]
        _print_encodings(args.text, encodings=encs)
        return

    if args.cmd == "serial-send":
        encs = [x.strip() for x in args.encodings.split(",") if x.strip()]
        _serial_send(args.port, args.baud, args.text, encs, args.gap_ms)
        return


if __name__ == "__main__":
    main()
