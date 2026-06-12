# -*- coding: utf-8 -*-
"""
Macro Recorder TDS - บันทึกเมาส์/คีย์บอร์ดทุกอย่าง เล่นซ้ำได้
+ ตรวจจับปุ่ม Restart สีเขียวของ Tower Defense Simulator อัตโนมัติ
รองรับ Windows และ Linux (X11) — ระบบตรวจจับปุ่ม/โหมด Roblox ใช้ได้เฉพาะ Windows

Windows: ดับเบิลคลิกไฟล์นี้เพื่อเปิด
Linux:   pip3 install pynput  แล้วรัน  python3 MacroRecorder_TDS.pyw

ปุ่มลัด:  F3 = บันทึก/หยุดบันทึก   F4 = เล่น/หยุด   F6 = กรอบตรวจจับ   Esc = หยุด
"""

import json
import os
import sys
import time
import threading

# ----- แก้ปัญหาตำแหน่งเมาส์เพี้ยนจาก Windows DPI scaling (เช่นจอขยาย 125%/150%) -----
# ต้องเรียกก่อนสร้างหน้าต่างใดๆ เพื่อให้พิกัดตอนบันทึกกับตอนเล่นซ้ำตรงกัน (พิกัดพิกเซลจริง)
if sys.platform == "win32":
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    # เพิ่มความละเอียดนาฬิกา Windows จาก ~15ms เป็น 1ms
    # ทำให้เล่นซ้ำได้แม่นยำ ขยับเมาส์ลื่นแม้มีพิมพ์คีย์บอร์ดแทรกถี่ๆ
    try:
        ctypes.windll.winmm.timeBeginPeriod(1)
    except Exception:
        pass

    # ---- ขยับเมาส์ผ่าน SendInput (สัญญาณเมาส์จริง) ----
    # SetCursorPos แค่ "ย้ายเคอร์เซอร์" หลายโปรแกรมจึงไม่นับเป็นการลากตอนคลิกค้าง
    # SendInput คงสถานะปุ่มกดค้างระหว่างขยับ -> คลิกค้าง+ลาก ทำงานเหมือนมือลากจริง
    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                    ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                    ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_size_t)]

    class _INPUT(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("mi", _MOUSEINPUT)]

    _MOVE_FLAGS = 0x0001 | 0x8000 | 0x4000  # MOVE | ABSOLUTE | VIRTUALDESK

    def send_mouse_move(x, y):
        gm = ctypes.windll.user32.GetSystemMetrics
        vx, vy = gm(76), gm(77)          # มุมซ้ายบนของจอเสมือน (รวมทุกจอ)
        vw, vh = gm(78), gm(79)          # ขนาดจอเสมือน
        ax = int((x - vx) * 65535 / max(vw - 1, 1))
        ay = int((y - vy) * 65535 / max(vh - 1, 1))
        inp = _INPUT(0, _MOUSEINPUT(ax, ay, 0, _MOVE_FLAGS, 0, 0))
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

    def send_mouse_move_rel(dx, dy):
        # ขยับแบบ relative (เดลต้า) — เกมอย่าง Roblox อ่านเมาส์แบบนี้
        inp = _INPUT(0, _MOUSEINPUT(int(dx), int(dy), 0, 0x0001, 0, 0))  # MOUSEEVENTF_MOVE
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

    def send_left(down):
        # กด/ปล่อยปุ่มซ้ายผ่าน SendInput ตรงๆ (LEFTDOWN/LEFTUP)
        flag = 0x0002 if down else 0x0004
        inp = _INPUT(0, _MOUSEINPUT(0, 0, 0, flag, 0, 0))
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

    # ---- กดคีย์บอร์ดแบบ scancode (ฮาร์ดแวร์จริง) ----
    # เกมส่วนใหญ่ (รวม Roblox) อ่านคีย์บอร์ดด้วย scancode/raw input
    # การยิงแบบ virtual key เฉยๆ เกมจะมองไม่เห็น -> เดิน WASD ค้างพร้อมเมาส์ไม่ได้
    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                    ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                    ("dwExtraInfo", ctypes.c_size_t)]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT)]

    class _INPUT2(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("u", _INPUTUNION)]

    # ปุ่มกลุ่ม extended (ลูกศร, Ins/Del/Home/End/PgUp/PgDn, Ctrl/Alt ขวา, Win ฯลฯ)
    _EXT_VKS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E,
                0x5B, 0x5C, 0x5D, 0x6F, 0x90, 0xA3, 0xA5}

    def send_key(vk, down):
        scan = ctypes.windll.user32.MapVirtualKeyW(vk, 0)
        inp = _INPUT2()
        inp.type = 1  # INPUT_KEYBOARD
        if scan:
            flags = 0x0008  # KEYEVENTF_SCANCODE
            if vk in _EXT_VKS:
                flags |= 0x0001  # EXTENDEDKEY
            if not down:
                flags |= 0x0002  # KEYUP
            inp.u.ki = _KEYBDINPUT(0, scan, flags, 0, 0)
        else:
            inp.u.ki = _KEYBDINPUT(vk, 0, 0 if down else 0x0002, 0, 0)
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

    # ---- Raw Input: อ่านเดลต้าเมาส์ดิบ (ค่าเดียวกับที่เกมใช้หมุนกล้อง) ----
    # ตอนลากขวาใน Roblox เกมจะล็อกเคอร์เซอร์ไว้ ตำแหน่งบนจอจึงไม่ขยับ
    # ต้องอ่านเดลต้าดิบจากฮาร์ดแวร์แทน ไม่งั้นข้อมูลการหันกล้องหายหมด
    class _RAWINPUTDEVICE(ctypes.Structure):
        _fields_ = [("usUsagePage", ctypes.c_ushort), ("usUsage", ctypes.c_ushort),
                    ("dwFlags", ctypes.c_ulong), ("hwndTarget", ctypes.c_void_p)]

    class _RAWINPUTHEADER(ctypes.Structure):
        _fields_ = [("dwType", ctypes.c_ulong), ("dwSize", ctypes.c_ulong),
                    ("hDevice", ctypes.c_void_p), ("wParam", ctypes.c_size_t)]

    class _RAWMOUSE(ctypes.Structure):
        _fields_ = [("usFlags", ctypes.c_ushort), ("ulButtons", ctypes.c_ulong),
                    ("ulRawButtons", ctypes.c_ulong), ("lLastX", ctypes.c_long),
                    ("lLastY", ctypes.c_long), ("ulExtraInformation", ctypes.c_ulong)]

    class _RAWINPUT(ctypes.Structure):
        _fields_ = [("header", _RAWINPUTHEADER), ("mouse", _RAWMOUSE)]

    _WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_void_p, ctypes.c_uint,
                                  ctypes.c_size_t, ctypes.c_ssize_t)
    _u32 = ctypes.windll.user32
    try:
        _SetWindowLongPtr = _u32.SetWindowLongPtrW
    except AttributeError:
        _SetWindowLongPtr = _u32.SetWindowLongW
    _SetWindowLongPtr.restype = ctypes.c_ssize_t
    _SetWindowLongPtr.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t)
    _u32.CallWindowProcW.restype = ctypes.c_ssize_t
    _u32.CallWindowProcW.argtypes = (ctypes.c_ssize_t, ctypes.c_void_p, ctypes.c_uint,
                                     ctypes.c_size_t, ctypes.c_ssize_t)
    _u32.GetRawInputData.restype = ctypes.c_uint
    _u32.GetRawInputData.argtypes = (ctypes.c_ssize_t, ctypes.c_uint, ctypes.c_void_p,
                                     ctypes.POINTER(ctypes.c_uint), ctypes.c_uint)

    # ---- อ่านสีพิกเซลบนจอ (ใช้ตรวจจับปุ่ม Restart สีเขียวของ TDS) ----
    _gdi32 = ctypes.windll.gdi32

    def get_pixel(x, y):
        hdc = _u32.GetDC(0)
        try:
            c = _gdi32.GetPixel(hdc, int(x), int(y))
        finally:
            _u32.ReleaseDC(0, hdc)
        return c & 0xFF, (c >> 8) & 0xFF, (c >> 16) & 0xFF  # (R, G, B)
else:
    send_mouse_move = None
    send_mouse_move_rel = None
    send_key = None
    send_left = None
    get_pixel = None

import tkinter as tk
from tkinter import messagebox, simpledialog

try:
    from pynput import mouse, keyboard
    from pynput.mouse import Button, Controller as MouseController
    from pynput.keyboard import Key, Controller as KeyboardController
except ImportError:
    import tkinter.messagebox as mb
    r = tk.Tk(); r.withdraw()
    mb.showerror("ขาด pynput",
                 "ยังไม่ได้ติดตั้ง pynput\n\n"
                 "Windows:  pip install pynput\n"
                 "Linux:    pip3 install pynput")
    sys.exit(1)

# ---------- ที่เก็บ macro (path สั้น เลี่ยงปัญหา Windows 260 ตัวอักษร) ----------
MACRO_DIR = os.path.join(os.path.expanduser("~"), "Documents", "MacroRecorder")
try:
    os.makedirs(MACRO_DIR, exist_ok=True)
except OSError:
    MACRO_DIR = os.path.join(os.path.expanduser("~"), "MacroRecorder")
    os.makedirs(MACRO_DIR, exist_ok=True)

SETTINGS_FILE = os.path.join(MACRO_DIR, "settings.json")

# ---------- ข้อความสองภาษา TH / EN ----------
L = {
    "th": {
        "ready": "พร้อมใช้งาน",
        "record": "●  บันทึก (F3)",
        "stop_record": "■  หยุดบันทึก (F3)",
        "play": "▶  เล่น/หยุด (F4)",
        "recording": "กำลังบันทึก...  (F3 เพื่อหยุด)",
        "playing": "กำลังเล่น '{name}'  รอบ {i}/{total}  (F4/Esc หยุด)",
        "saved": "บันทึกแล้ว ✓",
        "loop": "วนซ้ำ",
        "speed": "ความเร็ว",
        "gap": "หน่วง (วิ)",
        "infinite": "วนไม่รู้จบ ∞",
        "roblox": "โหมด Roblox",
        "sens": "คูณหัน",
        "macro": "MACRO",
        "rename": "เปลี่ยนชื่อ",
        "delete": "ลบ",
        "folder": "โฟลเดอร์",
        "refresh": "รีเฟรช",
        "hint": "F3 บันทึก  ·  F4 เล่น/หยุด  ·  F6 ตั้งปุ่ม Restart  ·  Esc หยุด",
        "tds": "ตรวจจับปุ่ม Restart (TDS)",
        "tds_set": "กรอบ (F6)",
        "tds_saved": "บันทึกกรอบตรวจจับแล้ว ✓",
        "tds_wait": "รอหลังกด (วิ)",
        "tds_found": "เจอปุ่ม Restart! กดปุ่มแล้วเริ่มรอบใหม่...",
        "no_macro_t": "ไม่มี macro",
        "no_macro_m": "ยังไม่มี macro ให้เล่น — กด F3 เพื่อบันทึกก่อน",
        "save_fail": "บันทึกไม่สำเร็จ",
        "save_fail_m": "เขียนไฟล์ไม่ได้:\n{path}\n\n{err}",
        "rename_t": "เปลี่ยนชื่อ",
        "rename_m": "ชื่อใหม่:",
    },
    "en": {
        "ready": "Ready",
        "record": "●  Record (F3)",
        "stop_record": "■  Stop recording (F3)",
        "play": "▶  Play/Stop (F4)",
        "recording": "Recording...  (F3 to stop)",
        "playing": "Playing '{name}'  loop {i}/{total}  (F4/Esc to stop)",
        "saved": "Saved ✓",
        "loop": "Loops",
        "speed": "Speed",
        "gap": "Gap (s)",
        "infinite": "Loop forever ∞",
        "roblox": "Roblox mode",
        "sens": "Turn ×",
        "macro": "MACROS",
        "rename": "Rename",
        "delete": "Delete",
        "folder": "Folder",
        "refresh": "Refresh",
        "hint": "F3 record  ·  F4 play/stop  ·  F6 set Restart btn  ·  Esc stop",
        "tds": "Restart detection (TDS)",
        "tds_set": "Zone (F6)",
        "tds_saved": "Detection zone saved ✓",
        "tds_wait": "Wait after (s)",
        "tds_found": "Restart found! Clicking & restarting...",
        "no_macro_t": "No macro",
        "no_macro_m": "Nothing to play yet — press F3 to record first",
        "save_fail": "Save failed",
        "save_fail_m": "Could not write file:\n{path}\n\n{err}",
        "rename_t": "Rename",
        "rename_m": "New name:",
    },
}


def load_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(d):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
    except OSError:
        pass


HOTKEYS = {keyboard.Key.f3, keyboard.Key.f4, keyboard.Key.f6, keyboard.Key.esc}
MOVE_INTERVAL = 0.002  # บันทึกตำแหน่งเมาส์ละเอียดสูงสุด ~500 ครั้ง/วินาที

# ---------- ชุดสี Dark Mode ----------
C = {
    "bg":      "#141519",   # พื้นหลังหลัก
    "panel":   "#141519",
    "card":    "#1e2026",   # การ์ด/ลิสต์
    "text":    "#ecedef",
    "muted":   "#84878f",
    "border":  "#2a2c33",
    "red":     "#e5484d",
    "red_h":   "#f2555a",
    "blue":    "#3e63dd",
    "blue_h":  "#5b7ae6",
    "gray":    "#26282f",
    "gray_h":  "#34373f",
    "green":   "#46a758",
    "sel":     "#2c3a63",
}
FONT   = ("Segoe UI", 10)
FONT_B = ("Segoe UI", 10, "bold")
FONT_BIG = ("Segoe UI", 12, "bold")


def make_button(parent, text, bg, hover, command, fg="#ffffff"):
    b = tk.Button(parent, text=text, command=command, font=FONT_B,
                  bg=bg, fg=fg, activebackground=hover, activeforeground=fg,
                  relief="flat", bd=0, padx=10, pady=8, cursor="hand2")
    b.bind("<Enter>", lambda e: b.config(bg=hover))
    b.bind("<Leave>", lambda e: b.config(bg=bg))
    return b


class MacroApp:
    def __init__(self, root):
        self.root = root
        self.cfg = load_settings()
        self.lang = self.cfg.get("lang", "th")
        self.recording = False
        self.playing = False
        self.events = []
        self.t0 = 0.0
        self.last_move_t = 0.0
        self.stop_flag = threading.Event()

        self.mouse_ctl = MouseController()
        self.kb_ctl = KeyboardController()
        self.mouse_listener = None
        self.kb_listener = None
        self._pressed_btns = set()   # ปุ่มเมาส์ที่ยังกดค้างระหว่างเล่น
        self._pressed_keys = set()   # คีย์ที่ยังกดค้างระหว่างเล่น
        self._game_mode = False      # โหมดเกม: ขยับเมาส์แบบ relative
        self._last_pos = (0, 0)
        self._game_sens = 1.0        # ตัวคูณความไวโหมดเกม
        self._rem = [0.0, 0.0]       # เศษเดลต้าสะสม (กันการปัดทิ้งจนหันช้า)
        self._restart_pending = False
        # กรอบตรวจจับปุ่ม Restart — กด F6 แสดง/ซ่อนกรอบบนจอ ลากย้าย+ปรับขนาดได้
        # ค่าเริ่มต้นครอบปุ่ม Restart Match ที่จอ 2560x1440
        old_pt = self.cfg.get("tds_point")
        self.tds_rect = self.cfg.get("tds_rect") or (
            {"x": old_pt["x"] - 153, "y": old_pt["y"] - 27, "w": 306, "h": 54}
            if old_pt else {"x": 953, "y": 1108, "w": 306, "h": 54})
        self._mark = None

        self._build_ui()
        self._refresh_list()

        self.hotkey_listener = keyboard.Listener(on_press=self._on_hotkey)
        self.hotkey_listener.daemon = True
        self.hotkey_listener.start()

        self._setup_raw_input()

    # ---------------- ภาษา ----------------
    def tr(self, key):
        return L[self.lang].get(key, L["th"].get(key, key))

    def _switch_lang(self):
        self.lang = "en" if self.lang == "th" else "th"
        self.cfg["lang"] = self.lang
        save_settings(self.cfg)
        # เก็บค่าตัวเลือกเดิม แล้วสร้าง UI ใหม่ในภาษาที่เลือก
        vals = (self.loop_var.get(), self.speed_var.get(), self.gap_var.get(),
                self.inf_var.get(), self.game_var.get(), self.cam_sens_var.get(),
                self.tds_var.get(), self.wait_var.get())
        for w in self.root.winfo_children():
            w.destroy()
        self._build_ui()
        self.loop_var.set(vals[0])
        self.speed_var.set(vals[1])
        self.gap_var.set(vals[2])
        self.inf_var.set(vals[3])
        self.game_var.set(vals[4])
        self.cam_sens_var.set(vals[5])
        self.tds_var.set(vals[6])
        self.wait_var.set(vals[7])
        self._refresh_list()

    @staticmethod
    def _draw_flag(c, lang):
        """วาดธงชาติเล็กๆ (อิโมจิธงใช้บน Windows ไม่ได้)"""
        w, h = 22, 14
        if lang == "th":
            for y0, y1, col in ((0, 2, "#A51931"), (2, 5, "#F4F5F8"),
                                (5, 9, "#2D2A4A"), (9, 12, "#F4F5F8"),
                                (12, 14, "#A51931")):
                c.create_rectangle(0, y0, w, y1, fill=col, outline="")
        else:  # ธงสหราชอาณาจักร (แบบย่อ)
            c.create_rectangle(0, 0, w, h, fill="#012169", outline="")
            c.create_line(0, 0, w, h, fill="white", width=3)
            c.create_line(0, h, w, 0, fill="white", width=3)
            c.create_line(0, 0, w, h, fill="#C8102E", width=1)
            c.create_line(0, h, w, 0, fill="#C8102E", width=1)
            c.create_line(w // 2, 0, w // 2, h, fill="white", width=5)
            c.create_line(0, h // 2, w, h // 2, fill="white", width=5)
            c.create_line(w // 2, 0, w // 2, h, fill="#C8102E", width=3)
            c.create_line(0, h // 2, w, h // 2, fill="#C8102E", width=3)

    # ---------------- UI ----------------
    def _build_ui(self):
        self.root.title("Macro Recorder · TDS")
        self.root.geometry("530x670")
        self.root.minsize(530, 590)  # ขั้นต่ำพอให้ตัวเลือกทุกช่องแสดงครบ
        self.root.configure(bg=C["bg"])
        self.root.attributes("-topmost", True)
        self._dark_titlebar()

        # ----- แถบสถานะ -----
        status_bar = tk.Frame(self.root, bg=C["bg"])
        status_bar.pack(fill="x", padx=18, pady=(16, 8))
        self.dot = tk.Label(status_bar, text="●", font=("Segoe UI", 10),
                            fg=C["green"], bg=C["bg"])
        self.dot.pack(side="left")
        self.status = tk.Label(status_bar, text=self.tr("ready"), font=("Segoe UI", 11, "bold"),
                               fg=C["text"], bg=C["bg"])
        self.status.pack(side="left", padx=(8, 0))
        # ปุ่มสลับภาษา TH/EN พร้อมธงชาติ (จำค่าไว้ใน settings)
        target = "en" if self.lang == "th" else "th"
        lang_f = tk.Frame(status_bar, bg=C["bg"], cursor="hand2")
        lang_f.pack(side="right")
        flag = tk.Canvas(lang_f, width=22, height=14, bg=C["bg"], highlightthickness=0)
        flag.pack(side="left")
        self._draw_flag(flag, target)
        lang_lbl = tk.Label(lang_f, text=target.upper(), font=("Segoe UI", 9, "bold"),
                            fg=C["muted"], bg=C["bg"], cursor="hand2")
        lang_lbl.pack(side="left", padx=(4, 0))
        for w in (lang_f, flag, lang_lbl):
            w.bind("<Button-1>", lambda e: self._switch_lang())
        self.pct = tk.Label(status_bar, text="", font=("Segoe UI", 10, "bold"),
                            fg=C["muted"], bg=C["bg"])
        self.pct.pack(side="right", padx=(0, 8))

        # หลอดความคืบหน้า (เส้นบาง)
        self.prog = tk.Canvas(self.root, height=4, bg=C["bg"], highlightthickness=0)
        self.prog.pack(fill="x", padx=18, pady=(0, 12))
        self._draw_progress(0.0)

        # ----- ปุ่มหลัก -----
        frm = tk.Frame(self.root, bg=C["bg"])
        frm.pack(fill="x", padx=18, pady=(0, 14))
        self.btn_rec = make_button(frm, self.tr("record"), C["red"], C["red_h"], self.toggle_record)
        self.btn_rec.pack(side="left", expand=True, fill="x", padx=(0, 5))
        self.btn_play = make_button(frm, self.tr("play"), C["blue"], C["blue_h"], self.toggle_play)
        self.btn_play.pack(side="left", expand=True, fill="x", padx=(5, 0))

        # ----- ตัวเลือก -----
        opt = tk.Frame(self.root, bg=C["card"])
        opt.pack(fill="x", padx=18, pady=(0, 14))

        def opt_label(text):
            return tk.Label(opt, text=text, font=("Segoe UI", 9), fg=C["muted"], bg=C["card"])

        def opt_spin(var, **kw):
            return tk.Spinbox(opt, textvariable=var, width=5, font=FONT,
                              bg=C["gray"], fg=C["text"], buttonbackground=C["gray"],
                              insertbackground=C["text"], relief="flat", bd=0,
                              highlightthickness=0, justify="center", **kw)

        opt_label(self.tr("loop")).grid(row=0, column=0, padx=(16, 6), pady=(14, 0))
        self.loop_var = tk.IntVar(value=1)
        opt_spin(self.loop_var, from_=1, to=9999).grid(row=0, column=1, pady=(14, 0))

        opt_label(self.tr("speed")).grid(row=0, column=2, padx=(18, 6), pady=(14, 0))
        self.speed_var = tk.StringVar(value="1.0x")
        sp = tk.OptionMenu(opt, self.speed_var, "0.5x", "1.0x", "1.5x", "2.0x", "3.0x")
        sp.config(font=FONT, bg=C["gray"], fg=C["text"], activebackground=C["gray_h"],
                  activeforeground=C["text"], relief="flat", bd=0,
                  highlightthickness=0, width=4, indicatoron=False, cursor="hand2")
        sp["menu"].config(bg=C["card"], fg=C["text"], font=FONT, bd=0,
                          activebackground=C["sel"], activeforeground=C["text"])
        sp.grid(row=0, column=3, pady=(14, 0))

        opt_label(self.tr("gap")).grid(row=0, column=4, padx=(18, 6), pady=(14, 0))
        self.gap_var = tk.DoubleVar(value=0.5)
        opt_spin(self.gap_var, from_=0, to=600, increment=0.5).grid(row=0, column=5, pady=(14, 0))

        def opt_check(text, var):
            return tk.Checkbutton(opt, text=text, variable=var, font=("Segoe UI", 9),
                                  bg=C["card"], fg=C["muted"], selectcolor=C["gray"],
                                  activebackground=C["card"], activeforeground=C["text"],
                                  cursor="hand2", highlightthickness=0, bd=0)

        self.inf_var = tk.BooleanVar(value=True)  # วนไม่รู้จบเป็นค่าเริ่มต้น
        opt_check(self.tr("infinite"), self.inf_var).grid(
            row=1, column=0, columnspan=3, padx=(12, 0), pady=(8, 12), sticky="w")
        # โหมด Roblox: หมุนกล้องด้วยเดลต้าดิบเฉพาะช่วงคลิกขวาค้าง
        # ตัวคูณหัน 1.0 = หันเท่าตอนอัดพอดี (ปรับเมื่อจำเป็นเท่านั้น)
        self.game_var = tk.BooleanVar(value=True)  # ติ๊กไว้เป็นค่าเริ่มต้น
        opt_check(self.tr("roblox"), self.game_var).grid(
            row=1, column=3, padx=(12, 0), pady=(8, 12), sticky="w")
        opt_label(self.tr("sens")).grid(row=1, column=4, padx=(12, 6), pady=(8, 12), sticky="e")
        self.cam_sens_var = tk.DoubleVar(value=1.0)
        opt_spin(self.cam_sens_var, from_=0.1, to=10, increment=0.1).grid(
            row=1, column=5, pady=(8, 12))

        # ----- TDS: ตรวจจับปุ่ม Restart สีเขียว -----
        self.tds_var = tk.BooleanVar(value=True)
        opt_check(self.tr("tds"), self.tds_var).grid(
            row=2, column=0, columnspan=3, padx=(12, 0), pady=(0, 4), sticky="w")
        tds_btn = tk.Button(opt, text=self.tr("tds_set"), command=self._toggle_mark,
                            font=("Segoe UI", 9), bg=C["gray"], fg=C["text"],
                            activebackground=C["gray_h"], activeforeground=C["text"],
                            relief="flat", bd=0, padx=8, pady=2, cursor="hand2")
        tds_btn.grid(row=2, column=3, padx=(12, 6), pady=(0, 4), sticky="w")
        # รอกี่วินาทีหลังกดปุ่ม Restart ก่อนเริ่ม loop ใหม่ (ตั้งเองได้)
        opt_label(self.tr("tds_wait")).grid(row=2, column=4, padx=(12, 6),
                                            pady=(0, 4), sticky="e")
        self.wait_var = tk.DoubleVar(value=2.0)
        opt_spin(self.wait_var, from_=0, to=60, increment=0.5).grid(
            row=2, column=5, pady=(0, 4))
        self.tds_lbl = tk.Label(opt, text="", font=("Segoe UI", 8),
                                fg=C["muted"], bg=C["card"])
        self.tds_lbl.grid(row=3, column=0, columnspan=6, padx=(14, 0),
                          pady=(0, 12), sticky="w")
        self._update_tds_lbl()

        # ----- รายการ macro -----
        tk.Label(self.root, text=self.tr("macro"), font=("Segoe UI", 8, "bold"),
                 fg=C["muted"], bg=C["bg"], anchor="w").pack(fill="x", padx=20)
        lf = tk.Frame(self.root, bg=C["card"], highlightthickness=0)
        lf.pack(fill="both", expand=True, padx=18, pady=(6, 8))
        self.listbox = tk.Listbox(lf, font=("Segoe UI", 10), bg=C["card"], fg=C["text"],
                                  selectbackground=C["sel"], selectforeground=C["text"],
                                  relief="flat", bd=0, highlightthickness=0,
                                  activestyle="none", selectmode=tk.EXTENDED)
        self.listbox.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        # คลุมดำ: ลากเลือกหลายตัวได้, Ctrl+A เลือกทั้งหมด, ปุ่ม Delete ลบที่เลือก
        self.listbox.bind("<Control-a>",
                          lambda e: (self.listbox.selection_set(0, tk.END), "break")[-1])
        self.listbox.bind("<Delete>", lambda e: self.delete_macro())
        sb = tk.Scrollbar(lf, command=self.listbox.yview, troughcolor=C["card"],
                          bg=C["gray"], activebackground=C["gray_h"], relief="flat", bd=0,
                          width=8)
        sb.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=sb.set)

        # ----- ปุ่มจัดการ (แบบลิงก์ เรียบๆ) -----
        bf = tk.Frame(self.root, bg=C["bg"])
        bf.pack(fill="x", padx=14, pady=(0, 2))
        for txt, cmd in ((self.tr("rename"), self.rename_macro),
                         (self.tr("delete"), self.delete_macro),
                         (self.tr("folder"), self.open_folder),
                         (self.tr("refresh"), self._refresh_list)):
            b = tk.Button(bf, text=txt, command=cmd, font=("Segoe UI", 9),
                          bg=C["bg"], fg=C["muted"], activebackground=C["bg"],
                          activeforeground=C["text"], relief="flat", bd=0,
                          padx=8, pady=3, cursor="hand2")
            b.bind("<Enter>", lambda e, b=b: b.config(fg=C["text"]))
            b.bind("<Leave>", lambda e, b=b: b.config(fg=C["muted"]))
            b.pack(side="left")

        tk.Label(self.root, text=self.tr("hint") + "   ·   TDS v1.6",
                 font=("Segoe UI", 8), fg=C["muted"], bg=C["bg"]).pack(pady=(0, 10))

    def _dark_titlebar(self):
        # ทำแถบหัวหน้าต่าง (ปุ่มย่อ/ขยาย/ปิด) เป็นสีเข้มให้เข้ากับธีม
        if sys.platform != "win32":
            return
        try:
            self.root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            value = ctypes.c_int(1)
            for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (20 / 19 บน Windows เก่า)
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                    break
            # บังคับให้วาดแถบหัวใหม่ทันที
            self.root.attributes("-alpha", 0.99)
            self.root.attributes("-alpha", 1.0)
        except Exception:
            pass

    def _set_status(self, text, color):
        def upd():
            self.status.config(text=text)
            self.dot.config(fg=color)
        self.root.after(0, upd)

    # ---------------- Progress bar ----------------
    def _draw_progress(self, pct):
        self.prog.delete("all")
        w = max(self.prog.winfo_width(), 1)
        self.prog.create_rectangle(0, 0, w, 4, fill=C["card"], outline="")
        if pct > 0:
            self.prog.create_rectangle(0, 0, int(w * min(pct, 1.0)), 4,
                                       fill=C["blue"], outline="")
        if hasattr(self, "pct"):
            self.pct.config(text=f"{int(min(pct, 1.0) * 100)}%" if self.playing else "")

    def _tick_progress(self):
        if self.playing:
            dur = getattr(self, "_play_duration", 0)
            if dur > 0:
                pct = (time.perf_counter() - self._play_start) / dur
                self._draw_progress(pct)
            self.root.after(100, self._tick_progress)
        else:
            self._draw_progress(0.0)

    def _refresh_list(self):
        self.listbox.delete(0, tk.END)
        files = [f for f in sorted(os.listdir(MACRO_DIR))
                 if f.endswith(".json") and f != "settings.json"]
        latest_idx = None
        latest_mtime = -1
        for i, f in enumerate(files):
            self.listbox.insert(tk.END, "  " + f[:-5])
            try:
                m = os.path.getmtime(os.path.join(MACRO_DIR, f))
            except OSError:
                m = 0
            if m > latest_mtime:
                latest_mtime = m
                latest_idx = i
        # เลือกตัวที่บันทึกล่าสุดเป็นค่าเริ่มต้นเสมอ
        if latest_idx is not None:
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(latest_idx)
            self.listbox.see(latest_idx)

    def _selected_file(self):
        sel = self.listbox.curselection()
        if not sel:
            if self.listbox.size() > 0:
                self.listbox.selection_set(0)
                sel = (0,)
            else:
                return None
        return os.path.join(MACRO_DIR, self.listbox.get(sel[0]).strip() + ".json")

    def open_folder(self):
        # เปิดโฟลเดอร์ macro ได้ทุก OS
        if sys.platform == "win32":
            os.startfile(MACRO_DIR)
        elif sys.platform == "darwin":
            os.system(f'open "{MACRO_DIR}"')
        else:
            os.system(f'xdg-open "{MACRO_DIR}" >/dev/null 2>&1 &')

    # ---------------- Raw Input (เดลต้าเมาส์ดิบ) ----------------
    def _setup_raw_input(self):
        if sys.platform != "win32":
            return
        try:
            self.root.update_idletasks()
            hwnd = self.root.winfo_id()
            rid = _RAWINPUTDEVICE(1, 2, 0x00000100, hwnd)  # mouse, RIDEV_INPUTSINK
            if not _u32.RegisterRawInputDevices(ctypes.byref(rid), 1,
                                                ctypes.sizeof(_RAWINPUTDEVICE)):
                return
            self._wndproc = _WNDPROC(self._on_raw_input)
            self._old_wndproc = _SetWindowLongPtr(
                hwnd, -4, ctypes.cast(self._wndproc, ctypes.c_void_p).value)
        except Exception:
            pass

    def _on_raw_input(self, hwnd, msg, wparam, lparam):
        if msg == 0x00FF and self.recording:  # WM_INPUT
            try:
                size = ctypes.c_uint(0)
                _u32.GetRawInputData(lparam, 0x10000003, None, ctypes.byref(size),
                                     ctypes.sizeof(_RAWINPUTHEADER))
                if size.value:
                    buf = (ctypes.c_byte * size.value)()
                    _u32.GetRawInputData(lparam, 0x10000003, buf, ctypes.byref(size),
                                         ctypes.sizeof(_RAWINPUTHEADER))
                    ri = ctypes.cast(buf, ctypes.POINTER(_RAWINPUT)).contents
                    if ri.header.dwType == 0 and not (ri.mouse.usFlags & 0x01):
                        dx, dy = ri.mouse.lLastX, ri.mouse.lLastY
                        if dx or dy:
                            t = self._t()
                            last = self.events[-1] if self.events else None
                            # รวมเดลต้าที่ติดกันภายใน 2ms ไว้ก้อนเดียว ไฟล์ไม่บวม
                            if (last is not None and last.get("e") == "rmove"
                                    and t - last["t"] < 0.002):
                                last["dx"] += dx
                                last["dy"] += dy
                            else:
                                self.events.append({"t": t, "e": "rmove",
                                                    "dx": dx, "dy": dy})
            except Exception:
                pass
        return _u32.CallWindowProcW(self._old_wndproc, hwnd, msg, wparam, lparam)

    # ---------------- Hotkeys ----------------
    def _on_hotkey(self, key):
        if key == keyboard.Key.f3:
            self.root.after(0, self.toggle_record)
        elif key == keyboard.Key.f4:
            # F10 = สลับ เล่น/หยุด
            if self.playing:
                self.stop_flag.set()
            else:
                self.root.after(0, self.play_selected)
        elif key == keyboard.Key.f6:
            # แสดง/ซ่อนกรอบตรวจจับบนหน้าจอ (ลากย้าย-ปรับขนาดได้)
            self.root.after(0, self._toggle_mark)
        elif key == keyboard.Key.esc:
            self.stop_flag.set()

    # ---------------- Recording ----------------
    def toggle_record(self):
        if self.playing:
            return
        if self.recording:
            self._stop_record()
        else:
            self._start_record()

    def _start_record(self):
        self._close_mark()  # ซ่อนกรอบ mark กันโดนอัดติดไป
        self.events = []
        self.recording = True
        self.t0 = time.perf_counter()
        self.last_move_t = 0.0
        self._set_status(self.tr("recording"), C["red"])
        self.btn_rec.config(text=self.tr("stop_record"))

        self.mouse_listener = mouse.Listener(
            on_move=self._rec_move, on_click=self._rec_click, on_scroll=self._rec_scroll)
        self.kb_listener = keyboard.Listener(
            on_press=self._rec_key_press, on_release=self._rec_key_release)
        self.mouse_listener.start()
        self.kb_listener.start()

    def _stop_record(self):
        self.recording = False
        if self.mouse_listener:
            self.mouse_listener.stop()
        if self.kb_listener:
            self.kb_listener.stop()
        self._set_status(self.tr("ready"), C["green"])
        self.btn_rec.config(text=self.tr("record"))

        if not self.events:
            return
        # เหตุการณ์มาจากหลายเธรด เรียงตามเวลาให้ชัวร์ก่อนเซฟ
        self.events.sort(key=lambda ev: ev["t"])
        # เซฟอัตโนมัติด้วยชื่อเวลา ไม่มีป๊อปอัปถาม (เปลี่ยนชื่อทีหลังได้)
        name = time.strftime("macro_%Y%m%d_%H%M%S")
        path = os.path.join(MACRO_DIR, name + ".json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.events, f, ensure_ascii=False)
        except OSError as e:
            messagebox.showerror(self.tr("save_fail"),
                                 self.tr("save_fail_m").format(path=path, err=e),
                                 parent=self.root)
            return
        self._refresh_list()
        # โชว์ "บันทึกแล้ว" 1 วินาทีแล้วกลับเป็นปกติ
        self._set_status(self.tr("saved"), C["green"])

        def back_to_ready():
            if not self.recording and not self.playing:
                self._set_status(self.tr("ready"), C["green"])
        self.root.after(1000, back_to_ready)

    def _t(self):
        return round(time.perf_counter() - self.t0, 4)

    def _rec_move(self, x, y):
        if not self.recording:
            return
        now = time.perf_counter()
        if now - self.last_move_t >= MOVE_INTERVAL:
            self.last_move_t = now
            self.events.append({"t": self._t(), "e": "move", "x": x, "y": y})

    def _rec_click(self, x, y, button, pressed):
        if not self.recording:
            return
        self.events.append({"t": self._t(), "e": "click", "x": x, "y": y,
                            "b": button.name, "p": pressed})

    def _rec_scroll(self, x, y, dx, dy):
        if not self.recording:
            return
        self.events.append({"t": self._t(), "e": "scroll", "x": x, "y": y, "dx": dx, "dy": dy})

    @staticmethod
    def _key_to_str(key):
        if isinstance(key, keyboard.KeyCode):
            # บันทึกเป็นรหัสปุ่มจริง (vk) เสมอ -> เล่นซ้ำเป็นการ "กดปุ่ม" จริงๆ
            # ไม่ใช่ "พิมพ์ตัวอักษร" จึงกดหลายปุ่มค้างพร้อมกันได้ ไม่ตีกับ Shift/Ctrl
            if key.vk is not None:
                return {"vk": key.vk}
            if key.char is not None:
                return {"c": key.char}
            return {}
        return {"k": key.name}

    def _rec_key_press(self, key):
        if not self.recording or key in HOTKEYS:
            return
        self.events.append({"t": self._t(), "e": "kd", **self._key_to_str(key)})

    def _rec_key_release(self, key):
        if not self.recording or key in HOTKEYS:
            return
        self.events.append({"t": self._t(), "e": "ku", **self._key_to_str(key)})

    # ---------------- Playback ----------------
    def toggle_play(self):
        if self.playing:
            self.stop_flag.set()
        else:
            self.play_selected()

    def play_selected(self):
        if self.recording or self.playing:
            return
        path = self._selected_file()
        if not path or not os.path.exists(path):
            messagebox.showwarning(self.tr("no_macro_t"), self.tr("no_macro_m"),
                                   parent=self.root)
            return
        with open(path, encoding="utf-8") as f:
            events = json.load(f)
        loops = None if self.inf_var.get() else max(1, self.loop_var.get())
        speed = float(self.speed_var.get().rstrip("x"))
        gap = max(0.0, self.gap_var.get())

        self.playing = True
        self.stop_flag.clear()
        self._pressed_btns.clear()
        self._pressed_keys.clear()
        self._game_mode = self.game_var.get()
        # ตัวคูณการหัน: เล่นเดลต้าดิบเหมือนตอนอัด ปกติตั้ง 1.0 พอดีเป๊ะ
        try:
            self._game_sens = float(self.cam_sens_var.get())
        except Exception:
            self._game_sens = 1.0
        if self._game_sens <= 0:
            self._game_sens = 1.0
        self._rem = [0.0, 0.0]
        self._play_start = time.perf_counter()
        self._play_duration = 0
        self.root.after(100, self._tick_progress)
        # อ่านค่า "รอหลังกด" ที่ผู้ใช้ตั้ง
        try:
            self._tds_wait = max(0.0, float(self.wait_var.get()))
        except Exception:
            self._tds_wait = 2.0
        # ซ่อนกรอบ mark ก่อนเล่น (กันสีเขียวของกรอบเองหลอกตัวตรวจจับ)
        self._close_mark()
        # เริ่มเธรดเฝ้าจับปุ่ม Restart (TDS)
        self._restart_pending = False
        threading.Thread(target=self._tds_monitor, daemon=True).start()
        threading.Thread(target=self._play_thread,
                         args=(events, loops, speed, gap, os.path.basename(path)[:-5]),
                         daemon=True).start()

    def _play_thread(self, events, loops, speed, gap, name):
        try:
            i = 0
            while not self.stop_flag.is_set():
                i += 1
                total = "∞" if loops is None else str(loops)
                self._set_status(self.tr("playing").format(name=name, i=i, total=total),
                                 C["blue"])
                self._play_once(events, speed)
                if self._restart_pending:
                    # เจอปุ่ม Restart: หยุดทุกอย่าง -> คลิกปุ่ม -> รอ 2 วิ -> เริ่มรอบใหม่
                    self._release_all()
                    self._set_status(self.tr("tds_found"), C["green"])
                    self.stop_flag.clear()
                    self._click_restart()
                    # พักตัวตรวจจับ = เวลารอ + 4 วิ (กันเด้งซ้ำตอนเกมกำลังโหลด)
                    self._tds_cool = time.perf_counter() + self._tds_wait + 4.0
                    # รอตามวินาทีที่ผู้ใช้ตั้ง (กด F4/Esc ระหว่างรอ = หยุดจริง)
                    if self.stop_flag.wait(timeout=max(0.05, self._tds_wait)):
                        break
                    self._restart_pending = False
                    i -= 1  # รอบที่ถูกขัดจังหวะให้เล่นใหม่ ไม่นับ
                    continue
                if self.stop_flag.is_set():
                    break
                if loops is not None and i >= loops:
                    break
                if gap > 0 and self.stop_flag.wait(timeout=gap):
                    break
        finally:
            self._release_all()
            self.playing = False
            self._set_status(self.tr("ready"), C["green"])

    def _wait_until(self, target):
        """รอจนถึงเวลา target แบบแม่นยำสูง คืนค่า True ถ้าถูกสั่งหยุด"""
        while True:
            remain = target - time.perf_counter()
            if remain <= 0:
                return False
            if remain > 0.003:
                if self.stop_flag.wait(timeout=remain - 0.002):
                    return True
            else:
                if self.stop_flag.is_set():
                    return True
                # หลับสั้นๆ แทน busy-spin -> สายเมาส์ไม่แย่ง CPU จนสายคีย์บอร์ดค้าง
                time.sleep(0.0002)

    def _move_to(self, x, y):
        if send_mouse_move is not None:
            send_mouse_move(x, y)
        else:
            self.mouse_ctl.position = (x, y)

    def _in_camera_drag(self):
        # Roblox หมุนกล้องเฉพาะตอนคลิกขวาค้าง
        return self._game_mode and Button.right in self._pressed_btns

    def _do_mouse_event(self, ev):
        e = ev["e"]
        if e == "rmove":
            # เดลต้าดิบจากตอนอัด -> ใช้เฉพาะช่วงคลิกขวาค้างในโหมด Roblox
            if self._in_camera_drag() and send_mouse_move_rel is not None:
                fx = ev["dx"] * self._game_sens + self._rem[0]
                fy = ev["dy"] * self._game_sens + self._rem[1]
                dx, dy = int(fx), int(fy)
                self._rem[0] = fx - dx
                self._rem[1] = fy - dy
                if dx or dy:
                    send_mouse_move_rel(dx, dy)
            return
        if e == "move":
            if self._in_camera_drag():
                return  # ช่วงหมุนกล้องใช้ rmove แทน ตำแหน่งจอไม่เกี่ยว
            self._move_to(ev["x"], ev["y"])
        elif e == "click":
            btn = getattr(Button, ev["b"], Button.left)
            # กันกล้องสะบัด: ระหว่างหมุนกล้อง และตอนปล่อยคลิกขวา
            # ห้าม jump ตำแหน่งเด็ดขาด (ปล่อยปุ่มที่ตำแหน่งปัจจุบันเลย)
            skip_move = self._game_mode and (
                self._in_camera_drag()
                or (btn == Button.right and not ev["p"]))
            if not skip_move:
                self._move_to(ev["x"], ev["y"])
            if ev["p"]:
                self.mouse_ctl.press(btn)
                self._pressed_btns.add(btn)
            else:
                self.mouse_ctl.release(btn)
                self._pressed_btns.discard(btn)
        elif e == "scroll":
            self.mouse_ctl.scroll(ev["dx"], ev["dy"])

    def _do_kb_event(self, ev):
        down = ev["e"] == "kd"
        # ใช้ scancode injection บน Windows (เกมมองเห็น) ถ้ามี vk
        if send_key is not None:
            vk = ev.get("vk")
            if vk is None and "k" in ev:
                k = getattr(Key, ev["k"], None)
                if k is not None and getattr(k.value, "vk", None) is not None:
                    vk = k.value.vk
            if vk is not None:
                try:
                    send_key(vk, down)
                    if down:
                        self._pressed_keys.add(vk)
                    else:
                        self._pressed_keys.discard(vk)
                except Exception:
                    pass
                return
        # fallback: macro เก่า/ระบบอื่น
        key = self._str_to_key(ev)
        if key is None:
            return
        try:
            if down:
                self.kb_ctl.press(key)
                self._pressed_keys.add(key)
            else:
                self.kb_ctl.release(key)
                self._pressed_keys.discard(key)
        except Exception:
            pass

    def _run_stream(self, events, speed, start, handler):
        """เล่นสายเหตุการณ์หนึ่งสาย (เมาส์หรือคีย์บอร์ด) ตามเวลาจริง"""
        for ev in events:
            if self.stop_flag.is_set():
                return
            if self._wait_until(start + ev["t"] / speed):
                return
            handler(ev)

    def _play_once(self, events, speed):
        # แยกเมาส์กับคีย์บอร์ดเป็น 2 สายขนานกัน ซิงค์เวลาเริ่มเดียวกัน
        # -> ลากเมาส์/คลิกค้าง พร้อมพิมพ์คีย์บอร์ดไปด้วยกันได้จริง
        mouse_events = [ev for ev in events
                        if ev["e"] in ("move", "click", "scroll", "rmove")]
        kb_events = [ev for ev in events if ev["e"] in ("kd", "ku")]
        start = time.perf_counter()
        # สำหรับหลอดความคืบหน้า
        self._play_start = start
        self._play_duration = (events[-1]["t"] / speed) if events else 0
        kb_thread = None
        if kb_events:
            kb_thread = threading.Thread(
                target=self._run_stream, args=(kb_events, speed, start, self._do_kb_event),
                daemon=True)
            kb_thread.start()
        self._run_stream(mouse_events, speed, start, self._do_mouse_event)
        if kb_thread:
            kb_thread.join()

    @staticmethod
    def _str_to_key(ev):
        if "vk" in ev:
            return keyboard.KeyCode.from_vk(ev["vk"])
        if "c" in ev:  # รองรับ macro เก่า
            ch = ev["c"]
            if ch and 1 <= ord(ch) <= 26:
                return chr(ord(ch) + 96)
            return ch
        if "k" in ev:
            return getattr(Key, ev["k"], None)
        return None

    def _release_all(self):
        # ปล่อยเฉพาะปุ่ม/คีย์ที่ยังกดค้างจริงเท่านั้น
        # (การส่ง release ปุ่มขวาโดยไม่เคยกด จะกลายเป็นคลิกขวาเอง — บั๊กเดิม)
        for k in list(self._pressed_keys):
            try:
                if isinstance(k, int) and send_key is not None:
                    send_key(k, False)
                else:
                    self.kb_ctl.release(k)
            except Exception:
                pass
        self._pressed_keys.clear()
        for b in list(self._pressed_btns):
            try:
                self.mouse_ctl.release(b)
            except Exception:
                pass
        self._pressed_btns.clear()

    def stop_all(self):
        self.stop_flag.set()
        if self.recording:
            self._stop_record()

    # ---------------- TDS: ตรวจจับปุ่ม Restart สีเขียว ----------------
    # จุดตรวจ 10 จุด คิดเป็น "สัดส่วน" ของกรอบ -> ปรับขนาดกรอบแล้วจุดขยับตามเอง
    # กระจายเลี่ยงตัวหนังสือสีขาวตรงกลางปุ่ม
    TDS_FRAC = ((-0.42, 0.0), (0.42, 0.0), (-0.36, -0.28), (-0.36, 0.28),
                (0.36, -0.28), (0.36, 0.28), (0.0, -0.33), (0.0, 0.33),
                (-0.20, 0.30), (0.20, -0.30))

    def _tds_points(self):
        r = self.tds_rect
        cx, cy = r["x"] + r["w"] / 2, r["y"] + r["h"] / 2
        return [(int(cx + fx * r["w"]), int(cy + fy * r["h"]))
                for fx, fy in self.TDS_FRAC]

    def _update_tds_lbl(self):
        r = self.tds_rect
        self.tds_lbl.config(text=f"{r['w']}×{r['h']} @ ({r['x']},{r['y']})")

    @staticmethod
    def _is_green(rgb):
        r, g, b = rgb
        return g >= 90 and g > r + 40 and g > b + 40

    def _tds_check(self):
        """เขียวอย่างน้อย 5 จาก 10 จุดในกรอบ = เจอปุ่ม Restart"""
        if get_pixel is None:
            return False
        hit = 0
        for x, y in self._tds_points():
            try:
                if self._is_green(get_pixel(x, y)):
                    hit += 1
                    if hit >= 5:
                        return True
            except Exception:
                return False
        return False

    def _tds_monitor(self):
        """เธรดเฝ้าจอระหว่างเล่น: ต้องเจอ 2 ครั้งติดกัน (กันภาพแวบ) จึงสั่ง restart"""
        consec = 0
        while self.playing:
            if (self.tds_var.get() and not self._restart_pending
                    and time.perf_counter() > getattr(self, "_tds_cool", 0)):
                if self._tds_check():
                    consec += 1
                    if consec >= 2:
                        self._restart_pending = True
                        self.stop_flag.set()  # หยุดการเล่นทั้งหมดทันที
                else:
                    consec = 0
            time.sleep(0.4)  # ตรวจทุก 0.4 วินาที

    def _click_restart(self):
        r = self.tds_rect
        x, y = r["x"] + r["w"] // 2, r["y"] + r["h"] // 2
        off = r["h"] * 3  # ระยะขยับขึ้น-ลง = 3 เท่าของความสูงกรอบ
        # วาร์ปไปที่ปุ่มก่อน
        self._move_to(x, y)
        time.sleep(0.3)
        # ขยับ "ออกจากปุ่ม" (ขึ้นด้านบน) แล้วไหลกลับลงมาที่เดิมแบบทีละสเต็ป
        # เพื่อให้ปุ่มเห็นเมาส์เคลื่อนเข้ามาจริงๆ -> hover/animation ทำงาน ปุ่มถึงรับคลิก
        steps = 12
        for i in range(1, steps + 1):        # ขึ้นออกนอกปุ่ม
            self._move_to(x, y - off * i / steps)
            time.sleep(0.02)
        time.sleep(0.15)
        for i in range(steps - 1, -1, -1):   # ไหลกลับลงมากลางปุ่ม
            self._move_to(x, y - off * i / steps)
            time.sleep(0.02)
        time.sleep(0.4)  # ให้ animation ปุ่มทำงานจนเสร็จ
        self._move_to(x, y)  # ยืนยันตำแหน่งกลางปุ่มอีกครั้ง
        time.sleep(0.05)
        try:
            if send_left is not None:
                send_left(True)
                time.sleep(0.12)
                send_left(False)
                time.sleep(0.05)
                send_left(False)  # ส่งปล่อยซ้ำอีกครั้ง กันปุ่มค้าง
            else:
                self.mouse_ctl.press(Button.left)
                time.sleep(0.12)
                self.mouse_ctl.release(Button.left)
        finally:
            # ไม่ว่ายังไงก็ต้องปล่อยปุ่มเสมอ
            try:
                self.mouse_ctl.release(Button.left)
            except Exception:
                pass

    # ---------------- กรอบ Mark บนหน้าจอ (ลากย้าย/ปรับขนาดได้) ----------------
    def _toggle_mark(self):
        if self._mark is not None and self._mark.winfo_exists():
            self._close_mark()
        else:
            self._show_mark()

    def _show_mark(self):
        r = self.tds_rect
        m = tk.Toplevel(self.root)
        self._mark = m
        m.overrideredirect(True)          # ไม่มีขอบหน้าต่าง
        m.attributes("-topmost", True)
        key = "#010203"                   # สีนี้จะกลายเป็นโปร่งใส
        m.config(bg=key)
        try:
            m.attributes("-transparentcolor", key)
        except Exception:
            m.attributes("-alpha", 0.35)  # fallback: โปร่งแสงทั้งบาน
        m.geometry(f"{r['w']}x{r['h']}+{r['x']}+{r['y']}")
        cv = tk.Canvas(m, bg=key, highlightthickness=0, cursor="fleur")
        cv.pack(fill="both", expand=True)
        self._mark_cv = cv
        cv.bind("<Button-1>", self._mark_press)
        cv.bind("<B1-Motion>", self._mark_drag)
        cv.bind("<ButtonRelease-1>", self._mark_release)
        m.bind("<Configure>", lambda e: self._draw_mark())
        self._draw_mark()

    def _draw_mark(self):
        if self._mark is None or not self._mark.winfo_exists():
            return
        cv = self._mark_cv
        w = max(self._mark.winfo_width(), 1)
        h = max(self._mark.winfo_height(), 1)
        g = "#22c55e"
        cv.delete("all")
        # กรอบหนา 5px (จับลากย้ายได้)
        cv.create_rectangle(2, 2, w - 2, h - 2, outline=g, width=5)
        # แถบหัวด้านบน ไว้จับลากสะดวกๆ
        cv.create_rectangle(0, 0, w, 16, fill=g, outline=g)
        cv.create_text(w // 2, 8, text="RESTART ZONE  (ลากย้าย · มุมขวาล่างปรับขนาด)",
                       fill="#06270f", font=("Segoe UI", 7, "bold"))
        # มุมขวาล่างสำหรับปรับขนาด
        cv.create_rectangle(w - 16, h - 16, w, h, fill=g, outline=g)

    def _mark_press(self, e):
        m = self._mark
        w, h = m.winfo_width(), m.winfo_height()
        self._mk_mode = "resize" if (e.x > w - 18 and e.y > h - 18) else "move"
        self._mk_start = (e.x_root, e.y_root, m.winfo_x(), m.winfo_y(), w, h)

    def _mark_drag(self, e):
        sx, sy, x0, y0, w0, h0 = self._mk_start
        dx, dy = e.x_root - sx, e.y_root - sy
        if self._mk_mode == "move":
            self._mark.geometry(f"+{x0 + dx}+{y0 + dy}")
        else:
            self._mark.geometry(f"{max(60, w0 + dx)}x{max(28, h0 + dy)}")

    def _mark_release(self, e):
        m = self._mark
        self.tds_rect = {"x": m.winfo_x(), "y": m.winfo_y(),
                         "w": m.winfo_width(), "h": m.winfo_height()}
        self.cfg["tds_rect"] = self.tds_rect
        save_settings(self.cfg)
        self._update_tds_lbl()
        self._set_status(self.tr("tds_saved"), C["green"])

        def back():
            if not self.recording and not self.playing:
                self._set_status(self.tr("ready"), C["green"])
        self.root.after(1200, back)

    def _close_mark(self):
        try:
            if self._mark is not None:
                self._mark.destroy()
        except Exception:
            pass
        self._mark = None

    # ---------------- Manage ----------------
    def rename_macro(self):
        path = self._selected_file()
        if not path:
            return
        old = os.path.basename(path)[:-5]
        new = simpledialog.askstring(self.tr("rename_t"), self.tr("rename_m"),
                                     initialvalue=old, parent=self.root)
        if new and new != old:
            os.rename(path, os.path.join(MACRO_DIR, new + ".json"))
            self._refresh_list()

    def delete_macro(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        names = [self.listbox.get(i).strip() for i in sel]
        for n in names:
            try:
                os.remove(os.path.join(MACRO_DIR, n + ".json"))
            except OSError:
                pass
        self._refresh_list()


if __name__ == "__main__":
    root = tk.Tk()
    app = MacroApp(root)
    root.mainloop()
