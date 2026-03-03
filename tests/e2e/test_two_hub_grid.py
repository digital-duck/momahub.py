"""E2E test: two hubs in a cluster."""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from igrid.hub.app import create_app

@pytest_asyncio.fixture
async def hub_a(tmp_path):
    app = create_app(hub_id="hub-A", operator_id="duck", db_path=str(tmp_path / "hub_a.db"), hub_url="http://hub-a")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://hub-a") as client:
        yield client

@pytest_asyncio.fixture
async def hub_b(tmp_path):
    app = create_app(hub_id="hub-B", operator_id="duck", db_path=str(tmp_path / "hub_b.db"), hub_url="http://hub-b")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://hub-b") as client:
        yield client

async def test_health_both_hubs(hub_a, hub_b):
    ra = await hub_a.get("/health"); rb = await hub_b.get("/health")
    assert ra.json()["hub_id"] == "hub-A" and rb.json()["hub_id"] == "hub-B"

async def test_agent_registers_with_hub_b(hub_b):
    resp = await hub_b.post("/join", json={"operator_id":"duck","agent_id":"agent-on-b","host":"192.168.1.20","port":8100,"supported_models":["llama3"],"gpus":[{"index":0,"model":"GTX 1080 Ti","vram_gb":11.0}]})
    assert resp.status_code == 200 and resp.json()["accepted"] is True

async def test_task_submitted_to_hub_a(hub_a):
    resp = await hub_a.post("/tasks", json={"task_id":"e2e-t-1","model":"llama3","prompt":"Hello grid."})
    assert resp.status_code == 202
    r = await hub_a.get("/tasks/e2e-t-1")
    assert r.json()["state"] == "PENDING"
