# RPM Injection Test Workflow

This document defines the requested deterministic profile:
- Increase target RPM by 1 every second from 0 to 200
- Then decrease by 1 every second back to 0
- Validate telemetry injection words against compatibility registers

## Test Files

- `tests/test_rpm_profile_injection.py`
- `tests/conftest.py`

## Why `conftest.py` Exists

When tests are run from `uart_simulator/tests`, Python may not include
`uart_simulator/src` in `sys.path`. `conftest.py` prepends `src` so imports such
as `from uart_simulator.emulator.model import DriveState` always resolve.

## Environment Setup

Run from project root (`uart_simulator`):

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

If you prefer to run only the minimum dependency:

```powershell
.\.venv\Scripts\python.exe -m pip install pytest
```

## Run Commands

From project root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

From tests folder:

```powershell
..\.venv\Scripts\python.exe -m pytest -q
```

## Expected Assertions

1. Velocity feedback follows exact profile when `force_feedback_to_target=True`.
2. Injection word mapping remains stable:
   - `w0` equals speed reference register `0x100B`
   - `w1` tracks current reference `0x100C` with allowed jitter of +/-1
   - `w2` equals bus voltage register `0x100D`
   - `w4` equals driver temperature register `0x1015`
   - `w7` marker is `0xF00B`

## Notes

- The `w1` tolerance is intentional because the server adds a tiny deterministic
  sinusoidal jitter to avoid UI pages suppressing fully static values.
- This test validates simulator-side correctness. WINDCON UI behavior can still
  differ if a page prefers a different source register than expected.
