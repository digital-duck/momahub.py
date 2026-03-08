"""IGridAdapter: SPL LLMAdapter that routes inference to the Momahub hub."""
from __future__ import annotations
import asyncio
import logging
import time
import uuid
import httpx

_log = logging.getLogger("igrid.spl.adapter")

try:
    from spl.adapters.base import LLMAdapter, GenerationResult
except ImportError:
    class GenerationResult:
        def __init__(self, **kw):
            for k, v in kw.items(): setattr(self, k, v)
    class LLMAdapter:
        async def generate(self, **kw) -> GenerationResult: raise NotImplementedError

class IGridAdapter(LLMAdapter):
    def __init__(self, hub_url: str = "http://localhost:8000", **kwargs):
        self.hub_url = hub_url.rstrip("/")

    async def generate(self, prompt: str, model: str, max_tokens: int = 1024,
                       temperature: float = 0.7, system: str = "", **kwargs) -> GenerationResult:
        task_id = str(uuid.uuid4())
        payload = {"task_id": task_id, "model": model, "prompt": prompt, "system": system,
                   "max_tokens": max_tokens, "temperature": temperature,
                   "min_vram_gb": kwargs.get("min_vram_gb", 0.0)}
        start = time.perf_counter()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{self.hub_url}/tasks", json=payload)
            resp.raise_for_status()
        result = await self._poll(task_id)
        latency_ms = (time.perf_counter() - start) * 1000
        return GenerationResult(content=result.get("content", ""), model=result.get("model", model),
                                input_tokens=result.get("input_tokens", 0), output_tokens=result.get("output_tokens", 0),
                                total_tokens=result.get("input_tokens", 0) + result.get("output_tokens", 0),
                                latency_ms=latency_ms, cost_usd=None)

    def count_tokens(self, text: str, model: str = "") -> int:
        return len(text) // 4

    def list_models(self) -> list[str]:
        return []

    async def _poll(self, task_id: str, timeout_s: int = 300) -> dict:
        deadline = time.monotonic() + timeout_s
        interval = 1.0
        async with httpx.AsyncClient(timeout=10.0) as client:
            while time.monotonic() < deadline:
                resp = await client.get(f"{self.hub_url}/tasks/{task_id}")
                data = resp.json()
                state = data.get("state", "")
                if state == "COMPLETE": return data.get("result") or data
                if state == "FAILED":
                    r = data.get("result") or {}
                    raise RuntimeError(f"Task {task_id} failed: {r.get('error', 'unknown')}")
                await asyncio.sleep(interval)
                interval = min(interval * 1.5, 10.0)
        raise TimeoutError(f"Task {task_id} timed out after {timeout_s}s")
