"""Screenshots of every page in light and dark mode, for docs/screens/ (not a pytest test).

    python tests/screens/capture.py before        -> docs/screens/before/<page>-<mode>.png
    python tests/screens/capture.py after-4b      -> docs/screens/after-4b/...
    python tests/screens/capture.py x chat,chat-empty   -> only those (chat-empty: Chat with a new, empty conversation)

Uses the Microsoft Edge that ships with Windows, in headless mode (no new package; Playwright would add a Chromium
download of about 150 MB). The app runs on a free 127.0.0.1 port with a scratch data folder seeded with a short
demo conversation, so the user's own data is never shown or changed. Nothing is sent anywhere.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EDGE = [Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Microsoft/Edge/Application/msedge.exe"]
SIZE = (1440, 960)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _seed(data: Path, models: Path) -> None:
    """A demo user and a short conversation, in the scratch folder only."""
    env = {**os.environ, "ADHYAKSH_DATA_DIR": str(data), "ADHYAKSH_MODELS_DIR": str(models)}
    work = data.parent / "workspace"  # demo files go here, never into the user's Documents workspace
    work.mkdir(exist_ok=True)
    code = ("from adhyaksh import db; db.init()\n"
            "from adhyaksh import config\n"
            f"assert config.configure_folders([{str(work)!r}], {str(work)!r})[0]\n"
            "from adhyaksh.nlu import registry\n"
            f"svm = {str(models / 'm3_svm.joblib')!r}\n"
            "import os\n"
            "if os.path.exists(svm):  # the copied intent model, made active in the scratch database\n"
            "    mid = db.execute(\"INSERT INTO model_registry(name,kind,path,dataset_hash,trained_at,is_active)\"\n"
            "                     \" VALUES('SVM','m3_svm',?,'',?,0)\", (svm, db.utcnow()))\n"
            "    registry.set_active(mid)\n"
            "from adhyaksh.chat import identity, context, engine\n"
            "identity.save_name('Demo')\n"
            "engine.handle_message('show system status', context.new_conversation())\n"
            "old = context.new_conversation('Shopping list')\n"
            "engine.handle_message('create shopping.txt with milk and eggs', old)\n"
            "cid = context.new_conversation()\n"
            "for t in ('hello', 'what is 12 * 7', 'remember that my car is Audi', 'what is my car',\n"
            "          'create notes.txt with buy milk'):\n"
            "    engine.handle_message(t, cid)\n")
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, check=True, capture_output=True)


def _empty_chat(data: Path, models: Path, make: bool) -> None:
    """For the 'chat-empty' shot: add a newest, empty conversation (the Chat page opens the newest), or remove it."""
    env = {**os.environ, "ADHYAKSH_DATA_DIR": str(data), "ADHYAKSH_MODELS_DIR": str(models)}
    code = ("from adhyaksh import db; from adhyaksh.chat import context; context.new_conversation()" if make else
            "from adhyaksh import db; db.execute('DELETE FROM conversations WHERE id NOT IN "
            "(SELECT DISTINCT conversation_id FROM messages)')")
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, check=True, capture_output=True)


def _set_theme(data: Path, models: Path, mode: str) -> None:
    env = {**os.environ, "ADHYAKSH_DATA_DIR": str(data), "ADHYAKSH_MODELS_DIR": str(models)}
    subprocess.run([sys.executable, "-c", f"from adhyaksh import config; config.set_value('theme', '{mode}')"],
                   cwd=ROOT, env=env, check=True, capture_output=True)


class _Cdp:
    """A minimal Chrome DevTools Protocol client over the installed websockets package."""

    def __init__(self, port: int):
        import json

        import requests
        from websockets.sync.client import connect
        for _ in range(40):
            try:
                targets = requests.get(f"http://127.0.0.1:{port}/json", timeout=1).json()
                page = next(t for t in targets if t.get("type") == "page")
                break
            except Exception:
                time.sleep(0.25)
        self.ws, self.n, self.json = connect(page["webSocketDebuggerUrl"], max_size=50_000_000), 0, json
        self.call("Page.enable")
        self.call("Emulation.setDeviceMetricsOverride", width=SIZE[0], height=SIZE[1], deviceScaleFactor=1, mobile=False)

    def call(self, method: str, **params):
        self.n += 1
        self.ws.send(self.json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            msg = self.json.loads(self.ws.recv())
            if msg.get("id") == self.n:
                return msg.get("result", {})

    def _eval(self, expr: str):
        return self.call("Runtime.evaluate", expression=expr, returnByValue=True).get("result", {}).get("value")

    def shot(self, url: str, path: Path, timeout_s: float, to_end: bool = False) -> bool:
        """Open the page, wait until Streamlit has drawn it and stopped running, then save a PNG. to_end scrolls to
        the bottom first (a chat is read at its latest turn)."""
        import base64
        self.call("Page.navigate", url=url)
        ready = ("(() => { const m = document.querySelector('[data-testid=\"stMain\"]');"
                 " const app = document.querySelector('[data-test-script-state]');"
                 " const run = document.querySelector('[data-testid=\"stStatusWidget\"]')"
                 "   || !app || app.getAttribute('data-test-script-state') !== 'notRunning';"
                 " const skel = document.querySelector('[data-testid=\"stSkeleton\"]');"
                 " const n = m ? m.innerText.trim().length : 0;"
                 " return (n > 20 && !run && !skel) ? n : -1; })()")
        deadline, stable, last = time.time() + timeout_s, 0, None
        while time.time() < deadline:
            n = self._eval(ready)
            # Quiet and no longer growing (a page with a timed fragment never shows "running" for long).
            stable = stable + 1 if isinstance(n, int) and n > 0 and n == last else 0
            last = n
            if stable >= 4:
                break
            time.sleep(0.5)
        if to_end:
            self._eval("(() => { const m = document.querySelector('[data-testid=\"stMain\"]');"
                       " if (m) m.scrollTop = m.scrollHeight; })()")
        time.sleep(1.5)  # let pinned parts (the chat composer) paint
        data = self.call("Page.captureScreenshot", format="png", fromSurface=True, captureBeyondViewport=False).get("data")
        if not data:
            return False
        path.write_bytes(base64.b64decode(data))
        return True

    def close(self) -> None:
        self.ws.close()


def capture(label: str, pages: list[str] | None = None, wait_ms: int = 25000) -> list[Path]:
    edge = next((p for p in EDGE if p.exists()), None)
    if edge is None:
        raise SystemExit("Microsoft Edge was not found.")
    out_dir = ROOT / "docs" / "screens" / label
    out_dir.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="adhy_screens_"))
    data, models = scratch / "data", scratch / "models"
    data.mkdir()
    # Trained intent models make the demo conversation realistic; copy only those (small) files.
    models.mkdir()
    for f in (ROOT / "models").glob("*.joblib"):
        shutil.copy2(f, models / f.name)
    _seed(data, models)
    port = _free_port()
    env = {**os.environ, "ADHYAKSH_DATA_DIR": str(data), "ADHYAKSH_MODELS_DIR": str(models), "ADHYAKSH_NO_OPEN": "1"}
    app = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app.py", "--server.headless=true",
                            "--server.address=127.0.0.1", f"--server.port={port}", "--browser.gatherUsageStats=false"],
                           cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    shots = []
    try:
        import requests
        for _ in range(60):
            try:
                if requests.get(f"http://127.0.0.1:{port}/_stcore/health", timeout=1).text == "ok":
                    break
            except requests.RequestException:
                time.sleep(1)
        sys.path.insert(0, str(ROOT))
        from adhyaksh.services import shell
        default = shell.pages()[0][0]
        if pages is None:
            pages = [slug for slug, _ in shell.pages()]
            pages.insert(pages.index(default) + 1, "chat-empty")  # the Chat page of a new conversation
        cdp_port = _free_port()
        browser = subprocess.Popen([str(edge), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                                    f"--remote-debugging-port={cdp_port}", f"--user-data-dir={scratch / 'edge'}",
                                    f"--window-size={SIZE[0]},{SIZE[1]}", "about:blank"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            cdp = _Cdp(cdp_port)
            for mode in ("light", "dark"):
                _set_theme(data, models, mode)
                cdp.call("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": mode}])
                for slug in pages:
                    path = out_dir / f"{slug}-{mode}.png"
                    empty = slug == "chat-empty"
                    if empty:
                        _empty_chat(data, models, True)
                    url_path = "" if slug in (default, "chat-empty") else slug  # the default page lives at "/"
                    if cdp.shot(f"http://127.0.0.1:{port}/{url_path}", path, wait_ms / 1000, to_end=slug == default):
                        shots.append(path)
                    if empty:
                        _empty_chat(data, models, False)
            cdp.close()
        finally:
            browser.terminate()
    finally:
        app.terminate()
        try:
            app.wait(timeout=10)
        except subprocess.TimeoutExpired:
            app.kill()
        shutil.rmtree(scratch, ignore_errors=True)
    return shots


if __name__ == "__main__":
    label = sys.argv[1] if len(sys.argv) > 1 else "latest"
    only = sys.argv[2].split(",") if len(sys.argv) > 2 else None
    for p in capture(label, only):
        print(p.relative_to(ROOT))
