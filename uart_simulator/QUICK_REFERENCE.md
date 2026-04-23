# Quick Reference & Troubleshooting

## Installation & Quick Start

```bash
# One-time setup
cd uart_simulator
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]

# Run tests
pytest tests/ -v

# Start emulator on virtual COM
uart-emulator --port COM11 --baud 115200 --node 1 --loglevel INFO

# Monitor traffic in another terminal
uart-sim-sniffer --port COM11 --baud 115200

# Launch GUI to control motor state
uart-sim-gui
```

---

## Common Commands

### Start Emulator (Main Loop)

```bash
# Minimal (defaults to COM10)
uart-emulator

# Explicit configuration
uart-emulator --port COM11 --baud 115200 --node 1

# With debug logging
uart-emulator --port COM11 --loglevel DEBUG
```

**Expected output:**
```
[emulator] Listening on COM11 @ 115200, node=1
```

### Monitor Traffic

```bash
# Capture all frames in real-time
uart-sniffer --port COM11 --baud 115200

# Save to log file
uart-sniffer --port COM11 > capture.log

# Combined timestamp + hex + ASCII
uart-sniffer --port COM11 2>&1 | tee capture.log
```

**Example output:**
```
12:45:30.123 raw=3a 30 31 03 00 00 00 08 ... text=:010300000008F4
```

### GUI Simulator

```bash
# Launch interactive motor controller
uart-sim-gui
```

If `uart-sim-gui` is not recognized in PowerShell, use:

```powershell
python launch_app.py
# or
.\run_gui.ps1
```

Features:
- Enable/Disable button
- Target velocity slider (−3000 to +3000 RPM)
- Live display of speed, position, temps, faults
- "Start WINDCON Test" scenario button (30s dynamic loop for end-to-end validation)

---

## Workflow: Test WINDCON with Emulator

### Setup (one-time)

1. **Install virtual COM pair**
   - Download & install **com0com**
   - Create pair: `COM10 ↔ COM11`

2. **Install emulator**
   ```bash
   cd uart_simulator
   pip install -e .
   ```

### Testing Session

1. **Terminal 1: Start emulator**
   ```bash
   uart-emulator --port COM11 --baud 115200 --node 1
   ```

2. **Terminal 2 (optional): Monitor traffic**
   ```bash
   uart-sniffer --port COM11
   ```

3. **Terminal 3 (optional): Launch GUI**
   ```bash
   uart-sim-gui
   ```

   In GUI click `Start WINDCON Test` to run a repeating 30-second profile:
   - forward accel
   - high-speed cruise
   - brake phase
   - reverse phase
   - fault inject/clear phase

4. **Window 4: Open WINDCON**
   - Select COM10
   - Click "Search Device" → should find address 1
   - Click "Connect"
   - Observe live pages: voltage/temp/current/speed/status/fault should cycle with scenario

### Using Manual Control for Interface Verification

The **Manual Control** tab in the GUI allows you to directly adjust telemetry values in real-time and verify that WINDCON correctly maps the Modbus interface:

1. **Launch GUI**
   ```bash
   uart-sim-gui
   ```

2. **Click the "Manual Control" tab** (appears next to "Controller" and "Animation")

3. **Enable Manual Override** checkbox
   - When enabled, manual values override the auto-simulation
   - All manually-set values appear instantly in Modbus responses

4. **Adjust test values:**
   - **Speed (RPM)**: Set to specific value (e.g., 1500) → check WINDCON speed display
   - **Motor Temp (°C)**: Set to test value (e.g., 80) → check WINDCON temperature gauge
   - **Driver Temp (°C)**: Verify driver has independent temp reading
   - **Bus Voltage (0.1V)**: Set to simulate different supply (e.g., 600 = 60V) → check WINDCON voltage display
   - **Position**: Set to specific value → verify position register in WINDCON
   - **Error Code**: Set non-zero code → check WINDCON fault/alarm pages

5. **Verify in WINDCON**
   - Watch the live data pages
   - Each value you adjust **should immediately appear** in WINDCON's corresponding display
   - If a value doesn't appear or appears incorrect, the interface mapping is wrong

**Example hardening flow:**
```
1. Set Speed = 2000 rpm  → WINDCON should show 2000 rpm
2. Set Speed = -500 rpm  → WINDCON should show −500 rpm (reverse)
3. Set Temp = 100°C      → Motor gauge should jump to 100°C
4. Set Voltage = 480     → Voltage page should show 48.0V
5. Set Error Code = 205  → Fault page should show code 205
```

---

## Register Cheat Sheet

### Quick Reads

| What | Address | Example |
|------|---------|---------|
| Motor enable state | 0x11DE | 1 = enabled, 0 = disabled |
| Current speed | 0x11EC | Returns RPM (−32768 to +32767) |
| Target speed | 0x11E6 | Set target before activating |
| Driver temperature | 0x22A2 | Returns °C |
| Motor temperature | 0x2002 | Returns °C |
| Bus voltage | 0x2003 | In 0.1V units (540 = 54V) |
| Fault code | 0x603F | 0 = OK, nonzero = error |

### Quick Writes

| Action | Address | Value |
|--------|---------|-------|
| Enable motor | 0x6040 | 0x000F |
| Disable motor | 0x6040 | 0x0000 |
| Set speed [rpm] | 0x11E6 | value (signed i16) |
| Set position | 0x11F0 | value (signed i32, two registers) |
| Clear fault | 0x603F | 0x0000 |

---

## Debugging Checklist

### Emulator won't start

- [ ] Port is free (close WINDCON, check Device Manager)
- [ ] Virtual COM pair exists (COM10 ↔ COM11)
- [ ] Port name is correct (`uart-emulator --port COM10` vs COM11)
- [ ] Baud rate matches (should be 115200)

### WINDCON can't find device

- [ ] Emulator is running: check Terminal 1
- [ ] "Search Device" in WINDCON on the **correct COM port**
- [ ] Node ID matches (should be 1 in both)
- [ ] Baud rates match (115200)
- [ ] Sniffer shows traffic: `uart-sniffer --port COM11`

### Motor doesn't enable

- [ ] Emulator is running
- [ ] WINDCON shows "Communication normal" (blue)
- [ ] Enable button press appears in sniffer output
- [ ] Try GUI: `uart-sim-gui` → click Enable → check if WINDCON responds

### Tests fail

```bash
# Run with full traceback
pytest tests/ -vv

# Run specific test
pytest tests/test_protocol.py::test_encode_frame -vv

# Check installed packages
pip list | grep uart
```

---

## Protocol Quick Ref

### Frame Structure

```
:AAFFPPPPPPPPLL\r\n

: = Start
AA = Address (hex, 00-FF)
FF = Function
PPPPPPPP = Payload
LL = LRC checksum
```

### Function Codes

| Code | Name | Read/Write |
|------|------|-----------|
| 0x03 | Read Holding Registers | R |
| 0x04 | Read Input Registers | R |
| 0x06 | Write Single Register | W |
| 0x10 | Write Multiple Registers | W |
| 0x17 | Read/Write Multiple Registers | R+W |

### Example Frames

**Read register 0x1234 (2 registers)**
```
Request:  :010300123400024D\r\n
Response: :010304ABCDEF1234CD\r\n
```

**Write value 0x5678 to register 0x1234**
```
Request:  :010611234567899C\r\n
Response: :010611234567899C\r\n
```

---

## Decode Receive Capture

```bash
# Decode WINDCON receive frames and print field statistics
uart-decode-log ..\data\Receive_20260326164249.txt

# Export decoded rows for plotting/correlation
uart-decode-log ..\data\Receive_20260326164249.txt --output-csv .\decoded_receive.csv
```

The decoder validates Modbus ASCII LRC, extracts 10 signed 16-bit words from each `:010314...` style frame, and labels common decompiled compatibility fields (speed/current/mode/marker/temp estimates).

---

## File Structure

```
uart_simulator/
├── src/uart_simulator/
│   ├── __init__.py
│   ├── config.py               # Configuration classes
│   ├── protocol/
│   │   ├── __init__.py
│   │   └── ascii_modbus.py    # Codec: frame encode/decode/LRC
│   ├── emulator/
│   │   ├── __init__.py
│   │   ├── server.py          # Main UART server loop
│   │   └── model.py           # Drive state machine & registers
│   ├── gui/
│   │   ├── __init__.py
│   │   └── app.py             # Tkinter GUI simulator
│   └── tools/
│       ├── __init__.py
│       ├── sniffer.py         # Serial traffic logger
│       └── decode_receive_log.py  # Receive capture decoder
├── tests/
│   ├── __init__.py
│   ├── test_protocol.py       # Codec tests
│   └── test_model.py          # State model tests
├── pyproject.toml             # Project metadata & entry points
├── README.md                  # Overview
├── SETUP_GUIDE.md            # Detailed setup & integration
└── PROTOCOL.md               # Protocol specification
```

---

## Entry Points

Once installed, these commands are available anywhere:

```bash
uart-emulator       → python -m uart_simulator.emulator.server
uart-sniffer        → python -m uart_simulator.tools.sniffer
uart-sim-gui        → python -m uart_simulator.gui.app
uart-decode-log     → python -m uart_simulator.tools.decode_receive_log
```

---

## Development Workflow

### Editing Code

Edit files in `src/uart_simulator/` and changes are live (editable install).

### Running Tests

```bash
# All tests
pytest tests/

# Verbose output
pytest tests/ -vv

# Specific file
pytest tests/test_protocol.py -v

# With coverage
pytest tests/ --cov=uart_simulator
```

### Debugging

Add breakpoints in any `.py` file:
```python
import pdb; pdb.set_trace()
```

Or use logging:
```python
import logging
logger = logging.getLogger(__name__)
logger.debug(f"Frame: {frame}")
```

Run with debug level:
```bash
uart-emulator --loglevel DEBUG
```

---

## Integration with Real Hardware

Once ready to test with actual FDK servo driver:

1. Connect RS485-to-USB adapter to laptop
2. Identify COM port: `python -c "import serial.tools.list_ports; print([p.device for p in serial.tools.list_ports.comports()])"`
3. Run emulator on that port:
   ```bash
   uart-emulator --port COM5 --baud 115200
   ```
4. Configure WINDCON to same port and test

---

## Support

### Check Logs

```bash
# Enable debug logging during run
uart-emulator --loglevel DEBUG 2>&1 | tee debug.log

# Capture all traffic
uart-sniffer --port COM11 > traffic.log

# Analyze captured frames offline
python -c "from uart_simulator.protocol.ascii_modbus import decode_frame; ..."
```

### Verify Installation

```bash
python -c "import uart_simulator; print(uart_simulator.__file__)"
python -m pytest --version
uart-emulator --help
```

### Run Full Suite

```bash
cd uart_simulator
pytest tests/ -vv --tb=short
```

---

**See also:**
- [SETUP_GUIDE.md](SETUP_GUIDE.md) – Detailed setup & architecture
- [PROTOCOL.md](PROTOCOL.md) – Complete protocol specification
- [README.md](README.md) – Project overview

---

Last Updated: March 21, 2026
