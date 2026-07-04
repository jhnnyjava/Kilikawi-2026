# UART Simulator

This package is the test bench for the WINDCON reverse-engineering work. It can emulate the RS485 controller, mirror captured traffic, and expose a legacy-style GUI for manual testing and direct controller writes.

## What you can run

- `uart-emulator`: Modbus ASCII emulator for the WINDCON controller.
- `uart-sim-gui`: modern simulator and control panel.
- `uart-legacy-gui`: old WINDCON-style dashboard with search, parameters, alarms, and write controls.
- `uart-sniffer`: serial traffic logger for capture analysis.
- `uart-encoding-ref`: encoding probe tool for CJK/serial compatibility testing.
- `uart-vterm`: local virtual terminal pair for protocol experiments.

## Quick Start

```bash
cd uart_simulator
python -m venv .venv
.venv\\Scripts\\activate
pip install -e .[dev]
```

If you are on Linux and the GUI fails to import `tkinter`, install the system Tk package first:

```bash
sudo apt-get install python3-tk
```

## Run the tools

Start the emulator:

```bash
uart-emulator --port COM9 --baud 115200 --node 1
```

Start the modern simulator:

```bash
uart-sim-gui
```

Start the legacy WINDCON-style app:

```bash
uart-legacy-gui
```

The legacy app includes:
- serial search and port configuration dialogs
- a parameter table window with editable values
- an alarm configuration window
- one-click enable, disable, speed, mode, and fault actions
- direct Modbus ASCII writes to a live controller

If PowerShell reports `uart-sim-gui` or `uart-legacy-gui` is not recognized, use:

```powershell
python launch_app.py
# or
.\run_gui.ps1
```

Capture serial traffic:

```bash
uart-sniffer --port COM9 --baud 115200
```

Run the encoding probe tool:

```bash
uart-encoding-ref probe --bytes "E794B5E69CBA"
uart-encoding-ref encode --text "参数读取"
```

Send text in multiple encodings on serial:

```bash
uart-encoding-ref serial-send --port COM31 --baud 115200 --text "参数读取"
```

Run a virtual terminal pair:

```bash
# Terminal 1: create pair
uart-vterm pair --left-port 7001 --right-port 7002

# Terminal 2: connect left side
uart-vterm term --port 7001 --encoding utf-8

# Terminal 3: connect right side
uart-vterm term --port 7002 --encoding gb18030
```

## Real controller use

- Use a USB-to-RS485 adapter for the controller and connect it to the documented RS485 pins.
- Start with read-only polling before attempting writes.
- Keep the motor unloaded for the first enable/speed test.
- Use the legacy GUI if you want the old app flow, or the direct controller write bench for custom registers.

## Notes

- For WINDCON integration on Windows, use a virtual COM pair such as `com0com`.
- Point WINDCON to one COM endpoint and the emulator to the other.
- Protocol behavior is intentionally conservative and should be refined from captured traffic.
- Pure Python cannot create native Windows COMx virtual pairs by itself; that still requires a signed kernel driver.
- `uart-vterm` is useful for protocol and encoding tests without paid software.
