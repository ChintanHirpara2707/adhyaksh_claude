"""The HUD window: a frameless, always-on-top ring in a corner of the screen.

* Shows the engine's state (ring colour and motion), the last reply and watchdog notices (battery, reminders).
* Ctrl+Alt+A (global): push-to-talk when native voice runs in the engine, otherwise a small box to type a command.
* Drag the ring to move it; right-click for Type a command, Stop speaking, Quit.
It talks only to the background engine on 127.0.0.1, with the per-install token. It runs nothing itself: every
command goes to the engine and through its safety gateway.
"""
from __future__ import annotations

import ctypes
import json
import queue
import threading
import time

from hud import core

SIZE = 120
KEY = "#010101"  # drawn in this colour = transparent on Windows
HOTKEY_ID, MOD_ALT, MOD_CONTROL, MOD_NOREPEAT, VK_A, WM_HOTKEY, WM_QUIT = 1, 0x1, 0x2, 0x4000, 0x41, 0x0312, 0x0012


class EngineLink:
    """HTTP calls and the event stream to the background engine."""

    def __init__(self, inbox: queue.Queue):
        from adhyaksh import config, server
        self.port, self.token, self.inbox = int(config.get("server_port")), server.token(), inbox
        self.base = f"http://127.0.0.1:{self.port}"
        self._stop = threading.Event()

    def post(self, path: str, body: dict | None = None, timeout: float = 120.0) -> dict:
        import requests
        r = requests.post(self.base + path, json=body or {}, headers={"X-Adhyaksh-Token": self.token}, timeout=timeout)
        return r.json() if r.headers.get("content-type", "").startswith("application/json") else {}

    def get(self, path: str, timeout: float = 3.0) -> dict:
        import requests
        r = requests.get(self.base + path, headers={"X-Adhyaksh-Token": self.token}, timeout=timeout)
        return r.json()

    def listen(self) -> None:
        """Forward engine events to the window; reconnect with backoff while the engine is away."""
        from websockets.sync.client import connect
        attempt = 0
        while not self._stop.is_set():
            try:
                with connect(f"ws://127.0.0.1:{self.port}/v1/events?token={self.token}", open_timeout=3,
                             close_timeout=1) as ws:
                    first = True
                    for raw in ws:
                        if self._stop.is_set():
                            break
                        if first:  # the engine sends its state right after a real accept; a refusal sends nothing
                            attempt, first = 0, False
                            self.inbox.put(("connected", True))
                        self.inbox.put(("event", json.loads(raw)))
            except Exception:
                pass
            self.inbox.put(("connected", False))
            self._stop.wait(core.backoff(attempt))
            attempt += 1

    def stop(self) -> None:
        self._stop.set()


class Hotkey:
    """A global hotkey through RegisterHotKey, in its own thread with a message loop."""

    def __init__(self, inbox: queue.Queue):
        self.inbox, self.thread_id, self.ok = inbox, 0, False
        self.thread = threading.Thread(target=self._run, name="hud-hotkey", daemon=True)

    def _run(self) -> None:
        from ctypes import wintypes
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        self.thread_id = ctypes.windll.kernel32.GetCurrentThreadId()  # type: ignore[attr-defined]
        self.ok = bool(user32.RegisterHotKey(None, HOTKEY_ID, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_A))
        if not self.ok:
            self.inbox.put(("error", "Ctrl+Alt+A is used by another program; right-click the ring instead."))
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self.inbox.put(("hotkey", None))
        user32.UnregisterHotKey(None, HOTKEY_ID)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        if self.thread_id:
            ctypes.windll.user32.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)  # type: ignore[attr-defined]


class Hud:
    def __init__(self):
        import tkinter as tk
        self.tk = tk
        self.model = core.HudModel()
        self.inbox: queue.Queue = queue.Queue()
        self.link = EngineLink(self.inbox)
        self.hotkey = Hotkey(self.inbox)
        self.angle, self.t0 = 0.0, time.time()

        self.root = tk.Tk()
        self.root.title("ADHYAKSH")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=KEY)
        self.root.attributes("-transparentcolor", KEY)
        w, h = SIZE + 260, SIZE + 10
        self.root.geometry(f"{w}x{h}+{self.root.winfo_screenwidth() - w - 24}+{self.root.winfo_screenheight() - h - 72}")
        self.canvas = tk.Canvas(self.root, width=w, height=h, bg=KEY, highlightthickness=0)
        self.canvas.pack()
        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="Type a command", command=self.ask_text)
        self.menu.add_command(label="Stop speaking", command=lambda: self._async(lambda: self.link.post("/v1/voice/stop_speaking")))
        self.menu.add_separator()
        self.menu.add_command(label="Quit", command=self.quit)
        self.canvas.bind("<ButtonPress-1>", self._drag_start)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<Button-3>", lambda e: self.menu.tk_popup(e.x_root, e.y_root))
        self._drag_from = (0, 0)

    # ---- drawing ----------------------------------------------------------------------------------------------------
    def draw(self) -> None:
        c, ring = self.canvas, self.model.ring()
        c.delete("all")
        cx = cy = SIZE // 2 + 5
        r = SIZE // 2 - 6
        c.create_oval(cx - r, cy - r, cx + r, cy + r, fill="#10161c", outline="#1d2a33", width=2)
        width = ring["width"]
        if ring.get("pulse"):
            width += 2 * abs(((time.time() - self.t0) * 1.6) % 2 - 1)
        if ring["speed"]:
            self.angle = (self.angle + ring["speed"]) % 360
            c.create_arc(cx - r + 4, cy - r + 4, cx + r - 4, cy + r - 4, start=self.angle, extent=260, style="arc",
                         outline=ring["color"], width=width)
        else:
            c.create_oval(cx - r + 4, cy - r + 4, cx + r - 4, cy + r - 4, outline=ring["color"], width=width)
        c.create_text(cx, cy, text=ring["label"], fill="#d7e3ea", font=("Segoe UI", 9))
        caption = self.model.visible_caption()
        if caption:
            c.create_text(SIZE + 12, cy, text=caption, anchor="w", width=240, fill="#e8eef2", font=("Segoe UI", 9),
                          tags="caption")
            box = c.bbox("caption")
            if box:
                c.create_rectangle(box[0] - 6, box[1] - 4, box[2] + 6, box[3] + 4, fill="#10161c", outline="#1d2a33")
                c.tag_raise("caption")

    def tick(self) -> None:
        while True:
            try:
                kind, data = self.inbox.get_nowait()
            except queue.Empty:
                break
            if kind == "event":
                self.model.apply(data)
            elif kind == "connected":
                self.model.set_connected(data)
            elif kind == "error":
                self.model.error(data)
            elif kind == "hotkey":
                self.on_hotkey()
        self.draw()
        self.root.after(40, self.tick)

    # ---- actions ---------------------------------------------------------------------------------------------------------
    def _async(self, fn) -> None:
        def run():
            try:
                fn()
            except Exception:
                self.inbox.put(("error", "The engine did not answer."))
        threading.Thread(target=run, daemon=True).start()

    def on_hotkey(self) -> None:
        def push_to_talk():
            if self.link.get("/v1/voice").get("running"):
                self.link.post("/v1/voice/listen")
            else:
                self.root.after(0, self.ask_text)
        self._async(push_to_talk)

    def ask_text(self) -> None:
        tk = self.tk
        box = tk.Toplevel(self.root)
        box.overrideredirect(True)
        box.attributes("-topmost", True)
        x, y = self.root.winfo_x(), self.root.winfo_y()
        box.geometry(f"360x34+{max(0, x - 240)}+{max(0, y - 40)}")
        entry = tk.Entry(box, font=("Segoe UI", 11), bg="#10161c", fg="#e8eef2", insertbackground="#e8eef2", relief="flat")
        entry.pack(fill="both", expand=True, padx=2, pady=2)
        entry.focus_force()

        def send(_=None):
            text = entry.get().strip()
            box.destroy()
            if text:
                self._async(lambda: self.link.post("/v1/message", {"text": text}))
        entry.bind("<Return>", send)
        entry.bind("<Escape>", lambda e: box.destroy())

    def _drag_start(self, e) -> None:
        self._drag_from = (e.x, e.y)

    def _drag(self, e) -> None:
        self.root.geometry(f"+{self.root.winfo_x() + e.x - self._drag_from[0]}+{self.root.winfo_y() + e.y - self._drag_from[1]}")

    def quit(self) -> None:
        self.link.stop()
        self.hotkey.stop()
        self.root.destroy()

    def run(self) -> None:
        threading.Thread(target=self.link.listen, name="hud-events", daemon=True).start()
        self.hotkey.start()
        self.tick()
        self.root.mainloop()


def main() -> int:
    Hud().run()
    return 0
