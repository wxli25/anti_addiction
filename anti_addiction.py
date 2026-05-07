"""
防沉迷守卫 - Anti-Addiction Guard
Windows 游戏时间管理工具
依赖: pip install psutil pystray Pillow
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import psutil
import json
import os
import sys
import time
import threading
import hashlib
import winreg
from datetime import datetime, date
from pathlib import Path

try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False

# ── 数据路径 ──────────────────────────────────────────────
DATA_DIR = Path(os.environ.get("APPDATA", ".")) / "AntiAddictionGuard"
DATA_DIR.mkdir(exist_ok=True)
CONFIG_FILE = DATA_DIR / "config.json"
LOG_FILE = DATA_DIR / "usage_log.json"

# ── 默认配置 ──────────────────────────────────────────────
DEFAULT_CONFIG = {
    "password_hash": "",
    "programs": {},   # { "exe_name": { "path": ..., "limit_minutes": 60, "display_name": ... } }
    "autostart": False,
}

# ══════════════════════════════════════════════════════════
#  工具函数
# ══════════════════════════════════════════════════════════
def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)

def save_config(cfg: dict):
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

def load_log() -> dict:
    if LOG_FILE.exists():
        try:
            return json.loads(LOG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def save_log(log: dict):
    LOG_FILE.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")

def today_str() -> str:
    return str(date.today())

def set_autostart(enable: bool):
    """写入/删除注册表启动项"""
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "AntiAddictionGuard"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        if enable:
            exe = sys.executable
            script = os.path.abspath(__file__)
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, f'"{exe}" "{script}" --minimized')
        else:
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception:
        pass

# ══════════════════════════════════════════════════════════
#  监控线程
# ══════════════════════════════════════════════════════════
class Monitor(threading.Thread):
    def __init__(self, app):
        super().__init__(daemon=True)
        self.app = app
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        while not self._stop:
            cfg = self.app.config
            log = load_log()
            today = today_str()
            if today not in log:
                log[today] = {}

            # 扫描正在运行的进程
            running_exes = {}
            for proc in psutil.process_iter(["name", "exe"]):
                try:
                    n = proc.info["name"].lower() if proc.info["name"] else ""
                    running_exes[n] = proc
                except Exception:
                    pass

            changed = False
            for exe_key, info in cfg.get("programs", {}).items():
                exe_name = exe_key.lower()
                limit = info.get("limit_minutes", 60) * 60  # 转秒
                today_used = log[today].get(exe_key, 0)

                if exe_name in running_exes:
                    proc = running_exes[exe_name]
                    if today_used >= limit:
                        # 超时 → 杀进程
                        try:
                            proc.kill()
                            self.app.after(0, lambda n=info.get("display_name", exe_key):
                                self.app.show_timeout_warning(n))
                        except Exception:
                            pass
                    else:
                        # 累计 1 秒
                        log[today][exe_key] = today_used + 1
                        changed = True

            if changed:
                save_log(log)
                self.app.after(0, self.app.refresh_usage)

            time.sleep(1)

# ══════════════════════════════════════════════════════════
#  主窗口 UI
# ══════════════════════════════════════════════════════════
class App(tk.Tk):
    ACCENT   = "#FF4757"
    BG       = "#0F0F1A"
    CARD     = "#1A1A2E"
    BORDER   = "#2A2A45"
    TEXT     = "#E8E8F0"
    MUTED    = "#6B6B8A"
    GREEN    = "#2ED573"
    YELLOW   = "#FFA502"

    def __init__(self):
        super().__init__()
        self.config_data = load_config()
        self._monitor = None
        self._tray = None
        self._build_ui()
        self._start_monitor()
        self.refresh_usage()

        if "--minimized" in sys.argv:
            self.after(200, self._hide_to_tray)

    # ── UI 构建 ─────────────────────────────────────────
    def _build_ui(self):
        self.title("防沉迷守卫")
        self.geometry("680x560")
        self.minsize(640, 500)
        self.configure(bg=self.BG)
        self.resizable(True, True)

        # 字体
        self.font_title  = ("Microsoft YaHei UI", 20, "bold")
        self.font_label  = ("Microsoft YaHei UI", 10)
        self.font_small  = ("Microsoft YaHei UI", 9)
        self.font_mono   = ("Consolas", 9)

        # 顶部标题栏
        header = tk.Frame(self, bg=self.BG)
        header.pack(fill="x", padx=24, pady=(20, 0))
        tk.Label(header, text="🛡  防沉迷守卫", font=self.font_title,
                 bg=self.BG, fg=self.TEXT).pack(side="left")
        status_frame = tk.Frame(header, bg=self.BG)
        status_frame.pack(side="right", pady=6)
        self.status_dot = tk.Label(status_frame, text="●", font=("", 12),
                                   bg=self.BG, fg=self.GREEN)
        self.status_dot.pack(side="left")
        tk.Label(status_frame, text=" 监控中", font=self.font_small,
                 bg=self.BG, fg=self.MUTED).pack(side="left")

        # 分割线
        tk.Frame(self, bg=self.BORDER, height=1).pack(fill="x", padx=24, pady=12)

        # 程序列表区
        list_card = tk.Frame(self, bg=self.CARD, bd=0, highlightthickness=1,
                             highlightbackground=self.BORDER)
        list_card.pack(fill="both", expand=True, padx=24, pady=(0, 8))

        # 列表标题
        list_header = tk.Frame(list_card, bg=self.CARD)
        list_header.pack(fill="x", padx=14, pady=(10, 4))
        tk.Label(list_header, text="已监控程序", font=("Microsoft YaHei UI", 11, "bold"),
                 bg=self.CARD, fg=self.TEXT).pack(side="left")
        btn_add = tk.Button(list_header, text="＋ 添加程序",
                            font=self.font_small, bg=self.ACCENT, fg="white",
                            relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
                            command=self._add_program)
        btn_add.pack(side="right")

        # 列表容器（可滚动）
        frame_wrap = tk.Frame(list_card, bg=self.CARD)
        frame_wrap.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        canvas = tk.Canvas(frame_wrap, bg=self.CARD, highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame_wrap, orient="vertical", command=canvas.yview)
        self.list_frame = tk.Frame(canvas, bg=self.CARD)
        self.list_frame.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.list_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._canvas = canvas

        # 底部按钮栏
        bottom = tk.Frame(self, bg=self.BG)
        bottom.pack(fill="x", padx=24, pady=(0, 16))

        # 开机自启
        self.autostart_var = tk.BooleanVar(value=self.config_data.get("autostart", False))
        chk = tk.Checkbutton(bottom, text="开机自动启动（最小化到托盘）",
                             variable=self.autostart_var,
                             font=self.font_small, bg=self.BG, fg=self.MUTED,
                             selectcolor=self.CARD, activebackground=self.BG,
                             command=self._toggle_autostart)
        chk.pack(side="left")

        btn_pwd = tk.Button(bottom, text="🔒 设置密码",
                            font=self.font_small, bg=self.CARD, fg=self.TEXT,
                            relief="flat", bd=0, padx=10, pady=6, cursor="hand2",
                            highlightthickness=1, highlightbackground=self.BORDER,
                            command=self._set_password)
        btn_pwd.pack(side="right", padx=(8, 0))

        btn_tray = tk.Button(bottom, text="最小化到托盘",
                             font=self.font_small, bg=self.CARD, fg=self.TEXT,
                             relief="flat", bd=0, padx=10, pady=6, cursor="hand2",
                             highlightthickness=1, highlightbackground=self.BORDER,
                             command=self._hide_to_tray)
        btn_tray.pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._hide_to_tray)
        self._render_list()

    # ── 程序列表渲染 ────────────────────────────────────
    def _render_list(self):
        for w in self.list_frame.winfo_children():
            w.destroy()

        programs = self.config_data.get("programs", {})
        if not programs:
            tk.Label(self.list_frame,
                     text="暂无监控程序，点击「＋ 添加程序」开始",
                     font=self.font_label, bg=self.CARD, fg=self.MUTED,
                     pady=30).pack()
            return

        log = load_log()
        today = today_str()
        today_log = log.get(today, {})

        for exe_key, info in programs.items():
            self._render_row(exe_key, info, today_log.get(exe_key, 0))

    def _render_row(self, exe_key: str, info: dict, used_seconds: int):
        limit_sec = info.get("limit_minutes", 60) * 60
        pct = min(used_seconds / limit_sec, 1.0) if limit_sec > 0 else 0
        used_m = used_seconds // 60
        limit_m = info.get("limit_minutes", 60)
        remaining = max(limit_m - used_m, 0)

        row = tk.Frame(self.list_frame, bg=self.CARD, pady=2)
        row.pack(fill="x", padx=6, pady=3)

        inner = tk.Frame(row, bg="#222240", pady=10, padx=14)
        inner.pack(fill="x")

        # 名称行
        top_row = tk.Frame(inner, bg="#222240")
        top_row.pack(fill="x")

        name = info.get("display_name", exe_key)
        tk.Label(top_row, text=f"🎮  {name}", font=("Microsoft YaHei UI", 10, "bold"),
                 bg="#222240", fg=self.TEXT).pack(side="left")

        # 状态标签
        if pct >= 1.0:
            tag_color, tag_text = self.ACCENT, "已达上限"
        elif pct >= 0.8:
            tag_color, tag_text = self.YELLOW, f"剩 {remaining} 分钟"
        else:
            tag_color, tag_text = self.GREEN, f"剩 {remaining} 分钟"

        tk.Label(top_row, text=tag_text, font=self.font_small,
                 bg=tag_color, fg="white", padx=6, pady=2).pack(side="right")

        # 删除按钮
        tk.Button(top_row, text="✕", font=self.font_small,
                  bg="#222240", fg=self.MUTED, relief="flat", bd=0,
                  cursor="hand2",
                  command=lambda k=exe_key: self._remove_program(k)).pack(
                      side="right", padx=(0, 8))

        # 修改时限按钮
        tk.Button(top_row, text="⏱ 修改时限", font=self.font_small,
                  bg="#222240", fg=self.MUTED, relief="flat", bd=0,
                  cursor="hand2",
                  command=lambda k=exe_key, i=info: self._edit_limit(k, i)).pack(
                      side="right", padx=(0, 4))

        # 进度条区域
        bar_frame = tk.Frame(inner, bg="#222240")
        bar_frame.pack(fill="x", pady=(8, 0))

        tk.Label(bar_frame, text=f"{used_m} 分钟 / {limit_m} 分钟",
                 font=self.font_mono, bg="#222240", fg=self.MUTED).pack(side="right")

        bar_bg = tk.Frame(bar_frame, bg=self.BORDER, height=6)
        bar_bg.pack(side="left", fill="x", expand=True, padx=(0, 12), pady=4)
        bar_bg.update_idletasks()
        w = int(bar_bg.winfo_width() * pct) or int(300 * pct)
        tk.Frame(bar_bg, bg=tag_color, height=6, width=max(w, 0)).place(x=0, y=0)

        # 路径提示
        path = info.get("path", exe_key)
        tk.Label(inner, text=path, font=self.font_mono,
                 bg="#222240", fg=self.MUTED, anchor="w").pack(fill="x", pady=(4, 0))

    # ── 刷新用量 ────────────────────────────────────────
    def refresh_usage(self):
        self._render_list()

    # ── 添加程序 ────────────────────────────────────────
    def _add_program(self):
        if not self._auth():
            return

        path = filedialog.askopenfilename(
            title="选择要监控的游戏/程序",
            filetypes=[("可执行文件", "*.exe"), ("所有文件", "*.*")]
        )
        if not path:
            return

        exe_name = os.path.basename(path)
        display = simpledialog.askstring("显示名称", f"程序名称（默认：{exe_name}）：",
                                         initialvalue=exe_name.replace(".exe", ""))
        if display is None:
            return

        limit = simpledialog.askinteger("每日时限",
                                        "每天最多游玩多少分钟？",
                                        initialvalue=60, minvalue=1, maxvalue=1440)
        if limit is None:
            return

        self.config_data.setdefault("programs", {})[exe_name.lower()] = {
            "path": path,
            "display_name": display or exe_name,
            "limit_minutes": limit,
        }
        save_config(self.config_data)
        self._render_list()

    # ── 删除程序 ────────────────────────────────────────
    def _remove_program(self, exe_key: str):
        if not self._auth():
            return
        if messagebox.askyesno("确认", f"移除对「{exe_key}」的监控？"):
            self.config_data.get("programs", {}).pop(exe_key, None)
            save_config(self.config_data)
            self._render_list()

    # ── 修改时限 ────────────────────────────────────────
    def _edit_limit(self, exe_key: str, info: dict):
        if not self._auth():
            return
        new_limit = simpledialog.askinteger(
            "修改每日时限",
            f"「{info.get('display_name', exe_key)}」每天最多游玩多少分钟？",
            initialvalue=info.get("limit_minutes", 60),
            minvalue=1, maxvalue=1440
        )
        if new_limit is not None:
            self.config_data["programs"][exe_key]["limit_minutes"] = new_limit
            save_config(self.config_data)
            self._render_list()

    # ── 密码验证 ────────────────────────────────────────
    def _auth(self) -> bool:
        pw_hash = self.config_data.get("password_hash", "")
        if not pw_hash:
            return True
        pw = simpledialog.askstring("验证密码", "请输入管理密码：", show="*")
        if pw is None:
            return False
        if hash_password(pw) != pw_hash:
            messagebox.showerror("错误", "密码错误！")
            return False
        return True

    def _set_password(self):
        if not self._auth():
            return
        new_pw = simpledialog.askstring("设置密码", "新密码（留空则取消密码保护）：", show="*")
        if new_pw is None:
            return
        self.config_data["password_hash"] = hash_password(new_pw) if new_pw else ""
        save_config(self.config_data)
        messagebox.showinfo("完成", "密码已更新！" if new_pw else "密码保护已关闭。")

    # ── 自启设置 ────────────────────────────────────────
    def _toggle_autostart(self):
        val = self.autostart_var.get()
        self.config_data["autostart"] = val
        save_config(self.config_data)
        set_autostart(val)

    # ── 超时提示 ────────────────────────────────────────
    def show_timeout_warning(self, name: str):
        win = tk.Toplevel(self)
        win.title("时间到！")
        win.configure(bg=self.BG)
        win.geometry("380x180")
        win.attributes("-topmost", True)
        win.resizable(False, False)
        tk.Label(win, text="⏰  今日时间已用完", font=("Microsoft YaHei UI", 14, "bold"),
                 bg=self.BG, fg=self.ACCENT, pady=20).pack()
        tk.Label(win, text=f"「{name}」今日游玩时间已达上限\n已自动关闭，明天再玩吧！",
                 font=self.font_label, bg=self.BG, fg=self.TEXT, justify="center").pack()
        tk.Button(win, text="好的，我去学习了 📚",
                  font=self.font_label, bg=self.ACCENT, fg="white",
                  relief="flat", bd=0, padx=16, pady=8, cursor="hand2",
                  command=win.destroy).pack(pady=16)

    # ── 系统托盘 ────────────────────────────────────────
    def _hide_to_tray(self):
        self.withdraw()
        if TRAY_AVAILABLE and self._tray is None:
            self._tray = self._create_tray()
            t = threading.Thread(target=self._tray.run, daemon=True)
            t.start()

    def _show_from_tray(self):
        self.deiconify()
        self.lift()

    def _quit_app(self):
        if self._tray:
            self._tray.stop()
        self.destroy()

    def _create_tray(self):
        img = Image.new("RGB", (64, 64), color=(15, 15, 26))
        draw = ImageDraw.Draw(img)
        draw.ellipse([8, 8, 56, 56], fill=(255, 71, 87))
        draw.text((20, 18), "守", fill="white")
        menu = pystray.Menu(
            pystray.MenuItem("打开界面", lambda: self.after(0, self._show_from_tray), default=True),
            pystray.MenuItem("退出", lambda: self.after(0, self._quit_app)),
        )
        return pystray.Icon("AntiAddiction", img, "防沉迷守卫 - 监控中", menu)

    # ── 监控线程 ────────────────────────────────────────
    def _start_monitor(self):
        self._monitor = Monitor(self)
        self._monitor.start()

    @property
    def config(self):
        return self.config_data


# ══════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = App()
    app.mainloop()
