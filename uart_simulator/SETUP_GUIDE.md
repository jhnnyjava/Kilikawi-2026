# UART Simulator - Complete Setup & Integration Guide

This guide walks you through setting up the UART emulator to work with WINDCON and your servo driver.

## Table of Contents

1. [Installation](#installation)
2. [Architecture](#architecture)
3. [Phase 1: Testing with Virtual COM Ports](#phase-1-testing-with-virtual-com-ports)
4. [Phase 2: Real Hardware Integration](#phase-2-real-hardware-integration)
5. [Tools & Commands](#tools--commands)
6. [Protocol Details](#protocol-details)
7. [Troubleshooting](#troubleshooting)

---

## Installation

### Prerequisites

- Python 3.10 or later
- Windows (for COM port utilities)
- pyserial
- Optional: PySide6 (if using GUI)

### Setup Steps

```bash
# Navigate to the uart_simulator directory
cd uart_simulator

# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Install in development mode with all dependencies
pip install -e .[dev]

# Verify installation
uart-emulator --help
uart-sniffer --help
uart-sim-gui --help

# Run tests to verify everything works
pytest tests/ -v
```

---

## Architecture

### Components

```
uart_simulator/
├── protocol/
│   ├── ascii_modbus.py      # Modbus ASCII codec (frame parsing, LRC)
│   └── __init__.py
├── emulator/
│   ├── server.py            # Serial/TCP server for emulator
│   ├── model.py             # Drive state machine (registers, physics)
│   └── __init__.py
├── gui/
│   ├── app.py               # Tkinter simulator control panel
│   └── __init__.py
├── tools/
│   ├── sniffer.py           # Packet capture/logging utility
│   └── __init__.py
└── config.py                # Global configuration
```

### Data Flow

```
┌─────────────────────────────────────────────────────────┐
│                     WINDCON App                         │
│          (runs on host, opens COM port)                │
└────────────────────────┬────────────────────────────────┘
                         │
                    COM1 ↕ Virtual COM Pair
                         │
        ┌────────────────┴────────────────┐
        │ Virtual COM (paired)            │
        │  - One side: WINDCON            │
        │  - Other side: uart-emulator    │
        └────────────────┬────────────────┘
                         │
    ┌────────────────────▼────────────────────┐
    │    uart-emulator (server.py)            │
    │  Listens on virtual COM port            │
    │  Decodes Modbus ASCII frames            │
    │  Executes register reads/writes         │
    └────────────────────┬────────────────────┘
                         │
    ┌────────────────────▼────────────────────┐
    │    DriveState Model (model.py)          │
    │  - Register map (0x11DE, 0x11DF, etc)  │
    │  - Motor physics (accel, position)      │
    │  - Thermal simulation                   │
    │  - Status bits, faults                  │
    └─────────────────────────────────────────┘
        ▲            │
        └────────────┘
         updated by
     uart-sim-gui (optional)
```

---

## Phase 1: Testing with Virtual COM Ports

Use virtual COM pairs to allow WINDCON and the emulator to communicate without real hardware.

### Step 1: Install Virtual COM Pair Utility

**Option A: com0com (Recommended for Windows)**

1. Download from: https://sourceforge.net/projects/com0com/files/
2. Install and run the setup utility
3. Create a virtual COM pair:
   - Pair: `COM10 <-> COM11`
   - This allows WINDCON to use COM10 and emulator to use COM11

**Option B: Serial Port Emulator (alternative)**

Use other USB-UART simulation tools available on Windows.

### Step 2: Launch Emulator on Virtual COM

```bash
# Terminal 1: Start the UART emulator on one end of the virtual COM pair
uart-emulator --port COM11 --baud 115200 --node 1 --loglevel DEBUG
```

Expected output:
```
[emulator] Listening on COM11 @ 115200, node=1
```

### Step 3: Configure WINDCON

1. Launch WINDCON Servo Assistant
2. Go to **Serial Configuration**
3. Select **COM10** (the other end of virtual pair)
4. Set:
   - **Baud Rate**: 115200
   - **Address**: 01
   - **Protocol**: ASCII
5. Click **Search Device** or **Connect**

### Step 4: Monitor Traffic (Optional)

```bash
# Terminal 2: Monitor frames in real-time
uart-sniffer --port COM11 --baud 115200
```

Example output:
```
12:34:56.123 raw=3a 30 31 03 00 00 00 08 f4 0d 0a text=:010300000008F4
12:34:56.134 raw=3a 30 31 03 10 41 41 41 41 41 41 41 41 00 00 45 0d 0a text=...
```

### Step 5: Simulate Motor Behavior

```bash
# Terminal 3: Launch the simulator GUI
uart-sim-gui
```

The GUI shows:
- **Controller Commands**: Enable/Disable buttons, Inject Fault
- **Target Velocity**: Slider (-3000 to +3000 RPM)
- **Device State**: Current speed, position, temps, faults

Interact with the GUI:
1. Click **Enable** → WINDCON should show motor "online"
2. Move **Target Velocity** slider → WINDCON speed display changes
3. Click **Inject Fault** → WINDCON shows fault indicator

---

## Phase 2: Real Hardware Integration

Once virtual COM testing works, connect to real hardware.

### Equipment Needed

- FDK Servo Driver (your motor controller)
- RS485-to-USB converter (e.g., CH340, FT232RL based)
- USB cable
- RS485 A/B/GND wiring

### Connection Diagram

```
Host (Laptop)
    │
    ├─ USB ─────────────────────────┐
    │                               │
    │ RS485-to-USB Converter        │
    │ (CH340 or similar)            │
    │                               │
    └─ RS485 A/B/GND ────────────┐  │
                                 │  │
                    ┌────────────┤  │
                    │            │  │
            FDK Servo Driver     │  │
            ┌─ A (red)           │  │
            ├─ B (green)         │  │
            └─ GND (black)       │  │
```

### Identify the USB Port

```bash
# Windows: Check Device Manager or use
wmic logicaldisk get name
# Or list available serial ports
python -c "import serial.tools.list_ports; print([p.device for p in serial.tools.list_ports.comports()])"
```

### Run Emulator on Real Hardware

```bash
# Replace COMx with your USB converter port
uart-emulator --port COMx --baud 115200 --node 1 --loglevel INFO
```

### Connect WINDCON to Real Hardware

Configure WINDCON to the same port and run discovery to auto-detect the driver.

---

## Tools & Commands

### uart-emulator

Main UART server that simulates the servo driver.

```bash
uart-emulator [OPTIONS]

Options:
  --port PORT           Serial port name (default: COM10)
  --baud BAUD           Baud rate (default: 115200)
  --node NODE           RS485 node address (default: 1)
  --loglevel LEVEL      DEBUG, INFO, WARNING, ERROR (default: INFO)
```

**Example: Run with debug logging**
```bash
uart-emulator --port COM11 --baud 115200 --node 1 --loglevel DEBUG
```

### uart-sniffer

Captures and displays serial traffic for protocol analysis.

```bash
uart-sniffer [OPTIONS]

Options:
  --port PORT           Serial port to monitor (default: COM9)
  --baud BAUD           Baud rate (default: 115200)
```

**Example: Capture traffic**
```bash
uart-sniffer --port COM11 --baud 115200
```

Output includes:
- Timestamp (HH:MM:SS.mmm)
- Raw hex bytes
- Decoded ASCII text

### uart-sim-gui

Local GUI for manually controlling simulated motor state without WINDCON.

```bash
uart-sim-gui
```

Features:
- Enable/Disable motor
- Set target velocity (slider -3000 to +3000 RPM)
- View actual speed, position, temps
- Inject faults for testing error handling
- Real-time state updates

---

## Protocol Details

### Modbus ASCII Frame Format

All communication uses Modbus ASCII protocol:

```
:AAFFPPPPPPPPLLCC\r

: = Start marker (0x3A)
AA = Address (2 hex chars, e.g., 01)
FF = Function code (2 hex chars, e.g., 03)
PPPPPPPP = Payload (variable, hex encoded)
LL = LRC checksum (2 hex chars)
CC = Terminator (0x0D 0x0A = \r\n)
```

Example:
```
:010300000008F4\r\n
  │ │ └──┬──┘ └─┬─┘
  │ │    │      └─ LRC checksum
  │ │    └──────── Payload (read 8 registers starting at 0x0000)
  │ └──────────── Function 0x03 (Read Holding Registers)
  └─────────────── Address 0x01
```

### Supported Function Codes

| Code | Name | Usage |
|------|------|-------|
| 0x03 | Read Holding Registers | WINDCON reads parameters |
| 0x04 | Read Input Registers | Alternative read |
| 0x06 | Write Single Register | Set a single parameter |
| 0x10 | Write Multiple Registers | Set multiple parameters at once |

### Key Registers (CANopen/DS402)

| Address | Name | Access | Description |
|---------|------|--------|-------------|
| 0x11DE | ControlWord | RW | Enable/disable, mode control |
| 0x11DF | StatusWord | RO | Motor state, faults, ready |
| 0x11E6 | TargetVelocity | RW | Desired motor speed (RPM signed) |
| 0x11EC | VelocityActual | RO | Current motor speed (RPM signed) |
| 0x11F0 | TargetPosition | RW | Desired position (signed int) |
| 0x1256 | PositionActual | RO | Current position (signed int) |
| 0x2003 | BusVoltage | RO | Supply voltage (0.1V units) |
| 0x2002 | MotorTemp | RO | Motor temperature (°C) |
| 0x22A2 | DriverTemp | RO | Driver temperature (°C) |
| 0x603F | ErrorCode | RW | Fault code (write 0 to clear) |

### LRC Calculation

LRC (Longitudinal Redundancy Check) = (−sum of all bytes) & 0xFF

Example: For `01 03 00 00 00 08`
- Sum = 0x01 + 0x03 + 0x00 + 0x00 + 0x00 + 0x08 = 0x0C
- LRC = (−0x0C) & 0xFF = 0xF4

---

## Troubleshooting

### Emulator won't start

**Error: "Port already in use"**
- Another program is using the COM port (WINDCON, another instance of uart-emulator)
- Solution: Close WINDCON, check Device Manager, or use a different virtual COM

**Error: "Port does not exist"**
- Virtual COM pair not created
- Solution: Install com0com and create a pair (COM10 <-> COM11)

### WINDCON can't find device

**"Search Device" returns no results**
1. Verify emulator is running on the correct port
2. Check baud rate matches (should be 115200)
3. Verify node address is 1 in both emulator and WINDCON
4. Try pinging: `uart-sniffer --port COMx --baud 115200` should show traffic

**"Communication timeout"**
- Emulator stopped or crashed
- Restart: `Ctrl+C` to stop, then re-run `uart-emulator`
- Check logs: run with `--loglevel DEBUG`

### GUI doesn't respond to controls

**Velocity slider isn't reflected in WINDCON**
- Make sure both GUI and emulator are running in the same Python process or share state
- Alternatively, use WINDCON's parameter table to write directly

**No temperature change**
- This is expected behavior; temperature only changes when motor is running
- Enable the motor to see temperature rise

### Packet capture shows odd characters

**"text=???" in sniffer output**
- This is normal for non-ASCII bytes; check the `raw=` hex dump instead
- If many invalid frames appear, check baud rate/cable connection

### Tests fail

**Run tests with verbose output:**
```bash
pytest tests/ -vv
```

**If imports fail:**
- Ensure you installed with `pip install -e .` (editable mode)
- Check Python path: `python -c "import uart_simulator; print(uart_simulator.__file__)"`

---

## Next Steps

### Capture Real Protocol

1. Connect real FDK servo driver via RS485-to-USB
2. Run WINDCON and sniffer simultaneously
3. Perform key operations (search, connect, enable, set speed, fault clear)
4. Capture all frames to a log file
5. Analyze and refine emulator behavior to match

### Extend Emulator

- Add more register types and physics models
- Implement additional function codes
- Add state persistence (parameters saved to file)
- Create automated test scenarios

### Build Standalone Tool

- Reuse protocol codec and register model
- Add UI for diagnostics (read system state, history, export logs)
- Add scripting API for automated testing

---

## Support & Questions

If you encounter issues:
1. Check the logs: run with `--loglevel DEBUG`
2. Capture packets: `uart-sniffer --port COMx > traffic.log`
3. Review the protocol documentation above
4. Check existing issues/PRs in the project

---

Last Updated: March 21, 2026
