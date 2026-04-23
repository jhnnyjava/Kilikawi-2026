#!/usr/bin/env python
import sys
import os

# Add src to path so imports like 'uart_simulator' work
src_path = os.path.join(os.path.dirname(__file__), 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from uart_simulator.gui.app import main

if __name__ == "__main__":
    main()
