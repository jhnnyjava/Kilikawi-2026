# Kilikawi 2026 - WINDCON Motor Driver Reverse Engineering Toolkit

A comprehensive suite of tools for reverse engineering, decoding, and analyzing WINDCON servo motor driver communication protocols (Modbus ASCII RS485 and CANopen CiA402).

## Overview

This project provides:
- **Modbus ASCII RS485 decoder** with human-readable telemetry fields
- **CANopen CiA402 protocol** definitions and PDO decoders
- **Filtered one-command decoder** for extracting only fields you care about
- **Full protocol documentation** extracted from binary analysis
- **Register mapping** and field labels for 50+ Object Dictionary entries
- **Test captures** (82,790+ frames) for validation

### Hardware Context

The WINDCON system consists of:
- **Main Controller**: FDK3533C-XC servo motor driver (30-pin connector A)
- **Communication Interfaces**:
  - RS485 (pins A8, A9): Modbus ASCII command/response at 115200 baud
  - CAN (pins A2, A3, A4): CANopen CiA402 motor control profile
- **Control Pins**:
  - A17/A24: Brake inputs (low-active, high-active)
  - A22/A30: Throttle output (+5V, 0-5V analog)
  - A26: READY signal output
  - A16/A19/A27: Signal grounds

## Installation

```bash
cd uart_simulator
pip install -e .
```

## Quick Start

### Decode RS485 Capture (All Fields)
```bash
python3 -m uart_simulator.tools.decode_receive_log capture.txt --output-csv output.csv --output-json output.json
```

### Decode with Field Filtering
```bash
# Using aliases (speed, current, voltage, temp, fault, status, marker)
python3 -m uart_simulator.tools.decode_receive_log capture.txt \
  --fields speed,fault,voltage \
  --output-csv filtered.csv

# Using full field names
python3 -m uart_simulator.tools.decode_receive_log capture.txt \
  --fields speed_feedback_rpm,fault_code,driver_temp_c \
  --output-json filtered.json
```

### Decode CAN Frames
```bash
python3 -m uart_simulator.tools.decode_can_log can_capture.txt \
  --output-csv can_decoded.csv \
  --output-json can_decoded.json
```

## Protocol Reference

### RS485 Modbus ASCII

**Frame Structure** (10-word telemetry block):
```
Word 0:  speed_feedback_rpm        (i16, RPM)
Word 1:  current_feedback_da       (i16, deci-amps: value/10 = amps)
Word 2:  bus_voltage_dv            (i16, 0.1V units: value/10 = volts)
Word 3:  status_latch              (i16, 10000=enabled, 0=disabled)
Word 4:  driver_temp_c             (i16, degrees Celsius)
Word 5:  work_mode                 (i16, 1=speed, 3=torque, 9=position)
Word 6:  run_mode                  (i16, operational mode)
Word 7:  marker_word               (i16, 0xF00B|0x4CCD|0x0000)
Word 8:  fault_code                (i16, error code)
Word 9:  fault_active              (i16, 0=ok, -1=fault)
```

**Modbus Registers** (common mappings):
- `0x1007`: WorkMode (1=speed, 3=torque, 9=position)
- `0x1008`: StartupMode / EnableControl
- `0x100B`: SpeedReference (target RPM)
- `0x100C`: CurrentReference (target amps×10)
- `0x100D`: BusVoltage (feedback voltage×10)
- `0x100E`: MotorTemp (feedback temperature)
- `0x1010`: StatusWord
- `0x1013`, `0x101D`: FaultCode

**Session Setup**:
- Baud: 115200, 8N1, no flow control
- Node ID: 0x01
- Transport: ASCII (LRC checksum)
- Functions: 0x03 (read holding registers), 0x06 (write single), 0x10 (write multiple)

### CANopen CiA402

**Standard PDO Mappings**:

| PDO | Type | COB-ID | Payload |
|-----|------|--------|---------|
| TPDO1 | TX | 0x180+N | Status word (u16) + Position (i32) |
| TPDO2 | TX | 0x280+N | Velocity (i16 rpm) + Current (i16 da) + Torque (i16) |
| TPDO3 | TX | 0x380+N | Bus Voltage (i16 dv) + Driver Temp (i16 c) + Motor Temp (i16 c) |
| RPDO1 | RX | 0x200+N | Control Word (u16) + Target Torque (i16) |
| RPDO2 | RX | 0x300+N | Target Velocity (i16 rpm) + Target Position (i32) |

**Object Dictionary** (50+ entries):
- `0x10B5`: CAN Node ID
- `0x10B6-0x10B7`: CAN communication method / baud rate
- `0x10B2-0x10B4`: RS485 address / baud / protocol
- `0x11DE`: Control Word
- `0x11DF`: Status Word
- `0x11E6`: Target Velocity
- `0x11EC`: Velocity Actual Value
- `0x11F0`: Target Position
- `0x1256`: Position Actual Value

## Project Structure

```
uart_simulator/
├── src/uart_simulator/
│   ├── protocol/
│   │   └── ascii_modbus.py         # LRC codec, frame parsing
│   ├── tools/
│   │   ├── windcon_map.py          # RS485 register label map
│   │   ├── decode_receive_log.py   # RS485 decoder (CSV/JSON + filtering)
│   │   ├── canopen_map.py          # CANopen COB-ID and PDO definitions
│   │   └── decode_can_log.py       # CAN frame decoder
│   ├── emulator/
│   │   ├── model.py                # DriveState simulation (40+ registers)
│   │   └── server.py               # Modbus server loop
│   └── __init__.py
├── tests/
│   └── test_windcon_map.py         # Decoder and label validation
├── data/
│   └── Receive_20260326164249.txt  # 82,790-frame test capture
└── README.md
```

## Captured Telemetry

**Test Capture** (`data/Receive_20260326164249.txt`):
- **Frames**: 82,790 valid Modbus ASCII responses
- **Duration**: Continuous operation log
- **Fields**: All 10 telemetry words decoded per frame
- **Marker Types**: 
  - 5,402 compat-marker (0xF00B)
  - 26,982 float-marker (0x4CCD)
  - 16,535 zero-marker (0x0000)
  - 33,871 mixed

**Statistics** (word ranges from full capture):
```
Speed Feedback:     -1074 to +1092 RPM
Current Feedback:   -412 to +6446 (deci-amps)
Bus Voltage:        -5826 to +15281 (0.1V)
Status:             0 or 10000
Driver Temp:        -1676 to +1149 °C
Motor Temp:         3 to 9600 °C
```

## Usage Examples

### Python API

```python
from pathlib import Path
from uart_simulator.tools.decode_receive_log import parse_frames, write_csv
from uart_simulator.tools.windcon_map import label_stream_words

# Parse capture
frames = parse_frames(Path("capture.txt"))
print(f"Decoded {len(frames)} frames")

# Get readable labels for a frame
readable = label_stream_words(frames[0].words_i16)
print(f"Speed: {readable['speed_feedback_rpm']} RPM")
print(f"Current: {readable['current_feedback_da']/10} A")
print(f"Voltage: {readable['bus_voltage_dv']/10} V")
print(f"Temp: {readable['driver_temp_c']} °C")

# Export to CSV
write_csv(frames, Path("output.csv"))
```

### CAN Decoding

```python
from uart_simulator.tools.decode_can_log import parse_can_frames
from uart_simulator.tools.canopen_map import decode_pdo_payload

frames = parse_can_frames(Path("can_capture.txt"))
for frame in frames:
    if frame.canopen.is_pdo:
        payload = frame.pdo_payload
        print(f"{frame.canopen.pdo_name}: {payload}")
```

## Reverse Engineering Notes

### What We Learned
1. **Protocol**: Modbus ASCII RS485 + optional CANopen CiA402 dual transport
2. **Motor Controller**: Standard CiA402 drive profile with proprietary register layout
3. **Telemetry Structure**: Fixed 10-word block with speed/current/voltage/temp/status/fault
4. **GUI**: Qt5-based with QSerialPort backend for RS485
5. **CAN Bridge**: ControlCAN.dll (GCTech USB-CAN VCI) handles CAN transport

### Binary Analysis
- Decompiled with Ghidra from:
  - `WINDCON Servo Assistant.exe` (main GUI, 1.9MB)
  - `ControlCAN.dll` (USB-CAN bridge, 382KB)
  - `Qt5SerialPort.dll` (serial abstraction, 244KB)

### Configuration Files
- `CAN402_MapConfig.ini`: PDO mappings and OD register addresses
- `WINDCON_RS485_CAN_DATA_MAP.md`: Full protocol cross-reference

## Hardware Modification Possibilities

### Pin Function Remapping
**Current State**: Motor driver firmware likely has fixed pin functions compiled in.

**Requirements to Change**:
1. Access firmware source code OR reverse engineer bootloader
2. Rebuild firmware with new pin configurations
3. Programming interface (likely JTAG/SWD on motor controller PCB)
4. Understanding of:
   - GPIO mapping in firmware
   - Interrupt/timer configurations
   - Analog/PWM settings
   - Motor control loop dependencies

**Feasibility**: ⚠️ **Moderate** - Possible but requires:
- Firmware reverse engineering or source access
- Hardware debugging capability
- Deep knowledge of motor control firmware architecture

### Real-Time Data Monitoring

**Option 1: Current RS485 Interface** ✅ **Easy**
```bash
# Monitor live telemetry via USB-to-RS485 adapter
python3 -m uart_simulator.tools.decode_receive_log /dev/ttyUSB0 \
  --fields speed,current,voltage,temp \
  --output-json /tmp/telemetry.json

# Parse and display in real-time (watch tool)
watch 'tail -1 /tmp/telemetry.json | jq .frames[0].readable'
```

**Option 2: CANopen CAN Bus** ✅ **Easy** (if CAN adapter available)
```bash
# Monitor CAN bus with cheap USB-CAN adapter (~$20)
python3 -m uart_simulator.tools.decode_can_log /dev/ttyUSB0 \
  --output-json /tmp/can_telemetry.json
```

**Option 3: Custom Serial Interface** ⚠️ **Moderate**
```
Add new UART port to motor firmware → streaming telemetry
Requires: Firmware modification + rebuilding
```

**Option 4: Embedded Web Dashboard** ✅ **Easy** (when combined with RS485)
```python
# Create Flask app to stream live telemetry to browser
# Uses existing RS485 decoder as backend
# Would show real-time plots of speed/current/voltage/temp
```

## Recommended Next Steps

1. **Live Monitoring** (Easiest):
   - Grab a USB-to-RS485 adapter
   - Use the decoder on `/dev/ttyUSB0`
   - Display with matplotlib/plotly in real-time

2. **Pin Remapping** (Moderate):
   - Obtain motor controller firmware via JTAG dump
   - Analyze GPIO init functions
   - Rebuild with modified pin assignments

3. **Add New Functionality** (Hard):
   - Extend motor firmware with new features
   - Requires embedded development knowledge
   - Need working build environment for motor controller

## License

This reverse engineering toolkit is for educational and interoperability purposes.

## References

- CANopen CiA301/CiA402 standard specifications
- Modbus ASCII specification (IEC 61131-3)
- Qt5 Serial Port API documentation
- USB-CAN VCI (ControlCAN.dll) API from GCTech

## Contact & Contributing

This toolkit enables open understanding of the WINDCON motor driver protocol. Contributions welcome for:
- Additional register mappings
- New capture file formats
- Protocol extensions
- GUI tools for live monitoring
