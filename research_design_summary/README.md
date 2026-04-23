# WINDCON Emulator Design and Research Summary

## Purpose
This folder captures the design decisions, reverse-engineering findings, and validation results for the WINDCON RS485/CAN emulator and telemetry mapping work.

## Scope Covered
- RS485 Modbus ASCII emulator behavior
- GUI control and manual override test workflow
- Register mapping across WINDCON profile variants
- Receive-log decoding and telemetry classification
- Status/error display behavior in WINDCON

## Project Design Overview

### Emulator Core
- Drive simulation is implemented in `uart_simulator/src/uart_simulator/emulator/model.py`.
- Protocol handling is implemented in `uart_simulator/src/uart_simulator/emulator/server.py`.
- Supported function codes: 0x03, 0x04, 0x06, 0x10, 0x17.

### GUI and Real-Time Testing
- GUI app is implemented in `uart_simulator/src/uart_simulator/gui/app.py`.
- Manual Control tab allows direct runtime edits of speed, temperatures, voltage, position, and error code.
- Manual override mode disables auto simulation and pushes explicit values into response paths for mapping validation.

### Protocol and Decode Tooling
- Capture decoder is implemented in `uart_simulator/src/uart_simulator/tools/decode_receive_log.py`.
- Decoder validates LRC and extracts fixed 10-word frames from `:010314...` responses.
- Current decode dataset confirms large-scale valid frame structure and useful marker classes.

## Reverse-Engineering Findings

### Configuration-Derived Register Mapping
WINDCON profile files in `WINDCON Servo Assistant/config/` show profile-specific register interpretation.

#### VSY_Single profile
- `WorkMode=1007`
- `RunMode=1008`
- `SpeedFdb=129E`
- `CurrentFdb=129F`
- `FaultCode1=1013`
- `FaultCode2=129B`

#### VSY_double profile
- `FaultCode1=1018`
- `FaultCode2=1019`
- `CurrentBase=1005`
- `SpeedBase=1006`

#### CAN402 map clues
From `config/quick_config/CAN402_MapConfig.ini`:
- `ControlWord=11DE`
- `StatusWord=11DF`
- `TargetVelocity=11E6`
- `VelocityActualValue=11EC`
- `TargetPosition=11F0`
- `position_actual_value=1256`

### Implication
A single fixed mapping is not enough for all WINDCON variants. The simulator must support profile-aware compatibility behavior, especially around fault and telemetry fields.

## Telemetry/Status Display Issue Analysis

### Observed issue
WINDCON UI could appear static even though communication was active.

### Root causes addressed
- Real-time 10-word stream needed stronger linkage to live status/error signals.
- Some variants treat `0x1018/0x1019` as fault fields, not float telemetry.
- Manual override activation needed immediate value push to avoid delayed visible updates.

### Implemented adjustments
- Real-format 10-word response now carries live speed/current/voltage/status/mode/run/fault values.
- Compatibility mode supports `FAULT_CODES` behavior for `0x1018/0x1019`.
- Manual override now applies values immediately when toggled on.

## Validation Summary
- Model and parser tests passed after changes.
- Full test suite currently passing.
- Decoder confirms valid frame population and stable structure in captured logs.

## Recommended Runtime Profiles

### For VSY_double-like behavior
Set:
- `WINDCON_1018_101A_MODE=FAULT_CODES`

### For VSY_Single-like behavior
Set:
- `WINDCON_1018_101A_MODE=VOLT_TEMP`

## Suggested Workflow
1. Start emulator with frame trace enabled.
2. Connect WINDCON and perform controlled value changes.
3. Confirm address polls and UI update correlation.
4. Keep adding findings here as field mappings are confirmed.

## Open Items
- Complete one-to-one map from all polled addresses to every WINDCON page widget.
- Capture and classify request traffic alongside responses for deterministic mapping.
- Finalize profile auto-detection strategy.

## Folder Use
- Keep this README as the high-level index.
- Add sub-docs for focused topics (for example: `register-matrix.md`, `capture-analysis.md`, `ui-mapping-tests.md`).

## Research Q&A Log

### 2026-04-01: How to get RPM/speed, throttle, and capped RPM controls

Question summary:
- Should speed/RPM and control commands use CAN or RS485?
- Are 30-pin IO and 8-pin encoder pins required?

Evidence used:
- `Kilikawi/WINDCON_RS485_CAN_DATA_MAP.md`
- `WINDCON Servo Assistant/config/VSY_Single.ini`
- `WINDCON Servo Assistant/config/VSY_double.ini`
- `WINDCON Servo Assistant/config/quick_config/CAN402_MapConfig.ini`

Conclusions:
1. For PC/WINDCON diagnostics and commissioning, use RS485 first.
	- Built-in app flow is explicitly RS485/RS422 serial oriented.
	- Speed feedback and setpoint paths are directly mapped in config (`SpeedFdb=129E`, `SpeedRef=12B0`, `RunMode=1008`, `WorkMode=1007`).

2. CAN is possible, but only if CAN profile/mapping is configured and matched end-to-end.
	- CAN stack and PDO map parameters exist (`CAN_NodeID`, PDO mapping group in CAN402 map), but this typically needs extra integration effort compared with RS485.

3. Throttle and capped RPM can be controlled over communication bus (no mandatory analog wiring for bench testing).
	- Throttle-like command paths exist as register setpoints (speed/current refs and mode/run words).
	- RPM cap behavior is generally parameter-based (speed max/base/limit type addresses), so RS485 writes are sufficient for software-level tests.

4. 30-pin and 8-pin physical signals are only required when validating real external hardware IO/sensor behavior.
	- 30-pin includes CAN and RS485 lines plus throttle analog lines.
	- 8-pin encoder connector is for resolver/temperature feedback hardware.
	- If your goal is WINDCON UI mapping and protocol verification, emulator + RS485 is enough.

Recommended practice:
- Phase 1 (fast validation): RS485 only (software/emulator), verify RPM/status/error updates.
- Phase 2 (vehicle-level realism): add 30-pin throttle/brake/IO and 8-pin encoder/resolver wiring.
- Phase 3 (network integration): move to CAN once RS485 mapping is stable and confirmed.

## Additional Diagram Evidence (Kilikawi Folder)

New artifacts reviewed from `Kilikawi/`:
- `4.7Typical Wiring Diagram for Controller Applications.PNG`
- `Encoder Feedback8PINSocket Port Analysis Diagram.PNG`
- `Analytical diagram of power supply and motor terminal blocks.PNG`
- `30_IO.jpg`
- `FDK3533C-XC smart controller V1.0.pdf` and EN manual variants

Confirmed by diagrams:
1. 30-pin connector includes RS485, CAN, throttle/pulse/IO lines and logic inputs.
	- RS485: pin 8 (T+), pin 9 (T-)
	- CAN: pin 2 (CAN-L), pin 3 (CAN-H), pin 4 isolation ground
	- Throttle path: pin 22 (+5V), pin 29 (throttle negative), pin 30 (throttle signal)

2. 8-pin encoder/resolver connector mapping is consistent:
	- 4 REF+, 8 REF-
	- 3 SIN+, 7 SIN-
	- 2 COS+, 6 COS-
	- 1/5 motor temperature detect +/−

3. Power terminal drawing confirms separate motor phase and battery terminal blocks:
	- U/V/W motor phases
	- B+/B- battery supply

Confidence and caveat:
- `30_IO.jpg` appears to be a different or generalized dashboard harness pin naming (turn signal, ABS, oil pressure, etc.) and does not fully match the FDK3533C-XC control pin naming.
- For this project, treat the FDK3533C-XC wiring diagrams and manual PDFs as primary source, and use `30_IO.jpg` only as secondary reference.

Engineering impact:
- This confirms we can keep RS485-only bench testing as primary path for protocol/UI mapping.
- It also gives a clear physical wiring upgrade path when moving from emulator to hardware-in-the-loop tests.

### 2026-04-01: Mega + ESP8266 microcontroller interface plan (throttle and motor lock)

Goal summary:
- Interface controller using Mega WiFi R3 (ATmega2560 + ESP8266).
- Send command-like throttle values.
- Trigger alarm/lock style motor inhibit behavior.

Evidence used:
- `WINDCON Servo Assistant/serial_settings.ini`
- `WINDCON Servo Assistant/config/VSY_Single.ini`
- `WINDCON Servo Assistant/config/VSY_double.ini`
- `Kilikawi/4.7Typical Wiring Diagram for Controller Applications.PNG`
- `Kilikawi/WINDCON_RS485_CAN_DATA_MAP.md`

Controller bus defaults (confirmed):
- Modbus mode: ASCII
- Node ID: 01
- Baud: 115200
- Data bits: 8
- Parity: None
- Stop bits: 1

Recommended hardware architecture:
1. Use ATmega2560 as real-time bus controller over RS485.
2. Use ESP8266 as network/UI bridge only (Wi-Fi API, telemetry upload, remote commands).
3. Add an isolated TTL-to-RS485 transceiver between Mega UART and controller pins 8/9.
4. Share correct signal reference via controller isolation/ground guidance from wiring diagram.

Why RS485 first:
- Existing WINDCON commissioning flow and known register map are RS485-oriented.
- CAN is possible, but payload mapping is still less deterministic in this project state.

Command strategy (register-level):
- Work mode: 0x1007
- Run/enable state: 0x1008
- Speed reference: 0x12B0 (profile evidence), compatibility mirror 0x100B
- Current reference: 0x12B1
- Candidate lock/fault control parameters: 0x1145 (single profile), 0x1129 (double profile)
- Additional vendor command words seen in configs: 0x12AE/0x12AF or 0x1032/0x1033

Verified Modbus ASCII write examples (node 01):
- Enable run (0x1008=1): :010610080001E0
- Disable run (0x1008=0): :010610080000E1
- Set speed +1500 rpm (0x12B0=0x05DC): :010612B005DC56
- Set speed -500 rpm (0x12B0=0xFE0C): :010612B0FE0C2D
- Set speed mode (0x1007=1): :010610070001E1

Candidate lock/alarm test writes (must be validated on bench):
- Write 0x1145=1: :010611450001A2
- Write 0x1129=1: :010611290001BE

Important caution:
- The lock/alarm semantics for 0x1145 and 0x1129 are inferred from profile labels (`FaultLockout`) and need controlled bench verification before production use.
- For immediate safe inhibit, using run disable (0x1008=0) is the most deterministic software path currently confirmed.

Integration phases:
1. Phase A: Mega + RS485 only, confirm read/write stability and speed command loop.
2. Phase B: Add ESP8266 command API and telemetry forwarding.
3. Phase C: Validate lock/alarm command behavior and fallback to run-disable safety path.
4. Phase D: Optional CAN migration after RS485 feature parity is complete.

### 2026-04-01: Where datasheet evidence shows RS485 command path

Question summary:
- Where does the datasheet show that commands can be sent via RS485?

Answer references:
- RS485 transport definition and connection method are documented in `Kilikawi/WINDCON_RS485_CAN_DATA_MAP.md` section 2 (`RS485 Communication`) including RS485/RS422 link and serial cable path.
- Command transport support is documented in section 2.3 and 2.4 (Modbus ASCII/RTU, FC 0x06 and FC 0x10 write operations).
- App TX command functions are listed in section 3.1 (`writeDataRequest`, `writeData`, `writeSerialData`, `ReadWriteSlot`).
- Physical RS485 pins are documented in section 5: 30-pin connector A8 (T+) and A9 (T-).
- Wiring visual confirmation is in `Kilikawi/4.7Typical Wiring Diagram for Controller Applications.PNG`.

Conclusion:
- The controller command path over RS485 is explicitly documented and is the primary commissioning/control path for this project.
- We have 20 request families not one ffixed register mapping.