from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import time
from itertools import combinations

import serial
import serial.tools.list_ports

from uart_simulator.emulator.model import DriveState
from uart_simulator.emulator.server import run as run_emulator


def _find_setupc() -> str | None:
    env_path = os.environ.get("COM0COM_SETUPC", "").strip()
    candidates = [
        env_path,
        r"C:\Program Files (x86)\com0com\setupc.exe",
        r"C:\Program Files\com0com\setupc.exe",
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    in_path = shutil.which("setupc.exe")
    if in_path:
        return in_path
    return None


def _run_setupc(setupc: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [setupc, *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=12,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess([setupc, *args], returncode=124, stdout="", stderr="setupc timeout")
    except OSError as exc:
        if getattr(exc, "winerror", None) == 740:
            raise RuntimeError(
                "com0com setup requires Administrator privileges. "
                "Run terminal as Administrator, or use --skip-virtual-setup if pair already exists."
            ) from exc
        raise


def _combined_output(proc: subprocess.CompletedProcess[str]) -> str:
    return ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()


def _parse_pair_indexes(list_text: str) -> list[int]:
    left = {int(m.group(1)) for m in re.finditer(r"CNCA(\d+)", list_text)}
    right = {int(m.group(1)) for m in re.finditer(r"CNCB(\d+)", list_text)}
    return sorted(left.intersection(right))


def _names_present(list_text: str, a_name: str, b_name: str) -> bool:
    text = list_text.upper()
    a = a_name.upper()
    b = b_name.upper()
    return (f"PORTNAME={a}" in text or f"REALPORTNAME={a}" in text) and (
        f"PORTNAME={b}" in text or f"REALPORTNAME={b}" in text
    )


def ensure_virtual_pair(windcon_port: str, bridge_port: str) -> None:
    setupc = _find_setupc()
    if setupc is None:
        raise RuntimeError(
            "com0com setup tool not found. Install com0com, or set COM0COM_SETUPC to setupc.exe path."
        )

    probe = _run_setupc(setupc, ["list"])
    combined_probe = _combined_output(probe)
    if _names_present(combined_probe, windcon_port, bridge_port):
        print(f"[virtual] Existing pair already references {windcon_port} and {bridge_port}")
        return

    # com0com canonical flow from vendor docs: create pair, then rename endpoints.
    indexes = _parse_pair_indexes(combined_probe)
    if not indexes:
        print("[virtual] No CNCA/CNCB pair found; attempting to create one via 'install - -'")
        created = _run_setupc(setupc, ["install", "-", "-"])
        if created.returncode not in (0, 1):
            out = _combined_output(created)
            raise RuntimeError(
                "Failed to create com0com pair. Run elevated shell and retry. "
                f"setupc output: {out}"
            )
        refreshed = _run_setupc(setupc, ["list"])
        combined_probe = _combined_output(refreshed)
        indexes = _parse_pair_indexes(combined_probe)

    if not indexes:
        raise RuntimeError(
            "com0com pair not detected after install. Driver may be blocked. "
            "Run PowerShell as Administrator and verify test-signed driver policy for this com0com build."
        )

    pair_idx = indexes[0]
    left = f"CNCA{pair_idx}"
    right = f"CNCB{pair_idx}"
    print(f"[virtual] Using pair {left} <-> {right}; assigning {windcon_port} <-> {bridge_port}")

    commands = [
        ["change", left, f"PortName={windcon_port}"],
        ["change", right, f"PortName={bridge_port}"],
        ["change", left, f"RealPortName={windcon_port}"],
        ["change", right, f"RealPortName={bridge_port}"],
    ]
    for cmd in commands:
        _run_setupc(setupc, cmd)

    verify = _run_setupc(setupc, ["list"])
    combined = _combined_output(verify)
    if _names_present(combined, windcon_port, bridge_port):
        print(f"[virtual] Pair ready: {windcon_port} <-> {bridge_port}")
        return

    raise RuntimeError(
        "Unable to map virtual COM names. setupc could not assign requested names. "
        "Try running as Administrator, then run: "
        f"\"{setupc}\" change {left} PortName={windcon_port} && "
        f"\"{setupc}\" change {right} PortName={bridge_port}"
    )


def run_passthrough(virtual_port: str, real_port: str, baud: int) -> None:
    left = serial.serial_for_url(virtual_port, baudrate=baud, timeout=0.01)
    right = serial.serial_for_url(real_port, baudrate=baud, timeout=0.01)

    print(f"[bridge] WINDCON side: {virtual_port} @ {baud}")
    print(f"[bridge] REAL controller side: {real_port} @ {baud}")
    print("[bridge] Press Ctrl+C to stop")

    bytes_lr = 0
    bytes_rl = 0
    last_report = time.perf_counter()

    try:
        while True:
            chunk_left = left.read(512)
            if chunk_left:
                right.write(chunk_left)
                bytes_lr += len(chunk_left)

            chunk_right = right.read(512)
            if chunk_right:
                left.write(chunk_right)
                bytes_rl += len(chunk_right)

            now = time.perf_counter()
            if now - last_report >= 2.0:
                print(f"[bridge] tx WINDCON->REAL={bytes_lr}B | REAL->WINDCON={bytes_rl}B")
                last_report = now

            time.sleep(0.001)
    except KeyboardInterrupt:
        print("[bridge] Stopped")
    finally:
        left.close()
        right.close()


def _available_ports() -> list[str]:
    return sorted([p.device.upper() for p in serial.tools.list_ports.comports()])


def _ensure_ports_exist(required: list[str], context: str) -> None:
    available = _available_ports()
    missing = [p for p in required if p.upper() not in available]
    if not missing:
        return
    raise RuntimeError(
        f"Missing COM ports for {context}: {', '.join(missing)}. "
        f"Available ports: {', '.join(available) if available else 'none'}. "
        "If Secure Boot is enabled, use a signed virtual COM pair tool and run with --virtual-backend manual."
    )


def _port_num(name: str) -> int:
    m = re.match(r"COM(\d+)$", name.upper())
    return int(m.group(1)) if m else -1


def suggest_manual_pairs() -> None:
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("[suggest] No serial ports detected.")
        print("[suggest] Install a signed virtual COM pair tool, then rerun with --suggest-pairs.")
        return

    print("[suggest] Detected serial ports:")
    for p in sorted(ports, key=lambda x: _port_num(x.device)):
        desc = p.description or ""
        manu = p.manufacturer or ""
        print(f"  - {p.device:>6} | {desc} | {manu}")

    keywords = (
        "virtual",
        "emulator",
        "null",
        "com0com",
        "vsp",
        "loop",
        "bridge",
        "bridged",
        "hhd",
    )
    virtual_like = [
        p
        for p in ports
        if any(k in " ".join([p.device, p.description or "", p.hwid or "", p.manufacturer or ""]).lower() for k in keywords)
    ]

    def fmt_command(a: str, b: str) -> str:
        return (
            f".\\run_virtual_lab.ps1 -Mode sim -VirtualBackend manual "
            f"-WindconPort {a} -BridgePort {b}"
        )

    if len(virtual_like) >= 2:
        names = sorted({p.device.upper() for p in virtual_like}, key=_port_num)
        print("[suggest] Virtual-like ports detected. Suggested commands:")
        shown = 0
        for a, b in combinations(names, 2):
            print(f"  {fmt_command(a, b)}")
            shown += 1
            if shown >= 3:
                break
        return

    # Fallback: suggest the two highest COM numbers as a quick manual trial.
    names = sorted({p.device.upper() for p in ports}, key=_port_num)
    if len(names) >= 2:
        a, b = names[-2], names[-1]
        print("[suggest] No clearly virtual pair detected.")
        print(f"[suggest] If you just created a signed pair, try: {fmt_command(a, b)}")
        print("[suggest] Then point WINDCON to the WindconPort value.")
    else:
        print("[suggest] Only one serial port found; a virtual pair requires two endpoints.")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Virtual lab launcher: simulated mode (emulator) or passthrough mode "
            "(real controller bridge) with optional com0com pair setup."
        )
    )
    p.add_argument(
        "--virtual-backend",
        choices=["com0com", "manual"],
        default="com0com",
        help="com0com=auto setup via setupc, manual=use pre-created signed virtual COM pair",
    )
    p.add_argument(
        "--suggest-pairs",
        action="store_true",
        help="List detected COM ports and suggest manual signed-pair commands",
    )
    p.add_argument("--mode", choices=["sim", "real"], default="sim", help="sim=emulator, real=serial passthrough")
    p.add_argument("--windcon-port", default="COM10", help="Port used by WINDCON app")
    p.add_argument("--bridge-port", default="COM11", help="Paired port used by emulator/bridge")
    p.add_argument("--real-port", default="", help="Real controller COM port (required for --mode real)")
    p.add_argument("--baud", type=int, default=115200, help="Baud rate")
    p.add_argument("--node", type=int, default=1, help="Node ID used by emulator in sim mode")
    p.add_argument(
        "--skip-virtual-setup",
        action="store_true",
        help="Skip automatic com0com pair creation",
    )
    return p


def main() -> None:
    args = _parser().parse_args()

    if args.suggest_pairs:
        suggest_manual_pairs()
        return

    if args.virtual_backend == "com0com" and not args.skip_virtual_setup:
        ensure_virtual_pair(args.windcon_port, args.bridge_port)
    elif args.virtual_backend == "manual" and not args.skip_virtual_setup:
        print("[virtual] Backend=manual; skipping auto setup and using existing virtual COM ports")

    # In manual backend, both virtual endpoints should already exist.
    if args.virtual_backend == "manual":
        _ensure_ports_exist([args.windcon_port, args.bridge_port], "manual virtual pair")

    active_windcon_port = args.windcon_port
    active_emulator_port = args.bridge_port
    print(f"[lab] WINDCON should connect to: {active_windcon_port}")

    def _raise_port_hint(exc: Exception) -> None:
        msg = str(exc)
        if "Access is denied" in msg or "PermissionError(13" in msg:
            raise RuntimeError(
                "Serial port is busy (Access is denied). "
                "Close any app using the port (WINDCON, HHD monitor/config, another Python bridge), "
                "then retry. In SIM mode with HHD pair COM1<->COM2, set WINDCON to COM1 and let emulator use COM2."
            ) from exc
        raise RuntimeError(f"Serial port open failed: {msg}") from exc

    if args.mode == "sim":
        print(f"[lab] Mode=SIM. Emulator binds: {active_emulator_port} @ {args.baud}, node={args.node}")
        try:
            run_emulator(
                port=active_emulator_port,
                baud=args.baud,
                node_id=args.node,
                state=DriveState(),
                step_state=True,
            )
        except serial.SerialException as exc:
            msg = str(exc)
            can_swap = (
                args.virtual_backend == "manual"
                and active_emulator_port.upper() != active_windcon_port.upper()
                and ("Access is denied" in msg or "PermissionError(13" in msg)
            )
            if can_swap:
                print(
                    "[lab] Selected emulator port is busy. "
                    "Trying opposite endpoint of the virtual pair..."
                )
                print(
                    f"[lab] If startup succeeds after swap, connect WINDCON to: {active_emulator_port}"
                )
                try:
                    run_emulator(
                        port=active_windcon_port,
                        baud=args.baud,
                        node_id=args.node,
                        state=DriveState(),
                        step_state=True,
                    )
                    return
                except serial.SerialException as swap_exc:
                    _raise_port_hint(swap_exc)
            _raise_port_hint(exc)
        return

    if not args.real_port:
        raise SystemExit("--real-port is required when --mode real")

    print(f"[lab] Mode=REAL. Bridging {args.bridge_port} <-> {args.real_port} @ {args.baud}")
    try:
        run_passthrough(args.bridge_port, args.real_port, args.baud)
    except serial.SerialException as exc:
        _raise_port_hint(exc)


if __name__ == "__main__":
    main()
