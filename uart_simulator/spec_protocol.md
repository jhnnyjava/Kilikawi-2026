# Protocol Draft (Initial)

Observed from WINDCON artifacts:

- Default transport appears as `modbus=ASCII`.
- Typical settings: 115200, 8N1, node/address 1.
- Register-oriented model with addresses such as 1008, 1020, 1055.

Current implementation assumption in this scaffold:

- Modbus ASCII framing (`:...\r\n`) with LRC.
- Function `0x03` read holding registers.
- Function `0x06` write single register.

Replace assumptions with confirmed behavior after frame capture.
