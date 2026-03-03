"""Unit tests for GridState."""
import pytest
import pytest_asyncio
from igrid.hub.db import init_db
from igrid.hub.state import GridState
from igrid.schema.enums import ComputeTier, TaskState
from igrid.schema.handshake import JoinRequest, GPUInfo
from igrid.schema.task import TaskRequest, TaskResult

@pytest_asyncio.fixture
async def state(tmp_path):
    db = await init_db(str(tmp_path / "test.db"))
    gs = GridState(db, hub_id="hub-test", operator_id="duck")
    yield gs
    await db.close()

async def test_register_and_list_agent(state):
    req = JoinRequest(operator_id="duck", agent_id="a1", host="127.0.0.1", port=8100,
                      gpus=[GPUInfo(index=0, model="GTX 1080 Ti", vram_gb=11.0)])
    await state.register_agent(req, ComputeTier.GOLD)
    agents = await state.list_agents()
    assert len(agents) == 1 and agents[0]["tier"] == "GOLD"

async def test_submit_and_get_task(state):
    await state.submit_task(TaskRequest(task_id="t1", model="llama3", prompt="Hi"))
    row = await state.get_task("t1")
    assert row is not None and row["state"] == TaskState.PENDING.value

async def test_claim_task(state):
    await state.register_agent(JoinRequest(operator_id="duck", agent_id="a1", host="127.0.0.1", port=8100), ComputeTier.BRONZE)
    await state.submit_task(TaskRequest(task_id="t2", model="llama3", prompt="Hi"))
    assert await state.claim_task("t2", "a1") is True
    assert (await state.get_task("t2"))["state"] == TaskState.DISPATCHED.value

async def test_fail_and_retry(state):
    await state.register_agent(JoinRequest(operator_id="duck", agent_id="a1", host="127.0.0.1", port=8100), ComputeTier.BRONZE)
    await state.submit_task(TaskRequest(task_id="t3", model="llama3", prompt="Hi"))
    await state.claim_task("t3", "a1")
    await state.fail_task("t3", "timeout")
    row = await state.get_task("t3")
    assert row["state"] == TaskState.PENDING.value and row["retries"] == 1

async def test_remove_agent_requeues_tasks(state):
    await state.register_agent(JoinRequest(operator_id="duck", agent_id="a1", host="127.0.0.1", port=8100), ComputeTier.BRONZE)
    await state.submit_task(TaskRequest(task_id="t4", model="llama3", prompt="Hi"))
    await state.claim_task("t4", "a1"); await state.mark_in_flight("t4")
    await state.remove_agent("a1")
    row = await state.get_task("t4")
    assert row["state"] == TaskState.PENDING.value and row["agent_id"] is None
