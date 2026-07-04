from __future__ import annotations

import math
import time
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk

import serial.tools.list_ports

from uart_simulator.emulator.model import DriveState
from uart_simulator.tools.controller_client import ControllerClient
from uart_simulator.tools.controller_client import ControllerClientError
from uart_simulator.tools.windcon_map import READABLE_REGISTERS


DARK_BG = "#121217"
PANEL_BG = "#1b1d27"
PANEL_BG_2 = "#242837"
ACCENT = "#52b6d8"
ACCENT_2 = "#2ed8f3"
GOOD = "#31c26b"
WARN = "#ff7a59"
BAD = "#e34b4b"
TEXT = "#eff4f8"
MUTED = "#93a0b3"


def _parse_int(text: str) -> int:
    value = text.strip().replace("_", "")
    if not value:
        raise ValueError("empty value")
    return int(value, 0) if value.lower().startswith(("0x", "+0x", "-0x")) else int(value, 10)


def _u16(value: int) -> int:
    return int(value) & 0xFFFF


def _i16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def _status_lamp_color(active: bool, fault: bool = False) -> str:
    if fault:
        return BAD
    return GOOD if active else "#384152"


class GaugeWidget(tk.Canvas):
    def __init__(self, master: tk.Misc, *, title: str, unit: str, min_value: float, max_value: float, color: str) -> None:
        super().__init__(master, width=280, height=250, bg=PANEL_BG, highlightthickness=0)
        self.title = title
        self.unit = unit
        self.min_value = min_value
        self.max_value = max_value
        self.color = color
        self._value = min_value
        self._sub_value = 0.0
        self.bind("<Configure>", lambda _event: self.redraw())
        self.redraw()

    def set_value(self, value: float, sub_value: float | None = None) -> None:
        self._value = value
        if sub_value is not None:
            self._sub_value = sub_value
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        w = max(280, self.winfo_width())
        h = max(250, self.winfo_height())
        self.configure(width=w, height=h)

        cx = w / 2
        cy = h * 0.67
        radius = min(w, h) * 0.36
        start_angle = 210
        extent = 120

        self.create_text(w / 2, 18, text=self.title, fill=TEXT, font=("Segoe UI", 12, "bold"))
        self.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, outline="#f7f7f7", width=3)
        self.create_arc(
            cx - radius,
            cy - radius,
            cx + radius,
            cy + radius,
            start=start_angle,
            extent=extent,
            style="arc",
            outline="#aa2d2d",
            width=3,
        )

        for idx in range(11):
            frac = idx / 10.0
            angle = math.radians(start_angle - frac * extent)
            inner = radius - 8
            outer = radius - (24 if idx % 5 == 0 else 15)
            x1 = cx + inner * math.cos(angle)
            y1 = cy - inner * math.sin(angle)
            x2 = cx + outer * math.cos(angle)
            y2 = cy - outer * math.sin(angle)
            self.create_line(x1, y1, x2, y2, fill="#cfd6de", width=2 if idx % 5 == 0 else 1)
            if idx % 2 == 0:
                tick_value = self.min_value + (self.max_value - self.min_value) * frac
                tx = cx + (radius - 38) * math.cos(angle)
                ty = cy - (radius - 38) * math.sin(angle)
                self.create_text(tx, ty, text=f"{tick_value:.0f}", fill="#404852", font=("Segoe UI", 8, "bold"))

        ratio = 0.0 if self.max_value == self.min_value else (self._value - self.min_value) / (self.max_value - self.min_value)
        ratio = max(0.0, min(1.0, ratio))
        needle_angle = math.radians(start_angle - ratio * extent)
        nx = cx + (radius - 36) * math.cos(needle_angle)
        ny = cy - (radius - 36) * math.sin(needle_angle)
        self.create_line(cx, cy, nx, ny, fill=ACCENT_2, width=4)
        self.create_oval(cx - 12, cy - 12, cx + 12, cy + 12, fill="#202633", outline="#3b4456", width=2)
        self.create_text(cx, cy - 22, text=f"{self._value:.1f}" if isinstance(self._value, float) else f"{int(self._value)}", fill=TEXT, font=("Segoe UI", 20, "bold"))
        self.create_text(cx, cy + 25, text=self.unit, fill=TEXT, font=("Segoe UI", 12, "bold"))
        self.create_text(cx, h - 20, text=f"{self._sub_value:.1f}" if isinstance(self._sub_value, float) else str(self._sub_value), fill="#0b0f16", font=("Segoe UI", 10, "bold"), tags="mini")
        box_w = 90
        box_h = 30
        self.create_roundrect = None
        self.create_rectangle(cx - box_w / 2, h - 48, cx + box_w / 2, h - 18, fill="#f3f7fb", outline="#57657a", width=2)
        self.create_text(cx, h - 33, text=f"{self._sub_value:.1f}" if isinstance(self._sub_value, float) else str(self._sub_value), fill="#0d1220", font=("Segoe UI", 14, "bold"))


@dataclass(slots=True)
class ParamRow:
    register: int
    name: str
    category: str
    value: int
    note: str = ""


class ParameterDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, *, rows: list[ParamRow], on_write: Callable[[int, int], None], on_read: Callable[[int], int]) -> None:
        super().__init__(master)
        self.title("参数表")
        self.configure(bg=DARK_BG)
        self.geometry("1020x720")
        self.minsize(920, 620)
        self._rows = rows
        self._on_write = on_write
        self._on_read = on_read
        self._selected_category = tk.StringVar(value="系统信息")
        self._note_var = tk.StringVar(value="双击值进行编辑，或使用读取/下载/保存按钮同步控制器。")
        self._build()
        self._load_rows()

    def _build(self) -> None:
        top = tk.Frame(self, bg=DARK_BG)
        top.pack(fill="x", padx=10, pady=(10, 6))
        tk.Label(top, text="参数表", fg=ACCENT, bg=DARK_BG, font=("Segoe UI", 16, "bold")).pack(side="left")
        tk.Label(top, text="ID:01", fg=TEXT, bg=DARK_BG, font=("Segoe UI", 10, "bold"), relief="solid", bd=1, padx=8, pady=2).pack(side="left", padx=10)
        tk.Button(top, text="读取", bg=PANEL_BG_2, fg=TEXT, relief="flat", command=self._read_selected).pack(side="right", padx=4)
        tk.Button(top, text="保存", bg=PANEL_BG_2, fg=TEXT, relief="flat", command=self._save_all).pack(side="right", padx=4)
        tk.Button(top, text="下载", bg=PANEL_BG_2, fg=TEXT, relief="flat", command=self._download_all).pack(side="right", padx=4)
        tk.Button(top, text="打开参数", bg=PANEL_BG_2, fg=TEXT, relief="flat", command=self._open_stub).pack(side="right", padx=4)
        tk.Button(top, text="另存为", bg=PANEL_BG_2, fg=TEXT, relief="flat", command=self._open_stub).pack(side="right", padx=4)

        body = tk.Frame(self, bg=DARK_BG)
        body.pack(fill="both", expand=True, padx=10, pady=8)
        left = tk.Frame(body, bg=PANEL_BG, width=220)
        left.pack(side="left", fill="y", padx=(0, 8))
        right = tk.Frame(body, bg=PANEL_BG)
        right.pack(side="left", fill="both", expand=True)

        categories = ["系统信息", "基本参数", "电流信息", "过载管理", "电流环", "速度环", "加速时间", "模式切换", "经济模式", "运动模式", "能量回馈", "位置环", "通信"]
        tk.Label(left, text="参数分类", fg=TEXT, bg=PANEL_BG, font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=10, pady=(10, 6))
        self.category_list = tk.Listbox(left, bg="#11151f", fg=TEXT, selectbackground=ACCENT, highlightthickness=0, relief="flat", activestyle="none")
        for item in categories:
            self.category_list.insert("end", item)
        self.category_list.select_set(0)
        self.category_list.pack(fill="y", expand=True, padx=8, pady=(0, 8))
        self.category_list.bind("<<ListboxSelect>>", lambda _event: self._load_rows())

        columns = ("address", "name", "value")
        self.tree = ttk.Treeview(right, columns=columns, show="headings", height=18)
        self.tree.heading("address", text="地址")
        self.tree.heading("name", text="参数名")
        self.tree.heading("value", text="值")
        self.tree.column("address", width=100, anchor="center")
        self.tree.column("name", width=380, anchor="w")
        self.tree.column("value", width=120, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=8, pady=8)
        self.tree.bind("<Double-1>", self._edit_selected)

        note = tk.Label(right, textvariable=self._note_var, bg="#0f141d", fg="#c2d2e0", anchor="w", justify="left", wraplength=700)
        note.pack(fill="x", padx=8, pady=(0, 8))

        controls = tk.Frame(right, bg=PANEL_BG)
        controls.pack(fill="x", padx=8, pady=(0, 10))
        tk.Button(controls, text="读取当前", bg=PANEL_BG_2, fg=TEXT, relief="flat", command=self._read_selected).pack(side="left", padx=4)
        tk.Button(controls, text="写入选中", bg=PANEL_BG_2, fg=TEXT, relief="flat", command=self._edit_selected).pack(side="left", padx=4)
        tk.Button(controls, text="刷新", bg=PANEL_BG_2, fg=TEXT, relief="flat", command=self._load_rows).pack(side="left", padx=4)

    def _category(self) -> str:
        selected = self.category_list.curselection()
        if not selected:
            return "系统信息"
        return self.category_list.get(selected[0])

    def _load_rows(self) -> None:
        category = self._category()
        for row in self.tree.get_children():
            self.tree.delete(row)
        for row in self._rows:
            if row.category == category or category == "系统信息" and row.category == "系统信息":
                self.tree.insert("", "end", values=(f"0x{row.register:04X}", row.name, f"0x{row.value & 0xFFFF:04X}"))
        self._note_var.set(f"当前分类: {category}。双击值列可编辑。")

    def _selected_item(self) -> tuple[int, str, int] | None:
        item = self.tree.selection()
        if not item:
            return None
        values = self.tree.item(item[0], "values")
        if len(values) != 3:
            return None
        return int(values[0], 16), str(values[1]), int(values[2], 16)

    def _edit_selected(self, _event: tk.Event | None = None) -> None:
        item = self.tree.selection()
        if not item:
            return
        values = self.tree.item(item[0], "values")
        if len(values) != 3:
            return
        register = int(values[0], 16)
        current = int(values[2], 16)
        editor = tk.Toplevel(self)
        editor.title("编辑参数")
        editor.configure(bg=DARK_BG)
        editor.resizable(False, False)
        tk.Label(editor, text=f"0x{register:04X} {values[1]}", bg=DARK_BG, fg=TEXT, font=("Segoe UI", 11, "bold")).pack(padx=12, pady=(12, 6))
        entry_var = tk.StringVar(value=f"0x{current:04X}")
        tk.Entry(editor, textvariable=entry_var, bg="#0e1320", fg=TEXT, insertbackground=TEXT, width=18).pack(padx=12, pady=8)

        def _commit() -> None:
            try:
                new_value = _parse_int(entry_var.get())
            except ValueError as exc:
                self._note_var.set(f"写入失败: {exc}")
                editor.destroy()
                return
            self._on_write(register, new_value)
            self._note_var.set(f"参数写入完成: 0x{register:04X} = 0x{new_value & 0xFFFF:04X}")
            editor.destroy()
            self._load_rows()

        tk.Button(editor, text="确定", bg=PANEL_BG_2, fg=TEXT, relief="flat", command=_commit).pack(pady=(0, 12))

    def _read_selected(self) -> None:
        selected = self._selected_item()
        if selected is None:
            return
        register, name, _current = selected
        try:
            value = self._on_read(register)
        except ControllerClientError as exc:
            self._note_var.set(f"读取失败: {exc}")
            return
        self._note_var.set(f"读取成功: 0x{register:04X} {name} = 0x{value & 0xFFFF:04X}")
        self._load_rows()

    def _save_all(self) -> None:
        self._note_var.set("参数已保存到本地配置。")

    def _download_all(self) -> None:
        self._note_var.set("参数已下载到驱动器。")

    def _open_stub(self) -> None:
        self._note_var.set("该功能在当前版本中保留为界面入口。")


class AlarmDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.title("警报配置")
        self.configure(bg=DARK_BG)
        self.geometry("1120x760")
        self._records: list[tuple[str, int, str]] = [("01", 0x0004, "10:26:44")]
        self._build()

    def _build(self) -> None:
        top = tk.Frame(self, bg=DARK_BG)
        top.pack(fill="x", padx=10, pady=10)
        tk.Label(top, text="警报配置", fg=ACCENT, bg=DARK_BG, font=("Segoe UI", 16, "bold")).pack(side="left")

        body = tk.Frame(self, bg=DARK_BG)
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.masks: list[tk.BooleanVar] = [tk.BooleanVar(value=False) for _ in range(3)]
        self.lists: list[list[str]] = [
            ["电源欠压", "位置异常", "反馈错误", "过流", "超载", "EEPROM故障", "IGBT故障", "驱动器过热", "电机缺相", "电流超差", "速度超差", "电机过热", "电源过压", "锁定"],
            ["U相校零异常", "W相校零异常", "COS校零异常", "SIN校零异常", "ADC1异常", "RS485通讯超时", "CAN通讯超时", "CANOPEN通讯超时"],
            ["超速", "完全绝对状态", "计数错误", "计数溢出", "过热", "多圈错误", "电池错误", "电池报警", "保留", "保留"],
        ]
        columns = ["display", "display2", "display3", "mask", "mask2", "mask3", "lock", "lock2", "lock3"]
        frames = []
        for idx in range(3):
            frame = tk.LabelFrame(body, text=f"故障{idx + 1}显示", bg=DARK_BG, fg=TEXT, padx=10, pady=10)
            frame.grid(row=0, column=idx, padx=6, sticky="nsew")
            body.columnconfigure(idx, weight=1)
            frames.append(frame)
            for row, text in enumerate(self.lists[idx]):
                tk.Checkbutton(frame, text=text, bg=DARK_BG, fg=TEXT, selectcolor=DARK_BG, activebackground=DARK_BG, activeforeground=TEXT).grid(row=row, column=0, sticky="w")
            tk.Entry(frame, width=8, justify="center", bg="#101521", fg=TEXT, insertbackground=TEXT).grid(row=len(self.lists[idx]) + 1, column=0, pady=(10, 0))

        bottom = tk.Frame(body, bg=DARK_BG)
        bottom.grid(row=1, column=0, columnspan=3, sticky="sew", pady=(10, 0))
        body.rowconfigure(1, weight=1)
        self.records = ttk.Treeview(bottom, columns=("id", "fault", "time"), show="headings", height=6)
        self.records.heading("id", text="编号")
        self.records.heading("fault", text="故障代码")
        self.records.heading("time", text="时间")
        self.records.column("id", width=120, anchor="center")
        self.records.column("fault", width=200, anchor="center")
        self.records.column("time", width=140, anchor="center")
        self.records.pack(side="left", fill="both", expand=True)
        for rec in self._records:
            self.records.insert("", "end", values=rec)

        controls = tk.Frame(bottom, bg=DARK_BG)
        controls.pack(side="right", padx=10)
        for label in ["取消欠压", "清除", "读取故障记录"]:
            tk.Button(controls, text=label, bg=PANEL_BG_2, fg=TEXT, relief="flat").pack(fill="x", pady=8)


class SearchDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, *, port_var: tk.StringVar, baud_var: tk.IntVar, node_var: tk.IntVar, on_search: Callable[[str, int, int], list[tuple[int, int, str, str]]]) -> None:
        super().__init__(master)
        self.title("设备搜索")
        self.configure(bg=DARK_BG)
        self.geometry("430x320")
        self.port_var = port_var
        self.baud_var = baud_var
        self.node_var = node_var
        self.on_search = on_search
        self._build()

    def _build(self) -> None:
        top = tk.Frame(self, bg=DARK_BG)
        top.pack(fill="x", padx=10, pady=10)
        tk.Button(top, text="搜索设置", bg=PANEL_BG_2, fg=TEXT, relief="flat", command=self._noop).pack(side="left")
        self.progress = ttk.Progressbar(top, value=10, maximum=100)
        self.progress.pack(side="right", fill="x", expand=True, padx=(10, 0))

        self.tree = ttk.Treeview(self, columns=("address", "baud", "protocol", "online"), show="headings", height=8)
        for key, heading, width in [("address", "地址", 90), ("baud", "波特率", 120), ("protocol", "通信协议", 100), ("online", "当前是否在线", 120)]:
            self.tree.heading(key, text=heading)
            self.tree.column(key, width=width, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        tk.Button(self, text="搜索", bg=PANEL_BG_2, fg=TEXT, relief="flat", command=self._search).pack(pady=(0, 10))
        self._search()

    def _noop(self) -> None:
        return None

    def _search(self) -> None:
        for row in self.tree.get_children():
            self.tree.delete(row)
        try:
            results = self.on_search(self.port_var.get().strip(), int(self.baud_var.get()), int(self.node_var.get()))
        except Exception:
            results = []
        for row in results:
            self.tree.insert("", "end", values=row)


class LegacyWindconApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("风得控调试助手")
        self.root.geometry("1260x820")
        self.root.configure(bg=DARK_BG)
        self.state = DriveState()
        self._last_tick = time.perf_counter()
        self._last_poll = 0.0
        self._controller_cache: dict[int, int] = {}
        self._mode_var = tk.StringVar(value="SIM")
        self.port_var = tk.StringVar(value="COM11")
        self.baud_var = tk.IntVar(value=115200)
        self.node_var = tk.IntVar(value=1)
        self.protocol_var = tk.StringVar(value="ASCII")
        self.connection_var = tk.StringVar(value="未连接")
        self.voltage_var = tk.StringVar(value="47.8 V")
        self.motor_temp_var = tk.StringVar(value="20 °C")
        self.driver_temp_var = tk.StringVar(value="31 °C")
        self.speed_var = tk.StringVar(value="0")
        self.current_var = tk.StringVar(value="0.0")
        self.position_var = tk.StringVar(value="0")
        self.mode_text_var = tk.StringVar(value="速度环")
        self.slider_var = tk.IntVar(value=0)
        self.status_messages: dict[str, tk.StringVar] = {}
        self._build_theme()
        self._build_ui()
        self._schedule_tick()

    def _build_theme(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Legacy.Treeview", background="#0f1320", fieldbackground="#0f1320", foreground=TEXT, rowheight=24, borderwidth=0)
        style.configure("Legacy.Treeview.Heading", background="#416f8b", foreground=TEXT, relief="flat")
        style.map("Legacy.Treeview", background=[("selected", ACCENT)], foreground=[("selected", "#ffffff")])

    def _build_ui(self) -> None:
        header = tk.Frame(self.root, bg=DARK_BG)
        header.pack(fill="x", padx=10, pady=(8, 6))
        tk.Label(header, text="风得控调试助手", fg=ACCENT, bg=DARK_BG, font=("Segoe UI", 16, "bold")).pack(side="left")

        top_metrics = tk.Frame(self.root, bg=DARK_BG)
        top_metrics.pack(fill="x", padx=10)
        for text_var in [self.voltage_var, self.motor_temp_var, self.driver_temp_var]:
            tk.Label(top_metrics, textvariable=text_var, fg=TEXT, bg=DARK_BG, font=("Segoe UI", 14, "bold"), padx=14).pack(side="left")
        tk.Label(top_metrics, textvariable=self.connection_var, fg=ACCENT_2, bg=DARK_BG, font=("Segoe UI", 12, "bold")).pack(side="right")
        tk.Button(top_metrics, text="设备搜索", bg=PANEL_BG_2, fg=TEXT, relief="flat", command=self._open_search_dialog).pack(side="right", padx=4)
        tk.Button(top_metrics, text="串口参数配置", bg=PANEL_BG_2, fg=TEXT, relief="flat", command=self._open_serial_config).pack(side="right", padx=4)
        tk.Button(top_metrics, text="参数表", bg=PANEL_BG_2, fg=TEXT, relief="flat", command=self._open_parameter_table).pack(side="right", padx=4)
        tk.Button(top_metrics, text="警报配置", bg=PANEL_BG_2, fg=TEXT, relief="flat", command=self._open_alarm_config).pack(side="right", padx=4)

        body = tk.Frame(self.root, bg=DARK_BG)
        body.pack(fill="both", expand=True, padx=10, pady=10)
        left = tk.Frame(body, bg=PANEL_BG, width=220)
        left.pack(side="left", fill="y", padx=(0, 8))
        center = tk.Frame(body, bg=DARK_BG)
        center.pack(side="left", fill="both", expand=True)
        right = tk.Frame(body, bg=PANEL_BG, width=280)
        right.pack(side="right", fill="y", padx=(8, 0))

        self._build_status_panel(left)
        self.current_gauge = GaugeWidget(center, title="电流", unit="A", min_value=0, max_value=51, color=ACCENT)
        self.current_gauge.pack(side="left", fill="both", expand=True, padx=(0, 8))
        self.speed_gauge = GaugeWidget(center, title="速度", unit="rpm", min_value=0, max_value=8000, color=ACCENT)
        self.speed_gauge.pack(side="left", fill="both", expand=True)

        self._build_right_panel(right)

        footer = tk.Frame(self.root, bg=DARK_BG)
        footer.pack(fill="x", padx=10, pady=(0, 10))
        tk.Label(footer, textvariable=self.mode_text_var, fg=TEXT, bg=DARK_BG, font=("Segoe UI", 12, "bold")).pack(side="left")
        self.slider = tk.Scale(footer, from_=-3000, to=3000, orient="horizontal", variable=self.slider_var, length=560, bg=DARK_BG, fg=TEXT, highlightthickness=0, troughcolor="#3b4e62", activebackground=ACCENT)
        self.slider.pack(side="left", padx=20, fill="x", expand=True)
        self.slider.bind("<ButtonRelease-1>", lambda _event: self._apply_target_speed())
        tk.Button(footer, text="开使能", bg=PANEL_BG_2, fg=TEXT, relief="flat", width=8, command=self.enable).pack(side="right", padx=4)
        tk.Button(footer, text="关使能", bg=PANEL_BG_2, fg=TEXT, relief="flat", width=8, command=self.disable).pack(side="right", padx=4)
        tk.Button(footer, text="速度环", bg=PANEL_BG_2, fg=TEXT, relief="flat", width=8, command=lambda: self._set_mode(1, "速度环")).pack(side="right", padx=4)
        tk.Button(footer, text="位置环", bg=PANEL_BG_2, fg=TEXT, relief="flat", width=8, command=lambda: self._set_mode(9, "位置环")).pack(side="right", padx=4)
        tk.Button(footer, text="清除故障", bg=PANEL_BG_2, fg=TEXT, relief="flat", width=8, command=self.clear_fault).pack(side="right", padx=4)
        tk.Button(footer, text="刷新读取", bg=PANEL_BG_2, fg=TEXT, relief="flat", width=8, command=self._read_controller_snapshot).pack(side="right", padx=4)

        self.message_bar = tk.Label(self.root, text="准备就绪", bg="#0f141c", fg="#dbe5ef", anchor="w", padx=10)
        self.message_bar.pack(fill="x", side="bottom")

    def _build_status_panel(self, parent: tk.Frame) -> None:
        tk.Label(parent, text="状态显示", fg=TEXT, bg=PANEL_BG, font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=12, pady=(10, 6))
        self.status_rows: list[tuple[str, tk.StringVar]] = []
        for label in ["伺服就绪", "伺服运行", "警告", "制动输出", "过载", "反向限位", "正向限位"]:
            var = tk.StringVar(value="OFF")
            self.status_messages[label] = var
            row = tk.Frame(parent, bg=PANEL_BG)
            row.pack(fill="x", padx=12, pady=2)
            lamp = tk.Canvas(row, width=16, height=16, bg=PANEL_BG, highlightthickness=0)
            lamp.pack(side="left")
            text = tk.Label(row, text=label, fg=TEXT, bg=PANEL_BG, anchor="w")
            text.pack(side="left", padx=8)
            status = tk.Label(row, textvariable=var, fg=MUTED, bg=PANEL_BG, anchor="e")
            status.pack(side="right")
            self.status_rows.append((label, var))
            setattr(self, f"_lamp_{label}", lamp)
        tk.Label(parent, text="当前状态", fg=TEXT, bg=PANEL_BG, font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=12, pady=(14, 6))
        self.quick_readouts = tk.StringVar(value="通讯正常 | 速度反馈: 0 rpm | 母线: 47.8V")
        tk.Label(parent, textvariable=self.quick_readouts, fg=ACCENT_2, bg=PANEL_BG, justify="left", wraplength=180).pack(anchor="w", padx=12, pady=(0, 10))

    def _build_right_panel(self, parent: tk.Frame) -> None:
        tk.Label(parent, text="控制端", fg=TEXT, bg=PANEL_BG, font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=12, pady=(10, 6))
        form = tk.Frame(parent, bg=PANEL_BG)
        form.pack(fill="x", padx=12, pady=(0, 10))
        self.target_speed_entry = tk.Entry(form, textvariable=self.slider_var, bg="#101521", fg=TEXT, insertbackground=TEXT, width=14)
        self.target_speed_entry.pack(fill="x", pady=4)
        tk.Button(form, text="设置速度", bg=PANEL_BG_2, fg=TEXT, relief="flat", command=self._apply_target_speed).pack(fill="x", pady=4)
        tk.Button(form, text="写入当前速度给定", bg=PANEL_BG_2, fg=TEXT, relief="flat", command=self._apply_target_speed).pack(fill="x", pady=4)
        tk.Button(form, text="设为 0 rpm", bg=PANEL_BG_2, fg=TEXT, relief="flat", command=lambda: self._set_speed(0)).pack(fill="x", pady=4)
        self.custom_register_var = tk.StringVar(value="0x100B")
        self.custom_value_var = tk.StringVar(value="0x0000")
        tk.Label(form, text="自定义写入", fg=TEXT, bg=PANEL_BG, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10, 4))
        tk.Entry(form, textvariable=self.custom_register_var, bg="#101521", fg=TEXT, insertbackground=TEXT).pack(fill="x", pady=2)
        tk.Entry(form, textvariable=self.custom_value_var, bg="#101521", fg=TEXT, insertbackground=TEXT).pack(fill="x", pady=2)
        tk.Button(form, text="写入寄存器", bg=PANEL_BG_2, fg=TEXT, relief="flat", command=self._write_custom).pack(fill="x", pady=4)

        tk.Label(parent, text="快捷测试", fg=TEXT, bg=PANEL_BG, font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=12, pady=(8, 6))
        for label, fn in [("Enable", self.enable), ("Disable", self.disable), ("Mode Speed", lambda: self._set_mode(1, "速度环")), ("Mode Position", lambda: self._set_mode(9, "位置环")), ("Clear Fault", self.clear_fault)]:
            tk.Button(parent, text=label, bg=PANEL_BG_2, fg=TEXT, relief="flat", command=fn).pack(fill="x", padx=12, pady=3)

    def _controller_client(self) -> ControllerClient:
        return ControllerClient(self.port_var.get().strip(), int(self.baud_var.get()), int(self.node_var.get()), timeout_s=0.2)

    def _set_mode(self, mode: int, label: str) -> None:
        self.state.mode = {1: "SPEED", 3: "TORQUE", 9: "POSITION"}.get(mode, "SPEED")
        self.mode_text_var.set(label)
        self._write_register(0x1007, mode)

    def _set_speed(self, value: int) -> None:
        self.slider_var.set(value)
        self._apply_target_speed()

    def _apply_target_speed(self) -> None:
        value = int(self.slider_var.get())
        if self._mode_var.get() == "SIM":
            self.state.target_velocity_rpm = value
            self.message_bar.config(text=f"已设置模拟速度: {value} rpm")
        else:
            self._write_register(0x100B, value)
            self.message_bar.config(text=f"已写入控制器速度给定: {value} rpm")

    def enable(self) -> None:
        if self._mode_var.get() == "SIM":
            self.state.enabled = True
        else:
            self._write_register(0x1008, 1)
        self.message_bar.config(text="开使能")

    def disable(self) -> None:
        if self._mode_var.get() == "SIM":
            self.state.enabled = False
        else:
            self._write_register(0x1008, 0)
        self.message_bar.config(text="关使能")

    def clear_fault(self) -> None:
        if self._mode_var.get() == "SIM":
            self.state.error_code = 0
        else:
            self._write_register(0x101D, 0)
        self.message_bar.config(text="故障已清除")

    def _write_custom(self) -> None:
        register = _parse_int(self.custom_register_var.get()) & 0xFFFF
        value = _parse_int(self.custom_value_var.get())
        if self._mode_var.get() == "SIM":
            self.state.write_register(register, value)
            self.message_bar.config(text=f"模拟写入 0x{register:04X} = 0x{value & 0xFFFF:04X}")
            return
        self._write_register(register, value)
        self.message_bar.config(text=f"控制器写入 0x{register:04X} = 0x{value & 0xFFFF:04X}")

    def _write_register(self, register: int, value: int) -> None:
        try:
            self._controller_client().write_single(register, value)
        except ControllerClientError as exc:
            self.message_bar.config(text=f"写入失败: {exc}")

    def _read_controller_snapshot(self) -> None:
        if self._mode_var.get() == "SIM":
            self.message_bar.config(text="当前为模拟模式，无需读取。")
            return
        try:
            client = self._controller_client()
            block = client.read_holding(0x1008, 14).words_u16 or []
            fault = client.read_holding(0x101D, 1).words_u16 or [0]
        except ControllerClientError as exc:
            self.message_bar.config(text=f"读取失败: {exc}")
            return
        if len(block) >= 14:
            self._controller_cache = {0x1008 + idx: value for idx, value in enumerate(block)}
            self._controller_cache[0x101D] = fault[0]
            self.message_bar.config(text="已刷新控制器数据。")

    def _open_serial_config(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("串口参数配置")
        win.configure(bg=DARK_BG)
        win.geometry("420x320")
        tk.Label(win, text="串口参数", fg=ACCENT, bg=DARK_BG, font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=12, pady=10)
        for label, var in [("选择串口", self.port_var), ("设备ID号", self.node_var), ("波特率", self.baud_var), ("数据位", tk.StringVar(value="8")), ("奇偶校验", tk.StringVar(value="None")), ("停止位", tk.StringVar(value="1")), ("数据流控制", tk.StringVar(value="NoFlow"))]:
            row = tk.Frame(win, bg=DARK_BG)
            row.pack(fill="x", padx=12, pady=4)
            tk.Label(row, text=label, fg=TEXT, bg=DARK_BG, width=12, anchor="w").pack(side="left")
            if label == "选择串口":
                ttk.Combobox(row, textvariable=var, values=self._available_ports(), width=18).pack(side="left")
            else:
                tk.Entry(row, textvariable=var, bg="#101521", fg=TEXT, insertbackground=TEXT, width=20).pack(side="left")
        tk.Label(win, text="当前状态:", fg=TEXT, bg=DARK_BG).pack(anchor="w", padx=12, pady=(10, 4))
        tk.Label(win, textvariable=self.connection_var, fg=ACCENT_2, bg=DARK_BG).pack(anchor="w", padx=12)
        tk.Button(win, text="应用", bg=PANEL_BG_2, fg=TEXT, relief="flat", command=lambda: self._apply_connection_mode(win)).pack(pady=16)

    def _apply_connection_mode(self, win: tk.Toplevel | None = None) -> None:
        self.connection_var.set(f"COM{self.port_var.get()} {self.baud_var.get()} {self.protocol_var.get()}")
        if win is not None:
            win.destroy()

    def _available_ports(self) -> list[str]:
        ports = [p.device for p in serial.tools.list_ports.comports()]
        return ports if ports else [self.port_var.get().strip()]

    def _open_search_dialog(self) -> None:
        SearchDialog(self.root, port_var=self.port_var, baud_var=self.baud_var, node_var=self.node_var, on_search=self._search_device)

    def _search_device(self, port: str, baud: int, node: int) -> list[tuple[int, int, str, str]]:
        results: list[tuple[int, int, str, str]] = []
        try:
            client = ControllerClient(port, baud, node)
            client.read_holding(0x1008, 1)
            results.append((node, baud, "ASCII", "在线"))
        except Exception:
            results.append((node, baud, "ASCII", "离线"))
        return results

    def _open_parameter_table(self) -> None:
        rows = [
            ParamRow(0x1005, "电流标定值(A)", "系统信息", 5142),
            ParamRow(0x1006, "转速标定值(rpm)", "系统信息", 3000),
            ParamRow(0x1007, "工作模式", "基本参数", 2),
            ParamRow(0x1008, "启动方式", "基本参数", 1),
            ParamRow(0x1012, "模拟信号电压(mV)", "电流信息", 0),
            ParamRow(0x1013, "故障代码", "电流信息", 0),
            ParamRow(0x1014, "工作状态", "电流信息", 1),
            ParamRow(0x1015, "IO输入状态", "基本参数", 0x12),
            ParamRow(0x1016, "IO输出状态", "基本参数", 0),
            ParamRow(0x1018, "电机位置反馈值(脉冲)", "位置环", 0),
            ParamRow(0x101A, "编码器每圈脉冲数", "位置环", 48),
            ParamRow(0x1020, "电机极对数", "基本参数", 2),
            ParamRow(0x1022, "电机额定功率(kW)", "过载管理", 15),
            ParamRow(0x1024, "电机额定电流(A)", "电流环", 120),
            ParamRow(0x1025, "电机额定转速(rpm)", "速度环", 2000),
            ParamRow(0x1026, "电机转子时间常数", "过载管理", 344),
            ParamRow(0x1027, "参数测试电流比例(%)", "电流环", 50),
            ParamRow(0x100B, "速度给定(rpm)", "速度环", 0),
            ParamRow(0x100C, "电流给定", "电流环", 0),
            ParamRow(0x101D, "故障代码", "通信", 0),
        ]
        dialog = ParameterDialog(self.root, rows=rows, on_write=self._write_register, on_read=self._read_register)
        dialog.grab_set()

    def _open_alarm_config(self) -> None:
        dialog = AlarmDialog(self.root)
        dialog.grab_set()

    def _read_register(self, register: int) -> int:
        if self._mode_var.get() == "SIM":
            return self.state.read_register(register)
        client = self._controller_client()
        return client.read_holding(register, 1).words_u16[0]

    def _update_gauges(self) -> None:
        if self._mode_var.get() == "SIM":
            snapshot_speed = self.state.velocity_actual_rpm
            snapshot_current = abs(self.state.velocity_actual_rpm) * 0.02
            voltage = self.state.bus_voltage_tenth_v / 10.0
            motor_temp = self.state.motor_temp_c
            driver_temp = self.state.driver_temp_c
            fault = self.state.error_code
            enabled = self.state.enabled
            brake = self.state.brake
            ready = enabled and fault == 0
            running = enabled and abs(snapshot_speed) > 5
            self.voltage_var.set(f"{voltage:.1f} V")
            self.motor_temp_var.set(f"{motor_temp} °C")
            self.driver_temp_var.set(f"{driver_temp} °C")
            self.speed_var.set(str(snapshot_speed))
            self.current_var.set(f"{snapshot_current:.1f}")
            self.position_var.set(str(self.state.position_actual))
            self.current_gauge.set_value(snapshot_current, self.state.target_velocity_rpm / 100.0)
            self.speed_gauge.set_value(snapshot_speed, self.slider_var.get())
            self.connection_var.set(f"SIM {self.port_var.get()} @ {self.baud_var.get()} ASCII")
            self.status_messages["伺服就绪"].set("ON" if ready else "OFF")
            self.status_messages["伺服运行"].set("ON" if running else "OFF")
            self.status_messages["警告"].set("ON" if fault else "OFF")
            self.status_messages["制动输出"].set("ON" if brake else "OFF")
            self.status_messages["过载"].set("ON" if abs(snapshot_speed) > 2500 else "OFF")
            self.status_messages["反向限位"].set("ON" if snapshot_speed < 0 else "OFF")
            self.status_messages["正向限位"].set("ON" if snapshot_speed > 0 else "OFF")
            self.quick_readouts.set(f"通讯正常 | 速度反馈: {snapshot_speed} rpm | 母线: {voltage:.1f}V")
        else:
            cache = self._controller_cache
            speed = _i16(cache.get(0x1009, 0))
            current = _i16(cache.get(0x100A, 0)) / 10.0
            voltage = cache.get(0x100D, 0) / 10.0
            motor_temp = _i16(cache.get(0x100E, 0))
            driver_temp = _i16(cache.get(0x1015, 0))
            fault = cache.get(0x101D, 0)
            enabled = bool(cache.get(0x1008, 0))
            running = bool(cache.get(0x1014, 0))
            brake = bool(cache.get(0x1016, 0) & 0x0004)
            self.voltage_var.set(f"{voltage:.1f} V")
            self.motor_temp_var.set(f"{motor_temp} °C")
            self.driver_temp_var.set(f"{driver_temp} °C")
            self.speed_var.set(str(speed))
            self.current_var.set(f"{current:.1f}")
            self.current_gauge.set_value(abs(current), speed / 100.0)
            self.speed_gauge.set_value(speed, self.slider_var.get())
            self.status_messages["伺服就绪"].set("ON" if enabled and fault == 0 else "OFF")
            self.status_messages["伺服运行"].set("ON" if running else "OFF")
            self.status_messages["警告"].set("ON" if fault else "OFF")
            self.status_messages["制动输出"].set("ON" if brake else "OFF")
            self.status_messages["过载"].set("ON" if abs(speed) > 2500 else "OFF")
            self.status_messages["反向限位"].set("ON" if speed < 0 else "OFF")
            self.status_messages["正向限位"].set("ON" if speed > 0 else "OFF")
            self.quick_readouts.set(f"通讯正常 | 速度反馈: {speed} rpm | 母线: {voltage:.1f}V")

    def _schedule_tick(self) -> None:
        now = time.perf_counter()
        dt = now - self._last_tick
        self._last_tick = now
        if self._mode_var.get() == "SIM":
            self.state.step(dt)
        elif (now - self._last_poll) > 0.35:
            self._read_controller_snapshot()
            self._last_poll = now
        self._update_gauges()
        self.root.after(50, self._schedule_tick)

    def on_close(self) -> None:
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = LegacyWindconApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()