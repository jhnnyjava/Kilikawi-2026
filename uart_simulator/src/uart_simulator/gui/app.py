from __future__ import annotations

import math
import csv
import struct
import threading
import time
import tkinter as tk
from tkinter import ttk
from datetime import datetime
from pathlib import Path
from collections.abc import Callable

from uart_simulator.emulator import server as emulator_server
from uart_simulator.emulator.model import (
    DriveState,
    ENCODER_PIN_FUNCTIONS,
    IO_PIN_FUNCTIONS,
)
from uart_simulator.tools.controller_client import ControllerClient
from uart_simulator.tools.controller_client import ControllerClientError


# Datasheet-oriented layout (3 rows x 10 columns), numbered by column:
# leftmost column is bottom/middle/top = A1/A2/A3, then A4/A5/A6, ... A28/A29/A30.
CONNECTOR_A_ROWS = [
    ["A3", "A6", "A9", "A12", "A15", "A18", "A21", "A24", "A27", "A30"],
    ["A2", "A5", "A8", "A11", "A14", "A17", "A20", "A23", "A26", "A29"],
    ["A1", "A4", "A7", "A10", "A13", "A16", "A19", "A22", "A25", "A28"],
]

CONNECTOR_A_PINS = {
    "A1": {"signal": "Wheel Motion", "direction": "Output", "notes": "Pulse when motor rotates", "group": "commspeed"},
    "A2": {"signal": "CAN L", "direction": "Bidirectional", "notes": "CAN bus Low", "group": "can"},
    "A3": {"signal": "CAN H", "direction": "Bidirectional", "notes": "CAN bus High", "group": "can"},
    "A4": {"signal": "Isolated GND", "direction": "Ground", "notes": "CAN/RS485 isolation ground", "group": "ground"},
    "A5": {"signal": "Isolated 5V", "direction": "Output", "notes": "Max 100 mA, Bluetooth only", "group": "power"},
    "A6": {"signal": "Speed Pulse / 1-Wire", "direction": "Output", "notes": "8 pulses/rev OR single-wire instrument", "group": "commspeed"},
    "A7": {"signal": "Instrument GND", "direction": "Ground", "notes": "Ground for pulse speedometer", "group": "ground"},
    "A8": {"signal": "RS485 Transmit (T+)", "direction": "Output", "notes": "Commissioning / command", "group": "rs485"},
    "A9": {"signal": "RS485 Receive (T-)", "direction": "Input", "notes": "Commissioning / command", "group": "rs485"},
    "A10": {"signal": "Key Switch", "direction": "Power Input", "notes": "B+ via key switch - powers controller", "group": "power"},
    "A11": {"signal": "Reverse", "direction": "Input", "notes": "Active LOW", "group": "active_low", "logic": "LOW"},
    "A12": {"signal": "Mid/Low Speed", "direction": "Input", "notes": "Active LOW", "group": "active_low", "logic": "LOW"},
    "A13": {"signal": "Key Switch (Alarm)", "direction": "Input", "notes": "Alarm unit key-on signal", "group": "power"},
    "A14": {"signal": "Alarm / Lock", "direction": "Input", "notes": "Active LOW", "group": "active_low", "logic": "LOW"},
    "A15": {"signal": "High Speed", "direction": "Input", "notes": "Active LOW", "group": "active_low", "logic": "LOW"},
    "A16": {"signal": "Signal GND", "direction": "Ground", "notes": "Common GND for active-low inputs", "group": "ground"},
    "A17": {"signal": "Low Brake", "direction": "Input", "notes": "Active LOW", "group": "brake", "logic": "LOW"},
    "A18": {"signal": "P-Gear", "direction": "Input", "notes": "Active LOW", "group": "active_low", "logic": "LOW"},
    "A19": {"signal": "Signal GND", "direction": "Ground", "notes": "Common GND for active-low inputs", "group": "ground"},
    "A20": {"signal": "Voltage Selection", "direction": "Input", "notes": "Active LOW - selects 48/60/72V", "group": "active_low", "logic": "LOW"},
    "A21": {"signal": "P-Gear Select", "direction": "Input", "notes": "Active LOW", "group": "active_low", "logic": "LOW"},
    "A22": {"signal": "Throttle Supply +", "direction": "Output", "notes": "5V out - powers throttle sensor (max 200 mA)", "group": "analog_power"},
    "A23": {"signal": "Direction Select", "direction": "Input", "notes": "Active LOW", "group": "active_low", "logic": "LOW"},
    "A24": {"signal": "High Brake", "direction": "Input", "notes": "Active HIGH - 12V signal", "group": "brake", "logic": "HIGH"},
    "A25": {"signal": "12V+ Output", "direction": "Output", "notes": "12V for active-high switch signals (max 200 mA)", "group": "power"},
    "A26": {"signal": "READY Signal", "direction": "Output", "notes": "5V when controller is active", "group": "output"},
    "A27": {"signal": "Signal GND", "direction": "Ground", "notes": "Common GND for active-low signals", "group": "ground"},
    "A28": {"signal": "B+ Output", "direction": "Output", "notes": "Battery voltage - key switch signal only (max 1 A)", "group": "power"},
    "A29": {"signal": "Throttle GND", "direction": "Ground", "notes": "Ground for throttle circuit", "group": "ground"},
    "A30": {"signal": "Throttle Signal", "direction": "Analog Input", "notes": "0-5V from throttle sensor", "group": "analog"},
}

CONNECTOR_B_LAYOUT = [["B1", "B2"], ["B3", "B4"], ["B5", "B6"], ["B7", "B8"]]

CONNECTOR_B_PINS = {
    "B1": {"signal": "Motor Temp +", "notes": "KTY84-150 temperature sensor positive", "group": "temp"},
    "B2": {"signal": "COS+", "notes": "Resolver cosine positive", "group": "cos"},
    "B3": {"signal": "SIN+", "notes": "Resolver sine positive", "group": "sin"},
    "B4": {"signal": "REF+", "notes": "Resolver excitation ~10 kHz, positive", "group": "ref"},
    "B5": {"signal": "Motor Temp -", "notes": "KTY84-150 temperature sensor negative", "group": "temp"},
    "B6": {"signal": "COS-", "notes": "Resolver cosine negative", "group": "cos"},
    "B7": {"signal": "SIN-", "notes": "Resolver sine negative", "group": "sin"},
    "B8": {"signal": "REF-", "notes": "Resolver excitation ~10 kHz, negative", "group": "ref"},
}

PIN_COLORS = {
    "can": "#3b82f6",
    "rs485": "#f97316",
    "commspeed": "#14b8a6",
    "active_low": "#a855f7",
    "brake": "#ef4444",
    "power": "#eab308",
    "ground": "#4b5563",
    "analog": "#22c55e",
    "analog_power": "#22c55e",
    "output": "#e5e7eb",
    "ref": "#ef4444",
    "sin": "#facc15",
    "cos": "#3b82f6",
    "temp": "#fb923c",
}


def _dim_hex(color: str, factor: float) -> str:
    color = color.lstrip("#")
    r = int(color[0:2], 16)
    g = int(color[2:4], 16)
    b = int(color[4:6], 16)
    r = max(0, min(255, int(r * factor)))
    g = max(0, min(255, int(g * factor)))
    b = max(0, min(255, int(b * factor)))
    return f"#{r:02x}{g:02x}{b:02x}"


def _scale_kwargs(
    *,
    from_: int,
    to: int,
    variable: tk.Variable,
    command: object | None = None,
) -> dict[str, object]:
    options: dict[str, object] = {
        "from_": from_,
        "to": to,
        "orient": "horizontal",
        "variable": variable,
    }
    if command is not None:
        options["command"] = command
    return options


class SimulatorApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("WINDCON Virtual Controller Lab")
        self.root.geometry("1380x900")

        self.state = DriveState()
        self._last_tick = time.perf_counter()
        self._uart_thread: threading.Thread | None = None
        self._uart_stop = threading.Event()

        self.port_var = tk.StringVar(value="COM11")
        self.bridge_mode_var = tk.StringVar(value="SIM")
        self.real_port_var = tk.StringVar(value="COM5")
        self.baud_var = tk.IntVar(value=115200)
        self.node_var = tk.IntVar(value=1)
        self.auto_start_bridge_var = tk.BooleanVar(value=True)
        self.push_telemetry_var = tk.BooleanVar(value=True)
        self.push_interval_ms_var = tk.IntVar(value=20)
        self.push_marker_mode_var = tk.StringVar(value="compat")
        self.push_idle_ms_var = tk.IntVar(value=120)
        self.push_schema_lock_ms_var = tk.IntVar(value=900)
        self.mode_var = tk.StringVar(value="SPEED")
        self.gear_var = tk.StringVar(value="FORWARD")
        self.eco_var = tk.BooleanVar(value=True)
        self.brake_var = tk.BooleanVar(value=False)
        self.throttle_var = tk.IntVar(value=60)
        self.target_velocity = tk.IntVar(value=1500)
        self.target_position = tk.IntVar(value=0)
        self.alarm_code_var = tk.IntVar(value=101)

        self.enabled_text = tk.StringVar(value="DISABLED")
        self.speed_text = tk.StringVar(value="0 rpm")
        self.position_text = tk.StringVar(value="0")
        self.temp_text = tk.StringVar(value="M:30 C / D:32 C")
        self.fault_text = tk.StringVar(value="OK")
        self.brake_probe_text = tk.StringVar(value="A17=H(LowBrake)  A24=L(HighBrake)")
        self.connection_text = tk.StringVar(value="UART bridge stopped")
        self.log_text = tk.StringVar(value="Data log: OFF")
        self.scenario_text = tk.StringVar(value="Scenario: OFF")
        self.reg_1008_text = tk.StringVar(value="0")
        self.reg_100b_text = tk.StringVar(value="0")
        self.reg_100d_text = tk.StringVar(value="0")
        self.reg_1010_text = tk.StringVar(value="0x0000")
        self.reg_1015_text = tk.StringVar(value="0")
        self.reg_101d_text = tk.StringVar(value="0")
        self.reg_1018_1019_text = tk.StringVar(value="0.00")
        self.reg_101a_101b_text = tk.StringVar(value="0.00")
        self.windcon_last_req_text = tk.StringVar(value="Waiting for WINDCON requests...")
        self.windcon_last_tx_text = tk.StringVar(value="No telemetry transmitted yet")
        self.windcon_words_text = tk.StringVar(value="w0..w9: -")
        self.windcon_named_words_text = tk.StringVar(
            value="w0=speed w1=current w2=voltage w3=statusLatch w4=driverTemp w5=workMode w6=runMode w7=marker w8=faultCode w9=faultActive"
        )
        self.windcon_mirror_text = tk.StringVar(value="Speed=-  Current=-  Voltage=-  Temp=-  Marker=-")
        self.windcon_marker_mode_text = tk.StringVar(value="marker mode=compat")
        self.io_info_text = tk.StringVar(value="Hover or click a pin in Connector A")
        self.encoder_info_text = tk.StringVar(value="Hover or click a pin in Connector B")
        self.manual_io_var = tk.BooleanVar(value=False)
        self.map_pin_var = tk.IntVar(value=1)
        self.map_function_var = tk.StringVar(value=CONNECTOR_A_PINS["A1"]["signal"])
        self.force_feedback_var = tk.BooleanVar(value=True)

        # Manual control variables
        self.manual_override_var = tk.BooleanVar(value=False)
        self.manual_speed_var = tk.IntVar(value=0)
        self.manual_temp_motor_var = tk.IntVar(value=30)
        self.manual_temp_driver_var = tk.IntVar(value=32)
        self.manual_voltage_var = tk.IntVar(value=540)
        self.manual_position_var = tk.IntVar(value=0)
        self.manual_error_code_var = tk.IntVar(value=0)

        self.controller_preset_var = tk.StringVar(value="Enable Drive")
        self.controller_register_var = tk.StringVar(value="0x1008")
        self.controller_value_var = tk.StringVar(value="0x0001")
        self.controller_read_register_var = tk.StringVar(value="0x1008")
        self.controller_read_count_var = tk.IntVar(value=1)
        self.controller_action_text = tk.StringVar(value="Direct controller writes are idle.")
        self.controller_result_text = tk.StringVar(
            value="Stop the bridge first if the controller port is already in use by another process."
        )

        self._selected_io_index = 0
        self._encoder_connected = [tk.BooleanVar(value=True) for _ in range(8)]
        self._io_mapping = [CONNECTOR_A_PINS[f"A{i}"]["signal"] for i in range(1, 31)]
        self._io_manual_values = [False] * 30
        self._encoder_wave_history = [[] for _ in range(8)]
        self._io_centers: list[tuple[float, float]] = []
        self._enc_centers: list[tuple[float, float]] = []
        self._io_hitboxes: list[tuple[int, int, int, int, str]] = []
        self._enc_hitboxes: list[tuple[int, int, int, int, str]] = []
        self._selected_io_pin = "A2"
        self._selected_enc_pin = "B1"
        self._anim_phase = 0.0
        self._log_active = False
        self._log_file = None
        self._log_writer: csv.writer | None = None
        self._log_path: Path | None = None
        self._log_period_s = 0.2
        self._last_log_at = 0.0
        self._scenario_active = False
        self._scenario_elapsed_s = 0.0

        self._build_ui()
        self._set_io_info_from_pin(self._selected_io_pin)
        self._set_enc_info_from_pin(self._selected_enc_pin)
        if self.auto_start_bridge_var.get():
            self.root.after(500, self._start_bridge)
        self._schedule_tick()

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=10)
        frame.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        top = ttk.LabelFrame(frame, text="Virtual UART Bridge (WINDCON endpoint)", padding=8)
        top.grid(row=0, column=0, sticky="ew")
        frame.columnconfigure(0, weight=1)

        ttk.Label(top, text="Port").grid(row=0, column=0, padx=4, pady=2, sticky="w")
        ttk.Entry(top, textvariable=self.port_var, width=10).grid(row=0, column=1, padx=4, pady=2)
        ttk.Label(top, text="Baud").grid(row=0, column=2, padx=4, pady=2, sticky="w")
        ttk.Entry(top, textvariable=self.baud_var, width=10).grid(row=0, column=3, padx=4, pady=2)
        ttk.Label(top, text="Node").grid(row=0, column=4, padx=4, pady=2, sticky="w")
        ttk.Entry(top, textvariable=self.node_var, width=6).grid(row=0, column=5, padx=4, pady=2)
        ttk.Button(top, text="Start Bridge", command=self._start_bridge).grid(row=0, column=6, padx=6)
        ttk.Button(top, text="Stop Bridge", command=self._stop_bridge).grid(row=0, column=7, padx=6)
        ttk.Label(top, textvariable=self.connection_text).grid(row=0, column=8, padx=8, sticky="w")
        ttk.Button(top, text="Start Log", command=self._start_log).grid(row=0, column=9, padx=6)
        ttk.Button(top, text="Stop Log", command=self._stop_log).grid(row=0, column=10, padx=6)
        ttk.Label(top, textvariable=self.log_text).grid(row=0, column=11, padx=8, sticky="w")

        ttk.Label(top, text="Bridge Mode").grid(row=1, column=0, padx=4, pady=2, sticky="w")
        ttk.Combobox(top, textvariable=self.bridge_mode_var, values=["SIM", "REAL"], state="readonly", width=8).grid(
            row=1, column=1, padx=4, pady=2, sticky="w"
        )
        ttk.Label(top, text="Real Ctrl Port").grid(row=1, column=2, padx=4, pady=2, sticky="w")
        ttk.Entry(top, textvariable=self.real_port_var, width=10).grid(row=1, column=3, padx=4, pady=2, sticky="w")
        ttk.Button(top, text="Connect Real Controller", command=self._connect_real_controller).grid(
            row=1, column=4, padx=6, pady=2, sticky="w"
        )
        ttk.Label(top, text="SIM: emulator on Port  |  REAL: Port <-> Real Ctrl Port").grid(
            row=1, column=5, columnspan=7, padx=4, pady=2, sticky="w"
        )

        ttk.Checkbutton(top, text="Auto Start Bridge", variable=self.auto_start_bridge_var).grid(
            row=2, column=0, columnspan=2, padx=4, pady=2, sticky="w"
        )
        ttk.Checkbutton(top, text="Push Telemetry", variable=self.push_telemetry_var).grid(
            row=2, column=2, padx=4, pady=2, sticky="w"
        )
        ttk.Label(top, text="Push Interval ms").grid(row=2, column=3, padx=4, pady=2, sticky="e")
        ttk.Entry(top, textvariable=self.push_interval_ms_var, width=8).grid(row=2, column=4, padx=4, pady=2, sticky="w")
        ttk.Label(top, text="Push Marker").grid(row=2, column=5, padx=4, pady=2, sticky="e")
        ttk.Combobox(
            top,
            textvariable=self.push_marker_mode_var,
            values=["compat", "float", "zero", "auto"],
            state="readonly",
            width=8,
        ).grid(row=2, column=6, padx=4, pady=2, sticky="w")
        ttk.Label(top, text="Idle Gate ms").grid(row=2, column=7, padx=4, pady=2, sticky="e")
        ttk.Entry(top, textvariable=self.push_idle_ms_var, width=8).grid(row=2, column=8, padx=4, pady=2, sticky="w")
        ttk.Label(top, text="Schema Lock ms").grid(row=2, column=9, padx=4, pady=2, sticky="e")
        ttk.Entry(top, textvariable=self.push_schema_lock_ms_var, width=8).grid(row=2, column=10, padx=4, pady=2, sticky="w")
        ttk.Label(top, textvariable=self.windcon_marker_mode_text).grid(row=2, column=11, columnspan=2, padx=6, pady=2, sticky="w")

        body = ttk.Frame(frame)
        body.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        frame.rowconfigure(1, weight=1)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        left = ttk.Notebook(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        right = ttk.Notebook(body)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        control_tab = ttk.Frame(left, padding=8)
        manual_tab = ttk.Frame(left, padding=8)
        anim_tab = ttk.Frame(left, padding=8)
        left.add(control_tab, text="Controller")
        left.add(manual_tab, text="Manual Control")
        left.add(anim_tab, text="Animation")

        io_tab = ttk.Frame(right, padding=8)
        enc_tab = ttk.Frame(right, padding=8)
        right.add(io_tab, text="30-Pin Connector")
        right.add(enc_tab, text="Encoder 8-Pin")

        self._build_control_panel(control_tab)
        self._build_manual_panel(manual_tab)
        self._build_animation_panel(anim_tab)
        self._build_io_panel(io_tab)
        self._build_encoder_panel(enc_tab)

    def _build_control_panel(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        parent.columnconfigure(3, weight=1)

        ttk.Button(parent, text="Enable", command=self.enable).grid(row=0, column=0, padx=3, pady=3, sticky="ew")
        ttk.Button(parent, text="Disable", command=self.disable).grid(row=0, column=1, padx=3, pady=3, sticky="ew")
        ttk.Button(parent, text="Alarm ON", command=self.alarm_on).grid(row=0, column=2, padx=3, pady=3, sticky="ew")
        ttk.Button(parent, text="Alarm OFF", command=self.alarm_off).grid(row=0, column=3, padx=3, pady=3, sticky="ew")

        ttk.Label(parent, text="Alarm Code").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Spinbox(parent, from_=1, to=9999, textvariable=self.alarm_code_var, width=10).grid(row=1, column=1, sticky="w")
        ttk.Button(parent, text="Clear Fault", command=self.clear_fault).grid(row=1, column=3, padx=3, pady=3, sticky="ew")

        ttk.Button(parent, text="Start WINDCON Test", command=self._toggle_test_scenario).grid(
            row=2, column=0, padx=3, pady=3, sticky="ew"
        )
        ttk.Label(parent, textvariable=self.scenario_text).grid(row=2, column=1, columnspan=3, sticky="w")

        ttk.Label(parent, text="Mode").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Combobox(
            parent,
            textvariable=self.mode_var,
            values=["SPEED", "POSITION", "TORQUE", "CURRENT", "HOMING", "PARAM_ID"],
            state="readonly",
            width=16,
        ).grid(row=3, column=1, sticky="ew")

        ttk.Label(parent, text="Gear").grid(row=3, column=2, sticky="w", pady=4)
        ttk.Combobox(
            parent,
            textvariable=self.gear_var,
            values=["FORWARD", "REVERSE"],
            state="readonly",
            width=10,
        ).grid(row=3, column=3, sticky="ew")

        ttk.Checkbutton(parent, text="Eco Mode", variable=self.eco_var).grid(row=4, column=0, sticky="w", pady=4)
        ttk.Checkbutton(parent, text="Brake", variable=self.brake_var).grid(row=4, column=1, sticky="w", pady=4)

        ttk.Label(parent, text="Throttle %").grid(row=5, column=0, sticky="w", pady=4)
        ttk.Scale(parent, from_=0, to=100, orient="horizontal", variable=self.throttle_var).grid(
            row=5, column=1, columnspan=3, sticky="ew"
        )

        ttk.Checkbutton(
            parent,
            text="Lock Feedback to Target (WINDCON display)",
            variable=self.force_feedback_var,
        ).grid(row=6, column=0, columnspan=4, sticky="w", pady=4)

        ttk.Label(parent, text="Target Velocity (rpm)").grid(row=7, column=0, sticky="w", pady=4)
        ttk.Scale(
            parent,
            **_scale_kwargs(from_=-3000, to=3000, variable=self.target_velocity, command=self._on_velocity_change),
        ).grid(
            row=7, column=1, columnspan=3, sticky="ew"
        )

        ttk.Label(parent, text="Target Position").grid(row=8, column=0, sticky="w", pady=4)
        ttk.Scale(
            parent,
            **_scale_kwargs(from_=-12000, to=12000, variable=self.target_position, command=self._on_position_change),
        ).grid(
            row=8, column=1, columnspan=3, sticky="ew"
        )

        status = ttk.LabelFrame(parent, text="Drive State", padding=8)
        status.grid(row=9, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        status.columnconfigure(1, weight=1)
        ttk.Label(status, text="Enabled:").grid(row=0, column=0, sticky="w")
        ttk.Label(status, textvariable=self.enabled_text).grid(row=0, column=1, sticky="w")
        ttk.Label(status, text="Speed:").grid(row=1, column=0, sticky="w")
        ttk.Label(status, textvariable=self.speed_text).grid(row=1, column=1, sticky="w")
        ttk.Label(status, text="Position:").grid(row=2, column=0, sticky="w")
        ttk.Label(status, textvariable=self.position_text).grid(row=2, column=1, sticky="w")
        ttk.Label(status, text="Temperature:").grid(row=3, column=0, sticky="w")
        ttk.Label(status, textvariable=self.temp_text).grid(row=3, column=1, sticky="w")
        ttk.Label(status, text="Brake Pins:").grid(row=4, column=0, sticky="w")
        ttk.Label(status, textvariable=self.brake_probe_text, font=("Segoe UI", 9, "bold"), foreground="#22c55e").grid(row=4, column=1, columnspan=3, sticky="w")
        ttk.Label(status, text="Fault:").grid(row=5, column=0, sticky="w")
        ttk.Label(status, textvariable=self.fault_text).grid(row=5, column=1, sticky="w")

        compat = ttk.LabelFrame(parent, text="WINDCON Register Watch", padding=8)
        compat.grid(row=10, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        compat.columnconfigure(1, weight=1)
        compat.columnconfigure(3, weight=1)

        ttk.Label(compat, text="0x1008 RunMode:").grid(row=0, column=0, sticky="w")
        ttk.Label(compat, textvariable=self.reg_1008_text).grid(row=0, column=1, sticky="w")
        ttk.Label(compat, text="0x100B SpeedRef:").grid(row=0, column=2, sticky="w")
        ttk.Label(compat, textvariable=self.reg_100b_text).grid(row=0, column=3, sticky="w")

        ttk.Label(compat, text="0x100D BusVoltage:").grid(row=1, column=0, sticky="w")
        ttk.Label(compat, textvariable=self.reg_100d_text).grid(row=1, column=1, sticky="w")
        ttk.Label(compat, text="0x1010 Status:").grid(row=1, column=2, sticky="w")
        ttk.Label(compat, textvariable=self.reg_1010_text).grid(row=1, column=3, sticky="w")

        ttk.Label(compat, text="0x1015 DriverTemp:").grid(row=2, column=0, sticky="w")
        ttk.Label(compat, textvariable=self.reg_1015_text).grid(row=2, column=1, sticky="w")
        ttk.Label(compat, text="0x101D FaultCode:").grid(row=2, column=2, sticky="w")
        ttk.Label(compat, textvariable=self.reg_101d_text).grid(row=2, column=3, sticky="w")

        ttk.Label(compat, text="0x1018/0x1019 Float:").grid(row=3, column=0, sticky="w")
        ttk.Label(compat, textvariable=self.reg_1018_1019_text).grid(row=3, column=1, sticky="w")
        ttk.Label(compat, text="0x101A/0x101B Float:").grid(row=3, column=2, sticky="w")
        ttk.Label(compat, textvariable=self.reg_101a_101b_text).grid(row=3, column=3, sticky="w")

        mirror = ttk.LabelFrame(parent, text="WINDCON Frame Mirror (What GUI Sends/Receives)", padding=8)
        mirror.grid(row=11, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        mirror.columnconfigure(1, weight=1)

        ttk.Label(mirror, text="Last WINDCON Request:").grid(row=0, column=0, sticky="w")
        ttk.Label(mirror, textvariable=self.windcon_last_req_text).grid(row=0, column=1, sticky="w")
        ttk.Label(mirror, text="Last TX Frame:").grid(row=1, column=0, sticky="w")
        ttk.Label(mirror, textvariable=self.windcon_last_tx_text).grid(row=1, column=1, sticky="w")
        ttk.Label(mirror, text="TX Words:").grid(row=2, column=0, sticky="w")
        ttk.Label(mirror, textvariable=self.windcon_words_text).grid(row=2, column=1, sticky="w")
        ttk.Label(mirror, text="Word Mapping:").grid(row=3, column=0, sticky="w")
        ttk.Label(mirror, textvariable=self.windcon_named_words_text).grid(row=3, column=1, sticky="w")
        ttk.Label(mirror, text="Decoded Mirror:").grid(row=4, column=0, sticky="w")
        ttk.Label(mirror, textvariable=self.windcon_mirror_text).grid(row=4, column=1, sticky="w")

        write_frame = ttk.LabelFrame(parent, text="Controller Write Bench", padding=8)
        write_frame.grid(row=12, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        write_frame.columnconfigure(1, weight=1)
        write_frame.columnconfigure(3, weight=1)

        ttk.Label(write_frame, text="Use this panel to send direct Modbus ASCII writes to the real controller.").grid(
            row=0, column=0, columnspan=4, sticky="w"
        )
        ttk.Label(write_frame, text="Target Port:").grid(row=1, column=0, sticky="w", pady=(6, 2))
        ttk.Label(write_frame, textvariable=self.real_port_var).grid(row=1, column=1, sticky="w", pady=(6, 2))
        ttk.Label(write_frame, text="Node:").grid(row=1, column=2, sticky="e", pady=(6, 2))
        ttk.Label(write_frame, textvariable=self.node_var).grid(row=1, column=3, sticky="w", pady=(6, 2))

        ttk.Label(write_frame, text="Preset").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Combobox(
            write_frame,
            textvariable=self.controller_preset_var,
            values=[
                "Enable Drive",
                "Disable Drive",
                "Mode Speed",
                "Mode Torque",
                "Mode Position",
                "Speed +500",
                "Speed +1000",
                "Speed -500",
                "Speed -1000",
                "Clear Fault",
            ],
            state="readonly",
            width=18,
        ).grid(row=2, column=1, sticky="w", pady=4)
        ttk.Button(write_frame, text="Apply Preset", command=self._apply_controller_preset).grid(
            row=2, column=2, padx=4, pady=4, sticky="w"
        )
        ttk.Button(write_frame, text="Read Register", command=self._read_controller_register).grid(
            row=2, column=3, padx=4, pady=4, sticky="w"
        )
        ttk.Label(write_frame, text="Count").grid(row=2, column=4, sticky="e", padx=(10, 4), pady=4)
        ttk.Entry(write_frame, textvariable=self.controller_read_count_var, width=6).grid(row=2, column=5, sticky="w", pady=4)

        ttk.Label(write_frame, text="Register").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Entry(write_frame, textvariable=self.controller_register_var, width=14).grid(row=3, column=1, sticky="w", pady=4)
        ttk.Label(write_frame, text="Value").grid(row=3, column=2, sticky="e", pady=4)
        ttk.Entry(write_frame, textvariable=self.controller_value_var, width=16).grid(row=3, column=3, sticky="w", pady=4)

        ttk.Button(write_frame, text="Write Single", command=self._write_controller_register).grid(
            row=4, column=0, padx=4, pady=(6, 2), sticky="w"
        )
        ttk.Label(
            write_frame,
            text="Common targets: 0x1007 mode, 0x1008 run, 0x100B speed ref, 0x100C current ref, 0x101D fault code",
        ).grid(row=4, column=1, columnspan=3, sticky="w", pady=(6, 2))

        ttk.Label(write_frame, text="Status:").grid(row=5, column=0, sticky="w", pady=(6, 2))
        ttk.Label(write_frame, textvariable=self.controller_action_text).grid(row=5, column=1, columnspan=3, sticky="w", pady=(6, 2))
        ttk.Label(write_frame, text="Last Response:").grid(row=6, column=0, sticky="w")
        ttk.Label(write_frame, textvariable=self.controller_result_text, wraplength=980, justify="left").grid(
            row=6, column=1, columnspan=3, sticky="w"
        )

    def _build_manual_panel(self, parent: ttk.Frame) -> None:
        """Manual control tab for real-time variable adjustment and interface verification."""
        parent.columnconfigure(1, weight=1)
        parent.columnconfigure(3, weight=1)

        # Enable/disable manual override
        override_frame = ttk.LabelFrame(parent, text="Manual Override Mode", padding=8)
        override_frame.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 10))
        override_frame.columnconfigure(1, weight=1)

        ttk.Checkbutton(
            override_frame,
            text="Enable Manual Override (Disables Auto-Simulation)",
            variable=self.manual_override_var,
            command=self._on_manual_override_toggle,
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=4, pady=4)

        ttk.Label(override_frame, text="When enabled, manually-set values are sent in Modbus responses.", font=("Segoe UI", 9)).grid(
            row=1, column=0, columnspan=4, sticky="w", padx=4
        )

        # Speed control
        ttk.Label(parent, text="Speed (RPM)").grid(row=1, column=0, sticky="w", pady=8)
        speed_scale = ttk.Scale(
            parent,
            from_=-3000,
            to=3000,
            orient="horizontal",
            variable=self.manual_speed_var,
            command=self._on_manual_value_change,
        )
        speed_scale.grid(row=1, column=1, columnspan=3, sticky="ew", padx=(4, 0))
        ttk.Label(parent, text="0 rpm", textvariable=tk.StringVar()).grid(row=1, column=4, sticky="w", padx=4)
        self.manual_speed_label = ttk.Label(parent, text="0 rpm", font=("Segoe UI", 9, "bold"))
        self.manual_speed_label.grid(row=1, column=4, sticky="e", padx=4)

        # Motor temperature control
        ttk.Label(parent, text="Motor Temp (°C)").grid(row=2, column=0, sticky="w", pady=8)
        motor_temp_scale = ttk.Scale(
            parent,
            from_=0,
            to=150,
            orient="horizontal",
            variable=self.manual_temp_motor_var,
            command=self._on_manual_value_change,
        )
        motor_temp_scale.grid(row=2, column=1, columnspan=3, sticky="ew", padx=(4, 0))
        self.manual_motor_temp_label = ttk.Label(parent, text="30 °C", font=("Segoe UI", 9, "bold"))
        self.manual_motor_temp_label.grid(row=2, column=4, sticky="e", padx=4)

        # Driver temperature control
        ttk.Label(parent, text="Driver Temp (°C)").grid(row=3, column=0, sticky="w", pady=8)
        driver_temp_scale = ttk.Scale(
            parent,
            from_=0,
            to=150,
            orient="horizontal",
            variable=self.manual_temp_driver_var,
            command=self._on_manual_value_change,
        )
        driver_temp_scale.grid(row=3, column=1, columnspan=3, sticky="ew", padx=(4, 0))
        self.manual_driver_temp_label = ttk.Label(parent, text="32 °C", font=("Segoe UI", 9, "bold"))
        self.manual_driver_temp_label.grid(row=3, column=4, sticky="e", padx=4)

        # Bus voltage control
        ttk.Label(parent, text="Bus Voltage (0.1V)").grid(row=4, column=0, sticky="w", pady=8)
        voltage_scale = ttk.Scale(
            parent,
            from_=400,
            to=1000,
            orient="horizontal",
            variable=self.manual_voltage_var,
            command=self._on_manual_value_change,
        )
        voltage_scale.grid(row=4, column=1, columnspan=3, sticky="ew", padx=(4, 0))
        self.manual_voltage_label = ttk.Label(parent, text="54.0 V", font=("Segoe UI", 9, "bold"))
        self.manual_voltage_label.grid(row=4, column=4, sticky="e", padx=4)

        # Position control
        ttk.Label(parent, text="Position").grid(row=5, column=0, sticky="w", pady=8)
        position_scale = ttk.Scale(
            parent,
            from_=-50000,
            to=50000,
            orient="horizontal",
            variable=self.manual_position_var,
            command=self._on_manual_value_change,
        )
        position_scale.grid(row=5, column=1, columnspan=3, sticky="ew", padx=(4, 0))
        self.manual_position_label = ttk.Label(parent, text="0", font=("Segoe UI", 9, "bold"))
        self.manual_position_label.grid(row=5, column=4, sticky="e", padx=4)

        # Error code control
        ttk.Label(parent, text="Error Code").grid(row=6, column=0, sticky="w", pady=8)
        ttk.Spinbox(
            parent,
            from_=0,
            to=9999,
            textvariable=self.manual_error_code_var,
            command=self._on_manual_value_change,
            width=10,
        ).grid(row=6, column=1, sticky="w", padx=4)

        # Status text
        status_frame = ttk.LabelFrame(parent, text="Stream Activity", padding=8)
        status_frame.grid(row=7, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        status_frame.columnconfigure(0, weight=1)

        self.manual_status_text = tk.StringVar(value="Manual override inactive. Enable to start sending custom values.")
        ttk.Label(status_frame, textvariable=self.manual_status_text, justify="left", wraplength=500).grid(
            row=0, column=0, sticky="w", padx=4, pady=4
        )

    def _on_manual_override_toggle(self) -> None:
        """Toggle manual override mode."""
        self.state.manual_override_active = self.manual_override_var.get()
        if self.state.manual_override_active:
            self.manual_status_text.set("✓ Manual override ACTIVE. Values below are sent in Modbus responses. Connect WINDCON to verify.")
            self._on_manual_value_change()
        else:
            self.manual_status_text.set("Manual override inactive. Simulator will use auto-simulation mode.")

    def _on_manual_value_change(self, *args) -> None:
        """Update manual control values and push to DriveState."""
        if not self.manual_override_var.get():
            return

        speed = self.manual_speed_var.get()
        motor_temp = self.manual_temp_motor_var.get()
        driver_temp = self.manual_temp_driver_var.get()
        voltage_tenth_v = self.manual_voltage_var.get()
        position = self.manual_position_var.get()
        error_code = self.manual_error_code_var.get()

        # Update state
        self.state.velocity_actual_rpm = speed
        self.state.motor_temp_c = motor_temp
        self.state.driver_temp_c = driver_temp
        self.state.bus_voltage_tenth_v = voltage_tenth_v
        self.state.position_actual = position
        self.state.error_code = error_code

        # Update labels
        self.manual_speed_label.config(text=f"{speed} rpm")
        self.manual_motor_temp_label.config(text=f"{motor_temp} °C")
        self.manual_driver_temp_label.config(text=f"{driver_temp} °C")
        self.manual_voltage_label.config(text=f"{voltage_tenth_v / 10.0:.1f} V")
        self.manual_position_label.config(text=str(position))

        # Update status
        self.manual_status_text.set(
            f"✓ Streaming: {speed} rpm, {motor_temp}°C motor, {driver_temp}°C driver, {voltage_tenth_v/10:.1f}V, "
            f"pos={position}, err_code={error_code}"
        )

    @staticmethod
    def _f32_from_words(hi: int, lo: int) -> float:
        packed = struct.pack(">HH", hi & 0xFFFF, lo & 0xFFFF)
        return struct.unpack(">f", packed)[0]

    @staticmethod
    def _u16_to_i16(value: int) -> int:
        value &= 0xFFFF
        return value - 0x10000 if (value & 0x8000) else value

    def _fmt_words(self, words: list[int], limit: int = 10) -> str:
        clipped = words[:limit]
        txt = " ".join(f"w{i}={v}" for i, v in enumerate(clipped))
        if len(words) > limit:
            return f"{txt} ..."
        return txt

    def _on_emulator_frame_event(self, event: dict[str, object]) -> None:
        def _apply() -> None:
            ev = str(event.get("event", ""))
            if ev == "rx_request":
                fn = int(event.get("function", 0))
                payload_hex = str(event.get("payload_hex", ""))
                req_detail = str(event.get("req_detail", ""))
                self.windcon_last_req_text.set(f"fn=0x{fn:02X} payload={payload_hex}{req_detail}")
                return

            if ev not in ("tx_push", "tx_response"):
                return

            frame_ascii = str(event.get("frame_ascii", ""))
            self.windcon_last_tx_text.set(frame_ascii)
            words_obj = event.get("words")
            if not isinstance(words_obj, list) or not words_obj:
                return

            words_i16: list[int] = [int(w) for w in words_obj]
            self.windcon_words_text.set(self._fmt_words(words_i16))

            speed = words_i16[0] if len(words_i16) > 0 else 0
            current = words_i16[1] if len(words_i16) > 1 else 0
            voltage = words_i16[2] if len(words_i16) > 2 else 0
            driver_temp = words_i16[4] if len(words_i16) > 4 else 0
            marker = words_i16[7] if len(words_i16) > 7 else 0
            self.windcon_mirror_text.set(
                f"Speed={speed}rpm  Current={current}  Voltage={voltage/10.0:.1f}V  Temp={driver_temp}C  Marker=0x{(marker & 0xFFFF):04X}"
            )

        self.root.after(0, _apply)

    def _build_animation_panel(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        self.anim_canvas = tk.Canvas(parent, bg="#081021", highlightthickness=0)
        self.anim_canvas.grid(row=0, column=0, sticky="nsew")

        # Draw controller block with explicit labeled interfaces.
        self.anim_canvas.create_rectangle(20, 40, 360, 260, fill="#1e293b", outline="#38bdf8", width=2)
        self.anim_canvas.create_text(190, 24, text="Controller Figure", fill="#e2e8f0", font=("Segoe UI", 11, "bold"))
        self.anim_canvas.create_rectangle(45, 70, 190, 120, fill="#0f172a", outline="#64748b")
        self.anim_canvas.create_text(118, 95, text="Control MCU", fill="#cbd5e1", font=("Segoe UI", 9, "bold"))
        self.anim_canvas.create_rectangle(205, 70, 335, 120, fill="#0f172a", outline="#64748b")
        self.anim_canvas.create_text(270, 95, text="Power Stage", fill="#cbd5e1", font=("Segoe UI", 9, "bold"))
        self.anim_canvas.create_rectangle(45, 135, 140, 175, fill="#0f172a", outline="#64748b")
        self.anim_canvas.create_text(92, 155, text="RS485", fill="#93c5fd", font=("Segoe UI", 8, "bold"))
        self.anim_canvas.create_rectangle(150, 135, 245, 175, fill="#0f172a", outline="#64748b")
        self.anim_canvas.create_text(197, 155, text="CAN", fill="#93c5fd", font=("Segoe UI", 8, "bold"))
        self.anim_canvas.create_rectangle(255, 135, 335, 175, fill="#0f172a", outline="#64748b")
        self.anim_canvas.create_text(295, 155, text="Encoder", fill="#93c5fd", font=("Segoe UI", 8, "bold"))
        self.anim_canvas.create_rectangle(45, 190, 190, 235, fill="#0f172a", outline="#64748b")
        self.anim_canvas.create_text(118, 212, text="DI/DO and Analog IO", fill="#cbd5e1", font=("Segoe UI", 8, "bold"))
        self.anim_canvas.create_rectangle(205, 190, 335, 235, fill="#0f172a", outline="#64748b")
        self.anim_canvas.create_text(270, 212, text="Brake / Gear / Throttle", fill="#cbd5e1", font=("Segoe UI", 8, "bold"))

        # Draw motor figure with clear labeled parts.
        self.anim_canvas.create_text(560, 24, text="Motor Figure", fill="#e2e8f0", font=("Segoe UI", 11, "bold"))
        self.anim_canvas.create_oval(430, 60, 690, 320, fill="#111827", outline="#22c55e", width=3, tags="motor_ring")
        self.anim_canvas.create_oval(470, 100, 650, 280, fill="#0b1220", outline="#475569", width=2)
        self.anim_canvas.create_text(560, 76, text="Stator", fill="#cbd5e1", font=("Segoe UI", 8, "bold"))
        self.anim_canvas.create_text(560, 114, text="Rotor", fill="#cbd5e1", font=("Segoe UI", 8, "bold"))
        self.anim_canvas.create_line(560, 190, 640, 190, fill="#f59e0b", width=5, tags="rotor_arm")
        self.anim_canvas.create_line(560, 190, 530, 130, fill="#f59e0b", width=4, tags="rotor_arm_2")
        self.anim_canvas.create_line(560, 190, 530, 250, fill="#f59e0b", width=4, tags="rotor_arm_3")
        self.anim_canvas.create_oval(548, 178, 572, 202, fill="#facc15", outline="#fde68a", tags="hub")
        self.anim_canvas.create_line(690, 190, 760, 190, fill="#94a3b8", width=6)
        self.anim_canvas.create_text(790, 190, text="Shaft", fill="#cbd5e1", anchor="w", font=("Segoe UI", 8, "bold"))
        self.anim_canvas.create_text(560, 305, text="Encoder Feedback and Temperature Model", fill="#93c5fd", font=("Segoe UI", 8))
        self.anim_canvas.create_oval(706, 66, 726, 86, fill="#2b3442", outline="#64748b", tags="alarm_beacon")
        self.anim_canvas.create_text(730, 76, text="Alarm", fill="#fca5a5", anchor="w", font=("Segoe UI", 8, "bold"))
        self.anim_canvas.create_text(560, 328, text="BRAKE RELEASED", fill="#22c55e", font=("Segoe UI", 8, "bold"), tags="brake_tag")

        # Link animation between controller and motor.
        self.anim_canvas.create_line(360, 170, 430, 190, fill="#60a5fa", width=3, dash=(8, 4))
        self.anim_canvas.create_text(392, 156, text="Control Bus", fill="#93c5fd", font=("Segoe UI", 8, "bold"))
        self.anim_canvas.create_oval(182, 88, 198, 104, fill="#334155", outline="#94a3b8", tags="pulse")

    def _build_io_panel(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        self.io_canvas = tk.Canvas(parent, bg="#111827", highlightthickness=0)
        self.io_canvas.grid(row=0, column=0, sticky="nsew")
        self.io_canvas.bind("<Button-1>", self._on_io_click)
        self.io_canvas.bind("<Motion>", self._on_io_hover)

        controls = ttk.LabelFrame(parent, text="Pin Mapping and Manual Override", padding=8)
        controls.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        ttk.Checkbutton(controls, text="Manual IO Override", variable=self.manual_io_var).grid(
            row=0, column=0, padx=4, sticky="w"
        )
        ttk.Label(controls, text="Pin").grid(row=0, column=1, padx=4, sticky="e")
        ttk.Spinbox(controls, from_=1, to=30, textvariable=self.map_pin_var, width=6).grid(row=0, column=2, padx=4)
        ttk.Label(controls, text="Function").grid(row=0, column=3, padx=4, sticky="e")
        ttk.Combobox(
            controls,
            textvariable=self.map_function_var,
            values=[CONNECTOR_A_PINS[f"A{i}"]["signal"] for i in range(1, 31)],
            width=28,
        ).grid(
            row=0, column=4, padx=4
        )
        ttk.Button(controls, text="Apply Mapping", command=self._apply_pin_mapping).grid(row=0, column=5, padx=4)
        ttk.Button(controls, text="Toggle Selected Pin", command=self._toggle_selected_pin).grid(row=0, column=6, padx=4)

        detail = ttk.LabelFrame(parent, text="Connector A Pin Details", padding=8)
        detail.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(detail, textvariable=self.io_info_text, justify="left").grid(row=0, column=0, sticky="w")

    def _build_encoder_panel(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        parent.rowconfigure(2, weight=0)

        wrap = ttk.Frame(parent)
        wrap.grid(row=0, column=0, sticky="nsew")
        wrap.columnconfigure(0, weight=2)
        wrap.columnconfigure(1, weight=1)
        wrap.rowconfigure(0, weight=1)

        self.enc_canvas = tk.Canvas(wrap, bg="#020617", highlightthickness=0)
        self.enc_canvas.grid(row=0, column=0, sticky="nsew")
        self.enc_canvas.bind("<Button-1>", self._on_enc_click)
        self.enc_canvas.bind("<Motion>", self._on_enc_hover)

        controls = ttk.LabelFrame(wrap, text="Connected Pins", padding=8)
        controls.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        for i, name in enumerate(ENCODER_PIN_FUNCTIONS):
            ttk.Checkbutton(controls, text=name, variable=self._encoder_connected[i]).grid(row=i, column=0, sticky="w", pady=2)

        detail = ttk.LabelFrame(parent, text="Connector B Pin Details", padding=8)
        detail.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(detail, textvariable=self.encoder_info_text, justify="left").grid(row=0, column=0, sticky="w")

        self.enc_wave_canvas = tk.Canvas(parent, bg="#0b1220", height=190, highlightthickness=0)
        self.enc_wave_canvas.grid(row=2, column=0, sticky="ew", pady=(6, 0))


    def _on_velocity_change(self, raw: str) -> None:
        self.state.target_velocity_rpm = int(float(raw))

    def _on_position_change(self, raw: str) -> None:
        self.state.set_target_position(int(float(raw)))

    def enable(self) -> None:
        self.state.enabled = True

    def disable(self) -> None:
        self.state.enabled = False

    def alarm_on(self) -> None:
        self.state.error_code = max(1, int(self.alarm_code_var.get()))

    def alarm_off(self) -> None:
        self.state.clear_fault()

    def inject_fault(self) -> None:
        if self.state.error_code:
            self.state.clear_fault()
        else:
            self.alarm_on()

    def clear_fault(self) -> None:
        self.state.clear_fault()

    def _apply_pin_mapping(self) -> None:
        pin = max(1, min(30, int(self.map_pin_var.get())))
        self._io_mapping[pin - 1] = self.map_function_var.get().strip() or CONNECTOR_A_PINS[f"A{pin}"]["signal"]
        self.io_info_text.set(f"A{pin} display label set to {self._io_mapping[pin - 1]}")

    def _toggle_selected_pin(self) -> None:
        idx = int(self._selected_io_pin[1:]) - 1
        self._io_manual_values[idx] = not self._io_manual_values[idx]
        level = "HIGH" if self._io_manual_values[idx] else "LOW"
        self.io_info_text.set(f"Manual override {self._selected_io_pin} -> {level}")

    def _start_bridge(self) -> None:
        if self._uart_thread is not None and self._uart_thread.is_alive():
            self.connection_text.set("UART bridge already running")
            return
        self._uart_stop.clear()
        mode = self.bridge_mode_var.get().strip().upper()
        bridge_port = self.port_var.get().strip()
        baud = int(self.baud_var.get())
        node = int(self.node_var.get())
        real_port = self.real_port_var.get().strip()
        push_mode = self.push_marker_mode_var.get().strip().lower() or "auto"
        push_telemetry = bool(self.push_telemetry_var.get())
        push_interval_ms = max(1, int(self.push_interval_ms_var.get()))
        push_when_idle_ms = max(0, int(self.push_idle_ms_var.get()))
        push_schema_lock_ms = max(0, int(self.push_schema_lock_ms_var.get()))
        if mode != "REAL":
            self.windcon_marker_mode_text.set(f"marker mode={push_mode}")

        def _worker() -> None:
            try:
                if mode == "REAL":
                    if not real_port:
                        raise RuntimeError("Real controller port is required in REAL mode")
                    self._run_real_bridge(bridge_port, real_port, baud)
                else:
                    emulator_server.run(
                        port=bridge_port,
                        baud=baud,
                        node_id=node,
                        state=self.state,
                        step_state=False,
                        stop_predicate=self._uart_stop.is_set,
                        trace_frames=True,
                        push_telemetry=push_telemetry,
                        push_interval_ms=push_interval_ms,
                        push_marker_mode=push_mode,
                        push_when_idle_ms=push_when_idle_ms,
                        push_schema_lock_ms=push_schema_lock_ms,
                        frame_event_cb=self._on_emulator_frame_event,
                    )
            except Exception as exc:
                message = f"Bridge error: {exc}"
                self.root.after(0, lambda m=message: self.connection_text.set(m))

        self._uart_thread = threading.Thread(target=_worker, daemon=True)
        self._uart_thread.start()
        if mode == "REAL":
            self.connection_text.set(f"REAL bridge {bridge_port} <-> {real_port} @ {baud}")
        else:
            self.connection_text.set(
                f"SIM bridge on {bridge_port} @ {baud} node={node} "
                f"push={'ON' if push_telemetry else 'OFF'}"
            )

    def _connect_real_controller(self) -> None:
        self.bridge_mode_var.set("REAL")
        self._stop_bridge()
        self._start_bridge()

    def _run_real_bridge(self, bridge_port: str, real_port: str, baud: int) -> None:
        import serial

        left = serial.serial_for_url(bridge_port, baudrate=baud, timeout=0.01)
        right = serial.serial_for_url(real_port, baudrate=baud, timeout=0.01)
        try:
            while not self._uart_stop.is_set():
                chunk_left = left.read(512)
                if chunk_left:
                    right.write(chunk_left)

                chunk_right = right.read(512)
                if chunk_right:
                    left.write(chunk_right)

                time.sleep(0.001)
        finally:
            left.close()
            right.close()

    def _stop_bridge(self) -> None:
        self._uart_stop.set()
        self.connection_text.set("UART bridge stopping")

    def _toggle_test_scenario(self) -> None:
        self._scenario_active = not self._scenario_active
        if self._scenario_active:
            self._scenario_elapsed_s = 0.0
            self.scenario_text.set("Scenario: ON (dynamic RS485/CAN map test)")
        else:
            self.scenario_text.set("Scenario: OFF")

    @staticmethod
    def _parse_int_text(raw: str) -> int:
        text = raw.strip().replace("_", "")
        if not text:
            raise ValueError("empty value")
        if text.lower().startswith(("0x", "+0x", "-0x")):
            return int(text, 0)
        if any(ch in "abcdefABCDEF" for ch in text):
            return int(text, 16)
        return int(text, 10)

    def _controller_client(self) -> ControllerClient:
        return ControllerClient(self.real_port_var.get().strip(), int(self.baud_var.get()), int(self.node_var.get()))

    def _run_controller_task(self, title: str, worker: Callable[[], tuple[str, str]]) -> None:
        self.controller_action_text.set(f"{title}...")

        def _background() -> None:
            try:
                summary, detail = worker()
            except (ControllerClientError, ValueError, OSError, RuntimeError) as exc:
                self.root.after(0, lambda e=exc: self.controller_action_text.set(f"{title} failed: {e}"))
                return

            self.root.after(0, lambda s=summary: self.controller_action_text.set(s))
            self.root.after(0, lambda d=detail: self.controller_result_text.set(d))

        threading.Thread(target=_background, daemon=True).start()

    def _apply_controller_preset(self) -> None:
        preset = self.controller_preset_var.get().strip().lower()
        presets: dict[str, tuple[int, int]] = {
            "enable drive": (0x1008, 0x0001),
            "disable drive": (0x1008, 0x0000),
            "mode speed": (0x1007, 0x0001),
            "mode torque": (0x1007, 0x0003),
            "mode position": (0x1007, 0x0009),
            "speed +500": (0x100B, 500),
            "speed +1000": (0x100B, 1000),
            "speed -500": (0x100B, -500),
            "speed -1000": (0x100B, -1000),
            "clear fault": (0x101D, 0x0000),
        }
        if preset not in presets:
            raise ValueError(f"Unknown preset: {self.controller_preset_var.get()}")
        register, value = presets[preset]
        self.controller_register_var.set(f"0x{register:04X}")
        self.controller_value_var.set(str(value) if value < 0 else f"0x{value & 0xFFFF:04X}")
        self._write_controller_register()

    def _write_controller_register(self) -> None:
        register = self._parse_int_text(self.controller_register_var.get()) & 0xFFFF
        value = self._parse_int_text(self.controller_value_var.get())

        def _worker() -> tuple[str, str]:
            client = self._controller_client()
            tx = client.write_single(register, value)
            summary = f"Wrote 0x{register:04X} = 0x{value & 0xFFFF:04X}"
            detail = f"TX {tx.request_frame.strip().decode('ascii', errors='replace')} | RX {tx.response_frame.strip().decode('ascii', errors='replace')}"
            return summary, detail

        self._run_controller_task("Writing register", _worker)

    def _read_controller_register(self) -> None:
        register = self._parse_int_text(self.controller_register_var.get()) & 0xFFFF
        count = max(1, min(16, int(self.controller_read_count_var.get())))

        def _worker() -> tuple[str, str]:
            client = self._controller_client()
            tx = client.read_holding(register, count)
            words = tx.words_u16 or []
            words_text = ", ".join(f"0x{word:04X}" for word in words) if words else "<no data>"
            summary = f"Read 0x{register:04X}+{count}"
            detail = f"TX {tx.request_frame.strip().decode('ascii', errors='replace')} | RX {tx.response_frame.strip().decode('ascii', errors='replace')} | Values: {words_text}"
            return summary, detail

        self._run_controller_task("Reading register", _worker)

    def _apply_test_scenario(self, dt: float) -> None:
        # 30-second loop exercising telemetry, enable states, direction,
        # and fault transitions as WINDCON pages poll live registers.
        self._scenario_elapsed_s = (self._scenario_elapsed_s + dt) % 30.0
        t = self._scenario_elapsed_s

        self.mode_var.set("SPEED")
        self.eco_var.set(False)

        if t < 6.0:
            self.state.enabled = True
            self.gear_var.set("FORWARD")
            self.brake_var.set(False)
            self.throttle_var.set(40)
            self.target_velocity.set(600)
            self.state.error_code = 0
        elif t < 12.0:
            self.state.enabled = True
            self.gear_var.set("FORWARD")
            self.brake_var.set(False)
            self.throttle_var.set(85)
            self.target_velocity.set(1800)
            self.state.error_code = 0
        elif t < 16.0:
            self.state.enabled = True
            self.gear_var.set("FORWARD")
            self.brake_var.set(True)
            self.throttle_var.set(15)
            self.target_velocity.set(1200)
            self.state.error_code = 0
        elif t < 22.0:
            self.state.enabled = True
            self.gear_var.set("REVERSE")
            self.brake_var.set(False)
            self.throttle_var.set(55)
            self.target_velocity.set(900)
            self.state.error_code = 0
        elif t < 26.0:
            self.state.enabled = True
            self.gear_var.set("FORWARD")
            self.brake_var.set(False)
            self.throttle_var.set(35)
            self.target_velocity.set(700)
            self.state.error_code = max(1, int(self.alarm_code_var.get()))
        else:
            self.state.enabled = False
            self.gear_var.set("FORWARD")
            self.brake_var.set(False)
            self.throttle_var.set(0)
            self.target_velocity.set(0)
            self.state.error_code = 0

        # Keep scale values and state target synchronized.
        self.state.target_velocity_rpm = self.target_velocity.get()

    def _start_log(self) -> None:
        if self._log_active:
            self.log_text.set("Data log: already active")
            return

        log_dir = Path(__file__).resolve().parents[3] / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._log_path = log_dir / f"controller_log_{stamp}.csv"
        self._log_file = self._log_path.open("w", newline="", encoding="utf-8")
        self._log_writer = csv.writer(self._log_file)
        self._log_writer.writerow(
            [
                "timestamp_iso",
                "epoch_s",
                "bridge_mode",
                "bridge_port",
                "real_port",
                "enabled",
                "mode",
                "gear",
                "eco_mode",
                "brake",
                "throttle_percent",
                "target_velocity_rpm",
                "velocity_actual_rpm",
                "target_position",
                "position_actual",
                "bus_voltage_v",
                "motor_temp_c",
                "driver_temp_c",
                "error_code",
            ]
        )
        self._log_file.flush()
        self._last_log_at = 0.0
        self._log_active = True
        self.log_text.set(f"Data log: ON ({self._log_path.name})")

    def _stop_log(self) -> None:
        self._log_active = False
        if self._log_file is not None:
            self._log_file.close()
        self._log_file = None
        self._log_writer = None
        if self._log_path is not None:
            self.log_text.set(f"Data log: saved {self._log_path.name}")
        else:
            self.log_text.set("Data log: OFF")

    def _write_log_row(self, snapshot: dict[str, object]) -> None:
        if not self._log_active or self._log_writer is None or self._log_file is None:
            return
        now_wall = time.time()
        now_iso = datetime.fromtimestamp(now_wall).isoformat(timespec="milliseconds")
        self._log_writer.writerow(
            [
                now_iso,
                f"{now_wall:.3f}",
                self.bridge_mode_var.get().strip().upper(),
                self.port_var.get().strip(),
                self.real_port_var.get().strip(),
                int(bool(snapshot["enabled"])),
                snapshot["mode"],
                snapshot["gear"],
                int(bool(snapshot["eco_mode"])),
                int(bool(snapshot["brake"])),
                int(snapshot["throttle_percent"]),
                int(snapshot["target_velocity_rpm"]),
                int(snapshot["velocity_actual_rpm"]),
                int(snapshot["target_position"]),
                int(snapshot["position_actual"]),
                float(snapshot["bus_voltage_tenth_v"]) / 10.0,
                int(snapshot["motor_temp_c"]),
                int(snapshot["driver_temp_c"]),
                int(snapshot["error_code"]),
            ]
        )
        self._log_file.flush()

    def _format_a_pin_details(self, pin: str) -> str:
        meta = CONNECTOR_A_PINS[pin]
        logic = meta.get("logic", "")
        logic_text = f"\nLogic: Active {logic}" if logic else ""
        return (
            f"{pin} - {meta['signal']}\n"
            f"Direction: {meta['direction']}\n"
            f"Notes: {meta['notes']}"
            f"{logic_text}"
        )

    def _set_io_info_from_pin(self, pin: str) -> None:
        self.io_info_text.set(self._format_a_pin_details(pin))

    def _draw_a_legend(self, y: int) -> None:
        entries = [
            ("can", "CAN bus"),
            ("rs485", "RS485"),
            ("commspeed", "Communication / Speed"),
            ("active_low", "Control inputs Active LOW"),
            ("brake", "Brake inputs"),
            ("power", "Power / Key switch"),
            ("ground", "Ground"),
            ("analog", "Analog / Throttle"),
            ("output", "Output signals"),
        ]
        self.io_canvas.create_text(28, y - 18, text="Legend", fill="#e2e8f0", anchor="w", font=("Segoe UI", 10, "bold"))
        x = 28
        for group, label in entries:
            color = PIN_COLORS[group]
            self.io_canvas.create_rectangle(x, y, x + 12, y + 12, fill=color, outline="#cbd5e1")
            self.io_canvas.create_text(x + 18, y + 6, text=label, fill="#cbd5e1", anchor="w", font=("Segoe UI", 8))
            x += 152
            if x > 640:
                x = 28
                y += 18

    def _draw_io(self, io_pins: list[bool]) -> None:
        self.io_canvas.delete("all")
        draw_pins = list(io_pins)
        if self.manual_io_var.get():
            for idx, val in enumerate(self._io_manual_values):
                draw_pins[idx] = bool(val)
        w, h = 840, 520
        ox, oy = 12, 12
        self.io_canvas.create_rectangle(ox, oy, ox + w, oy + h, fill="#0b1220", outline="#334155", width=2)
        self.io_canvas.create_text(ox + w / 2, oy + 26, text="Connector A - 30-Pin IO", fill="#e2e8f0", font=("Segoe UI", 13, "bold"))

        # Orientation notch indicates the top side of the physical housing.
        notch_x = ox + 28
        self.io_canvas.create_polygon(notch_x, oy + 44, notch_x + 18, oy + 44, notch_x + 9, oy + 30, fill="#fbbf24", outline="#f59e0b")
        self.io_canvas.create_text(notch_x + 26, oy + 36, text="Orientation Notch (TOP)", fill="#fbbf24", anchor="w", font=("Segoe UI", 8, "bold"))

        body_x0, body_y0 = ox + 22, oy + 64
        body_x1, body_y1 = ox + w - 22, oy + 372
        self.io_canvas.create_rectangle(body_x0, body_y0, body_x1, body_y1, fill="#111827", outline="#64748b", width=2)

        pin_w = 74
        pin_h = 76
        gap_x = 6
        row_top = [body_y0 + 14, body_y0 + 114, body_y0 + 214]
        start_x = body_x0 + 10
        self._io_hitboxes = []

        for row_idx, row in enumerate(CONNECTOR_A_ROWS):
            self.io_canvas.create_text(body_x0 - 8, row_top[row_idx] + pin_h / 2, text=f"Row {row_idx + 1}", fill="#93c5fd", anchor="e", font=("Segoe UI", 9, "bold"))
            for col_idx, pin in enumerate(row):
                meta = CONNECTOR_A_PINS[pin]
                color = PIN_COLORS[meta["group"]]
                pin_num = int(pin[1:])
                label = self._io_mapping[pin_num - 1]
                active = bool(draw_pins[pin_num - 1])
                fill_color = color if active else _dim_hex(color, 0.45)
                x0 = start_x + col_idx * (pin_w + gap_x)
                y0 = row_top[row_idx]
                x1 = x0 + pin_w
                y1 = y0 + pin_h

                outline = "#38bdf8" if pin == self._selected_io_pin else "#1f2937"
                self.io_canvas.create_rectangle(x0, y0, x1, y1, fill=fill_color, outline=outline, width=2)
                self.io_canvas.create_text(x0 + 6, y0 + 10, text=pin, fill="#0b1220", anchor="w", font=("Segoe UI", 8, "bold"))
                self.io_canvas.create_text(x0 + pin_w / 2, y0 + 28, text=label, fill="#0b1220", width=pin_w - 8, font=("Segoe UI", 7, "bold"))
                self.io_canvas.create_text(x0 + pin_w / 2, y0 + 56, text=meta["direction"], fill="#111827", width=pin_w - 10, font=("Segoe UI", 6))
                led = "#22c55e" if active else "#334155"
                self.io_canvas.create_oval(x1 - 14, y1 - 14, x1 - 4, y1 - 4, fill=led, outline="#cbd5e1")
                self.io_canvas.create_text(x1 - 20, y1 - 10, text=("H" if active else "L"), fill="#e2e8f0", font=("Segoe UI", 6, "bold"))

                if meta.get("logic") == "HIGH":
                    self.io_canvas.create_rectangle(x0 + 2, y1 - 16, x0 + 30, y1 - 4, fill="#ef4444", outline="#7f1d1d")
                    self.io_canvas.create_text(x0 + 16, y1 - 10, text="HIGH", fill="#ffffff", font=("Segoe UI", 6, "bold"))
                elif meta.get("logic") == "LOW":
                    self.io_canvas.create_rectangle(x0 + 2, y1 - 16, x0 + 28, y1 - 4, fill="#7c3aed", outline="#4c1d95")
                    self.io_canvas.create_text(x0 + 15, y1 - 10, text="LOW", fill="#ffffff", font=("Segoe UI", 6, "bold"))

                self._io_hitboxes.append((x0, y0, x1, y1, pin))

        self._draw_a_legend(body_y1 + 22)

    def _pin_from_io_event(self, event: tk.Event) -> str | None:
        for x0, y0, x1, y1, pin in self._io_hitboxes:
            if x0 <= event.x <= x1 and y0 <= event.y <= y1:
                return pin
        return None

    def _on_io_hover(self, event: tk.Event) -> None:
        pin = self._pin_from_io_event(event)
        if pin is not None:
            self._set_io_info_from_pin(pin)

    def _on_io_click(self, event: tk.Event) -> None:
        pin = self._pin_from_io_event(event)
        if pin is not None:
            self._selected_io_pin = pin
            self.map_pin_var.set(int(pin[1:]))
            self.map_function_var.set(self._io_mapping[int(pin[1:]) - 1])
            self._set_io_info_from_pin(pin)

    def _format_b_pin_details(self, pin: str) -> str:
        meta = CONNECTOR_B_PINS[pin]
        return f"{pin} - {meta['signal']}\nNotes: {meta['notes']}"

    def _set_enc_info_from_pin(self, pin: str) -> None:
        self.encoder_info_text.set(self._format_b_pin_details(pin))

    def _draw_b_legend(self, y: int) -> None:
        entries = [("ref", "REF pair"), ("sin", "SIN pair"), ("cos", "COS pair"), ("temp", "TEMP pair")]
        x = 26
        self.enc_canvas.create_text(x, y - 18, text="Legend", fill="#e2e8f0", anchor="w", font=("Segoe UI", 10, "bold"))
        for group, label in entries:
            self.enc_canvas.create_rectangle(x, y, x + 14, y + 14, fill=PIN_COLORS[group], outline="#cbd5e1")
            self.enc_canvas.create_text(x + 20, y + 7, text=label, fill="#cbd5e1", anchor="w", font=("Segoe UI", 8))
            x += 160

    def _draw_encoder(self, encoder_pins: list[bool]) -> None:
        self.enc_canvas.delete("all")
        w, h = 760, 360
        ox, oy = 14, 14
        self.enc_canvas.create_rectangle(ox, oy, ox + w, oy + h, fill="#0f172a", outline="#334155", width=2)
        self.enc_canvas.create_text(ox + w / 2, oy + 22, text="Connector B - 8-Pin Encoder", fill="#e2e8f0", font=("Segoe UI", 12, "bold"))

        notch_x = ox + 26
        self.enc_canvas.create_polygon(notch_x, oy + 44, notch_x + 16, oy + 44, notch_x + 8, oy + 30, fill="#fbbf24", outline="#f59e0b")
        self.enc_canvas.create_text(notch_x + 22, oy + 36, text="Orientation Notch (TOP)", fill="#fbbf24", anchor="w", font=("Segoe UI", 8, "bold"))

        body_x0, body_y0 = ox + 180, oy + 66
        body_x1, body_y1 = ox + 560, oy + 286
        self.enc_canvas.create_rectangle(body_x0, body_y0, body_x1, body_y1, fill="#111827", outline="#64748b", width=2)
        self._enc_hitboxes = []

        pin_w = 150
        pin_h = 42
        gap_x = 26
        gap_y = 10
        start_x = body_x0 + 26
        start_y = body_y0 + 14

        for row_idx, row in enumerate(CONNECTOR_B_LAYOUT):
            for col_idx, pin in enumerate(row):
                meta = CONNECTOR_B_PINS[pin]
                group = meta["group"]
                color = PIN_COLORS[group]
                pin_num = int(pin[1:])
                active = bool(encoder_pins[pin_num - 1]) and self._encoder_connected[pin_num - 1].get()
                x0 = start_x + col_idx * (pin_w + gap_x)
                y0 = start_y + row_idx * (pin_h + gap_y)
                x1 = x0 + pin_w
                y1 = y0 + pin_h
                outline = "#38bdf8" if pin == self._selected_enc_pin else "#1f2937"

                self.enc_canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline=outline, width=2)
                self.enc_canvas.create_text(x0 + 8, y0 + 10, text=pin, anchor="w", fill="#0b1220", font=("Segoe UI", 8, "bold"))
                self.enc_canvas.create_text(x0 + pin_w / 2, y0 + 24, text=meta["signal"], fill="#0b1220", font=("Segoe UI", 8, "bold"))
                led = "#22c55e" if active else "#334155"
                self.enc_canvas.create_oval(x1 - 16, y0 + 4, x1 - 6, y0 + 14, fill=led, outline="#cbd5e1")
                self._enc_hitboxes.append((x0, y0, x1, y1, pin))

        self._draw_b_legend(body_y1 + 18)

        lines: list[str] = []
        for idx, name in enumerate(ENCODER_PIN_FUNCTIONS):
            connected = self._encoder_connected[idx].get()
            active = bool(encoder_pins[idx]) and connected
            state_txt = "ON" if active else ("OFF" if connected else "NC")
            lines.append(f"B{idx + 1}: {CONNECTOR_B_PINS[f'B{idx + 1}']['signal']} -> {state_txt}")
            self._encoder_wave_history[idx].append(1 if active else 0)
            if len(self._encoder_wave_history[idx]) > 260:
                self._encoder_wave_history[idx] = self._encoder_wave_history[idx][-260:]

        self.encoder_info_text.set(" | ".join(lines[:4]) + "\n" + " | ".join(lines[4:]))
        self._draw_encoder_waves()

    def _pin_from_enc_event(self, event: tk.Event) -> str | None:
        for x0, y0, x1, y1, pin in self._enc_hitboxes:
            if x0 <= event.x <= x1 and y0 <= event.y <= y1:
                return pin
        return None

    def _on_enc_hover(self, event: tk.Event) -> None:
        pin = self._pin_from_enc_event(event)
        if pin is not None:
            self._set_enc_info_from_pin(pin)

    def _on_enc_click(self, event: tk.Event) -> None:
        pin = self._pin_from_enc_event(event)
        if pin is not None:
            self._selected_enc_pin = pin
            self._set_enc_info_from_pin(pin)

    def _draw_encoder_waves(self) -> None:
        c = self.enc_wave_canvas
        c.delete("all")
        width = max(700, c.winfo_width())
        c.create_rectangle(0, 0, width, 190, fill="#0b1220", outline="")
        row_h = 22
        x0 = 70
        x1 = width - 10
        sample_count = max(1, x1 - x0)
        for idx, _name in enumerate(ENCODER_PIN_FUNCTIONS):
            pin = f"B{idx + 1}"
            name = CONNECTOR_B_PINS[pin]["signal"]
            y_mid = 10 + idx * row_h
            y_hi = y_mid - 6
            y_lo = y_mid + 6
            c.create_text(6, y_mid, anchor="w", text=name, fill="#93c5fd", font=("Segoe UI", 7, "bold"))
            c.create_line(x0, y_mid, x1, y_mid, fill="#1f2937")
            hist = self._encoder_wave_history[idx]
            if not hist:
                continue
            if len(hist) > sample_count:
                hist = hist[-sample_count:]
            points: list[float] = []
            x = x1 - len(hist)
            prev = hist[0]
            points.extend([x, y_hi if prev else y_lo])
            for val in hist[1:]:
                points.extend([x + 1, y_hi if prev else y_lo])
                points.extend([x + 1, y_hi if val else y_lo])
                x += 1
                prev = val
            points.extend([x + 1, y_hi if prev else y_lo])
            c.create_line(points, fill="#f59e0b", width=1)

    def _draw_animation(self, snapshot: dict[str, object]) -> None:
        angle = float(snapshot["rotor_angle_deg"])
        speed = int(snapshot["velocity_actual_rpm"])
        self._anim_phase = (self._anim_phase + 0.08 + min(abs(speed) / 12000.0, 0.25)) % (2.0 * math.pi)
        rad = angle * math.pi / 180.0
        x2 = 560 + 72 * math.cos(rad)
        y2 = 190 - 72 * math.sin(rad)
        self.anim_canvas.coords("rotor_arm", 560, 190, x2, y2)
        self.anim_canvas.coords(
            "rotor_arm_2",
            560,
            190,
            560 + 60 * math.cos(rad + 2.09),
            190 - 60 * math.sin(rad + 2.09),
        )
        self.anim_canvas.coords(
            "rotor_arm_3",
            560,
            190,
            560 + 60 * math.cos(rad - 2.09),
            190 - 60 * math.sin(rad - 2.09),
        )
        pulse_on = bool(snapshot["io_pins"][29])
        self.anim_canvas.itemconfig("pulse", fill="#22c55e" if pulse_on else "#334155")
        motor_color = "#ef4444" if bool(snapshot["error_code"]) else ("#22c55e" if bool(snapshot["enabled"]) else "#64748b")
        self.anim_canvas.itemconfig("motor_ring", outline=motor_color)
        ring_glow = 2 + int(min(abs(speed) / 600, 4))
        self.anim_canvas.itemconfig("motor_ring", width=ring_glow)

        beacon_on = bool(snapshot["error_code"]) and (math.sin(self._anim_phase * 6.0) > 0)
        self.anim_canvas.itemconfig("alarm_beacon", fill="#ef4444" if beacon_on else "#2b3442")
        if bool(snapshot["brake"]):
            self.anim_canvas.itemconfig("brake_tag", text="BRAKE ACTIVE", fill="#f87171")
        else:
            self.anim_canvas.itemconfig("brake_tag", text="BRAKE RELEASED", fill="#22c55e")

        self.anim_canvas.delete("speed_tag")
        self.anim_canvas.create_text(
            550,
            275,
            text=f"{speed} rpm  |  mode={snapshot['mode']}  |  throttle={snapshot['throttle_percent']}%  |  alarm={snapshot['error_code']}",
            fill="#e2e8f0",
            font=("Segoe UI", 10, "bold"),
            tags="speed_tag",
        )

    def _schedule_tick(self) -> None:
        now = time.perf_counter()
        dt = now - self._last_tick
        self._last_tick = now

        if self._scenario_active:
            self._apply_test_scenario(dt)

        self.state.set_mode(self.mode_var.get())
        self.state.set_gear(self.gear_var.get())
        self.state.set_eco_mode(self.eco_var.get())
        self.state.set_brake(self.brake_var.get())
        self.state.set_throttle(self.throttle_var.get())
        self.state.force_feedback_to_target = self.force_feedback_var.get()
        self.state.step(dt)

        snapshot = self.state.snapshot()
        self.enabled_text.set("ENABLED" if snapshot["enabled"] else "DISABLED")
        self.speed_text.set(f"{snapshot['velocity_actual_rpm']} rpm")
        self.position_text.set(f"actual={snapshot['position_actual']} / target={snapshot['target_position']}")
        self.temp_text.set(f"M:{snapshot['motor_temp_c']} C / D:{snapshot['driver_temp_c']} C")
        a17_state = snapshot["io_pins"][16]  # A17 is index 16 (0-based)
        a24_state = snapshot["io_pins"][23]  # A24 is index 23 (0-based)
        a17_label = "H" if a17_state else "L"
        a24_label = "H" if a24_state else "L"
        self.brake_probe_text.set(f"A17={a17_label}(LowBrake)  A24={a24_label}(HighBrake)")
        self.fault_text.set(f"FAULT ({snapshot['error_code']})" if snapshot["error_code"] else "OK")

        reg_1008 = self.state.read_register(0x1008)
        reg_100b = self.state.read_register(0x100B)
        reg_100d = self.state.read_register(0x100D)
        reg_1010 = self.state.read_register(0x1010)
        reg_1015 = self.state.read_register(0x1015)
        reg_101d = self.state.read_register(0x101D)
        reg_1018 = self.state.read_register(0x1018)
        reg_1019 = self.state.read_register(0x1019)
        reg_101a = self.state.read_register(0x101A)
        reg_101b = self.state.read_register(0x101B)

        self.reg_1008_text.set(str(reg_1008))
        self.reg_100b_text.set(str(reg_100b))
        self.reg_100d_text.set(f"{reg_100d / 10.0:.1f} V ({reg_100d})")
        self.reg_1010_text.set(f"0x{reg_1010:04X}")
        self.reg_1015_text.set(f"{reg_1015} C")
        self.reg_101d_text.set(str(reg_101d))
        self.reg_1018_1019_text.set(f"{self._f32_from_words(reg_1018, reg_1019):.2f}")
        self.reg_101a_101b_text.set(f"{self._f32_from_words(reg_101a, reg_101b):.2f}")

        self._draw_animation(snapshot)
        self._draw_io(snapshot["io_pins"])

        masked_encoder = []
        for idx, val in enumerate(snapshot["encoder_pins"]):
            masked_encoder.append(bool(val) and self._encoder_connected[idx].get())
        self._draw_encoder(masked_encoder)

        if self._log_active and (now - self._last_log_at) >= self._log_period_s:
            self._write_log_row(snapshot)
            self._last_log_at = now

        self.root.after(50, self._schedule_tick)

    def on_close(self) -> None:
        self._stop_log()
        self._stop_bridge()
        self.root.after(120, self.root.destroy)



def main() -> None:
    root = tk.Tk()
    app = SimulatorApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        app.on_close()


if __name__ == "__main__":
    main()
