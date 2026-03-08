"""Handshake schemas: agent JOIN / hub ACK."""
from __future__ import annotations
from pydantic import BaseModel, Field
from igrid.schema.enums import ComputeTier

class GPUInfo(BaseModel):
    index: int
    model: str
    vram_gb: float

class JoinRequest(BaseModel):
    operator_id: str = Field(max_length=256)
    agent_id: str = Field(max_length=256)
    host: str = Field(max_length=256)
    port: int = Field(ge=1, le=65535)
    name: str = Field(default="", max_length=256)
    gpus: list[GPUInfo] = Field(default_factory=list, max_length=32)
    cpu_cores: int = Field(default=0, ge=0, le=4096)
    ram_gb: float = Field(default=0.0, ge=0.0, le=65536.0)
    supported_models: list[str] = Field(default_factory=list, max_length=200)
    cached_models: list[str] = Field(default_factory=list, max_length=200)
    max_concurrent: int = Field(default=3, ge=1, le=128)
    pull_mode: bool = Field(default=False)
    api_key: str = Field(default="", max_length=512)

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
