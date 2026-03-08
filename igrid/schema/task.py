"""Task submission and result schemas."""
from __future__ import annotations
from pydantic import BaseModel, Field
from igrid.schema.enums import TaskState, ComputeTier

class TaskRequest(BaseModel):
    task_id: str = Field(default="", max_length=256)
    model: str = Field(max_length=256)
    prompt: str = Field(max_length=200_000)
    system: str = Field(default="", max_length=100_000)
    max_tokens: int = Field(default=1024, ge=1, le=32_768)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    min_tier: ComputeTier = ComputeTier.BRONZE
    min_vram_gb: float = Field(default=0.0, ge=0.0, le=1024.0)
    timeout_s: int = Field(default=300, ge=10, le=3600)
    priority: int = Field(default=1, ge=0, le=100)

class TaskResult(BaseModel):
    task_id: str
    state: TaskState
    content: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    agent_id: str = ""
    agent_name: str = ""
    error: str = ""

class TaskStatusResponse(BaseModel):
    task_id: str
    state: TaskState
    result: TaskResult | None = None
