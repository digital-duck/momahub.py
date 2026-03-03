"""Reward / accounting schemas (PoC placeholder)."""
from __future__ import annotations
from pydantic import BaseModel

class RewardEntry(BaseModel):
    operator_id: str
    agent_id: str
    task_id: str
    tokens_generated: int
    credits_earned: float

class RewardSummary(BaseModel):
    operator_id: str
    total_tasks: int
    total_tokens: int
    total_credits: float
