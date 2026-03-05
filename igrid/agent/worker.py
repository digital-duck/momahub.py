"""Agent worker FastAPI app."""
from __future__ import annotations
import asyncio
import logging
import socket
import uuid
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, Request
from igrid.agent.hardware import detect_gpus, cpu_info
from igrid.agent.llm import OllamaBackend
from igrid.agent.telemetry import TelemetrySender
from igrid.schema.enums import tier_from_tps, TaskState
from igrid.schema.handshake import JoinRequest, GPUInfo as SchemaGPU
from igrid.schema.task import TaskRequest, TaskResult

_log = logging.getLogger("igrid.agent.worker")

class AgentStats:
    def __init__(self): self.tasks_completed = 0; self.current_tps: float = 0.0
    def get(self): return self.tasks_completed, self.current_tps

def create_agent_app(agent_id: str | None = None, operator_id: str = "duck",
                     hub_urls: list[str] | None = None, ollama_url: str = "http://localhost:11434",
                     api_key: str = "", pull_mode: bool = False,
                     agent_name: str = "",
                     max_concurrent: int = 3,
                     max_prompt_chars: int = 200_000) -> FastAPI:
    _agent_id = agent_id or str(uuid.uuid4())
    _agent_name = agent_name or socket.gethostname()
    _hub_urls = hub_urls or ["http://localhost:8000"]
    _stats = AgentStats()
    _backend = OllamaBackend(ollama_url)
    _semaphore = asyncio.Semaphore(max_concurrent)
    _max_prompt_chars = max_prompt_chars

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        gpus = detect_gpus()
        schema_gpus = [SchemaGPU(index=g.index, model=g.model, vram_gb=g.vram_gb) for g in gpus]
        cpu_cores, ram_gb = cpu_info()
        models = await _backend.list_models()
        initial_tps = 0.0
        if models:
            initial_tps = await _backend.benchmark(models[0])
            _stats.current_tps = initial_tps
        host = app.state.host; port = app.state.port
        join_req = JoinRequest(operator_id=operator_id, agent_id=_agent_id, host=host, port=port,
                               name=_agent_name, gpus=schema_gpus, cpu_cores=cpu_cores, ram_gb=ram_gb,
                               supported_models=models, cached_models=models,
                               pull_mode=pull_mode, api_key=api_key)
        async with httpx.AsyncClient(timeout=10.0) as client:
            for hub_url in _hub_urls:
                try:
                    resp = await client.post(f"{hub_url}/join", json=join_req.model_dump())
                    resp.raise_for_status()
                    _log.info("registered with hub %s  tier=%s", hub_url, resp.json().get("tier"))
                except Exception as exc:
                    _log.error("failed to register with hub %s: %s", hub_url, exc)
        app.state.agent_id = _agent_id; app.state.stats = _stats; app.state.backend = _backend
        tele = TelemetrySender(_agent_id, operator_id, _hub_urls, _stats.get)
        tele_task = asyncio.create_task(tele.run(), name="telemetry")
        sse_tasks: list[asyncio.Task] = []
        if pull_mode:
            from igrid.agent.sse_consumer import run_sse_consumer
            for hub_url in _hub_urls:
                t = asyncio.create_task(
                    run_sse_consumer(_agent_id, hub_url, _backend, _stats),
                    name=f"sse-{hub_url}",
                )
                sse_tasks.append(t)
            _log.info("pull mode: %d SSE consumer(s) started", len(sse_tasks))
        yield
        for t in sse_tasks: t.cancel()
        async with httpx.AsyncClient(timeout=5.0) as client:
            for hub_url in _hub_urls:
                try: await client.post(f"{hub_url}/leave", json={"operator_id": operator_id, "agent_id": _agent_id})
                except Exception: pass
        tele.stop(); tele_task.cancel()

    app = FastAPI(title="i-grid Agent", version="0.2.0", lifespan=lifespan)
    app.state.host = "127.0.0.1"; app.state.port = 8100

    @app.get("/health")
    async def health(request: Request):
        tc, tps = request.app.state.stats.get()
        return {"agent_id": request.app.state.agent_id, "operator_id": operator_id, "status": "ok",
                "tasks_completed": tc, "current_tps": tps}

    @app.post("/run", response_model=TaskResult)
    async def run_task(req: TaskRequest, request: Request):
        aid = request.app.state.agent_id
        # Prompt size check
        if len(req.prompt) > _max_prompt_chars:
            return TaskResult(task_id=req.task_id, state=TaskState.FAILED,
                              error=f"Prompt exceeds {_max_prompt_chars} chars", agent_id=aid)
        # Concurrency check
        if _semaphore.locked():
            return TaskResult(task_id=req.task_id, state=TaskState.FAILED,
                              error="Agent at capacity", agent_id=aid)
        async with _semaphore:
            backend: OllamaBackend = request.app.state.backend
            stats: AgentStats = request.app.state.stats
            try:
                data = await backend.generate(req.model, req.prompt, req.system, req.max_tokens, req.temperature)
                stats.tasks_completed += 1; stats.current_tps = data["tps"]
                return TaskResult(task_id=req.task_id, state=TaskState.COMPLETE, content=data["content"],
                                  model=req.model, input_tokens=data["input_tokens"],
                                  output_tokens=data["output_tokens"], latency_ms=data["latency_ms"],
                                  agent_id=aid)
            except Exception as exc:
                return TaskResult(task_id=req.task_id, state=TaskState.FAILED, error=str(exc),
                                  agent_id=aid)

    return app
