# Protocol Specification & Implementation Notes

## Overview

The FDK Servo Driver uses **Modbus ASCII** protocol over RS485 for communication. This document specifies the exact frame format, supported commands, register mapping, and simulation behavior used by the UART emulator.

---

## Modbus ASCII Protocol

### Frame Format

All frames follow the Modbus ASCII standard:

```
:AAFFPPPPPPPPLL\r\n

Component          Size    Description
─────────────────────────────────────────
:                  1 byte  Start marker (0x3A, colon)
AA                 2 hex   Slave address (00-FF)
FF                 2 hex   Function code (00-FF)
PPPPPPPP           Var     Payload (function-dependent)
LL                 2 hex   LRC checksum
\r\n               2 bytes Terminator (CR LF)
```

### Example: Read 8 Registers from Address 0x0000

**Request (WINDCON → Emulator):**
```
:010300000008F4\r\n

Parse:
  : = Start
  01 = Address 1
  03 = Function (Read Holding Registers)
  0000 = Start register
  0008 = Quantity (8 registers)
  F4 = LRC
```

**Response (Emulator → WINDCON):**
```
:0103101041414141414141414141AB\r\n

Parse:
  : = Start
  01 = Address 1  
  03 = Function (Read Holding Registers)
  10 = Byte count (16 bytes = 8 registers × 2 bytes)
  1041...41 = Data (8 × u16 values)
  AB = LRC
```

### LRC Calculation

LRC (Longitudinal Redundancy Check) is a simple checksum covering all bytes except the start marker (`:`) and the LRC itself.

```python
def calc_lrc(data: bytes) -> int:
    """Calculate Modbus ASCII LRC."""
    return (-sum(data)) & 0xFF

# Example:
# Data: 01 03 00 00 00 08
# Sum: 0x01 + 0x03 + 0x00 + 0x00 + 0x00 + 0x08 = 0x0C
# LRC: (−0x0C) & 0xFF = 0xF4
```

For verification, the LRC should be recalculated and compared:
```python
if calc_lrc(body) != lrc_from_frame:
    raise ProtocolError("LRC mismatch")
```

### Data Encoding

All binary data in Modbus ASCII is encoded as hexadecimal strings:
- Each byte → 2 hex characters
- Uppercase or lowercase (both valid)
- Big-endian (network byte order)

Example:
```
Value 0x11DE (16-bit register address) → "11DE" in ASCII
Value 0xFC18 (−1000 as signed 16-bit) → "FC18" in ASCII
```

---

## Function Codes

### 0x03: Read Holding Registers

**Request:**
```
:AAFFSSSSCCCCLL\r\n

AA = Address
FF = 0x03
SSSS = Start register (16-bit, big-endian)
CCCC = Quantity of registers (16-bit, big-endian)
```

**Response:**
```
:AAFFBBVVVV...LL\r\n

AA = Address
FF = 0x03
BB = Byte count (quantity × 2)
VVVV... = Register values (each 16-bit, big-endian)
```

**Constraints:**
- Address: 0x00-0xFF (usually 0x01 for driving)
- Start register: any 16-bit value
- Quantity: 1-125 registers (Modbus limit)
- Each register value: 16 bits (0x0000-0xFFFF)

**Example:**
```
Request:  :010300000002E5\r\n
          Read 2 registers starting at 0x0000

Response: :010304ABCDEF1234CD\r\n
          Return 4 bytes: 0xABCD, 0xEF12
```

### 0x04: Read Input Registers

Identical to 0x03 (Read Holding Registers) in this implementation.

### 0x06: Write Single Register

**Request:**
```
:AAFFRRRRWWWWLL\r\n

AA = Address
FF = 0x06
RRRR = Register address (16-bit)
WWWW = Value (16-bit)
```

**Response:**
```
Echo the request payload unchanged.
```

**Example:**
```
Request:  :010611DE000FCE\r\n
          Write 0x000F to register 0x11DE

Response: :010611DE000FCE\r\n
          Echo confirmation
```

### 0x10: Write Multiple Registers

**Request:**
```
:AAFFSSSSCCCCBBVVVV...LL\r\n

AA = Address
FF = 0x10
SSSS = Start register
CCCC = Quantity
BB = Byte count (quantity × 2)
VVVV... = Values (each 16-bit)
```

**Response:**
```
:AAFFSSSSCCCCLL\r\n

Returns the start address and quantity written.
```

**Example:**
```
Request:  :0110119E000204ABCDEF12340A\r\n
          Write 2 values (0xABCD, 0xEF12) starting at 0x119E

Response: :01101199E00020D7\r\n
          Confirms 2 registers written at 0x119E
```

### Error Response

If a request is invalid or unsupported:

**Response:**
```
:AAFFEE LL\r\n

FF = Original function code | 0x80
EE = Exception code
```

**Exception Codes:**
- 0x01: Illegal Function (function not supported)
- 0x02: Illegal Data Address (register address invalid)
- 0x03: Illegal Data Value (value out of range)
- 0x04: Device Failure (internal error)
- 0x05: Acknowledge (slave received but still processing)

**Example:**
```
Request:  :010300FFFF0001ED\r\n
Response: :810302EE\r\n
          Function 0x03 failed with exception 0x02 (illegal address)
```

---

## Register Map

Registers are organized by function/subsystem. All registers are 16-bit (u16 or i16).

### Control & Status (CANopen DS402 Profile)

| Address | Name | Type | Access | Description |
|---------|------|------|--------|-------------|
| 0x6040 | Controlword | u16 | RW | FSM control; bit 0-3: enable state |
| 0x6041 | Statusword | u16 | RO | FSM state; bits indicate ready/error/op-enabled |
| 0x603F | ErrorCode | u16 | RO | Fault code (0x0000 = no fault) |

**Controlword Bits (0x6040):**
```
Bits 0-3: State machine transitions
  0x0000-0x0005 = Disabled
  0x0006 = Ready to switch on
  0x000F = Operation enabled

Typical enable sequence:
  1. Set 0x0006 (ready)
  2. Set 0x000F (enable)
```

**Statusword Bits (0x6041):**
```
Bit 0: Ready to switch on (1 = ready)
Bit 2: Operation enabled (1 = motor running)
Bit 3: Fault (1 = error occurred)
```

### Velocity Control

| Address | Name | Type | Description |
|---------|------|------|-------------|
| 0x11E6 | TargetVelocity | i16 | Desired speed in RPM (−32768 to 32767) |
| 0x11EC | VelocityActual | i16 | Actual speed feedback in RPM |

Signed interpretation:
- Positive = forward rotation
- Negative = reverse rotation
- Resolution: 1 RPM

### Position Control

| Address | Name | Type | Description |
|---------|------|------|-------------|
| 0x11F0 | TargetPosition | i32 | Desired position (encoded as two u16) |
| 0x1256 | PositionActual | i32 | Actual position feedback |

Position is integrated from velocity; no external feedback assumed.

### Analog Feedback

| Address | Name | Type | Description |
|---------|------|------|-------------|
| 0x2003 | BusVoltage | u16 | Supply voltage in 0.1V units (e.g., 540 = 54V) |
| 0x2002 | MotorTemp | u16 | Motor case temperature in °C |
| 0x22A2 | DriverTemp | u16 | Driver heatsink temperature in °C |

---

## Device State Model

### State Variables

```python
@dataclass
class DriveState:
    enabled: bool              # Output of control logic
    target_velocity_rpm: int   # From register 0x11E6
    velocity_actual_rpm: int   # Simulated; increments toward target
    target_position: int       # From register 0x11F0
    position_actual: int       # Integrated from velocity
    bus_voltage_tenth_v: int   # Supply voltage (540 = 54V)
    motor_temp_c: int          # Simulated; rises with motor speed
    driver_temp_c: int         # Simulated; rises with dissipation
    error_code: int            # 0 = OK, nonzero = fault
```

### Update/Step Function

Called periodically (e.g., every 10ms) to simulate motor physics:

```python
def step(self, dt_s: float):
    # 1. Determine target speed based on enable state
    if not enabled:
        target = 0
    else:
        target = target_velocity_rpm
    
    # 2. Ramp velocity toward target (accel/decel limit)
    accel_limit = 800 RPM/s
    delta = clamp(target − velocity_actual_rpm, ±accel_limit × dt_s)
    velocity_actual_rpm += delta
    
    # 3. Integrate position
    position_actual += (velocity_actual_rpm / 60.0) × 1000.0 × dt_s
    
    # 4. Thermal model (simplistic)
    abs_speed = abs(velocity_actual_rpm)
    motor_temp_c = min(140, 28 + abs_speed / 180)
    driver_temp_c = min(120, 30 + abs_speed / 200)
```

This mimics realistic motor behavior:
- **Acceleration**: Gradual speed ramp-up / ramp-down
- **Position tracking**: Dead reckoning from velocity
- **Thermal rise**: Speed-dependent temperature increase
- **Saturation**: Temperature capped at max safe values

---

## Frame Lifecycle

### Example: Enable Motor and Set Speed

**Step 1: Search Device (auto-detect address/baud)**

WINDCON sends broadcast probe:
```
:010300B500024F\r\n      → Read parameter at 0x00B5
```

Emulator responds (if this register is defined):
```
:010302ABCD01\r\n
```

**Step 2: Connect (open persistent link)**

WINDCON sends:
```
:010301000040C7\r\n      → Read status word (0x1000)
```

Emulator responds:
```
:0103021000FF\r\n        → Status: 0x0100 (ready)
```

**Step 3: Enable Motor**

WINDCON writes control word:
```
:010611DE000FAB\r\n      → Write 0x000F to 0x11DE (enable)
```

Emulator:
- Sets `enabled = True`
- Responds with echo: `:010611DE000FAB\r\n`

**Step 4: Set Target Speed**

WINDCON writes velocity:
```
:010611E603E832\r\n      → Write 0x03E8 (1000 RPM) to 0x11E6
```

Emulator:
- Sets `target_velocity_rpm = 1000`
- Responds with echo: `:010611E603E832\r\n`
- On next `step()` call: begins accelerating velocity toward 1000
- Subsequent reads of 0x11EC return gradually increasing values

**Step 5: Poll Actual Speed**

WINDCON periodically reads:
```
:010300EC0001AC\r\n      → Read actual velocity
```

Emulator responds:
```
:010302XXXX03\r\n        → XXXX increases each read (accel ramp)
```

Sequence of responses:
- Initial: `0000` (stationary)
- +10ms: `0066` (near 100 RPM)
- +20ms: `00CD` (near 205 RPM)
- +30ms: `0133` (near 307 RPM)
- ...continues until reaching target 1000 RPM

---

## Implementation in uart_simulator

### Protocol Codec (`protocol/ascii_modbus.py`)

```python
def encode_frame(address, function, payload) -> bytes:
    """Encode a response frame to ASCII bytes."""
    body = bytes([address, function]) + payload
    lrc = calc_lrc(body)
    ascii_hex = (body + bytes([lrc])).hex().upper().encode('ascii')
    return b':' + ascii_hex + b'\r\n'

def decode_frame(raw: bytes) -> AsciiFrame:
    """Parse incoming ASCII frame, validate LRC."""
    binary = bytes.fromhex(raw[1:-2].decode('ascii'))
    address, function = binary[0], binary[1]
    payload, lrc = binary[2:-1], binary[-1]
    assert calc_lrc(binary[:-1]) == lrc
    return AsciiFrame(address, function, payload, lrc)
```

### Drive State Model (`emulator/model.py`)

```python
class DriveState:
    def read_register(self, addr: int) -> int:
        """Return current value of a register."""
        if addr == 0x6040:
            return 0x000F if self.enabled else 0x0006
        elif addr == 0x11EC:
            return self.velocity_actual_rpm & 0xFFFF
        # ... (more registers)
        else:
            return 0

    def write_register(self, addr: int, value: int):
        """Update a register value."""
        if addr == 0x6040:  # Control word
            self.enabled = bool(value & 0x000F)
        elif addr == 0x11E6:  # Target velocity
            self.target_velocity_rpm = _to_i16(value)
        # ... (more registers)

    def step(self, dt_s: float):
        """Simulate one time step."""
        # Acceleration
        target = self.target_velocity_rpm if self.enabled else 0
        delta = clamp(target - self.velocity_actual_rpm, dt * 800)
        self.velocity_actual_rpm += delta
        
        # Position integration
        self.position_actual += (self.velocity_actual_rpm / 60) * 1000 * dt_s
        
        # Thermal
        abs_speed = abs(self.velocity_actual_rpm)
        self.driver_temp_c = min(120, 30 + abs_speed // 200)
        # ...
```

### Server Loop (`emulator/server.py`)

```python
async def connection_handler(reader, writer):
    """Accept and process incoming frames."""
    while True:
        # Read until \n
        frame_bytes = await reader.readuntil(b'\n')
        
        # Decode and handle
        frame = decode_frame(frame_bytes)
        response_payload = handle_frame(frame)
        response = encode_frame(frame.address, frame.function, response_payload)
        
        # Send back
        writer.write(response)
        await writer.drain()

async def run():
    """Main loop with periodic state updates."""
    tasks = [
        update_drive_state(),  # Call state.step() periodically
        connection_handler(),   # Handle client connections
    ]
    await asyncio.gather(*tasks)
```

---

## Extending the Emulator

### Add a New Register

1. Define a constant in `emulator/model.py`:
   ```python
   REG_MY_PARAM = 0x1234
   ```

2. Add read logic:
   ```python
   def read_register(self, addr):
       if addr == REG_MY_PARAM:
           return self.my_param_value & 0xFFFF
   ```

3. Add write logic (if needed):
   ```python
   def write_register(self, addr, value):
       if addr == REG_MY_PARAM:
           self.my_param_value = _to_i16(value)
   ```

### Support a New Function Code

Edit `emulator/server.py`:

```python
def handle_frame(self, frame):
    if frame.function == 0x03:
        return self._handle_read_holding_registers(frame)
    elif frame.function == 0x2B:  # Custom code
        return self._handle_custom_function(frame)

def _handle_custom_function(self, frame):
    # Parse, execute, return response_data
    response_data = [...]
    return Frame(frame.address, frame.function, response_data)
```

---

## Debugging

### Enable Frame Logging

```bash
uart-emulator --port COM11 --loglevel DEBUG
```

Output shows:
```
[RX] fn=0x03 payload=000000008 
[TX] fn=0x03 response=[16 bytes...]
```

### Capture to File

```bash
uart-sniffer --port COM11 --baud 115200 | tee traffic.log
```

Then analyze `traffic.log` offline.

### Validate Frames Manually

```python
from uart_simulator.protocol.ascii_modbus import decode_frame, calc_lrc

raw = b':010300000008F4\r\n'
frame = decode_frame(raw)
print(f"Address: {frame.address}")
print(f"Function: 0x{frame.function:02X}")
print(f"Payload: {frame.payload.hex()}")
print(f"LRC: 0x{frame.lrc:02X}")
```

---

**Last Updated:** March 21, 2026
