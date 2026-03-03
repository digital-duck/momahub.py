"""Background monitors: agent health and cluster sync."""
from __future__ import annotations
import asyncio
import logging
from igrid.hub.state import GridState

_log = logging.getLogger("igrid.hub.monitor")

async def agent_monitor(state: GridState) -> None:
    while True:
        await asyncio.sleep(30)
        try:
            evicted = await state.evict_stale_agents()
            if evicted: _log.info("evicted %d stale agent(s)", evicted)
        except Exception as exc:
            _log.error("agent monitor error: %s", exc)

async def cluster_monitor(state: GridState, cluster_mgr) -> None:
    from igrid.schema.enums import TaskState, ComputeTier
    from igrid.schema.task import TaskRequest
    while True:
        await asyncio.sleep(60)
        try:
            await cluster_mgr.push_capabilities()
            async with state.db.execute("SELECT * FROM tasks WHERE state=? ORDER BY created_at LIMIT 20",
                                        (TaskState.PENDING.value,)) as cur:
                rows = [dict(r) for r in await cur.fetchall()]
            for row in rows:
                req = TaskRequest(task_id=row["task_id"], model=row["model"], prompt=row["prompt"],
                                  system=row["system"] or "", max_tokens=row["max_tokens"],
                                  temperature=row["temperature"], min_tier=ComputeTier(row["min_tier"]),
                                  min_vram_gb=row["min_vram_gb"], timeout_s=row["timeout_s"])
                asyncio.create_task(cluster_mgr.forward_task(req), name=f"fwd-{req.task_id[:8]}")
        except Exception as exc:
            _log.error("cluster monitor error: %s", exc)
