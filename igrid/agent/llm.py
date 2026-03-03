"""LLM backend: Ollama HTTP API."""
from __future__ import annotations
import logging
import time
import httpx

_log = logging.getLogger("igrid.agent.llm")
OLLAMA_BASE = "http://localhost:11434"

class OllamaBackend:
    def __init__(self, base_url: str = OLLAMA_BASE):
        self.base_url = base_url.rstrip("/")

    async def generate(self, model: str, prompt: str, system: str = "",
                       max_tokens: int = 1024, temperature: float = 0.7) -> dict:
        payload = {"model": model, "prompt": prompt, "system": system,
                   "options": {"num_predict": max_tokens, "temperature": temperature}, "stream": False}
        start = time.perf_counter()
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(f"{self.base_url}/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()
        latency_ms = (time.perf_counter() - start) * 1000
        eval_count = data.get("eval_count", 0)
        eval_ns = data.get("eval_duration", 0)
        tps = (eval_count / (eval_ns / 1e9)) if eval_ns > 0 else 0.0
        return {"content": data.get("response", ""), "input_tokens": data.get("prompt_eval_count", 0),
                "output_tokens": eval_count, "tps": round(tps, 2), "latency_ms": round(latency_ms, 1)}

    async def list_models(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                resp.raise_for_status()
            return [m["name"] for m in resp.json().get("models", [])]
        except Exception: return []

    async def benchmark(self, model: str, sample_prompt: str = "Say hello") -> float:
        try:
            result = await self.generate(model, sample_prompt, max_tokens=50)
            return result["tps"]
        except Exception: return 0.0
