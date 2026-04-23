# UART Simulator Scaffold

This project is a starter kit for reverse engineering and emulating the RS485/UART device used by WINDCON.

## What is included

- `uart-emulator`: serial server skeleton that parses Modbus ASCII-like frames and responds.
- `uart-sniffer`: logs serial traffic with timestamps.
- `uart-sim-gui`: local motor/controller simulator panel.
- `uart-encoding-ref`: encoding reference/probe tool (UTF-8/GBK/GB18030/etc, CJK-aware).
- `uart-vterm`: free Python virtual terminal pair and interactive terminal.

## Quick start

```bash
cd uart_simulator
python -m venv .venv
.venv\\Scripts\\activate
pip install -e .[dev]
```

Run emulator:

```bash
uart-emulator --port COM9 --baud 115200 --node 1
```

Run sniffer:

```bash
uart-sniffer --port COM9 --baud 115200
```

Run GUI simulator:

```bash
uart-sim-gui
```

If PowerShell reports `uart-sim-gui` is not recognized (common when the
project path contains non-ASCII characters and editable install fails), use:

```powershell
python launch_app.py
# or
.\run_gui.ps1
```

Run encoding reference tool:

```bash
uart-encoding-ref probe --bytes "E794B5E69CBA"
uart-encoding-ref encode --text "参数读取"
```

Send text in multiple encodings on serial (for compatibility probing):

```bash
uart-encoding-ref serial-send --port COM31 --baud 115200 --text "参数读取"
```

Run free virtual terminals over localhost TCP:

```bash
# Terminal 1: create pair
uart-vterm pair --left-port 7001 --right-port 7002

# Terminal 2: connect left side
uart-vterm term --port 7001 --encoding utf-8

# Terminal 3: connect right side
uart-vterm term --port 7002 --encoding gb18030
```

## Notes

- For WINDCON integration on Windows, use a virtual COM pair (example: `com0com`).
- Point WINDCON to one COM endpoint and `uart-emulator` to the other.
- Protocol behavior in this scaffold is intentionally minimal and should be refined from captured traffic.
- Pure Python cannot create native Windows COMx virtual pairs by itself; that still requires a signed kernel driver.
- The `uart-vterm` tool is free and useful for protocol/encoding tests without paid software.
