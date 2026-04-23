# WINDCON RS485 and CAN Data Map (Decompiled + Manual)

## 1. Scope
This document summarizes what data the WINDCON software can send and receive, how it communicates over RS485, and what CAN/other connector pins are used.

The mapping is built from:
- Decompiled indicators from `WINDCON Servo Assistant.exe`, `ControlCAN.dll`, `fileProc.dll`
- Built-in app docs in `WINDCON Servo Assistant/documentation/*.html`
- Communication defaults in `WINDCON Servo Assistant/serial_settings.ini`
- Protocol details in `uart_simulator/PROTOCOL.md`
- Connector/pin text extracted from `Kilikawi/FDK3533C-XC_Manual_EN_v3.docx`

## 2. RS485 Communication (How)

### 2.1 Physical link
- PC side uses USB-to-serial adapter.
- Controller side uses RS485/RS422 communication interface.
- Built-in docs explicitly state the assistant connects through an RS485/RS422-to-USB serial cable.

### 2.2 Session setup (default)
From `WINDCON Servo Assistant/serial_settings.ini`:
- mode: ASCII
- node id: 0x01
- baud: 115200
- data bits: 8
- parity: None
- stop bits: 1
- flow control: none

### 2.3 Protocol mode behavior
- RS485 command transport supports Modbus ASCII and RTU paths in code.
- Firmware upgrade path is ASCII-only (built-in FAQ states RTU does not support remote upgrade).

### 2.4 Frame-level behavior
Based on `uart_simulator/PROTOCOL.md` and app strings (`getModbusSerialData_ASCII`, `getModbusSerialData_RTU`, `writeSerialData`, `readMultiData`):
- Read: FC 0x03/0x04 style register reads (single and multi-read workflows)
- Write single: FC 0x06
- Write multiple: FC 0x10
- ASCII transport includes LRC verification paths (`verifyWritedData`, `miniVerifyWritedData`, `lrc Check Error`).

## 3. RS485 Data the App Sends and Receives

### 3.1 Data sent from app to controller (TX)
Observed command families and UI-driven writes:
- open/close communication and mode switching
  - `openSerialPort`, `closeSerialPort`, `setSerialParam`, `setModbusMode`, `enableModbus`
- command issue
  - `writeDataRequest`, `writeData`, `writeSerialData`, `ReadWriteSlot`
- parameter operations
  - parameter table write, save command, read all parameters

Likely written categories (from UI and strings):
- enable/disable control
- work mode selection
- reference current and reference speed
- parameter table values (addresses in 0x1000 range and higher)

### 3.2 Data received by app from controller (RX)
Observed receive/parse paths:
- `readyRead`, `serialReadData`, `readSerialDataSlot`, `readedDataProcess`, `miniReadedDataProcess`, `readMultiData`, `mReadMultiData`

Telemetry/status fields shown in app and decompiled symbol strings:
- bus voltage
- motor temperature
- driver temperature
- current feedback
- speed feedback
- position feedback
- reference current
- reference speed
- alarm and status bitfields
- communication status / fault status

### 3.3 Register/address clues from decompiled constants and docs
From decompiled constant-reference pass:
- main app: 0x1000, 0x1014 seen in active compare/move paths
- ControlCAN.dll: 0x1000, 0x1009, 0x100A, 0x101C appear in branch logic

From built-in docs (human-readable address references):
- 1008: enable/disable logic
- 1133 to 1142: DI/DO config values
- 1055, 1056, 1076: speed/position reach tolerances
- many fault/protection thresholds at 10xx/12xx addresses

## 4. CAN Communication (How and What)

### 4.1 Physical CAN pins (from controller manual text)
On 30-pin Connector A:
- A2: CAN_L
- A3: CAN_H
- A4: ISO GND (CAN/RS485 isolation ground)

Manual notes indicate:
- isolated CAN bus
- built-in 120 ohm termination in controller
- add 120 ohm at each bus end as needed
- protocol is customizable (not fixed to one public profile in docs)

### 4.2 CAN software path (decompiled)
`ControlCAN.dll` shows CAN stack and USB-CAN bridge APIs:
- `VCI_InitCAN`
- `VCI_StartCAN`
- `VCI_ResetCAN`
- `VCI_ReadCANStatus`
- `VCI_ReadErrInfo`
- `VCI_ReadBoardInfo`
- `canIoctl`
- `CH375ReadInter`, `CH375ReadData`, `CH375WriteData`, `CH375AbortRead`, `CH375AbortWrite`

This indicates:
- app uses a CAN abstraction DLL and USB bridge layer
- CAN transport/control is implemented separately from the RS485 Modbus serial path

### 4.3 CAN data categories (inferred)
The same high-level controller state appears exposed to UI regardless of transport:
- status/fault
- speed/current/voltage/temperature
- command/state transitions

But exact CAN frame IDs/payload formats are not directly visible from string-level headless output alone and need deeper cross-reference disassembly pass.

## 5. Other Non-RS485 Pins You Asked About

From 30-pin connector text extraction (manual):
- RS485:
  - A8: RS485 T+
  - A9: RS485 T-
- CAN:
  - A2: CAN_L
  - A3: CAN_H
  - A4: ISO GND
- Control and IO examples:
  - A17: low brake input
  - A24: high brake input (active-high path)
  - A22: throttle +5V output
  - A30: throttle analog signal (0 to 5V)
  - A26: READY signal output
  - A16/A19/A27: signal grounds (by mode group)
  - A25: 12V output for active-high switch signals

Interpretation: the app can interact with more than RS485-only data paths because IO/control and CAN are present in the same controller harness model.

## 6. Practical Send/Receive Summary

### RS485
- Send: Modbus-like read/write commands (ASCII/RTU paths), parameter writes, mode/enable commands.
- Receive: telemetry + status/fault + parameter readback.
- Best documented and most directly visible in app UI/decompiled strings.

### CAN
- Send/receive path exists through `ControlCAN.dll` VCI/CH375 APIs.
- Physical lines are A2/A3 with isolation ground A4.
- Frame schema is likely vendor-custom and not fully decoded in this pass.

### FileProc role
- `fileProc.dll` appears focused on authorization/serial-number checks (`getSerialNum`, `checkTempAutFileX`) rather than runtime fieldbus payload formatting.

## 7. What is confirmed vs. pending

Confirmed now:
- RS485 mode, framing behavior, and major TX/RX function families
- Key telemetry/status categories visible in receive processing
- CAN transport implementation path and connector pin mapping
- Non-RS485 pins for throttle/brake/ready/signal IO

Still pending for full reverse map:
- exact CAN frame IDs and byte-level payload map
- one-to-one mapping between each 0x10xx register and each UI field for every model variant

## 8. Recommended next reverse step
To finish byte-level CAN and register maps, run a targeted cross-reference pass in Ghidra for:
- `writeDataRequest`
- `readedDataProcess`
- `getModbusSerialData_ASCII`
- `VCI_ReadCANStatus`
- `VCI_InitCAN`
- constants `0x1009`, `0x100A`, `0x1014`, `0x101C`

This will produce direct function xref chains from command parser to UI field setters.
