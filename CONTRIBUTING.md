# Contributing

## Local Development Setup

From the `windcony/uart_simulator` package directory, create a fresh virtual environment and install the package in editable mode with development dependencies.

### Linux/macOS

```bash
cd windcony/uart_simulator
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pytest -v
```

### Windows PowerShell

```powershell
cd windcony\uart_simulator
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pytest -v
```

## Repository Hygiene

Keep source code, tests, protocol notes, captured research data, and curated vendor reference artifacts under version control. Generated Python environments and build outputs should stay untracked:

```gitignore
uart_simulator/.venv/
uart_simulator/src/*.egg-info/
__pycache__/
*.pyc
dist/
build/
```

The WINDCON Servo Assistant executables, DLLs, SYS drivers, and zipped driver bundles are useful reverse-engineering references because they document the exact tooling and driver stack being studied. Keep them tracked while the repository is used as a research archive. If the repo becomes a distributable Python package later, move those vendor binaries to a documented external archive with checksums and retrieval instructions, then keep only the protocol notes, hashes, and licensing/provenance records in Git.
