"""SSE consumer: pull tasks from hub via Server-Sent Events."""
from __future__ import annotations
import asyncio
import json
import logging
import httpx
from igrid.agent.llm import OllamaBackend
from igrid.schema.enums import TaskState
from igrid.schema.task import TaskRequest, TaskResult

_log = logging.getLogger("igrid.agent.sse")


async def run_sse_consumer(
    agent_id: str,
    hub_url: str,
    backend: OllamaBackend,
    stats,
    max_concurrent: int = 3,
) -> None:
    """Connect to hub SSE stream and process tasks. Auto-reconnects on failure."""
    url = f"{hub_url}/task-stream/{agent_id}"
    backoff = 2.0
    max_backoff = 30.0
    _semaphore = asyncio.Semaphore(max_concurrent)

    while True:
        try:
            _log.info("SSE connecting to %s", url)
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("GET", url) as resp:
                    resp.raise_for_status()
                    _log.info("SSE connected to %s", hub_url)
                    backoff = 2.0  # reset on successful connect
                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            payload = line[6:]
                            try:
                                req = TaskRequest(**json.loads(payload))
                                asyncio.create_task(
                                    _handle_task(agent_id, hub_url, backend, stats, req, _semaphore),
                                    name=f"sse-task-{req.task_id[:8]}",
                                )
                            except Exception as exc:
                                _log.warning("bad SSE payload: %s", exc)
                        # keepalive lines (": keepalive") are silently ignored
        except asyncio.CancelledError:
            _log.info("SSE consumer cancelled for %s", hub_url)
            return
        except Exception as exc:
            _log.warning("SSE connection lost (%s): %s — reconnecting in %.0fs", hub_url, exc, backoff)

        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, max_backoff)


async def _handle_task(
    agent_id: str,
    hub_url: str,
    backend: OllamaBackend,
    stats,
    req: TaskRequest,
    semaphore: asyncio.Semaphore,
) -> None:
    """Run inference and POST result back to the hub."""
    async with semaphore:
        try:
            data = await backend.generate(req.model, req.prompt, req.system, req.max_tokens, req.temperature)
            stats.tasks_completed += 1
            stats.current_tps = data["tps"]
            result = TaskResult(
                task_id=req.task_id, state=TaskState.COMPLETE, content=data["content"],
                model=req.model, input_tokens=data["input_tokens"],
                output_tokens=data["output_tokens"], latency_ms=data["latency_ms"],
                agent_id=agent_id,
            )
        except Exception as exc:
            _log.error("task %s failed: %s", req.task_id, exc)
            result = TaskResult(task_id=req.task_id, state=TaskState.FAILED,
                                error=str(exc), agent_id=agent_id)
    # POST result back to hub
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{hub_url}/results", json=result.model_dump())
            resp.raise_for_status()
        _log.info("task %s result posted to %s", req.task_id, hub_url)
    except Exception as exc:
        _log.error("failed to post result for task %s: %s", req.task_id, exc)
