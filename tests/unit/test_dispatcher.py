"""Unit tests for dispatcher agent-selection logic."""
import pytest
import pytest_asyncio
from igrid.hub.db import init_db
from igrid.hub.state import GridState
from igrid.hub.dispatcher import pick_agent
from igrid.schema.enums import ComputeTier
from igrid.schema.handshake import JoinRequest, GPUInfo
from igrid.schema.task import TaskRequest

@pytest_asyncio.fixture
async def state(tmp_path):
    db = await init_db(str(tmp_path / "test.db"))
    gs = GridState(db, hub_id="hub-test", operator_id="duck")
    yield gs
    await db.close()

async def _add(state, aid, tier, vram=0, models=None, status="ONLINE"):
    gpus = [GPUInfo(index=0, model="GTX", vram_gb=vram)] if vram else []
    await state.register_agent(JoinRequest(operator_id="duck", agent_id=aid, host="127.0.0.1", port=8100, gpus=gpus, supported_models=models or []), tier)
    await state.db.execute("UPDATE agents SET status=? WHERE agent_id=?", (status, aid))
    await state.db.commit()

async def test_tier_filter(state):
    await _add(state, "bronze", ComputeTier.BRONZE)
    assert await pick_agent(state, TaskRequest(task_id="t", model="llama3", prompt="hi", min_tier=ComputeTier.GOLD)) is None

async def test_selects_best_tier(state):
    await _add(state, "bronze", ComputeTier.BRONZE); await _add(state, "gold", ComputeTier.GOLD)
    agent = await pick_agent(state, TaskRequest(task_id="t", model="llama3", prompt="hi", min_tier=ComputeTier.BRONZE))
    assert agent["agent_id"] == "gold"

async def test_vram_filter(state):
    await _add(state, "small", ComputeTier.GOLD, vram=8.0)
    assert await pick_agent(state, TaskRequest(task_id="t", model="llama3", prompt="hi", min_vram_gb=11.0)) is None

async def test_model_filter(state):
    await _add(state, "a", ComputeTier.GOLD, models=["llama3"]); await _add(state, "b", ComputeTier.GOLD, models=["mistral"])
    agent = await pick_agent(state, TaskRequest(task_id="t", model="mistral", prompt="hi"))
    assert agent["agent_id"] == "b"

async def test_prefers_online_over_busy(state):
    await _add(state, "busy", ComputeTier.GOLD, status="BUSY"); await _add(state, "online", ComputeTier.GOLD, status="ONLINE")
    agent = await pick_agent(state, TaskRequest(task_id="t", model="llama3", prompt="hi"))
    assert agent["agent_id"] == "online"
