# 🚀 START HERE

Welcome to the **UART Simulator for FDK Servo Driver**. This project provides a complete Python framework for emulating, testing, and reverse-engineering the RS485/UART communication protocol used by the WINDCON servo debugging assistant.

---

## What You Can Do Now

✅ **Run the emulator**: Simulates an FDK servo driver without real hardware  
✅ **Test WINDCON**: Connect WINDCON to the emulator via virtual COM ports  
✅ **Monitor traffic**: Capture and analyze protocol frames  
✅ **Control the motor**: GUI sliders to set speed, enable, inject faults  
✅ **Unit tests**: 35 tests validating protocol and motor physics  
✅ **Extend**: Add new registers, function codes, and physics models  

---

## 5-Minute Quick Start

### Step 1: Install

```bash
cd uart_simulator
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
```

### Step 2: Verify Installation

```bash
# Should show help text
uart-emulator --help
uart-sniffer --help
uart-sim-gui --help

# Run tests (should pass)
pytest tests/ -v
```

### Step 3: Run Emulator

```bash
# Terminal 1: Start the emulator
uart-emulator --port COM11 --baud 115200 --node 1
```

**Expected output:**
```
[emulator] Listening on COM11 @ 115200, node=1
```

### Step 4 (Optional): Monitor Traffic

```bash
# Terminal 2: Watch frames in real-time
uart-sniffer --port COM11 --baud 115200
```

### Step 5 (Optional): Launch GUI

```bash
# Terminal 3: Control motor with GUI
uart-sim-gui
```

If `uart-sim-gui` is not recognized on Windows PowerShell, launch without entry points:

```powershell
python launch_app.py
# or
.\run_gui.ps1
```

Use the GUI to:
- Click **Enable** to turn on motor
- Move **Target Velocity** slider to set speed
- Watch live speed, position, temperature updates
- Click **Inject Fault** to test error handling

---

## Integration with WINDCON

To use the emulator with WINDCON:

### Prerequisites

- Windows machine
- WINDCON Servo Assistant (already installed on your system)
- Virtual COM pair utility: **[com0com](https://sourceforge.net/projects/com0com/files/)**

### Setup (One-time)

1. **Install com0com**:
   - Download & run installer from [com0com releases](https://sourceforge.net/projects/com0com/files/)
   - Create a virtual COM pair: **COM10 ↔ COM11**
   - Verify in Device Manager: should see both ports

2. **Install & test emulator**:
   ```bash
   cd uart_simulator
   pip install -e .[dev]
   pytest tests/ -v     # All 35 tests should pass
   ```

### Testing Session

**Terminal 1: Start emulator on COM11**
```bash
uart-emulator --port COM11 --baud 115200 --node 1 --loglevel INFO
```

**Open WINDCON: Configure to use COM10**
1. Launch WINDCON Servo Assistant
2. **Serial Configuration** → Select **COM10**
3. Set Baud Rate: **115200**
4. Set Address: **01**
5. Click **"Search Device"** or **"Connect"**

**Expected behavior:**
- WINDCON should show "Communication normal" (blue/green)
- Parameters table should be readable
- You can enable/disable motor (using WINDCON buttons or GUI)

**Terminal 2 (optional): Monitor traffic**
```bash
uart-sniffer --port COM11
```

**Terminal 3 (optional): Control with GUI**
```bash
uart-sim-gui
```

---

## Documentation

Start with these files in order:

| File | Read Time | Purpose |
|------|-----------|---------|
| **🔵 This file** | 5 min | Get oriented and running |
| **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** | 10 min | Common commands, cheat sheet |
| **[SETUP_GUIDE.md](SETUP_GUIDE.md)** | 30 min | Detailed setup, real hardware, troubleshooting |
| **[PROTOCOL.md](PROTOCOL.md)** | 30 min | Protocol spec, registers, frame format, debugging |
| **[IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)** | 20 min | Architecture, components, extending code |

---

## File Structure

```
uart_simulator/
└── src/uart_simulator/
    ├── protocol/ascii_modbus.py   ← Modbus ASCII codec
    ├── emulator/server.py         ← Main UART server
    ├── emulator/model.py          ← Drive state simulation
    ├── gui/app.py                 ← Tkinter GUI
    └── tools/sniffer.py           ← Traffic capture

Entry points (installed as commands):
  uart-emulator                   ← Run simulator server
  uart-sniffer                    ← Monitor traffic
  uart-sim-gui                    ← Control panel GUI
```

---

## Common Workflows

### Workflow 1: Test Protocol Implementation

```bash
# Run protocol tests
pytest tests/test_protocol.py -vv

# Expected: All pass, showing frame encoding/decoding works correctly
```

### Workflow 2: Validate Motor Simulation

```bash
# Run model tests
pytest tests/test_model.py -vv

# Expected: All pass, showing acceleration/physics work
```

### Workflow 3: Capture Real WINDCON Traffic

```bash
# Terminal 1: Run emulator with debug logging
uart-emulator --port COM11 --loglevel DEBUG

# Terminal 2: Capture frames
uart-sniffer --port COM11 > capture.log

# In WINDCON: perform key operations (search, enable, set speed, clear fault)

# Analyze: cat capture.log or parse programmatically
```

### Workflow 4: Extend with New Register

Edit `src/uart_simulator/emulator/model.py`:

```python
# Add constant
REG_MY_NEW_PARAM = 0x1111

# Add to read logic
def read_register(self, addr):
    if addr == REG_MY_NEW_PARAM:
        return self.my_param_value & 0xFFFF
    # ...

# Add to write logic
def write_register(self, addr, value):
    if addr == REG_MY_NEW_PARAM:
        self.my_param_value = value
    # ...

# Add test in tests/test_model.py
def test_new_register():
    state = DriveState()
    state.write_register(REG_MY_NEW_PARAM, 1234)
    assert state.read_register(REG_MY_NEW_PARAM) == 1234
```

---

## Troubleshooting

### "Port already in use"

```bash
# Check what's using the port
tasklist | findstr COM
# Close WINDCON and other serial tools, then try again
```

### "uart-sim-gui is not recognized"

This usually means editable install did not create console scripts in your current shell environment.

```powershell
cd uart_simulator
python launch_app.py
# or
.\run_gui.ps1
```

### "Port does not exist"

```bash
# Verify virtual COM pair was created
python -c "import serial.tools.list_ports; print([p.device for p in serial.tools.list_ports.comports()])"
# Should show COM10, COM11
# If not, install com0com
```

### WINDCON can't find device

1. Verify emulator is running on the **other** COM port (COM11, not COM10)
2. Check baud rate: should be **115200**
3. Check node address: should be **01**
4. Run sniffer to verify traffic: `uart-sniffer --port COM11`

### Tests fail

```bash
# Run with full output
pytest tests/ -vv --tb=short

# Verify installation
pip show uart-simulator

# Check Python path
python -c "import uart_simulator; print(uart_simulator.__file__)"
```

---

## Next Steps

### For Immediate Use

1. ✅ Follow **Quick Start** above (5 min)
2. ✅ Read **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** (10 min)
3. ✅ Test WINDCON integration (15 min)
4. ✅ Capture some real traffic with sniffer (5 min)

### For Protocol Learning

1. 📖 Read **[PROTOCOL.md](PROTOCOL.md)** (30 min)
2. 🔍 Analyze captured traffic using frame decoder
3. 🧪 Add test cases for new commands

### For Extending

1. 📚 Read **[IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)** (20 min)
2. 💻 Add new registers to `model.py`
3. ✅ Write tests in `tests/test_model.py`
4. 🧪 Verify with GUI and WINDCON

### For Real Hardware

1. 📖 Read Phase 2 in **[SETUP_GUIDE.md](SETUP_GUIDE.md)**
2. 🔌 Connect RS485-to-USB adapter
3. 🎯 Run emulator on real port
4. 🧪 Test with WINDCON against actual driver

---

## Key Commands Reference

```bash
# Install & verify
pip install -e .              # Install package
pytest tests/ -v              # Run 35 tests

# Run tools
uart-emulator --port COM11 --baud 115200 --node 1
uart-sniffer --port COM11 --baud 115200
uart-sim-gui

# Development
pytest tests/test_protocol.py -vv     # Just protocol tests
pytest tests/test_model.py -vv        # Just model tests
python -m pytest --cov=uart_simulator # Coverage report
```

---

## Support & Questions

1. **Check logs**: Run emulator with `--loglevel DEBUG`
2. **Capture traffic**: Use `uart-sniffer` to save frames
3. **Review docs**: Start with QUICK_REFERENCE.md
4. **Check tests**: Look at `tests/` for usage examples
5. **Search code**: Look for similar patterns in existing modules

---

## Project Status

| Component | Status | Notes |
|-----------|--------|-------|
| Protocol codec | ✅ Complete | Modbus ASCII encode/decode |
| Drive model | ✅ Complete | Registers + physics |
| UART server | ✅ Complete | Async frame handler |
| GUI | ✅ Complete | Tkinter controls |
| Sniffer | ✅ Complete | Traffic capture |
| Tests | ✅ Complete | 35 tests, all passing |
| Documentation | ✅ Complete | 4 comprehensive guides |

**Ready for**: Immediate use with WINDCON, hardware testing, protocol reverse-engineering

---

## Version Info

- **Version**: 0.1.0
- **Python**: 3.10+
- **Dependencies**: pyserial
- **Optional**: pytest (for testing)
- **Date**: March 21, 2026

---

## Let's Get Started! 🎯

**Option 1: Just get it running (5 min)**
```bash
cd uart_simulator
pip install -e .[dev]
uart-emulator --port COM11
# In another terminal: uart-sim-gui
```

**Option 2: Run tests first (10 min)**
```bash
cd uart_simulator
pip install -e .[dev]
pytest tests/ -v
# Then: uart-emulator --port COM11
```

**Option 3: Full WINDCON integration (20 min)**
- Install com0com, create COM10 ↔ COM11 pair
- Run emulator on COM11
- Configure WINDCON for COM10
- Test!

---

**Choose your path above and get started!**  
Questions? Check the relevant guide file listed above.

---

**Next file to read:** [QUICK_REFERENCE.md](QUICK_REFERENCE.md)
