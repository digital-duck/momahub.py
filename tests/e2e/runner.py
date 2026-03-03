"""Test runner: submit batches of prompts to an i-grid hub and collect results."""
from __future__ import annotations
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import httpx

DEFAULT_PROMPTS = Path(__file__).parent.parent / "lan" / "prompts.json"


@dataclass
class TaskResult:
    task_id: str
    category: str
    prompt: str
    model: str
    state: str = ""
    content: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    agent_id: str = ""
    error: str = ""
    submit_time: float = 0.0
    complete_time: float = 0.0

    @property
    def wall_time_ms(self) -> float:
        if self.complete_time and self.submit_time:
            return (self.complete_time - self.submit_time) * 1000
        return 0.0

    @property
    def tps(self) -> float:
        if self.latency_ms > 0 and self.output_tokens > 0:
            return self.output_tokens / (self.latency_ms / 1000)
        return 0.0


@dataclass
class RunReport:
    label: str
    hub_url: str
    results: list[TaskResult] = field(default_factory=list)
    started_at: float = 0.0
    finished_at: float = 0.0

    @property
    def completed(self) -> list[TaskResult]:
        return [r for r in self.results if r.state == "COMPLETE"]

    @property
    def failed(self) -> list[TaskResult]:
        return [r for r in self.results if r.state == "FAILED"]

    @property
    def timed_out(self) -> list[TaskResult]:
        return [r for r in self.results if r.state not in ("COMPLETE", "FAILED")]

    @property
    def total_wall_s(self) -> float:
        return self.finished_at - self.started_at if self.finished_at else 0.0

    def summary(self) -> dict:
        comp = self.completed
        if not comp:
            return {"total": len(self.results), "completed": 0, "failed": len(self.failed),
                    "timed_out": len(self.timed_out)}
        total_tokens = sum(r.output_tokens for r in comp)
        avg_latency = sum(r.latency_ms for r in comp) / len(comp)
        avg_tps = total_tokens / (sum(r.latency_ms for r in comp) / 1000) if sum(r.latency_ms for r in comp) > 0 else 0
        agents = set(r.agent_id for r in comp if r.agent_id)
        models = set(r.model for r in comp if r.model)
        return {
            "total": len(self.results),
            "completed": len(comp),
            "failed": len(self.failed),
            "timed_out": len(self.timed_out),
            "total_tokens": total_tokens,
            "avg_latency_ms": round(avg_latency, 1),
            "avg_tps": round(avg_tps, 1),
            "wall_time_s": round(self.total_wall_s, 1),
            "agents_used": len(agents),
            "models_used": sorted(models),
            "agent_distribution": {a: sum(1 for r in comp if r.agent_id == a) for a in agents},
        }

    def to_json(self) -> dict:
        return {
            "label": self.label,
            "hub_url": self.hub_url,
            "summary": self.summary(),
            "results": [
                {
                    "task_id": r.task_id, "category": r.category, "prompt": r.prompt,
                    "model": r.model, "state": r.state, "content": r.content,
                    "input_tokens": r.input_tokens, "output_tokens": r.output_tokens,
                    "latency_ms": r.latency_ms, "agent_id": r.agent_id,
                    "error": r.error, "wall_time_ms": round(r.wall_time_ms, 1),
                    "tps": round(r.tps, 1),
                }
                for r in self.results
            ],
        }


def load_prompts(path: str | Path | None = None) -> dict[str, list[dict]]:
    """Load prompts from JSON file. Returns {category: [prompt_dicts]}."""
    p = Path(path) if path else DEFAULT_PROMPTS
    with open(p) as f:
        return json.load(f)


def _submit_and_poll(hub_url: str, category: str, entry: dict,
                     timeout_s: int = 300,
                     on_progress: Callable | None = None) -> TaskResult:
    """Submit a single task to the hub and poll until complete or timeout."""
    task_id = str(uuid.uuid4())
    prompt = entry.get("prompt", "")
    model = entry.get("model", "llama3.1:8b")
    max_tokens = entry.get("max_tokens", 1024)
    temperature = entry.get("temperature", 0.7)
    system = entry.get("system", "")

    result = TaskResult(task_id=task_id, category=category, prompt=prompt, model=model)
    result.submit_time = time.monotonic()

    try:
        httpx.post(
            f"{hub_url}/tasks",
            json={"task_id": task_id, "model": model, "prompt": prompt,
                  "system": system, "max_tokens": max_tokens, "temperature": temperature},
            timeout=10.0,
        ).raise_for_status()
    except Exception as exc:
        result.state = "FAILED"
        result.error = f"submit error: {exc}"
        result.complete_time = time.monotonic()
        return result

    deadline = time.monotonic() + timeout_s
    interval = 1.0
    with httpx.Client(timeout=10.0) as client:
        while time.monotonic() < deadline:
            try:
                data = client.get(f"{hub_url}/tasks/{task_id}").json()
            except Exception:
                time.sleep(interval)
                continue
            state = data.get("state", "")
            if on_progress:
                on_progress(task_id, state)
            if state == "COMPLETE":
                r = data.get("result", {})
                result.state = "COMPLETE"
                result.content = r.get("content", "")
                result.model = r.get("model", model)
                result.input_tokens = r.get("input_tokens", 0)
                result.output_tokens = r.get("output_tokens", 0)
                result.latency_ms = r.get("latency_ms", 0.0)
                result.agent_id = r.get("agent_id", "")
                result.complete_time = time.monotonic()
                return result
            if state == "FAILED":
                result.state = "FAILED"
                result.error = data.get("result", {}).get("error", "unknown")
                result.complete_time = time.monotonic()
                return result
            time.sleep(interval)
            interval = min(interval * 1.2, 5.0)

    result.state = "TIMEOUT"
    result.error = f"timed out after {timeout_s}s"
    result.complete_time = time.monotonic()
    return result


def run_batch(hub_url: str, prompts: list[dict], category: str = "batch",
              concurrency: int = 1, timeout_s: int = 300, repeat: int = 1,
              on_progress: Callable | None = None,
              on_result: Callable | None = None,
              label: str = "") -> RunReport:
    """Run a batch of prompts against the hub.

    Args:
        hub_url: Hub base URL
        prompts: List of prompt dicts with keys: prompt, model, max_tokens, etc.
        category: Category label
        concurrency: Max parallel submissions
        timeout_s: Per-task timeout
        repeat: How many times to repeat the entire batch
        on_progress: callback(task_id, state) for live updates
        on_result: callback(TaskResult) when each task completes
        label: Label for the report
    """
    report = RunReport(label=label or category, hub_url=hub_url)
    report.started_at = time.monotonic()

    all_entries = []
    for _ in range(repeat):
        for entry in prompts:
            all_entries.append(entry)

    if concurrency <= 1:
        for entry in all_entries:
            r = _submit_and_poll(hub_url, category, entry, timeout_s, on_progress)
            report.results.append(r)
            if on_result:
                on_result(r)
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {
                pool.submit(_submit_and_poll, hub_url, category, entry, timeout_s, on_progress): entry
                for entry in all_entries
            }
            for future in as_completed(futures):
                r = future.result()
                report.results.append(r)
                if on_result:
                    on_result(r)

    report.finished_at = time.monotonic()
    return report


def run_categories(hub_url: str, prompts_dict: dict[str, list[dict]],
                   categories: list[str] | None = None,
                   concurrency: int = 1, timeout_s: int = 300, repeat: int = 1,
                   on_progress: Callable | None = None,
                   on_result: Callable | None = None,
                   label: str = "") -> RunReport:
    """Run one or more categories from a prompts dict."""
    cats = categories or list(prompts_dict.keys())
    all_entries = []
    for cat in cats:
        if cat not in prompts_dict:
            continue
        for entry in prompts_dict[cat]:
            all_entries.append(({**entry, "_category": cat}))

    report = RunReport(label=label or "+".join(cats), hub_url=hub_url)
    report.started_at = time.monotonic()

    expanded = []
    for _ in range(repeat):
        expanded.extend(all_entries)

    if concurrency <= 1:
        for entry in expanded:
            cat = entry.pop("_category", "unknown")
            r = _submit_and_poll(hub_url, cat, entry, timeout_s, on_progress)
            report.results.append(r)
            if on_result:
                on_result(r)
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {}
            for entry in expanded:
                cat = entry.pop("_category", "unknown")
                futures[pool.submit(_submit_and_poll, hub_url, cat, entry, timeout_s, on_progress)] = entry
            for future in as_completed(futures):
                r = future.result()
                report.results.append(r)
                if on_result:
                    on_result(r)

    report.finished_at = time.monotonic()
    return report
