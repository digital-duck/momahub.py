"""Task submission and result schemas."""
from __future__ import annotations
from pydantic import BaseModel, Field
from igrid.schema.enums import TaskState, ComputeTier

class TaskRequest(BaseModel):
    task_id: str
    model: str
    prompt: str
    system: str = ""
    max_tokens: int = 1024
    temperature: float = 0.7
    min_tier: ComputeTier = ComputeTier.BRONZE
    min_vram_gb: float = 0.0
    timeout_s: int = 300

class TaskResult(BaseModel):
    task_id: str
    state: TaskState
    content: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    agent_id: str = ""
    error: str = ""

class TaskStatusResponse(BaseModel):
    task_id: str
    state: TaskState
    result: TaskResult | None = None
