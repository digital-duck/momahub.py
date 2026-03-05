"""Integration tests for hub FastAPI endpoints."""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from igrid.hub.app import create_app

@pytest_asyncio.fixture
async def client(tmp_path):
    app = create_app(hub_id="hub-test", operator_id="duck",
                     db_path=str(tmp_path / "hub.sqlite"), hub_url="http://localhost:8000")
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac

async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200 and resp.json()["hub_id"] == "hub-test"

async def test_join(client):
    resp = await client.post("/join", json={"operator_id":"duck","agent_id":"a1","host":"127.0.0.1","port":8100,"gpus":[{"index":0,"model":"GTX","vram_gb":11.0}],"supported_models":["llama3"]})
    assert resp.status_code == 200 and resp.json()["accepted"] is True

async def test_submit_task(client):
    resp = await client.post("/tasks", json={"task_id":"t1","model":"llama3","prompt":"Hello"})
    assert resp.status_code == 202 and resp.json()["task_id"] == "t1"

async def test_get_task_status(client):
    await client.post("/tasks", json={"task_id":"t2","model":"llama3","prompt":"Hi"})
    resp = await client.get("/tasks/t2")
    assert resp.status_code == 200 and resp.json()["state"] == "PENDING"

async def test_get_task_not_found(client):
    assert (await client.get("/tasks/nope")).status_code == 404

async def test_pulse(client):
    await client.post("/join", json={"operator_id":"duck","agent_id":"ap","host":"127.0.0.1","port":8100})
    resp = await client.post("/pulse", json={"operator_id":"duck","agent_id":"ap","status":"ONLINE","current_tps":38.0,"tasks_completed":5})
    assert resp.status_code == 200 and resp.json()["ok"] is True

async def test_leave(client):
    await client.post("/join", json={"operator_id":"duck","agent_id":"al","host":"127.0.0.1","port":8102})
    resp = await client.post("/leave", json={"operator_id":"duck","agent_id":"al"})
    assert resp.status_code == 200 and resp.json()["ok"] is True

async def test_rewards_empty(client):
    resp = await client.get("/rewards")
    assert resp.status_code == 200 and resp.json()["summary"] == []

async def test_logs(client):
    await client.post("/join", json={"operator_id":"duck","agent_id":"alog","host":"127.0.0.1","port":8103})
    await client.post("/pulse", json={"operator_id":"duck","agent_id":"alog","status":"ONLINE","current_tps":20.0,"tasks_completed":1})
    resp = await client.get("/logs")
    assert resp.status_code == 200 and len(resp.json()["logs"]) >= 1
