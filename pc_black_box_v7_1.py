import csv
import ctypes
import json
import os
import platform
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

import psutil

APP_NAME = "PC Black Box"
APP_VERSION = "V7.1"
UDP_PORT_DEFAULT = 4210
BRIDGE_TASK_NAME = "PC Black Box Hardware Bridge"


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(filename):
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, filename)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)


def set_windows_app_id():
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "MOAYAD.PCBlackBox.V7"
            )
        except Exception:
            pass


BASE_DIR = app_dir()
BRIDGE_EXE = os.path.join(BASE_DIR, "HardwareBridgeRuntime", "HardwareBridge.exe")
BRIDGE_FILE = os.path.join(BASE_DIR, "hardware_sensors.json")
CSV_FILE = os.path.join(BASE_DIR, "pc_black_box_live_log.csv")
SETTINGS_FILE = os.path.join(BASE_DIR, "pc_black_box_settings.json")

THEMES = {
    "Dark": {
        "bg": "#0b1017",
        "sidebar": "#101722",
        "panel": "#111a25",
        "card": "#101923",
        "card2": "#15202d",
        "text": "#f4f8fc",
        "muted": "#8193a8",
        "accent": "#149dff",
        "accent2": "#32b5ff",
        "green": "#20d99a",
        "purple": "#7b4dff",
        "warn": "#f5b94f",
        "bad": "#ff6b6b",
        "border": "#213145",
        "grid": "#17304b",
    },
    "Midnight": {
        "bg": "#050a10",
        "sidebar": "#07101a",
        "panel": "#091421",
        "card": "#09131d",
        "card2": "#0d1a28",
        "text": "#edf7ff",
        "muted": "#71879e",
        "accent": "#009cff",
        "accent2": "#41c2ff",
        "green": "#00d996",
        "purple": "#8057ff",
        "warn": "#ffc35a",
        "bad": "#ff6868",
        "border": "#15304b",
        "grid": "#0e2940",
    },
    "Light": {
        "bg": "#eef3f8",
        "sidebar": "#ffffff",
        "panel": "#f7f9fc",
        "card": "#ffffff",
        "card2": "#edf2f7",
        "text": "#13202d",
        "muted": "#667789",
        "accent": "#087fe7",
        "accent2": "#1599ff",
        "green": "#00a874",
        "purple": "#6f42e7",
        "warn": "#a86b00",
        "bad": "#c43f3f",
        "border": "#d9e2ec",
        "grid": "#d9e7f4",
    },
}


def fmt_uptime(seconds):
    seconds = max(0, int(seconds))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if days:
        return f"{days}d {hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def fmt_bytes(value):
    value = float(max(0, value))
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit in ("B", "KB"):
                return f"{value:.0f} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024


def fmt_rate(bytes_per_second):
    bps = max(0.0, float(bytes_per_second)) * 8.0
    if bps >= 1_000_000_000:
        return f"{bps / 1_000_000_000:.1f} Gbps"
    if bps >= 1_000_000:
        return f"{bps / 1_000_000:.1f} Mbps"
    if bps >= 1_000:
        return f"{bps / 1_000:.0f} Kbps"
    return f"{bps:.0f} bps"


class PCBlackBox(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1080x700")
        self.minsize(960, 640)

        self._runtime_icon = resource_path("PC_Black_Box_NEW.ico")
        try:
            self.iconbitmap(default=self._runtime_icon)
        except Exception:
            pass

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.bridge_process = None
        self.sender_thread = None
        self.sending = False
        self.packet_count = 0
        self.current_page = "Dashboard"
        self.latest = {}
        self.history_limit = 70
        self.cpu_history = [0.0] * self.history_limit
        self.ram_history = [0.0] * self.history_limit

        self.settings = {
            "theme": "Midnight",
            "esp32_ip": "192.168.1.50",
            "esp32_port": UDP_PORT_DEFAULT,
            "auto_start_bridge": True,
            "auto_start_sender": False,
        }
        self.load_settings()
        self.theme_name = self.settings.get("theme", "Midnight")
        if self.theme_name not in THEMES:
            self.theme_name = "Midnight"

        self.cpu_var = tk.StringVar(value="0%")
        self.cpu_temp_var = tk.StringVar(value="N/A")
        self.cpu_temp_short_var = tk.StringVar(value="N/A")
        self.ram_var = tk.StringVar(value="0%")
        self.ram_detail_var = tk.StringVar(value="- / -")
        self.disk_var = tk.StringVar(value="0%")
        self.disk_detail_var = tk.StringVar(value="- / -")
        self.uptime_var = tk.StringVar(value="00:00:00")
        self.gpu_name_var = tk.StringVar(value="Detecting GPU...")
        self.gpu_usage_var = tk.StringVar(value="N/A")
        self.gpu_usage_short_var = tk.StringVar(value="N/A")
        self.gpu_temp_var = tk.StringVar(value="N/A")
        self.gpu_temp_short_var = tk.StringVar(value="N/A")
        self.bridge_status_var = tk.StringVar(value="Starting bridge...")
        self.sender_status_var = tk.StringVar(value="Stopped")
        self.packet_var = tk.StringVar(value="0 packets")
        self.last_packet_var = tk.StringVar(value="-")
        self.download_var = tk.StringVar(value="↓ 0 bps")
        self.upload_var = tk.StringVar(value="↑ 0 bps")
        self.ip_var = tk.StringVar(value=str(self.settings.get("esp32_ip", "192.168.1.50")))
        self.port_var = tk.StringVar(value=str(self.settings.get("esp32_port", UDP_PORT_DEFAULT)))
        self.theme_var = tk.StringVar(value=self.theme_name)

        self.last_net = psutil.net_io_counters()
        self.last_net_time = time.time()

        self.build_ui()
        self.apply_theme()
        self.show_page("Dashboard")

        psutil.cpu_percent(interval=None)

        if self.settings.get("auto_start_bridge", True):
            self.after(300, self.start_bridge)

        self.after(650, self.update_stats)

        if self.settings.get("auto_start_sender", False):
            self.after(1800, self.start_sending)

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------------- Settings ----------------

    def load_settings(self):
        try:
            if os.path.isfile(SETTINGS_FILE):
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                if isinstance(saved, dict):
                    self.settings.update(saved)
        except Exception:
            pass

    def save_settings(self):
        self.settings["theme"] = self.theme_var.get()
        self.settings["esp32_ip"] = self.ip_var.get().strip()
        try:
            self.settings["esp32_port"] = int(self.port_var.get().strip())
        except Exception:
            self.settings["esp32_port"] = UDP_PORT_DEFAULT
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2)
        except Exception:
            pass

    # ---------------- UI helpers ----------------

    def frame(self, parent, role="bg", **kwargs):
        w = tk.Frame(parent, bd=0, **kwargs)
        w._theme_role = role
        return w

    def label(self, parent, text="", textvariable=None, role="text", **kwargs):
        w = tk.Label(parent, text=text, textvariable=textvariable, bd=0, **kwargs)
        w._theme_role = role
        return w

    def button(self, parent, text, command, role="action", **kwargs):
        w = tk.Button(
            parent,
            text=text,
            command=command,
            relief="flat",
            bd=0,
            cursor="hand2",
            **kwargs,
        )
        w._theme_role = role
        return w

    def card(self, parent, **kwargs):
        w = self.frame(parent, "card", highlightthickness=1, **kwargs)
        return w

    def card_header(self, parent, title, subtitle=None):
        self.label(
            parent, title, role="text",
            font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", padx=16, pady=(13, 2 if subtitle else 10))
        if subtitle:
            self.label(
                parent, subtitle, role="muted",
                font=("Segoe UI", 8)
            ).pack(anchor="w", padx=16, pady=(0, 8))

    def page_header(self, page, title, subtitle):
        row = self.frame(page, "bg")
        row.pack(fill="x", padx=22, pady=(18, 12))
        left = self.frame(row, "bg")
        left.pack(side="left", fill="x", expand=True)
        self.label(left, title, role="text", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        self.label(left, subtitle, role="muted", font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 0))
        return row

    def metric_card(self, parent, title, icon_text, main_var, detail_var, bar_style):
        c = self.card(parent)
        top = self.frame(c, "card")
        top.pack(fill="x", padx=15, pady=(13, 4))

        icon = self.label(
            top, icon_text, role="accent",
            font=("Segoe UI Symbol", 14, "bold"),
            width=2
        )
        icon.pack(side="left", padx=(0, 8))

        tx = self.frame(top, "card")
        tx.pack(side="left", fill="x", expand=True)
        self.label(tx, title, role="muted", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.label(tx, textvariable=main_var, role="text", font=("Segoe UI", 17, "bold")).pack(anchor="w", pady=(2, 0))

        detail = self.label(
            c, textvariable=detail_var, role="muted",
            font=("Segoe UI", 8)
        )
        detail.pack(anchor="e", padx=15, pady=(0, 4))

        pb = ttk.Progressbar(c, maximum=100, style=bar_style)
        pb.pack(fill="x", padx=15, pady=(1, 14))
        return c, pb

    # ---------------- Main layout ----------------

    def build_ui(self):
        self.sidebar = self.frame(self, "sidebar", width=190)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        self.content = self.frame(self, "bg")
        self.content.pack(side="right", fill="both", expand=True)

        brand = self.frame(self.sidebar, "sidebar")
        brand.pack(fill="x", padx=14, pady=(18, 14))
        self.label(brand, "PC BLACK BOX", role="text", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        self.label(brand, APP_VERSION, role="muted", font=("Segoe UI", 8)).pack(anchor="w", pady=(4, 0))

        self.nav_buttons = {}
        nav_items = [
            ("Dashboard", "⌂"),
            ("System Info", "▣"),
            ("Hardware", "◉"),
            ("Performance", "⌁"),
            ("Tools", "⚒"),
            ("Settings", "⚙"),
            ("About", "ⓘ"),
        ]

        nav = self.frame(self.sidebar, "sidebar")
        nav.pack(fill="x", padx=7)

        for page, icon in nav_items:
            btn = self.button(
                nav,
                f"{icon}   {page}",
                lambda p=page: self.show_page(p),
                role="nav",
                anchor="w",
                font=("Segoe UI", 9),
                padx=12,
                pady=10,
            )
            btn.pack(fill="x", pady=1)
            self.nav_buttons[page] = btn

        self.sidebar_spacer = self.frame(self.sidebar, "sidebar")
        self.sidebar_spacer.pack(fill="both", expand=True)

        divider = self.frame(self.sidebar, "border", height=1)
        divider.pack(fill="x", padx=14, pady=(4, 10))

        self.label(
            self.sidebar,
            textvariable=self.bridge_status_var,
            role="muted",
            font=("Segoe UI", 8),
            wraplength=155,
            justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 15))

        self.page_container = self.frame(self.content, "bg")
        self.page_container.pack(fill="both", expand=True)

        self.pages = {}
        self.build_dashboard()
        self.build_system_info()
        self.build_hardware()
        self.build_performance()
        self.build_tools()
        self.build_settings()
        self.build_about()

    def make_page(self, name):
        p = self.frame(self.page_container, "bg")
        self.pages[name] = p
        return p

    # ---------------- Dashboard ----------------

    def build_dashboard(self):
        page = self.make_page("Dashboard")

        header = self.frame(page, "bg")
        header.pack(fill="x", padx=22, pady=(17, 10))

        iconbox = self.frame(header, "card", width=44, height=44, highlightthickness=1)
        iconbox.pack(side="left", padx=(0, 12))
        iconbox.pack_propagate(False)
        self.label(iconbox, "◇", role="accent", font=("Segoe UI Symbol", 22, "bold")).pack(expand=True)

        titlebox = self.frame(header, "bg")
        titlebox.pack(side="left", fill="x", expand=True)
        self.label(titlebox, "System Overview", role="text", font=("Segoe UI", 17, "bold")).pack(anchor="w")
        self.label(titlebox, "Real-Time Monitoring", role="muted", font=("Segoe UI", 9)).pack(anchor="w", pady=(1, 0))

        upt = self.frame(header, "bg")
        upt.pack(side="right")
        self.label(upt, "Uptime", role="muted", font=("Segoe UI", 8)).pack(anchor="e")
        self.label(upt, textvariable=self.uptime_var, role="text", font=("Segoe UI", 11)).pack(anchor="e", pady=(2, 0))

        body = self.frame(page, "bg")
        body.pack(fill="both", expand=True, padx=22, pady=(0, 18))

        cards = self.frame(body, "bg")
        cards.pack(fill="x")
        cards.columnconfigure(0, weight=1)
        cards.columnconfigure(1, weight=1)

        self.cpu_card, self.cpu_bar = self.metric_card(
            cards, "CPU", "◉", self.cpu_var, self.cpu_temp_short_var, "CPU.Horizontal.TProgressbar"
        )
        self.cpu_card.grid(row=0, column=0, sticky="nsew", padx=(0, 7), pady=(0, 7))

        self.gpu_card, self.gpu_bar = self.metric_card(
            cards, "GPU", "▣", self.gpu_usage_short_var, self.gpu_temp_short_var, "GPU.Horizontal.TProgressbar"
        )
        self.gpu_card.grid(row=0, column=1, sticky="nsew", padx=(7, 0), pady=(0, 7))

        self.ram_card, self.ram_bar = self.metric_card(
            cards, "RAM", "▥", self.ram_detail_var, self.ram_var, "RAM.Horizontal.TProgressbar"
        )
        self.ram_card.grid(row=1, column=0, sticky="nsew", padx=(0, 7), pady=(7, 0))

        self.disk_card, self.disk_bar = self.metric_card(
            cards, "Storage", "▰", self.disk_detail_var, self.disk_var, "DISK.Horizontal.TProgressbar"
        )
        self.disk_card.grid(row=1, column=1, sticky="nsew", padx=(7, 0), pady=(7, 0))

        bottom = self.frame(body, "bg")
        bottom.pack(fill="both", expand=True, pady=(14, 0))

        chart_card = self.card(bottom)
        chart_card.pack(side="left", fill="both", expand=True, padx=(0, 8))
        self.chart_title = self.label(chart_card, "Live CPU History", role="muted", font=("Segoe UI", 8, "bold"))
        self.chart_title.pack(anchor="w", padx=14, pady=(10, 2))

        self.dashboard_chart = tk.Canvas(chart_card, height=150, bd=0, highlightthickness=0)
        self.dashboard_chart._theme_role = "canvas"
        self.dashboard_chart.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self.dashboard_chart.bind("<Configure>", lambda _e: self.draw_dashboard_chart())

        network = self.card(bottom, width=160)
        network.pack(side="right", fill="y")
        network.pack_propagate(False)
        self.card_header(network, "Network")
        self.label(network, textvariable=self.download_var, role="accent", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=15, pady=(8, 5))
        self.label(network, textvariable=self.upload_var, role="green", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=15, pady=5)
        self.label(network, "Live throughput", role="muted", font=("Segoe UI", 8)).pack(anchor="w", padx=15, pady=(12, 0))

        footer = self.frame(page, "bg")
        footer.pack(fill="x", padx=22, pady=(0, 12))
        self.label(footer, "PC BLACK BOX", role="muted", font=("Segoe UI", 7)).pack(side="left")
        self.label(footer, "KEEP YOUR SYSTEM IN CHECK", role="muted", font=("Segoe UI", 7)).pack(side="right")

    # ---------------- System Info ----------------

    def build_system_info(self):
        page = self.make_page("System Info")
        self.page_header(page, "System Info", "PC identity and operating system information")

        body = self.frame(page, "bg")
        body.pack(fill="both", expand=True, padx=22, pady=(0, 18))

        host = self.card(body)
        host.pack(fill="x", pady=(0, 8))
        self.card_header(host, "Computer")
        self.label(host, f"Hostname: {platform.node()}", role="text", font=("Segoe UI", 10)).pack(anchor="w", padx=16, pady=3)
        self.label(host, f"OS: {platform.system()} {platform.release()} ({platform.machine()})", role="muted", font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(3, 14))

        cpu_model = platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER", "Processor information unavailable")
        proc = self.card(body)
        proc.pack(fill="x", pady=8)
        self.card_header(proc, "Processor")
        self.label(proc, cpu_model, role="text", font=("Segoe UI", 10), wraplength=760, justify="left").pack(anchor="w", padx=16, pady=(3, 14))

        mem = psutil.virtual_memory()
        disk = psutil.disk_usage(os.environ.get("SystemDrive", "C:") + "\\")
        res = self.card(body)
        res.pack(fill="x", pady=8)
        self.card_header(res, "Memory & Storage")
        self.label(res, f"RAM: {fmt_bytes(mem.total)}", role="text", font=("Segoe UI", 10)).pack(anchor="w", padx=16, pady=3)
        self.label(res, f"System Drive: {fmt_bytes(disk.total)} total", role="muted", font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(3, 14))

    # ---------------- Hardware ----------------

    def build_hardware(self):
        page = self.make_page("Hardware")
        self.page_header(page, "Hardware", "Live CPU and GPU data from Hardware Bridge")

        body = self.frame(page, "bg")
        body.pack(fill="both", expand=True, padx=22, pady=(0, 18))

        cpu = self.card(body)
        cpu.pack(fill="x", pady=(0, 8))
        self.card_header(cpu, "Processor")
        self.label(cpu, textvariable=self.cpu_var, role="text", font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=16)
        self.label(cpu, textvariable=self.cpu_temp_var, role="muted", font=("Segoe UI", 10)).pack(anchor="w", padx=16, pady=(3, 14))

        gpu = self.card(body)
        gpu.pack(fill="x", pady=8)
        self.card_header(gpu, "Graphics")
        self.label(gpu, textvariable=self.gpu_name_var, role="text", font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=16)
        self.label(gpu, textvariable=self.gpu_usage_var, role="muted", font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(4, 2))
        self.label(gpu, textvariable=self.gpu_temp_var, role="muted", font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(2, 14))

        bridge = self.card(body)
        bridge.pack(fill="x", pady=8)
        self.card_header(bridge, "Hardware Bridge")
        self.label(
            bridge, textvariable=self.bridge_status_var, role="muted",
            font=("Segoe UI", 9), wraplength=760, justify="left"
        ).pack(anchor="w", padx=16, pady=(2, 9))

        row = self.frame(bridge, "card")
        row.pack(anchor="w", padx=16, pady=(0, 14))
        self.button(row, "Start Bridge", self.start_bridge, padx=13, pady=7).pack(side="left", padx=(0, 7))
        self.button(row, "Restart Bridge", self.restart_bridge, padx=13, pady=7).pack(side="left")

    # ---------------- Performance ----------------

    def build_performance(self):
        page = self.make_page("Performance")
        self.page_header(page, "Performance", "Rolling CPU and memory utilization")

        body = self.frame(page, "bg")
        body.pack(fill="both", expand=True, padx=22, pady=(0, 18))

        statrow = self.frame(body, "bg")
        statrow.pack(fill="x")

        c1 = self.card(statrow)
        c1.pack(side="left", fill="both", expand=True, padx=(0, 6))
        self.card_header(c1, "CPU Usage")
        self.label(c1, textvariable=self.cpu_var, role="accent", font=("Segoe UI", 20, "bold")).pack(anchor="w", padx=16, pady=(0, 14))

        c2 = self.card(statrow)
        c2.pack(side="left", fill="both", expand=True, padx=6)
        self.card_header(c2, "RAM Usage")
        self.label(c2, textvariable=self.ram_var, role="purple", font=("Segoe UI", 20, "bold")).pack(anchor="w", padx=16, pady=(0, 14))

        c3 = self.card(statrow)
        c3.pack(side="left", fill="both", expand=True, padx=(6, 0))
        self.card_header(c3, "GPU Usage")
        self.label(c3, textvariable=self.gpu_usage_short_var, role="green", font=("Segoe UI", 20, "bold")).pack(anchor="w", padx=16, pady=(0, 14))

        graph = self.card(body)
        graph.pack(fill="both", expand=True, pady=(12, 0))
        self.card_header(graph, "CPU / RAM History")
        self.performance_chart = tk.Canvas(graph, bd=0, highlightthickness=0)
        self.performance_chart._theme_role = "canvas"
        self.performance_chart.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.performance_chart.bind("<Configure>", lambda _e: self.draw_performance_chart())

    # ---------------- Tools / ESP32 / Logs ----------------

    def build_tools(self):
        page = self.make_page("Tools")
        self.page_header(page, "Tools", "ESP32 telemetry and local black box logs")

        body = self.frame(page, "bg")
        body.pack(fill="both", expand=True, padx=22, pady=(0, 18))

        conn = self.card(body)
        conn.pack(fill="x", pady=(0, 8))
        self.card_header(conn, "ESP32 Connection", "UDP telemetry sender")

        form = self.frame(conn, "card")
        form.pack(fill="x", padx=16, pady=(3, 8))
        self.label(form, "ESP32 IP", role="muted", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", pady=5)
        self.ip_entry = tk.Entry(form, textvariable=self.ip_var, relief="flat", width=28)
        self.ip_entry._theme_role = "entry"
        self.ip_entry.grid(row=0, column=1, padx=12, pady=5)

        self.label(form, "UDP Port", role="muted", font=("Segoe UI", 9, "bold")).grid(row=1, column=0, sticky="w", pady=5)
        self.port_entry = tk.Entry(form, textvariable=self.port_var, relief="flat", width=28)
        self.port_entry._theme_role = "entry"
        self.port_entry.grid(row=1, column=1, padx=12, pady=5)

        actions = self.frame(conn, "card")
        actions.pack(anchor="w", padx=16, pady=(0, 13))
        self.start_btn = self.button(actions, "Start Sending", self.start_sending, padx=14, pady=7)
        self.start_btn.pack(side="left", padx=(0, 7))
        self.stop_btn = self.button(actions, "Stop", self.stop_sending, role="secondary", padx=14, pady=7, state="disabled")
        self.stop_btn.pack(side="left")

        status = self.card(body)
        status.pack(fill="x", pady=8)
        self.card_header(status, "Sender Status")
        self.label(status, textvariable=self.sender_status_var, role="text", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16)
        self.label(status, textvariable=self.packet_var, role="muted", font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(3, 13))

        logs = self.card(body)
        logs.pack(fill="both", expand=True, pady=8)
        self.card_header(logs, "Local Log")
        self.label(logs, CSV_FILE, role="muted", font=("Segoe UI", 8), wraplength=760, justify="left").pack(anchor="w", padx=16, pady=(2, 7))
        self.button(logs, "Open Log Folder", self.open_log_folder, padx=13, pady=7).pack(anchor="w", padx=16)
        self.label(logs, "Last UDP Packet", role="muted", font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=16, pady=(12, 2))
        self.label(
            logs, textvariable=self.last_packet_var, role="text",
            font=("Consolas", 8), wraplength=760, justify="left"
        ).pack(anchor="w", padx=16, pady=(0, 14))

    # ---------------- Settings ----------------

    def build_settings(self):
        page = self.make_page("Settings")
        self.page_header(page, "Settings", "Appearance and startup behavior")

        body = self.frame(page, "bg")
        body.pack(fill="both", expand=True, padx=22, pady=(0, 18))

        appearance = self.card(body)
        appearance.pack(fill="x", pady=(0, 8))
        self.card_header(appearance, "Appearance")

        row = self.frame(appearance, "card")
        row.pack(anchor="w", padx=16, pady=(2, 14))
        self.label(row, "Theme", role="muted", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 12))
        self.theme_combo = ttk.Combobox(
            row, textvariable=self.theme_var,
            values=list(THEMES.keys()), state="readonly", width=18
        )
        self.theme_combo.pack(side="left")
        self.theme_combo.bind("<<ComboboxSelected>>", lambda _e: self.change_theme())

        startup = self.card(body)
        startup.pack(fill="x", pady=8)
        self.card_header(startup, "Startup")

        self.auto_bridge_var = tk.BooleanVar(value=self.settings.get("auto_start_bridge", True))
        self.auto_sender_var = tk.BooleanVar(value=self.settings.get("auto_start_sender", False))

        self.auto_bridge_check = tk.Checkbutton(
            startup,
            text="Start Hardware Bridge automatically",
            variable=self.auto_bridge_var,
            command=self.update_startup_settings,
            anchor="w",
        )
        self.auto_bridge_check._theme_role = "check"
        self.auto_bridge_check.pack(anchor="w", padx=16, pady=(2, 6))

        self.auto_sender_check = tk.Checkbutton(
            startup,
            text="Start ESP32 sender automatically",
            variable=self.auto_sender_var,
            command=self.update_startup_settings,
            anchor="w",
        )
        self.auto_sender_check._theme_role = "check"
        self.auto_sender_check.pack(anchor="w", padx=16, pady=(0, 14))

        note = self.card(body)
        note.pack(fill="x", pady=8)
        self.card_header(note, "Sensor Note")
        self.label(
            note,
            "The app never invents missing sensor values. V7.1 can use a one-time elevated Hardware Bridge task for CPU temperature. If a sensor is not exposed, it is shown as N/A.",
            role="muted", font=("Segoe UI", 9), wraplength=760, justify="left"
        ).pack(anchor="w", padx=16, pady=(0, 14))

    # ---------------- About ----------------

    def build_about(self):
        page = self.make_page("About")
        self.page_header(page, "About", "PC Black Box project information")

        body = self.frame(page, "bg")
        body.pack(fill="both", expand=True, padx=22, pady=(0, 18))

        about = self.card(body)
        about.pack(fill="x")

        self.label(about, f"{APP_NAME} {APP_VERSION}", role="text", font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=18, pady=(18, 8))
        self.label(
            about,
            "The project was designed and programmed by MOAYAD Alharbi",
            role="text", font=("Segoe UI", 10)
        ).pack(anchor="w", padx=18, pady=3)
        self.label(
            about,
            "Social Media: IG @54N7",
            role="accent", font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", padx=18, pady=3)
        self.label(
            about,
            "Independent PC monitoring • Hardware Bridge • ESP32 telemetry • Local logging",
            role="muted", font=("Segoe UI", 9)
        ).pack(anchor="w", padx=18, pady=(12, 3))
        self.label(
            about,
            f"{platform.node()} • {platform.system()} {platform.release()}",
            role="muted", font=("Segoe UI", 8)
        ).pack(anchor="w", padx=18, pady=(3, 18))

    # ---------------- Navigation / themes ----------------

    def show_page(self, name):
        if name not in self.pages:
            return
        self.current_page = name
        for page in self.pages.values():
            page.pack_forget()
        self.pages[name].pack(fill="both", expand=True)

        t = THEMES[self.theme_name]
        for page_name, btn in self.nav_buttons.items():
            if page_name == name:
                btn.configure(
                    bg=t["accent"], fg="#ffffff",
                    activebackground=t["accent2"], activeforeground="#ffffff"
                )
            else:
                btn.configure(
                    bg=t["sidebar"], fg=t["text"],
                    activebackground=t["card2"], activeforeground=t["text"]
                )

    def parent_bg(self, widget, fallback):
        try:
            return widget.master.cget("bg")
        except Exception:
            return fallback

    def apply_widget_theme(self, widget, t):
        for child in widget.winfo_children():
            role = getattr(child, "_theme_role", None)

            if isinstance(child, tk.Frame):
                bg = {
                    "bg": t["bg"],
                    "sidebar": t["sidebar"],
                    "panel": t["panel"],
                    "card": t["card"],
                    "card2": t["card2"],
                    "border": t["border"],
                }.get(role, self.parent_bg(child, t["bg"]))
                try:
                    child.configure(bg=bg)
                    if int(child.cget("highlightthickness")) > 0:
                        child.configure(highlightbackground=t["border"])
                except Exception:
                    pass

            elif isinstance(child, tk.Label):
                parent_bg = self.parent_bg(child, t["bg"])
                fg = {
                    "text": t["text"],
                    "muted": t["muted"],
                    "accent": t["accent2"],
                    "green": t["green"],
                    "purple": t["purple"],
                    "warn": t["warn"],
                    "bad": t["bad"],
                }.get(role, t["text"])
                try:
                    child.configure(bg=parent_bg, fg=fg)
                except Exception:
                    pass

            elif isinstance(child, tk.Button):
                parent_bg = self.parent_bg(child, t["bg"])
                if role == "nav":
                    pass
                elif role == "secondary":
                    child.configure(
                        bg=t["card2"], fg=t["text"],
                        activebackground=t["border"], activeforeground=t["text"],
                        disabledforeground=t["muted"],
                    )
                else:
                    child.configure(
                        bg=t["accent"], fg="#ffffff",
                        activebackground=t["accent2"], activeforeground="#ffffff",
                        disabledforeground=t["muted"],
                    )

            elif isinstance(child, tk.Entry):
                try:
                    child.configure(
                        bg=t["card2"], fg=t["text"],
                        insertbackground=t["text"],
                        disabledbackground=t["card2"],
                        disabledforeground=t["muted"],
                        highlightthickness=1,
                        highlightbackground=t["border"],
                        highlightcolor=t["accent"],
                    )
                except Exception:
                    pass

            elif isinstance(child, tk.Checkbutton):
                parent_bg = self.parent_bg(child, t["card"])
                try:
                    child.configure(
                        bg=parent_bg, fg=t["text"],
                        activebackground=parent_bg, activeforeground=t["text"],
                        selectcolor=t["card2"],
                    )
                except Exception:
                    pass

            elif isinstance(child, tk.Canvas):
                try:
                    child.configure(bg=t["card"])
                except Exception:
                    pass

            self.apply_widget_theme(child, t)

    def apply_theme(self):
        t = THEMES[self.theme_name]

        self.configure(bg=t["bg"])

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        def pb(name, color):
            style.configure(
                name,
                troughcolor=t["card2"],
                background=color,
                bordercolor=t["card2"],
                lightcolor=color,
                darkcolor=color,
                thickness=7,
            )

        pb("CPU.Horizontal.TProgressbar", t["accent"])
        pb("GPU.Horizontal.TProgressbar", t["green"])
        pb("RAM.Horizontal.TProgressbar", t["purple"])
        pb("DISK.Horizontal.TProgressbar", t["accent2"])

        style.configure(
            "TCombobox",
            fieldbackground=t["card2"],
            background=t["card2"],
            foreground=t["text"],
            arrowcolor=t["text"],
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", t["card2"])],
            foreground=[("readonly", t["text"])],
            selectbackground=[("readonly", t["card2"])],
            selectforeground=[("readonly", t["text"])],
        )

        self.apply_widget_theme(self, t)
        self.show_page(self.current_page)
        self.draw_dashboard_chart()
        self.draw_performance_chart()

    def change_theme(self):
        name = self.theme_var.get()
        if name in THEMES:
            self.theme_name = name
            self.save_settings()
            self.apply_theme()

    def update_startup_settings(self):
        self.settings["auto_start_bridge"] = bool(self.auto_bridge_var.get())
        self.settings["auto_start_sender"] = bool(self.auto_sender_var.get())
        self.save_settings()

    # ---------------- Charts ----------------

    def draw_grid(self, canvas, width, height, t):
        canvas.delete("all")
        for i in range(1, 6):
            y = int(height * i / 6)
            canvas.create_line(0, y, width, y, fill=t["grid"], width=1)
        for i in range(1, 10):
            x = int(width * i / 10)
            canvas.create_line(x, 0, x, height, fill=t["grid"], width=1)

    def draw_series(self, canvas, values, color, width, height, line_width=2):
        if len(values) < 2:
            return
        step = width / max(1, len(values) - 1)
        points = []
        for i, value in enumerate(values):
            x = i * step
            y = height - (max(0.0, min(100.0, value)) / 100.0) * max(1, height - 4) - 2
            points.extend([x, y])
        if len(points) >= 4:
            canvas.create_line(*points, fill=color, width=line_width, smooth=True)

    def draw_dashboard_chart(self):
        if not hasattr(self, "dashboard_chart"):
            return
        c = self.dashboard_chart
        t = THEMES[self.theme_name]
        w = max(100, c.winfo_width())
        h = max(70, c.winfo_height())
        self.draw_grid(c, w, h, t)
        self.draw_series(c, self.cpu_history, t["accent"], w, h, 2)

    def draw_performance_chart(self):
        if not hasattr(self, "performance_chart"):
            return
        c = self.performance_chart
        t = THEMES[self.theme_name]
        w = max(100, c.winfo_width())
        h = max(100, c.winfo_height())
        self.draw_grid(c, w, h, t)
        self.draw_series(c, self.cpu_history, t["accent"], w, h, 2)
        self.draw_series(c, self.ram_history, t["purple"], w, h, 2)

        c.create_text(12, 12, text="CPU", fill=t["accent2"], anchor="nw", font=("Segoe UI", 8, "bold"))
        c.create_text(50, 12, text="RAM", fill=t["purple"], anchor="nw", font=("Segoe UI", 8, "bold"))

    def scheduled_bridge_task_exists(self):
        if os.name != "nt":
            return False
        try:
            creationflags = subprocess.CREATE_NO_WINDOW
            result = subprocess.run(
                ["schtasks", "/Query", "/TN", BRIDGE_TASK_NAME],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    def run_scheduled_bridge_task(self):
        if os.name != "nt":
            return False
        try:
            creationflags = subprocess.CREATE_NO_WINDOW
            result = subprocess.run(
                ["schtasks", "/Run", "/TN", BRIDGE_TASK_NAME],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    def end_scheduled_bridge_task(self):
        if os.name != "nt":
            return
        try:
            creationflags = subprocess.CREATE_NO_WINDOW
            subprocess.run(
                ["schtasks", "/End", "/TN", BRIDGE_TASK_NAME],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
                timeout=5,
            )
        except Exception:
            pass

    # ---------------- Hardware bridge ----------------

    def start_bridge(self):
        if self.bridge_process and self.bridge_process.poll() is None:
            return

        # If another bridge is already producing fresh data, reuse it.
        try:
            if os.path.isfile(BRIDGE_FILE) and (time.time() - os.path.getmtime(BRIDGE_FILE) < 3.0):
                self.bridge_status_var.set("Bridge connected ✓")
                return
        except Exception:
            pass

        if not os.path.isfile(BRIDGE_EXE):
            self.bridge_status_var.set("Hardware Bridge runtime not found")
            return

        # V7.1: prefer the one-time configured Windows Scheduled Task.
        # The task runs HardwareBridge.exe with highest privileges without
        # showing a UAC prompt every time PC Black Box starts.
        if self.scheduled_bridge_task_exists():
            if self.run_scheduled_bridge_task():
                self.bridge_status_var.set("Starting elevated Hardware Bridge...")
                return
            self.bridge_status_var.set("Elevated Bridge failed; using standard mode")

        # Safe fallback: standard non-elevated bridge.
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            self.bridge_process = subprocess.Popen(
                [BRIDGE_EXE, BRIDGE_FILE],
                cwd=BASE_DIR,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            self.bridge_status_var.set("Hardware Bridge started (standard mode)")
        except Exception as exc:
            self.bridge_status_var.set(f"Bridge start error: {exc}")

    def stop_bridge(self):
        # Stop elevated Scheduled Task copy if V7.1 setup is installed.
        if self.scheduled_bridge_task_exists():
            self.end_scheduled_bridge_task()

        if self.bridge_process and self.bridge_process.poll() is None:
            try:
                self.bridge_process.terminate()
                self.bridge_process.wait(timeout=2)
            except Exception:
                try:
                    self.bridge_process.kill()
                except Exception:
                    pass
        self.bridge_process = None

    def restart_bridge(self):
        self.stop_bridge()
        self.after(350, self.start_bridge)

    def read_bridge(self):
        try:
            if not os.path.isfile(BRIDGE_FILE):
                return None, "Waiting for Hardware Bridge..."
            age = time.time() - os.path.getmtime(BRIDGE_FILE)
            if age > 4:
                return None, f"Bridge data stale ({age:.0f}s)"
            with open(BRIDGE_FILE, "r", encoding="utf-8") as f:
                return json.load(f), "Bridge connected ✓"
        except json.JSONDecodeError:
            return None, "Bridge updating..."
        except Exception as exc:
            return None, f"Bridge error: {exc}"

    # ---------------- Live stats ----------------

    def update_stats(self):
        try:
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            drive = os.environ.get("SystemDrive", "C:") + "\\"
            disk = psutil.disk_usage(drive)
            uptime = int(time.time() - psutil.boot_time())

            self.cpu_var.set(f"{cpu:.0f}%")
            self.ram_var.set(f"{mem.percent:.0f}%")
            self.ram_detail_var.set(f"{mem.used / (1024**3):.1f} / {mem.total / (1024**3):.1f} GB")
            self.disk_var.set(f"{disk.percent:.0f}%")
            self.disk_detail_var.set(f"{disk.used / (1024**3):.0f} / {disk.total / (1024**3):.0f} GB")
            self.uptime_var.set(fmt_uptime(uptime))

            self.cpu_bar["value"] = cpu
            self.ram_bar["value"] = mem.percent
            self.disk_bar["value"] = disk.percent

            bridge, status = self.read_bridge()
            self.bridge_status_var.set(status)

            cpu_temp = None
            gpu_name = None
            gpu_usage = None
            gpu_temp = None

            if bridge:
                cpu_temp = bridge.get("cpu_temp")
                gpu_name = bridge.get("gpu_name")
                gpu_usage = bridge.get("gpu_usage")
                gpu_temp = bridge.get("gpu_temp")

                if cpu_temp is not None:
                    cpu_temp = float(cpu_temp)
                    cpu_sensor_name = bridge.get("cpu_temp_name") or "CPU"
                    self.cpu_temp_var.set(f"{cpu_temp:.1f} °C  •  {cpu_sensor_name}")
                    self.cpu_temp_short_var.set(f"{cpu_temp:.0f}°C")
                else:
                    self.cpu_temp_var.set("Temperature: N/A")
                    self.cpu_temp_short_var.set("N/A")

                self.gpu_name_var.set(gpu_name or "GPU not detected")

                if gpu_usage is not None:
                    gpu_usage = float(gpu_usage)
                    usage_name = bridge.get("gpu_usage_name") or "GPU Load"
                    self.gpu_usage_var.set(f"{gpu_usage:.1f}%  •  {usage_name}")
                    self.gpu_usage_short_var.set(f"{gpu_usage:.0f}%")
                    self.gpu_bar["value"] = gpu_usage
                else:
                    self.gpu_usage_var.set("GPU load: N/A")
                    self.gpu_usage_short_var.set("N/A")
                    self.gpu_bar["value"] = 0

                if gpu_temp is not None:
                    gpu_temp = float(gpu_temp)
                    self.gpu_temp_var.set(f"{gpu_temp:.1f} °C")
                    self.gpu_temp_short_var.set(f"{gpu_temp:.0f}°C")
                else:
                    self.gpu_temp_var.set("GPU temperature not exposed by this APU")
                    self.gpu_temp_short_var.set("N/A")
            else:
                self.cpu_temp_var.set("Temperature: N/A")
                self.cpu_temp_short_var.set("N/A")
                self.gpu_name_var.set("Waiting for bridge...")
                self.gpu_usage_var.set("GPU load: N/A")
                self.gpu_usage_short_var.set("N/A")
                self.gpu_temp_var.set("GPU temperature: N/A")
                self.gpu_temp_short_var.set("N/A")
                self.gpu_bar["value"] = 0

            now = time.time()
            net = psutil.net_io_counters()
            elapsed = max(0.001, now - self.last_net_time)
            down_bps = (net.bytes_recv - self.last_net.bytes_recv) / elapsed
            up_bps = (net.bytes_sent - self.last_net.bytes_sent) / elapsed
            self.last_net = net
            self.last_net_time = now
            self.download_var.set(f"↓ {fmt_rate(down_bps)}")
            self.upload_var.set(f"↑ {fmt_rate(up_bps)}")

            self.cpu_history.append(float(cpu))
            self.ram_history.append(float(mem.percent))
            self.cpu_history = self.cpu_history[-self.history_limit:]
            self.ram_history = self.ram_history[-self.history_limit:]
            self.draw_dashboard_chart()
            self.draw_performance_chart()

            self.latest = {
                "type": "PC_ALIVE",
                "hostname": platform.node(),
                "cpu": round(float(cpu), 1),
                "cpu_temp": round(cpu_temp, 1) if cpu_temp is not None else None,
                "ram": round(float(mem.percent), 1),
                "ram_used_gb": round(mem.used / (1024**3), 2),
                "ram_total_gb": round(mem.total / (1024**3), 2),
                "disk": round(float(disk.percent), 1),
                "uptime_s": uptime,
                "gpu_name": gpu_name,
                "gpu_usage": round(gpu_usage, 1) if gpu_usage is not None else None,
                "gpu_temp": round(gpu_temp, 1) if gpu_temp is not None else None,
                "net_down_Bps": round(down_bps, 1),
                "net_up_Bps": round(up_bps, 1),
                "timestamp": int(now),
            }

        except Exception as exc:
            self.bridge_status_var.set(f"Monitor error: {exc}")

        self.after(1000, self.update_stats)

    # ---------------- ESP32 sender / logging ----------------

    def start_sending(self):
        if self.sending:
            return

        ip = self.ip_var.get().strip()
        try:
            port = int(self.port_var.get().strip())
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid Port", "UDP port must be between 1 and 65535.")
            return

        if not ip:
            messagebox.showerror("Invalid IP", "Enter the ESP32 IP address.")
            return

        self.save_settings()
        self.sending = True
        self.packet_count = 0
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.sender_status_var.set(f"Sending to {ip}:{port}")
        self.sender_thread = threading.Thread(target=self.send_loop, args=(ip, port), daemon=True)
        self.sender_thread.start()

    def stop_sending(self):
        self.sending = False
        if hasattr(self, "start_btn"):
            self.start_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")
        self.sender_status_var.set("Stopped")

    def write_csv(self, payload):
        fields = [
            "timestamp", "hostname", "cpu", "cpu_temp",
            "ram", "ram_used_gb", "ram_total_gb",
            "disk", "uptime_s", "gpu_name", "gpu_usage", "gpu_temp",
            "net_down_Bps", "net_up_Bps",
        ]
        exists = os.path.isfile(CSV_FILE)
        with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            if not exists:
                writer.writeheader()
            writer.writerow({k: payload.get(k) for k in fields})

    def send_loop(self, ip, port):
        while self.sending:
            try:
                payload = dict(self.latest)
                if not payload:
                    time.sleep(0.3)
                    continue
                payload["timestamp"] = int(time.time())
                packet = json.dumps(payload, separators=(",", ":"))
                self.sock.sendto(packet.encode("utf-8"), (ip, port))
                self.write_csv(payload)
                self.packet_count += 1
                self.after(0, self.packet_var.set, f"{self.packet_count} packets sent")
                self.after(0, self.last_packet_var.set, packet)
            except Exception as exc:
                self.after(0, self.sender_status_var.set, f"Send error: {exc}")
            time.sleep(1)

    def open_log_folder(self):
        try:
            os.startfile(BASE_DIR)
        except Exception:
            pass

    # ---------------- Close ----------------

    def on_close(self):
        self.sending = False
        self.save_settings()
        self.stop_bridge()
        try:
            self.sock.close()
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    set_windows_app_id()
    app = PCBlackBox()
    app.mainloop()
