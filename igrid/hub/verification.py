"""Verification suite for agent auto-approval pipeline."""
from __future__ import annotations
import random
import uuid
from igrid.schema.task import TaskRequest, TaskResult
from igrid.schema.enums import ComputeTier

VERIFICATION_PROMPTS = [
    {"prompt": "List the planets in our solar system in order from the sun.", "min_tokens": 20},
    {"prompt": "Explain what photosynthesis is in two sentences.", "min_tokens": 15},
    {"prompt": "Write a Python function that returns the sum of a list.", "min_tokens": 10},
    {"prompt": "What are the three states of matter?", "min_tokens": 10},
    {"prompt": "Translate 'hello world' into French, Spanish, and German.", "min_tokens": 10},
    {"prompt": "Name five programming languages and one use case for each.", "min_tokens": 15},
    {"prompt": "What is the speed of light in meters per second?", "min_tokens": 5},
    {"prompt": "Describe how a binary search algorithm works.", "min_tokens": 15},
]

VERIFY_TASK_PREFIX = "verify-"


def pick_verification_task(agent_id: str, model: str) -> TaskRequest:
    """Pick a random verification prompt and return it as a TaskRequest."""
    entry = random.choice(VERIFICATION_PROMPTS)
    return TaskRequest(
        task_id=f"{VERIFY_TASK_PREFIX}{uuid.uuid4().hex[:12]}",
        model=model,
        prompt=entry["prompt"],
        system="Answer concisely.",
        max_tokens=256,
        temperature=0.7,
        min_tier=ComputeTier.BRONZE,
        timeout_s=120,
        priority=0,
    )


def check_verification_result(result: TaskResult, elapsed_ms: float) -> bool:
    """Validate a verification task result.

    Checks:
    1. Response is non-empty
    2. Output tokens > 0 (agent actually ran inference)
    3. Latency is reasonable (< 120s)
    """
    if not result.content or not result.content.strip():
        return False
    if result.output_tokens <= 0:
        return False
    if elapsed_ms > 120_000:
        return False
    return True


def should_sample_for_review(rate: float = 0.1) -> bool:
    """Return True with probability `rate` to flag for manual review."""
    return random.random() < rate
