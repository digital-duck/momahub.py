"""i-grid Hub FastAPI application."""
from __future__ import annotations
import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from igrid.hub.db import init_db
from igrid.hub.state import GridState
from igrid.hub.dispatcher import dispatch_pending
from igrid.hub.cluster import ClusterManager
from igrid.hub.monitor import agent_monitor, cluster_monitor
from igrid.schema.enums import AgentStatus, ComputeTier, TaskState, tier_from_tps
from igrid.schema.handshake import JoinRequest, JoinAck, LeaveRequest, LeaveAck
from igrid.schema.pulse import PulseReport, PulseAck
from igrid.schema.task import TaskRequest, TaskResult, TaskStatusResponse
from igrid.schema.cluster import PeerHandshake, PeerHandshakeAck, PeerCapabilityUpdate, ClusterStatus

_log = logging.getLogger("igrid.hub")

def create_app(hub_id: str | None = None, operator_id: str = "duck",
               db_path: str = ".igrid/hub.db", hub_url: str = "http://localhost:8000",
               api_key: str = "") -> FastAPI:
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
        tasks = [
            asyncio.create_task(agent_monitor(_state), name="agent-monitor"),
            asyncio.create_task(cluster_monitor(_state, _cluster_mgr), name="cluster-monitor"),
            asyncio.create_task(_dispatch_loop(_state), name="dispatch-loop"),
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
    async def join(req: JoinRequest, state: GridDep):
        await state.register_agent(req, ComputeTier.BRONZE)
        _log.info("agent %s joined", req.agent_id)
        return JoinAck(accepted=True, hub_id=state.hub_id, operator_id=req.operator_id,
                       agent_id=req.agent_id, tier=ComputeTier.BRONZE, message="Welcome to the grid.")

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

    return app

async def _dispatch_loop(state: GridState, interval_s: float = 2.0) -> None:
    while True:
        try:
            n = await dispatch_pending(state)
            if n: _log.debug("dispatched %d tasks", n)
        except Exception as exc:
            _log.error("dispatch loop error: %s", exc)
        await asyncio.sleep(interval_s)
