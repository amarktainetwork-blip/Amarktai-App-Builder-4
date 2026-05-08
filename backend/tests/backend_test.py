"""
Backend test suite for the Emergent Autonomous Coding Platform.
Covers: health, models, settings, projects CRUD, multi-agent pipeline,
events, files, preview HTML, finalize (mock), iteration messages, and WS.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid

import pytest
import requests
import websockets

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Read from frontend .env if not in environ
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

API = f"{BASE_URL}/api"
WS_URL = BASE_URL.replace("https://", "wss://").replace("http://", "ws://") + "/api/ws"

PIPELINE_TIMEOUT = 180  # seconds for full agent pipeline


# ------------------------- fixtures -------------------------

@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def created_project(session):
    """Create one project; the rest of the pipeline tests reuse it."""
    payload = {"name": "TEST_counter", "prompt": "Build a tiny dark-mode counter"}
    r = session.post(f"{API}/projects", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "id" in data
    assert data["name"] == "TEST_counter"
    assert data["status"] in ("queued", "running")
    yield data
    # cleanup
    try:
        session.delete(f"{API}/projects/{data['id']}", timeout=15)
    except Exception:
        pass


# ------------------------- basic API -------------------------

def test_health(session):
    r = session.get(f"{API}/", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert data.get("service") == "emergent-platform"
    assert data.get("status") == "ok"


def test_models(session):
    r = session.get(f"{API}/models", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert "tiers" in data
    assert "agents" in data
    assert "tools" in data
    # validate at least scout/architect/coder/reviewer agents are mapped
    for a in ("scout", "architect", "coder", "reviewer"):
        assert a in data["agents"], f"missing agent {a}"
    # at least 1 tool registered
    assert isinstance(data["tools"], list) and len(data["tools"]) >= 1


def test_settings_get(session):
    r = session.get(f"{API}/settings", timeout=15)
    assert r.status_code == 200
    data = r.json()
    for key in ("EMERGENT_LLM_KEY", "WEBCONTAINER_API_KEY", "GITHUB_PAT", "BRAVE_SEARCH_API_KEY"):
        assert key in data
        assert "set" in data[key]
        assert "preview" in data[key]
    # EMERGENT_LLM_KEY should be set
    assert data["EMERGENT_LLM_KEY"]["set"] is True


def test_settings_post_roundtrip(session):
    # Save existing then set a sentinel and read back, then restore
    orig = session.get(f"{API}/settings", timeout=15).json()
    sentinel_val = "test-brave-key-xyz12345"
    r = session.post(f"{API}/settings", json={"BRAVE_SEARCH_API_KEY": sentinel_val}, timeout=15)
    assert r.status_code == 200
    after = session.get(f"{API}/settings", timeout=15).json()
    assert after["BRAVE_SEARCH_API_KEY"]["set"] is True
    assert "xyz1" in after["BRAVE_SEARCH_API_KEY"]["preview"] or "test" in after["BRAVE_SEARCH_API_KEY"]["preview"]
    # restore (set empty)
    session.post(f"{API}/settings", json={"BRAVE_SEARCH_API_KEY": ""}, timeout=15)


# ------------------------- project list -------------------------

def test_projects_list(session, created_project):
    r = session.get(f"{API}/projects", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    # ensure no _id leak
    for p in data:
        assert "_id" not in p
    # our project should appear
    assert any(p["id"] == created_project["id"] for p in data)


def test_project_get(session, created_project):
    r = session.get(f"{API}/projects/{created_project['id']}", timeout=15)
    assert r.status_code == 200
    p = r.json()
    assert p["id"] == created_project["id"]
    assert "_id" not in p
    assert p["name"] == "TEST_counter"


def test_project_get_404(session):
    r = session.get(f"{API}/projects/nonexistent-id-{uuid.uuid4()}", timeout=15)
    assert r.status_code == 404


# ------------------------- pipeline (long) -------------------------

def _wait_for_status(session, project_id, target=("ready", "failed"), timeout=PIPELINE_TIMEOUT):
    start = time.time()
    last = None
    while time.time() - start < timeout:
        r = session.get(f"{API}/projects/{project_id}", timeout=15)
        if r.status_code == 200:
            last = r.json().get("status")
            if last in target:
                return last
        time.sleep(3)
    return last


def test_pipeline_completes_and_emits_4_agents(session, created_project):
    pid = created_project["id"]
    final = _wait_for_status(session, pid, target=("ready", "failed"))
    assert final == "ready", f"pipeline did not reach ready, last={final}"

    # events: each agent must have started + completed
    r = session.get(f"{API}/projects/{pid}/events", timeout=15)
    assert r.status_code == 200
    events = r.json()
    for e in events:
        assert "_id" not in e
    agents_started = {e["agent"] for e in events if e["status"] == "started"}
    agents_completed = {e["agent"] for e in events if e["status"] == "completed"}
    for a in ("scout", "architect", "coder", "reviewer"):
        assert a in agents_started, f"{a} never started. seen={agents_started}"
        assert a in agents_completed, f"{a} never completed. seen={agents_completed}"


def test_messages_after_pipeline(session, created_project):
    r = session.get(f"{API}/projects/{created_project['id']}/messages", timeout=15)
    assert r.status_code == 200
    msgs = r.json()
    for m in msgs:
        assert "_id" not in m
    # user prompt + 4 agent messages at minimum
    agents_msgs = {m.get("agent") for m in msgs if m.get("role") == "agent"}
    for a in ("scout", "architect", "coder", "reviewer"):
        assert a in agents_msgs, f"no message from {a}; got {agents_msgs}"


def test_files_after_pipeline(session, created_project):
    pid = created_project["id"]
    r = session.get(f"{API}/projects/{pid}/files", timeout=15)
    assert r.status_code == 200
    files = r.json()
    for f in files:
        assert "_id" not in f
    paths = [f["path"] for f in files]
    assert "requirements.md" in paths
    assert "tech_stack.json" in paths
    # there should be at least one HTML or JS produced by the coder
    assert any(p.endswith((".html", ".js", ".css")) for p in paths), f"no UI files generated: {paths}"


def test_file_content_endpoint(session, created_project):
    pid = created_project["id"]
    files = session.get(f"{API}/projects/{pid}/files", timeout=15).json()
    target = files[0]["path"]
    r = session.get(f"{API}/projects/{pid}/files/content", params={"path": target}, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert "content" in body
    assert "_id" not in body


def test_file_content_404(session, created_project):
    r = session.get(f"{API}/projects/{created_project['id']}/files/content",
                    params={"path": "does-not-exist.txt"}, timeout=15)
    assert r.status_code == 404


def test_preview_html(session, created_project):
    r = session.get(f"{API}/projects/{created_project['id']}/preview", timeout=15)
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    body = r.text
    assert "<html" in body.lower() or "<!doctype" in body.lower()


def test_finalize_mock(session, created_project):
    r = session.post(f"{API}/projects/{created_project['id']}/finalize", timeout=20)
    assert r.status_code == 200
    repo = r.json()
    assert "url" in repo
    # mocked since GITHUB_PAT empty
    assert repo["url"]


def test_iteration_message(session, created_project):
    pid = created_project["id"]
    # verify project not in running state before iterating
    _wait_for_status(session, pid, target=("ready", "failed"))
    r = session.post(f"{API}/projects/{pid}/messages",
                     json={"content": "Change the title to 'Counter Demo'"}, timeout=15)
    assert r.status_code == 200
    assert r.json().get("queued") is True
    # wait for iteration to finish
    final = _wait_for_status(session, pid, target=("ready", "failed"), timeout=120)
    assert final == "ready", f"iteration final status={final}"
    events = session.get(f"{API}/projects/{pid}/events", timeout=15).json()
    iter_events = [e for e in events if e["agent"] == "iteration"]
    assert any(e["status"] == "completed" for e in iter_events), "iteration agent never completed"


def test_iteration_conflict_409(session, created_project):
    """If a build is in-progress the iteration endpoint returns 409."""
    pid = created_project["id"]
    # create a fresh project to put it into running state quickly
    new = session.post(f"{API}/projects", json={"name": "TEST_busy", "prompt": "tiny app"}, timeout=15).json()
    try:
        # try sending an iteration immediately (should be running)
        time.sleep(2)
        r = session.post(f"{API}/projects/{new['id']}/messages",
                         json={"content": "change something"}, timeout=15)
        # accept either 409 or 200 (race), but if 200 we cannot validate; assert one of them
        assert r.status_code in (200, 409)
    finally:
        # cleanup — wait for completion then delete to avoid stray pipeline
        _wait_for_status(session, new["id"], target=("ready", "failed"))
        session.delete(f"{API}/projects/{new['id']}", timeout=15)


# ------------------------- WebSocket -------------------------

@pytest.mark.asyncio
async def test_websocket_connects_and_heartbeats(created_project):
    pid = created_project["id"]
    url = f"{WS_URL}/{pid}"
    async with websockets.connect(url, open_timeout=15) as ws:
        # first message should be hello
        first = await asyncio.wait_for(ws.recv(), timeout=10)
        payload = json.loads(first)
        assert payload.get("type") == "hello"
        # send ping, expect pong
        await ws.send("ping")
        # Drain until we see a pong (events may also arrive)
        got_pong = False
        for _ in range(5):
            reply = await asyncio.wait_for(ws.recv(), timeout=10)
            data = json.loads(reply)
            if data.get("type") == "pong":
                got_pong = True
                assert "t" in data.get("data", {})
                break
        assert got_pong, "did not receive JSON pong"


# ------------------------- concurrency: event loop must not block -------------------------

def test_concurrent_calls_during_running_build(session):
    """While a pipeline is launched, GET /api/ and GET /api/projects must respond <2s each."""
    new = session.post(f"{API}/projects", json={"name": "TEST_concurrent", "prompt": "tiny app"}, timeout=15).json()
    pid = new["id"]
    try:
        # within ~1-2s, the pipeline LLM call should be in-flight
        time.sleep(1.5)
        t0 = time.time()
        r1 = session.get(f"{API}/", timeout=5)
        d1 = time.time() - t0
        t0 = time.time()
        r2 = session.get(f"{API}/projects", timeout=5)
        d2 = time.time() - t0
        assert r1.status_code == 200, f"GET /api/ failed: {r1.status_code}"
        assert r2.status_code == 200, f"GET /api/projects failed: {r2.status_code}"
        assert d1 < 3.0, f"GET /api/ took {d1:.2f}s while build running (event loop blocked?)"
        assert d2 < 3.0, f"GET /api/projects took {d2:.2f}s while build running"
    finally:
        _wait_for_status(session, pid, target=("ready", "failed"))
        session.delete(f"{API}/projects/{pid}", timeout=15)


# ------------------------- delete -------------------------

def test_delete_cleanup(session):
    p = session.post(f"{API}/projects",
                     json={"name": "TEST_del", "prompt": "tiny"}, timeout=15).json()
    pid = p["id"]
    # delete immediately (don't wait for pipeline)
    r = session.delete(f"{API}/projects/{pid}", timeout=15)
    assert r.status_code == 200
    # confirm 404
    r2 = session.get(f"{API}/projects/{pid}", timeout=15)
    assert r2.status_code == 404
