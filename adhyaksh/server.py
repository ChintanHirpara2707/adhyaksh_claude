"""The background engine: a local HTTP and WebSocket server so the assistant keeps working without a browser tab
(the desktop HUD, voice and reminders talk to it; the Streamlit console can too).

Run: python -m adhyaksh.server        (listens on 127.0.0.1:<server_port>, default 8765)

Security, because any program or web page on this PC can try to reach localhost:
* bound to 127.0.0.1 only; a request whose Host header is not the loopback address is refused (blocks DNS rebinding);
* a browser request (it carries an Origin header) is refused unless it comes from the assistant's own console;
* every endpoint except a bare health check needs the per-install token from data/server_token (created on first
  start, never logged); WebSocket clients pass it as ?token=, because browsers cannot set WebSocket headers.
Every action still goes through the safety gateway exactly as in the app; the server adds no new powers.
"""
# No "from __future__ import annotations" here: FastAPI reads the request models from the real annotations.
import asyncio
import hmac
import queue
import secrets
import threading

from adhyaksh import __version__, config, events, logging_setup

TOKEN_FILE = "server_token"
HEADER = "X-Adhyaksh-Token"
_ENGINE_LOCK = threading.Lock()  # one user, one conversation state: requests are handled one at a time


def token() -> str:
    """The per-install token (created once, stored in the git-ignored data folder)."""
    path = config.data_dir() / TOKEN_FILE
    try:
        value = path.read_text(encoding="utf-8").strip()
        if len(value) >= 32:
            return value
    except OSError:
        pass
    value = secrets.token_urlsafe(32)
    path.write_text(value, encoding="utf-8")
    return value


def port() -> int:
    return int(config.get("server_port"))


def allowed_hosts() -> set[str]:
    p = port()
    return {f"127.0.0.1:{p}", f"localhost:{p}", "127.0.0.1", "localhost"}


def allowed_origins() -> set[str]:
    p, ui = port(), int(config.get("console_port"))
    return {f"http://127.0.0.1:{p}", f"http://localhost:{p}", f"http://127.0.0.1:{ui}", f"http://localhost:{ui}"}


def _check(headers, query_token: str | None = None) -> tuple[int, str] | None:
    """(status, reason) when the request must be refused, else None."""
    host = (headers.get("host") or "").casefold()
    if host not in allowed_hosts():
        return 403, "wrong host"
    origin = headers.get("origin")
    if origin and origin.rstrip("/").casefold() not in allowed_origins():
        return 403, "origin not allowed"
    given = headers.get(HEADER.casefold()) or headers.get(HEADER) or query_token or ""
    if not hmac.compare_digest(given.encode(), token().encode()):
        return 401, "missing or wrong token"
    return None


def create_app():
    from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel, Field

    app = FastAPI(title="ADHYAKSH background engine", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)

    class Message(BaseModel):
        text: str = Field(min_length=1, max_length=8000)
        conversation_id: int | None = None
        mode: str = Field(default="cowork", pattern="^(chat|cowork)$")
        voice: bool = False

    class Confirm(BaseModel):
        conversation_id: int
        accept: bool

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if request.url.path == "/v1/health":
            if (request.headers.get("host") or "").casefold() not in allowed_hosts():
                return JSONResponse({"error": "wrong host"}, status_code=403)
            return await call_next(request)
        refused = _check(request.headers)
        if refused:
            logging_setup.event("server_refused", path=request.url.path, reason=refused[1])
            return JSONResponse({"error": refused[1]}, status_code=refused[0])
        return await call_next(request)

    @app.get("/v1/health")
    def health():
        return {"ok": True, "version": __version__}

    @app.get("/v1/state")
    def state():
        return events.current_state()

    @app.post("/v1/message")
    def message(body: Message):
        from adhyaksh.chat import context, engine
        with _ENGINE_LOCK:
            cid = body.conversation_id or context.latest_conversation()
            res = engine.handle_message(body.text, cid, voice=body.voice, mode=body.mode)
        if not res.ok:
            return JSONResponse({"error": res.message, "code": res.error_code}, status_code=400)
        return {"conversation_id": cid, **{k: v for k, v in res.data.items() if k != "timings"}}

    @app.post("/v1/confirm")
    def confirm(body: Confirm):
        from adhyaksh.chat import engine
        with _ENGINE_LOCK:
            res = engine.confirm(body.conversation_id, body.accept)
        if not res.ok:
            return JSONResponse({"error": res.message, "code": res.error_code}, status_code=400)
        return res.data

    @app.get("/v1/pending/{conversation_id}")
    def pending(conversation_id: int):
        """The confirmation this conversation is waiting for (without anything executable), or null."""
        from adhyaksh.chat import context
        ctx = context.get(conversation_id)
        p = ctx.pending_confirm or ctx.pending_agent_confirm
        return {"pending": {k: p.get(k) for k in ("token", "action", "target")} if p else None}

    @app.get("/v1/voice")
    def voice_status():
        from adhyaksh.voice import pipeline
        return pipeline.status()

    @app.post("/v1/voice/listen")
    def voice_listen():
        """Push-to-talk (the HUD hotkey): the next phrase is a command, no wake word needed."""
        from adhyaksh.voice import pipeline
        pipe = pipeline._state["pipeline"]
        if pipe is None or not pipeline.status()["running"]:
            return JSONResponse({"error": "Native voice is not running. Turn it on in Settings and restart the engine."},
                                status_code=409)
        pipe.listen_now()
        return {"listening": True}

    @app.post("/v1/voice/stop_speaking")
    def voice_quiet():
        from adhyaksh.voice import pipeline
        pipe = pipeline._state["pipeline"]
        if pipe is not None and pipe.speaker is not None:
            pipe.speaker.stop()
        return {"ok": True}

    @app.websocket("/v1/events")
    async def stream(ws: WebSocket):
        refused = _check(ws.headers, ws.query_params.get("token"))
        await ws.accept()  # accept first so the close code can say why; nothing is sent before a refusal
        if refused:
            logging_setup.event("server_refused", path="/v1/events", reason=refused[1])
            await ws.close(code=4401 if refused[0] == 401 else 4403)
            return
        q = events.subscribe()
        try:
            await ws.send_json({"type": "state", **events.current_state()})
            loop = asyncio.get_running_loop()
            while True:
                try:
                    event = await loop.run_in_executor(None, lambda: q.get(timeout=1.0))
                except queue.Empty:
                    continue
                await ws.send_json(event)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            events.unsubscribe(q)

    return app


def main() -> int:
    import uvicorn

    from adhyaksh import db
    db.init()
    token()
    logging_setup.event("server_start", port=port())
    from adhyaksh import watchdog
    watchdog.start()
    if config.get_bool("voice_engine"):
        from adhyaksh.voice import pipeline
        ok, why = pipeline.start()
        if not ok:
            logging_setup.event("voice_not_started", reason=why)
    uvicorn.run(create_app(), host="127.0.0.1", port=port(), log_level="warning", access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
