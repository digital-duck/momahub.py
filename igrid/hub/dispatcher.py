"""Dispatcher: match PENDING tasks to available agents."""
from __future__ import annotations
import asyncio
import json
import logging
import httpx
from igrid.schema.enums import ComputeTier, TaskState
from igrid.schema.task import TaskRequest, TaskResult
from igrid.hub.state import GridState

_log = logging.getLogger("igrid.hub.dispatcher")
_TIER_ORDER = [ComputeTier.PLATINUM, ComputeTier.GOLD, ComputeTier.SILVER, ComputeTier.BRONZE]

def _tier_index(tier_str: str) -> int:
    try: return _TIER_ORDER.index(ComputeTier(tier_str))
    except ValueError: return len(_TIER_ORDER)

async def pick_agent(state: GridState, req: TaskRequest) -> dict | None:
    agents = await state.list_agents()
    min_idx = _tier_index(req.min_tier.value)
    candidates = []
    for a in agents:
        if a["status"] in ("OFFLINE", "PENDING_APPROVAL"): continue
        if _tier_index(a["tier"]) > min_idx: continue
        gpus = json.loads(a.get("gpus") or "[]")
        primary_vram = gpus[0]["vram_gb"] if gpus else 0.0
        if req.min_vram_gb > 0 and primary_vram < req.min_vram_gb: continue
        supported = json.loads(a.get("supported_models") or "[]")
        if supported and req.model:
            def _norm(m: str) -> str:
                return m[:-7] if m.endswith(":latest") else m
            req_model_norm = _norm(req.model)
            if not any(_norm(m) == req_model_norm for m in supported):
                continue
        # Rate limiting: skip agent if at its reported max concurrent tasks
        agent_max = a.get("max_concurrent", 3)
        async with state.db.execute(
            "SELECT COUNT(*) FROM tasks WHERE agent_id=? AND state IN (?,?)",
            (a["agent_id"], TaskState.DISPATCHED.value, TaskState.IN_FLIGHT.value),
        ) as cur:
            active_count = (await cur.fetchone())[0]
        if active_count >= agent_max:
            continue
        candidates.append((a, active_count))
    if not candidates: return None
    # Sort: prefer ONLINE, then best tier, then least loaded
    candidates.sort(key=lambda x: (0 if x[0]["status"] == "ONLINE" else 1,
                                   _tier_index(x[0]["tier"]), x[1]))
    return candidates[0][0]

async def deliver_task(agent: dict, req: TaskRequest) -> TaskResult:
    url = f"http://{agent['host']}:{agent['port']}/run"
    async with httpx.AsyncClient(timeout=httpx.Timeout(req.timeout_s + 10.0)) as client:
        resp = await client.post(url, json=req.model_dump())
        resp.raise_for_status()
    return TaskResult(**resp.json())

async def dispatch_pending(state: GridState, sse_queues: dict | None = None) -> int:
    async with state.db.execute("SELECT * FROM tasks WHERE state=? ORDER BY priority DESC, created_at LIMIT 50", (TaskState.PENDING.value,)) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    dispatched = 0
    for row in rows:
        req = TaskRequest(task_id=row["task_id"], model=row["model"], prompt=row["prompt"],
                          system=row["system"] or "", max_tokens=row["max_tokens"],
                          temperature=row["temperature"], min_tier=ComputeTier(row["min_tier"]),
                          min_vram_gb=row["min_vram_gb"], timeout_s=row["timeout_s"],
                          priority=row["priority"])
        agent = await pick_agent(state, req)
        if agent is None: continue
        claimed = await state.claim_task(req.task_id, agent["agent_id"])
        if not claimed: continue
        _log.info("dispatching task %s → agent %s", req.task_id, agent["agent_id"])
        asyncio.create_task(_deliver_and_update(state, agent, req, sse_queues), name=f"deliver-{req.task_id[:8]}")
        dispatched += 1
    return dispatched

async def _deliver_and_update(state: GridState, agent: dict, req: TaskRequest,
                              sse_queues: dict | None = None) -> None:
    aid = agent["agent_id"]
    # Pull mode: put task on SSE queue, agent will POST results back
    if sse_queues and aid in sse_queues:
        await state.mark_in_flight(req.task_id)
        await sse_queues[aid].put(req)
        _log.info("task %s queued via SSE for agent %s", req.task_id, aid)
        return
    # Push mode: HTTP POST to agent /run endpoint
    await state.mark_in_flight(req.task_id)
    try:
        result = await deliver_task(agent, req)
        if result.state == TaskState.FAILED and "Agent at capacity" in (result.error or ""):
            # Re-queue on capacity fail
            await state.fail_task(req.task_id, result.error or "Agent at capacity")
            return
            
        await state.complete_task(req.task_id, result)
        tokens = result.output_tokens
        await state.record_reward(agent.get("operator_id", "unknown"), aid, req.task_id, tokens, tokens / 1000.0)
        _log.info("task %s complete  tokens=%d", req.task_id, tokens)
    except Exception as exc:
        _log.warning("task %s failed on agent %s: %s", req.task_id, aid, exc)
        await state.fail_task(req.task_id, str(exc))
