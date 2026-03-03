"""Unit tests for Pydantic schemas."""
import pytest
from igrid.schema.handshake import JoinRequest, JoinAck, GPUInfo
from igrid.schema.task import TaskRequest, TaskResult
from igrid.schema.enums import ComputeTier, TaskState, AgentStatus
from igrid.schema.pulse import PulseReport

def test_join_request_defaults():
    req = JoinRequest(operator_id="duck", agent_id="a1", host="127.0.0.1", port=8100)
    assert req.gpus == [] and req.api_key == ""

def test_join_request_with_gpus():
    gpu = GPUInfo(index=0, model="GTX 1080 Ti", vram_gb=11.0)
    req = JoinRequest(operator_id="duck", agent_id="a1", host="127.0.0.1", port=8100, gpus=[gpu])
    assert req.gpus[0].vram_gb == 11.0

def test_join_ack():
    ack = JoinAck(accepted=True, hub_id="hub-1", operator_id="duck", agent_id="a1", tier=ComputeTier.GOLD)
    assert ack.tier == ComputeTier.GOLD and ack.accepted is True

def test_task_request_defaults():
    req = TaskRequest(task_id="t1", model="llama3", prompt="Hi")
    assert req.min_tier == ComputeTier.BRONZE and req.min_vram_gb == 0.0

def test_task_result_complete():
    r = TaskResult(task_id="t1", state=TaskState.COMPLETE, content="Hi!", output_tokens=5)
    assert r.state == TaskState.COMPLETE
