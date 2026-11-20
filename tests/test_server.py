"""Phase 3a-2: the local background server. Requests go through FastAPI's in-process test client (no port is
opened). Host, Origin and token checks are tested from the attacker's side as well as the client's."""
import pytest
from starlette.testclient import TestClient

from adhyaksh import config, events, server
from adhyaksh.chat import context
from adhyaksh.memory import store
from tests.helpers import fresh_env

BASE = "http://127.0.0.1:8765"


@pytest.fixture
def client():
    fresh_env()
    events.reset()
    c = TestClient(server.create_app(), base_url=BASE)
    yield c
    events.reset()


def _h(**extra):
    return {server.HEADER: server.token(), **extra}


# ---- token ----------------------------------------------------------------------------------------------------------
def test_token_is_created_once_and_kept(client):
    t = server.token()
    assert len(t) >= 32 and server.token() == t and (config.data_dir() / server.TOKEN_FILE).read_text().strip() == t


def test_health_needs_no_token_and_tells_nothing(client):
    r = client.get("/v1/health")
    assert r.status_code == 200 and set(r.json()) == {"ok", "version"}


@pytest.mark.parametrize("headers,status", [
    ({}, 401),
    ({server.HEADER: "wrong"}, 401),
])
def test_requests_without_the_token_are_refused(client, headers, status):
    r = client.post("/v1/message", json={"text": "hello"}, headers=headers)
    assert r.status_code == status and "token" in r.json()["error"]


def test_a_web_page_cannot_use_the_server_even_with_the_token(client):
    """A page on any site can send requests to localhost: its Origin header gives it away."""
    r = client.post("/v1/message", json={"text": "delete notes.txt"}, headers=_h(Origin="https://evil.example"))
    assert r.status_code == 403 and r.json()["error"] == "origin not allowed"
    ok = client.post("/v1/message", json={"text": "hello"}, headers=_h(Origin="http://localhost:8501"))  # the console
    assert ok.status_code == 200


def test_dns_rebinding_is_refused(client):
    """A page whose own domain resolves to 127.0.0.1 still sends its own name as Host."""
    r = client.get("/v1/state", headers=_h(Host="evil.example:8765"))
    assert r.status_code == 403 and r.json()["error"] == "wrong host"
    assert client.get("/v1/health", headers={"Host": "evil.example"}).status_code == 403


# ---- endpoints ----------------------------------------------------------------------------------------------------------
def test_message_and_state(client):
    r = client.post("/v1/message", json={"text": "what is 2 + 3"}, headers=_h())
    assert r.status_code == 200 and "5" in r.json()["reply"] and r.json()["conversation_id"]
    assert client.get("/v1/state", headers=_h()).json()["state"] == "idle"


def test_bad_bodies_are_rejected(client):
    assert client.post("/v1/message", json={"text": ""}, headers=_h()).status_code == 422
    assert client.post("/v1/message", json={"text": "hi", "mode": "root"}, headers=_h()).status_code == 422
    assert client.post("/v1/message", json={"text": "x" * 8001}, headers=_h()).status_code == 422


def test_confirmation_round_trip_through_the_server(client):
    store.save_fact("my car is Audi")
    cid = context.new_conversation()
    r = client.post("/v1/message", json={"text": "forget my car", "conversation_id": cid}, headers=_h()).json()
    assert r["confirmation"] and store.list_facts()
    r = client.post("/v1/confirm", json={"conversation_id": cid, "accept": True}, headers=_h())
    assert r.status_code == 200 and r.json()["reply"] == "Forgotten: my car is Audi." and not store.list_facts()
    assert client.post("/v1/confirm", json={"conversation_id": cid, "accept": True}, headers=_h()).status_code == 400


# ---- events over WebSocket -------------------------------------------------------------------------------------------------
WS_HOST = {"host": "127.0.0.1:8765"}  # starlette's test client sends Host: testserver for WebSockets otherwise


def _refused_code(client, url, headers):
    from starlette.websockets import WebSocketDisconnect
    with client.websocket_connect(url, headers=headers) as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    return exc.value.code


def test_websocket_needs_the_token_the_host_and_a_good_origin(client):
    assert _refused_code(client, "/v1/events?token=wrong", WS_HOST) == 4401
    assert _refused_code(client, f"/v1/events?token={server.token()}", {**WS_HOST, "Origin": "https://evil.example"}) == 4403
    assert _refused_code(client, f"/v1/events?token={server.token()}", {"host": "evil.example:8765"}) == 4403


def test_websocket_streams_state_and_replies(client):
    with client.websocket_connect(f"/v1/events?token={server.token()}", headers=WS_HOST) as ws:
        assert ws.receive_json()["type"] == "state"
        client.post("/v1/message", json={"text": "hello"}, headers=_h())
        seen = []
        while not seen or seen[-1]["type"] != "reply":
            seen.append(ws.receive_json())
        assert ("state", "thinking") in [(e["type"], e.get("state")) for e in seen] and seen[-1]["intent"]
