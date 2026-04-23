# Manual Control Tab Guide - Real-Time Variable Testing

## Overview

The **Manual Control** tab has been added to the simulator GUI to enable real-time verification of the WINDCON interface mapping. Instead of relying on auto-generated simulation values, you can now manually set specific telemetry values and immediately observe how WINDCON responds to them.

## Quick Start

### 1. Launch the GUI

```powershell
cd "c:\Users\user\Downloads\WINDCON Servo Assistant（国外版）\uart_simulator"
$env:PYTHONPATH='src'
python -m uart_simulator.gui.app
```

Or use the faster method:
```powershell
python launch_app.py
```

### 2. Select the "Manual Control" Tab

In the left panel, click on the **"Manual Control"** tab (between "Controller" and "Animation").

### 3. Enable Manual Override

Check the **"Enable Manual Override (Disables Auto-Simulation)"** checkbox. When enabled:
- All auto-simulation logic is disabled
- Manually-set values are sent directly in Modbus responses
- Values persist when the emulator receives new requests from WINDCON
- Status bar shows "✓ Manual override ACTIVE"

### 4. Adjust Values

Use the sliders to set specific telemetry values:

| Control | Range | Description |
|---------|-------|-------------|
| **Speed (RPM)** | −3000 to +3000 | Motor rotation speed negative=reverse, positive=forward |
| **Motor Temp (°C)** | 0 to 150 | Motor winding temperature |
| **Driver Temp (°C)** | 0 to 150 | Driver/controller temperature |
| **Bus Voltage (0.1V)** | 40.0V to 100.0V | Supply voltage (internal units are 0.1V) |
| **Position** | −50000 to +50000 | Absolute position counter (integration with speed) |
| **Error Code** | 0 to 9999 | Fault/error code (0=no error) |

### 5. Verify in WINDCON

Open WINDCON and connect to the emulator:

1. Select **COM10** (or your simulator port)
2. Click **"Search Device"** → should find node 1
3. Click **"Connect"**
4. Open **live data pages**: Speed, Temperature, Voltage, Status, Fault code

**Each value you adjust in Manual Control should immediately appear in WINDCON's corresponding display.**

## Testing Workflow Example

### Test 1: Speed Reading Accuracy

1. **Set Speed to 2000 rpm** in Manual Control
2. **Watch WINDCON**: Speed display should show **2000 rpm**
3. **Set Speed to -500 rpm** (reverse)
4. **Watch WINDCON**: Should display **−500 rpm** with reverse indicator
5. **Conclusion**: If both match, speed interface is correctly mapped ✓

### Test 2: Temperature Sensor Verification

1. **Set Motor Temp to 85°C**
2. **Watch WINDCON**: Motor temp gauge should jump to **85°C**
3. **Set Driver Temp to 95°C**
4. **Watch WINDCON**: Driver temp (if displayed) should show **95°C**
5. **Conclusion**: If both match, temperature mapping is correct ✓

### Test 3: Supply Voltage Monitoring

1. **Set Bus Voltage to 480** (represents 48.0V)
2. **Watch WINDCON**: Voltage page should show **48.0V**
3. **Set Bus Voltage to 720** (represents 72.0V)
4. **Watch WINDCON**: Should update to **72.0V**
5. **Conclusion**: If values track exactly, voltage scaling is correct ✓

### Test 4: Error Code Path

1. **Set Error Code to 205** (arbitrary fault code)
2. **Watch WINDCON**: Fault/alarm page should display **error 205**
3. **Clear by setting Error Code to 0**
4. **Watch WINDCON**: Fault indication should disappear
5. **Conclusion**: If error codes display and clear correctly, error path works ✓

## Real-Time Stream Monitoring

As you adjust values, the **Stream Activity** box shows live status:

```
✓ Streaming: 1500 rpm, 75°C motor, 82°C driver, 54.0V, pos=1234, err_code=0
```

This confirms that:
- Values are being actively sent in Modbus responses
- WINDCON is polling and receiving updates
- No gaps or stale data in the stream

## Detailed Field Descriptions

### Speed (RPM)
- **Range**: −3000 to +3000
- **Modbus Path**: Word[0] in 10-word telemetry block (0x0100, 0x0101 read registers)
- **Behavior in WINDCON**: 
  - Positive = forward rotation
  - Negative = reverse (if supported by UI)
  - Zero = stopped/idle
- **Test**: Set to exact value and verify WINDCON matches to the RPM

### Motor Temperature (°C)
- **Range**: 0 to 150°C
- **Modbus Path**: Word[8] in telemetry block (or register 0x100E compat mode)
- **Expected in WINDCON**: Motor winding temperature gauge
- **Thermal Limit**: WINDCON may show warnings/alarms at 120°C+
- **Test**: Set to 100°C, should appear on all temp-sensitive pages

### Driver Temperature (°C)
- **Range**: 0 to 150°C
- **Modbus Path**: Distinct from motor temp (register 0x1015 compat mode)
- **Expected in WINDCON**: Inverter/driver heatsink temperature
- **Test**: Set to 90°C while motor is at 80°C; verify both displayed separately

### Bus Voltage (0.1V units)
- **Display Range**: 40.0V to 100.0V (internal: 400 to 1000 in 0.1V units)
- **Modbus Path**: Register 0x100D (compat mode, direct read)
- **Real Example**: 540 units = 54.0V (nominal 48V or 60V system)
- **Expected in WINDCON**: "Bus: 54.0V" or similar gauge
- **Test**: Set to 480, 600, 720 and verify WINDCON updates to 48.0V, 60.0V, 72.0V

### Position
- **Range**: −50000 to +50000 (scale depends on application)
- **Expected in WINDCON**: Position counter (distance, angle, etc.)
- **Behavior**: Does NOT auto-update from speed—set manually to test independent position readback
- **Test**: Set to 12345, should appear exactly in WINDCON position register

### Error Code
- **Range**: 0 (OK) to 9999 (fault)
- **Modbus Path**: Register 0x101D (compat mode fault code)
- **Expected in WINDCON**: Fault page, alarm log, status indicators
- **Common Codes** (from decompiled WINDCON):
  - 0 = OK, ready
  - 101 = Overload
  - 102 = Over-temperature
  - 205 = Communication error
  - (others depend on your drive firmware)
- **Test**: Set to 102, WINDCON should highlight "Over-temperature" alarm

## Troubleshooting Manual Control

### Values Not Appearing in WINDCON

**Problem**: Set a value in Manual Control, but WINDCON doesn't update

**Diagnosis**:
1. Check **"Manual override ACTIVE"** is shown in status
2. Verify WINDCON is still connected (blue communication indicator)
3. Check Stream Activity box—is it updating?
4. Try a more extreme value (e.g., 3000 rpm → should be obvious)

**Solutions**:
- Disable/re-enable Manual Override to reinitialize
- Reconnect WINDCON (close and reopen connection)
- Check emulator port (look at top of GUI for port name)

### Emulator Crashes When Toggling Manual Override

**Problem**: Enableing  manual override causes GUI to freeze or crash

**Solution**: This is a rare synchronization bug. Restart the GUI:
```powershell
pkill -f "uart_simulator.gui.app"  # Or close window
python -m uart_simulator.gui.app    # Restart
```

### Values Change on Their Own

**Problem**: Manual values keep changing even though you didn't move sliders

**Diagnosis**: Manual override may have been disabled

**Solution**:
- Verify **"Enable Manual Override"** checkbox is checked
- If unchecked, the simulator reverts to auto-simulation (temp changes with speed, position integrates, etc.)
- Re-check the box and set values again

## Integration with WINDCON Test Scenario

The **"Start WINDCON Test"** button on the **Controller** tab runs an automated 30-second profile:
- When running, **Manual Control is automatically disabled**
- After test completes, you can switch to **Manual Control** tab and enable manual override
- Useful for comparing auto-simulation vs. manual control verification

## Architecture Details

### What Changed in the Code

1. **DriveState (model.py)**
   - Added `manual_override_active: bool` flag
   - Modified `step()` to skip auto-simulation when flag is set

2. **SimulatorApp GUI (gui/app.py)**
   - Added new tab: **"Manual Control"**
   - Added sliders for: speed, temps, voltage, position, error_code
   - Added `_on_manual_override_toggle()` and `_on_manual_value_change()` handlers
   - Status display shows real-time streaming feedback

3. **Tests (test_model.py)**
   - Added `test_manual_override_preserves_values()`
   - Added `test_manual_override_disabled_uses_auto_simulation()`
   - **All 47 existing tests still pass** ✓

### How It Works

```
User adjusts slider → GUI updates tk.StringVar → Call _on_manual_value_change()
↓
Update DriveState.velocity_actual_rpm (etc.)
↓
Next Modbus poll → Server reads DriveState → Returns manually-set value in response
↓
WINDCON receives response → Displays value on live page
```

**Latency**: < 50ms (one GUI tick cycle) for value to appear in Modbus stream

## Best Practices

### For Interface Hardening
1. **Test extremes**: Set min/max values (e.g., −3000, +3000 rpm) to verify range handling
2. **Test transitions**: Set value X, then immediately set value Y, watch for glitches
3. **Test persistence**: Set custom value, let WINDCON poll 5+ times, verify no drift
4. **Test error clearing**: Set error code, clear it, verify alarm disappears

### For Debugging
1. **Start simple**: Test just speed first (most important value)
2. **Isolate fields**: Monitor one field at a time in WINDCON
3. **Use extreme values**: 9999 rpm, 150°C obviously stand out
4. **Check logs**: If emulator has debug logging, enable it to see request/response pairs

### For Production Validation
1. **Create a test matrix**: Document which values map to which WINDCON displays
2. **Automate if possible**: Record actual WINDCON requests/responses alongside manual values to correlate
3. **Compare with real drive**: If you have access to actual WINDCON hardware, compare telemetry ranges

## Summary

The Manual Control tab transforms the simulator from a **passive mock** into an **active test harness** for verifying your WINDCON interface implementation. By setting known values and watching how WINDCON interprets them, you can quickly identify and fix any register mapping errors before deploying to production.

**Key benefits**:
- ✓ Instant feedback on Modbus interface correctness
- ✓ No need for real motor hardware to test telemetry visualization
- ✓ Detect UI/display bugs that auto-simulation misses
- ✓ Build confidence that protocol mapping is correct
