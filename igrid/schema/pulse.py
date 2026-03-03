"""Pulse (heartbeat) schemas."""
from __future__ import annotations
from pydantic import BaseModel
from igrid.schema.enums import AgentStatus

class PulseReport(BaseModel):
    operator_id: str
    agent_id: str
    status: AgentStatus
    gpu_utilization_pct: float = 0.0
    vram_used_gb: float = 0.0
    tasks_completed: int = 0
    current_tps: float = 0.0

class PulseAck(BaseModel):
    ok: bool
    hub_time: str
