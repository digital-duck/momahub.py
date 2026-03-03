"""i-grid Hub FastAPI application."""
from __future__ import annotations
import asyncio
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from igrid.hub.db import init_db
from igrid.hub.state import GridState
from igrid.hub.dispatcher import dispatch_pending, deliver_task
from igrid.hub.cluster import ClusterManager
from igrid.hub.monitor import agent_monitor, cluster_monitor
from igrid.hub.verification import (
    pick_verification_task, check_verification_result,
    should_sample_for_review, VERIFY_TASK_PREFIX,
)
from igrid.schema.enums import AgentStatus, ComputeTier, TaskState, tier_from_tps
from igrid.schema.handshake import JoinRequest, JoinAck, LeaveRequest, LeaveAck
from igrid.schema.pulse import PulseReport, PulseAck
from igrid.schema.task import TaskRequest, TaskResult, TaskStatusResponse
from igrid.schema.cluster import PeerHandshake, PeerHandshakeAck, PeerCapabilityUpdate, ClusterStatus

_log = logging.getLogger("igrid.hub")

def create_app(hub_id: str | None = None, operator_id: str = "duck",
               db_path: str = ".igrid/hub.db", hub_url: str = "http://localhost:8000",
               api_key: str = "", admin_mode: bool = False,
               max_concurrent_tasks: int = 3) -> FastAPI:
    _hub_id = hub_id or f"hub-{uuid.uuid4().hex[:8]}"
    _state: GridState | None = None
    _cluster_mgr: ClusterManager | None = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal _state, _cluster_mgr
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        db = await init_db(db_path)
        for k, v in [("hub_id", _hub_id), ("operator_id", operator_id), ("hub_url", hub_url)]:
            await db.execute("INSERT OR REPLACE INTO hub_config(key,value) VALUES (?,?)", (k, v))
        await db.commit()
        _state = GridState(db, _hub_id, operator_id)
        _cluster_mgr = ClusterManager(_state, hub_url)
        app.state.grid = _state
        app.state.cluster = _cluster_mgr
        app.state.api_key = api_key
        app.state.admin_mode = admin_mode
        app.state.max_concurrent_tasks = max_concurrent_tasks
        app.state.allowed_countries = []  # empty = all allowed
        app.state.sse_queues = {}
        tasks = [
            asyncio.create_task(agent_monitor(_state), name="agent-monitor"),
            asyncio.create_task(cluster_monitor(_state, _cluster_mgr), name="cluster-monitor"),
            asyncio.create_task(_dispatch_loop(_state, app), name="dispatch-loop"),
        ]
        _log.info("hub %s started  url=%s  db=%s", _hub_id, hub_url, db_path)
        yield
        for t in tasks: t.cancel()
        await db.close()

    app = FastAPI(title="i-grid Hub", version="0.2.0", lifespan=lifespan)

    def get_state(request: Request) -> GridState: return request.app.state.grid
    def get_cluster(request: Request) -> ClusterManager: return request.app.state.cluster
    async def check_api_key(request: Request) -> None:
        configured = request.app.state.api_key
        if configured and request.headers.get("X-API-Key", "") != configured:
            raise HTTPException(status_code=401, detail="Invalid API key")

    GridDep = Annotated[GridState, Depends(get_state)]
    ClusterDep = Annotated[ClusterManager, Depends(get_cluster)]

    @app.get("/health")
    async def health(state: GridDep):
        agents = await state.list_agents()
        return {"hub_id": state.hub_id, "operator_id": state.operator_id, "status": "ok",
                "agents_online": len([a for a in agents if a["status"] != "OFFLINE"]),
                "time": datetime.now(timezone.utc).isoformat()}

    @app.post("/join", response_model=JoinAck, dependencies=[Depends(check_api_key)])
    async def join(req: JoinRequest, request: Request, state: GridDep):
        is_admin = request.app.state.admin_mode
        initial_status = await state.register_agent(req, ComputeTier.BRONZE, admin_mode=is_admin)
        _log.info("agent %s joined  status=%s  admin_mode=%s", req.agent_id, initial_status, is_admin)
        if initial_status == AgentStatus.PENDING_APPROVAL.value:
            # Spawn background verification task
            asyncio.create_task(
                _verify_agent(state, request.app, req),
                name=f"verify-{req.agent_id[:8]}",
            )
            return JoinAck(accepted=True, hub_id=state.hub_id, operator_id=req.operator_id,
                           agent_id=req.agent_id, tier=ComputeTier.BRONZE,
                           status=AgentStatus.PENDING_APPROVAL.value,
                           message="Pending verification. A benchmark task has been sent.")
        return JoinAck(accepted=True, hub_id=state.hub_id, operator_id=req.operator_id,
                       agent_id=req.agent_id, tier=ComputeTier.BRONZE,
                       status=AgentStatus.ONLINE.value,
                       message="Welcome to the grid.")

    @app.post("/leave", response_model=LeaveAck)
    async def leave(req: LeaveRequest, state: GridDep):
        await state.remove_agent(req.agent_id)
        return LeaveAck(ok=True)

    @app.post("/pulse", response_model=PulseAck)
    async def pulse(report: PulseReport, state: GridDep):
        await state.record_pulse(report.agent_id, report.status, report.gpu_utilization_pct,
                                 report.vram_used_gb, report.current_tps, report.tasks_completed)
        return PulseAck(ok=True, hub_time=datetime.now(timezone.utc).isoformat())

    @app.post("/tasks", status_code=202)
    async def submit_task(req: TaskRequest, state: GridDep):
        if not req.task_id: req.task_id = str(uuid.uuid4())
        await state.submit_task(req)
        return {"task_id": req.task_id, "state": TaskState.PENDING.value}

    @app.get("/tasks/{task_id}", response_model=TaskStatusResponse)
    async def get_task(task_id: str, state: GridDep):
        row = await state.get_task(task_id)
        if row is None: raise HTTPException(status_code=404, detail="Task not found")
        result = None
        if row["state"] in (TaskState.COMPLETE.value, TaskState.FAILED.value):
            result = TaskResult(task_id=row["task_id"], state=TaskState(row["state"]),
                                content=row.get("content") or "", model=row.get("model") or "",
                                input_tokens=row.get("input_tokens") or 0, output_tokens=row.get("output_tokens") or 0,
                                latency_ms=row.get("latency_ms") or 0.0, agent_id=row.get("agent_id") or "",
                                error=row.get("error") or "")
        return TaskStatusResponse(task_id=row["task_id"], state=TaskState(row["state"]), result=result)

    @app.get("/tasks")
    async def list_tasks(state: GridDep, limit: int = 50):
        return {"tasks": await state.list_tasks(limit)}

    @app.get("/agents")
    async def list_agents(state: GridDep):
        return {"agents": await state.list_agents()}

    @app.get("/agents/pending")
    async def list_pending_agents(state: GridDep):
        """List agents awaiting approval (admin mode)."""
        return {"agents": await state.list_pending_agents()}

    @app.post("/agents/{agent_id}/approve")
    async def approve_agent(agent_id: str, state: GridDep):
        """Manually approve a pending agent."""
        ok = await state.approve_agent(agent_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Agent not found")
        _log.info("agent %s manually approved", agent_id)
        return {"ok": True, "agent_id": agent_id, "status": "ONLINE"}

    @app.post("/agents/{agent_id}/reject")
    async def reject_agent(agent_id: str, state: GridDep):
        """Reject/ban a pending agent."""
        ok = await state.reject_agent(agent_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Agent not found")
        _log.info("agent %s rejected", agent_id)
        return {"ok": True, "agent_id": agent_id, "status": "OFFLINE"}

    @app.get("/rewards")
    async def reward_summary(state: GridDep):
        return {"summary": await state.reward_summary()}

    @app.get("/logs")
    async def recent_logs(state: GridDep, limit: int = 50):
        return {"logs": await state.recent_pulse_logs(limit)}

    @app.post("/cluster/handshake", response_model=PeerHandshakeAck)
    async def cluster_handshake(hs: PeerHandshake, state: GridDep):
        await state.add_peer(hs.hub_id, hs.hub_url, hs.operator_id)
        from igrid.hub.cluster import _capabilities_from_agents
        caps = _capabilities_from_agents(await state.list_agents())
        return PeerHandshakeAck(accepted=True, hub_id=state.hub_id, hub_url=hub_url, capabilities=caps)

    @app.post("/cluster/capabilities")
    async def update_capabilities(update: PeerCapabilityUpdate, state: GridDep):
        await state.mark_peer_seen(update.hub_id)
        return {"ok": True}

    @app.post("/cluster/peers")
    async def add_peer(body: dict, state: GridDep, cluster: ClusterDep):
        peer_url = body.get("url", "").rstrip("/")
        if not peer_url: raise HTTPException(status_code=400, detail="url is required")
        ack = await cluster.add_peer(peer_url)
        return ack.model_dump()

    @app.get("/cluster/status", response_model=ClusterStatus)
    async def cluster_status(state: GridDep):
        return ClusterStatus(this_hub_id=state.hub_id, peers=await state.list_peers())

    # ── SSE pull-mode endpoints ──────────────────────────────────

    @app.get("/task-stream/{agent_id}")
    async def task_stream(agent_id: str, request: Request):
        """SSE endpoint for pull-mode agents. Yields task JSON as events."""
        queue: asyncio.Queue = asyncio.Queue()
        request.app.state.sse_queues[agent_id] = queue
        _log.info("SSE stream opened for agent %s", agent_id)

        async def event_generator():
            try:
                while True:
                    try:
                        task = await asyncio.wait_for(queue.get(), timeout=15.0)
                        yield f"data: {task.model_dump_json()}\n\n"
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
                    if await request.is_disconnected():
                        break
            finally:
                request.app.state.sse_queues.pop(agent_id, None)
                _log.info("SSE stream closed for agent %s", agent_id)

        return StreamingResponse(event_generator(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/results")
    async def receive_results(result: TaskResult, state: GridDep):
        """Receive task results from pull-mode agents."""
        row = await state.get_task(result.task_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Task not found")
        # Idempotent: skip if already completed
        if row["state"] in (TaskState.COMPLETE.value, TaskState.FAILED.value):
            return {"ok": True, "detail": "already completed"}
        await state.complete_task(result.task_id, result)
        if result.state == TaskState.COMPLETE and result.output_tokens > 0:
            agent_id = result.agent_id or row.get("agent_id") or ""
            operator_id = "unknown"
            if agent_id:
                async with state.db.execute("SELECT operator_id FROM agents WHERE agent_id=?", (agent_id,)) as cur:
                    agent_row = await cur.fetchone()
                if agent_row:
                    operator_id = agent_row[0]
            await state.record_reward(operator_id, agent_id, result.task_id,
                                      result.output_tokens, result.output_tokens / 1000.0)
        _log.info("results received for task %s from agent %s", result.task_id, result.agent_id)
        return {"ok": True}

    return app

async def _dispatch_loop(state: GridState, app: FastAPI, interval_s: float = 2.0) -> None:
    while True:
        try:
            n = await dispatch_pending(
                state,
                sse_queues=app.state.sse_queues,
                max_concurrent=app.state.max_concurrent_tasks,
            )
            if n: _log.debug("dispatched %d tasks", n)
        except Exception as exc:
            _log.error("dispatch loop error: %s", exc)
        await asyncio.sleep(interval_s)


async def _verify_agent(state: GridState, app: FastAPI, req: JoinRequest) -> None:
    """Background task: send verification benchmark to a newly joined agent."""
    agent_id = req.agent_id
    model = req.cached_models[0] if req.cached_models else (req.supported_models[0] if req.supported_models else "llama3")
    vtask = pick_verification_task(agent_id, model)

    # Look up agent record for HTTP delivery
    async with state.db.execute(
        "SELECT host, port, pull_mode FROM agents WHERE agent_id=?", (agent_id,)
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        _log.warning("verify: agent %s not found in DB", agent_id)
        return

    agent_host, agent_port, pull_mode = row[0], row[1], row[2]
    _log.info("verify: sending benchmark to agent %s  model=%s  task=%s", agent_id, model, vtask.task_id)

    try:
        t0 = time.monotonic()
        url = f"http://{agent_host}:{agent_port}/run"
        async with httpx.AsyncClient(timeout=httpx.Timeout(vtask.timeout_s + 10.0)) as client:
            resp = await client.post(url, json=vtask.model_dump())
            resp.raise_for_status()
        elapsed_ms = (time.monotonic() - t0) * 1000
        result = TaskResult(**resp.json())
    except Exception as exc:
        _log.warning("verify: benchmark failed for agent %s: %s", agent_id, exc)
        return  # stays PENDING_APPROVAL for manual review

    # Check benchmark result
    if not check_verification_result(result, elapsed_ms):
        _log.warning("verify: agent %s failed benchmark (tokens=%d, elapsed=%.0fms)",
                     agent_id, result.output_tokens, elapsed_ms)
        return  # stays PENDING_APPROVAL

    # Geo-IP check
    allowed_countries = app.state.allowed_countries
    if allowed_countries:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                geo = await client.get(f"http://ip-api.com/json/{agent_host}")
                country = geo.json().get("countryCode", "")
            if country not in allowed_countries:
                _log.warning("verify: agent %s geo-IP %s not in allowed list", agent_id, country)
                return  # stays PENDING_APPROVAL
        except Exception as exc:
            _log.warning("verify: geo-IP check failed for agent %s: %s (proceeding)", agent_id, exc)

    # Random sampling for manual review
    if should_sample_for_review():
        _log.info("verify: agent %s passed but sampled for manual review", agent_id)
        return  # stays PENDING_APPROVAL, flagged for review

    # Auto-approve
    await state.approve_agent(agent_id)
    _log.info("verify: agent %s auto-approved", agent_id)
