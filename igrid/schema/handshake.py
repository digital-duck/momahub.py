"""Handshake schemas: agent JOIN / hub ACK."""
from __future__ import annotations
from pydantic import BaseModel, Field
from igrid.schema.enums import ComputeTier

class GPUInfo(BaseModel):
    index: int
    model: str
    vram_gb: float

class JoinRequest(BaseModel):
    operator_id: str
    agent_id: str
    host: str
    port: int
    name: str = ""
    gpus: list[GPUInfo] = Field(default_factory=list)
    cpu_cores: int = 0
    ram_gb: float = 0.0
    supported_models: list[str] = Field(default_factory=list)
    cached_models: list[str] = Field(default_factory=list, description="Models already pulled locally in Ollama")
    pull_mode: bool = Field(default=False, description="True = agent uses SSE pull instead of HTTP push")
    api_key: str = ""

class JoinAck(BaseModel):
    accepted: bool
    hub_id: str
    operator_id: str
    agent_id: str
    tier: ComputeTier
    name: str = ""
    message: str = ""
    status: str = "ONLINE"

class LeaveRequest(BaseModel):
    operator_id: str
    agent_id: str

class LeaveAck(BaseModel):
    ok: bool
