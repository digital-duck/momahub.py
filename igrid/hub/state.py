"""GridState: shared async state injected into every FastAPI handler."""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
import aiosqlite
from igrid.schema.enums import AgentStatus, ComputeTier, TaskState, tier_from_tps
from igrid.schema.handshake import JoinRequest
from igrid.schema.task import TaskRequest, TaskResult

_log = logging.getLogger("igrid.hub.state")
MAX_RETRIES = 3
AGENT_TIMEOUT_S = 90

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

class GridState:
    def __init__(self, db: aiosqlite.Connection, hub_id: str, operator_id: str):
        self.db = db
        self.hub_id = hub_id
        self.operator_id = operator_id

    async def register_agent(self, req: JoinRequest, tier: ComputeTier,
                             admin_mode: bool = False) -> str:
        """Register an agent. Returns the initial status string."""
        await self.db.execute("INSERT OR IGNORE INTO operators(operator_id) VALUES (?)", (req.operator_id,))
        gpus_json = json.dumps([g.model_dump() for g in req.gpus])
        models_json = json.dumps(req.supported_models)

        # Determine initial status
        if admin_mode:
            # Check if agent was previously approved (re-join keeps ONLINE)
            async with self.db.execute(
                "SELECT status FROM agents WHERE agent_id=?", (req.agent_id,)
            ) as cur:
                existing = await cur.fetchone()
            if existing and existing[0] == AgentStatus.ONLINE.value:
                initial_status = AgentStatus.ONLINE.value
            else:
                initial_status = AgentStatus.PENDING_APPROVAL.value
        else:
            initial_status = AgentStatus.ONLINE.value

        # For re-joining agents in admin mode, preserve approved status
        on_conflict_status = (
            "CASE WHEN agents.status = 'ONLINE' THEN 'ONLINE' ELSE excluded.status END"
            if admin_mode else "'ONLINE'"
        )
        await self.db.execute(f"""
            INSERT INTO agents
                (agent_id, operator_id, name, host, port, status, tier, gpus, cpu_cores, ram_gb, supported_models, max_concurrent, pull_mode, joined_at, last_pulse)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(agent_id) DO UPDATE SET
                name=excluded.name, host=excluded.host, port=excluded.port, status={on_conflict_status}, tier=excluded.tier,
                gpus=excluded.gpus, cpu_cores=excluded.cpu_cores, ram_gb=excluded.ram_gb,
                supported_models=excluded.supported_models, max_concurrent=excluded.max_concurrent, 
                pull_mode=excluded.pull_mode, last_pulse=excluded.last_pulse
            """,
            (req.agent_id, req.operator_id, req.name, req.host, req.port,
             initial_status, tier.value, gpus_json, req.cpu_cores, req.ram_gb, models_json,
             req.max_concurrent, int(req.pull_mode), _now(), _now()))
        await self.db.commit()
        return initial_status

    async def remove_agent(self, agent_id: str) -> None:
        await self.db.execute("UPDATE agents SET status=? WHERE agent_id=?", (AgentStatus.OFFLINE.value, agent_id))
        await self.db.execute("""
            UPDATE tasks SET state=?, agent_id=NULL, updated_at=?
            WHERE agent_id=? AND state IN (?,?)
            """, (TaskState.PENDING.value, _now(), agent_id, TaskState.DISPATCHED.value, TaskState.IN_FLIGHT.value))
        await self.db.commit()

    async def approve_agent(self, agent_id: str) -> bool:
        """Approve a pending agent → ONLINE. Returns True if agent existed."""
        async with self.db.execute(
            "UPDATE agents SET status=? WHERE agent_id=? RETURNING agent_id",
            (AgentStatus.ONLINE.value, agent_id),
        ) as cur:
            row = await cur.fetchone()
        await self.db.commit()
        return row is not None

    async def reject_agent(self, agent_id: str) -> bool:
        """Reject/ban an agent → OFFLINE. Returns True if agent existed."""
        async with self.db.execute(
            "UPDATE agents SET status=? WHERE agent_id=? RETURNING agent_id",
            (AgentStatus.OFFLINE.value, agent_id),
        ) as cur:
            row = await cur.fetchone()
        await self.db.commit()
        return row is not None

    async def list_pending_agents(self) -> list[dict]:
        """List agents awaiting approval."""
        async with self.db.execute(
            "SELECT * FROM agents WHERE status=? ORDER BY joined_at",
            (AgentStatus.PENDING_APPROVAL.value,),
        ) as cur:
            return [dict(row) for row in await cur.fetchall()]

    async def record_pulse(self, agent_id: str, status: AgentStatus, gpu_util: float, vram_used: float, tps: float, tasks_done: int) -> None:
        now = _now()
        await self.db.execute("""
            UPDATE agents SET status=?, current_tps=?, tasks_completed=?, last_pulse=?, tier=?
            WHERE agent_id=?
            """, (status.value, tps, tasks_done, now, tier_from_tps(tps).value if tps > 0 else None, agent_id))
        await self.db.execute("""
            INSERT INTO pulse_log (agent_id, status, gpu_util_pct, vram_used_gb, current_tps, tasks_completed, logged_at)
            VALUES (?,?,?,?,?,?,?)
            """, (agent_id, status.value, gpu_util, vram_used, tps, tasks_done, now))
        await self.db.commit()

    async def list_agents(self) -> list[dict]:
        async with self.db.execute("SELECT * FROM agents WHERE status != 'OFFLINE' ORDER BY tier") as cur:
            return [dict(row) for row in await cur.fetchall()]

    async def evict_stale_agents(self) -> int:
        cutoff = f"datetime('now', '-{AGENT_TIMEOUT_S} seconds')"
        async with self.db.execute(f"SELECT agent_id FROM agents WHERE status='ONLINE' AND last_pulse < {cutoff}") as cur:
            stale = [row[0] for row in await cur.fetchall()]
        for aid in stale:
            _log.warning("evicting stale agent %s", aid)
            await self.remove_agent(aid)
        return len(stale)

    async def submit_task(self, req: TaskRequest) -> str:
        await self.db.execute("""
            INSERT INTO tasks (task_id, state, model, prompt, system, max_tokens, temperature, min_tier, min_vram_gb, timeout_s, priority, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (req.task_id, TaskState.PENDING.value, req.model, req.prompt, req.system, req.max_tokens,
                  req.temperature, req.min_tier.value, req.min_vram_gb, req.timeout_s, req.priority, _now(), _now()))
        await self.db.commit()
        return req.task_id

    async def get_task(self, task_id: str) -> dict | None:
        async with self.db.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def claim_task(self, task_id: str, agent_id: str) -> bool:
        async with self.db.execute("""
            UPDATE tasks SET state=?, agent_id=?, updated_at=?
            WHERE task_id=? AND state=?
            RETURNING task_id
            """, (TaskState.DISPATCHED.value, agent_id, _now(), task_id, TaskState.PENDING.value)) as cur:
            row = await cur.fetchone()
        await self.db.commit()
        return row is not None

    async def mark_in_flight(self, task_id: str) -> None:
        await self.db.execute("UPDATE tasks SET state=?, updated_at=? WHERE task_id=?", (TaskState.IN_FLIGHT.value, _now(), task_id))
        await self.db.commit()

    async def complete_task(self, task_id: str, result: TaskResult) -> None:
        await self.db.execute("""
            UPDATE tasks SET state=?, content=?, input_tokens=?, output_tokens=?, latency_ms=?, error=?, updated_at=?
            WHERE task_id=?
            """, (result.state.value, result.content, result.input_tokens, result.output_tokens, result.latency_ms, result.error, _now(), task_id))
        await self.db.commit()

    async def fail_task(self, task_id: str, error: str) -> None:
        async with self.db.execute("SELECT retries FROM tasks WHERE task_id=?", (task_id,)) as cur:
            row = await cur.fetchone()
        if row is None:
            return
        retries = row[0] + 1
        new_state = TaskState.PENDING if retries < MAX_RETRIES else TaskState.FAILED
        await self.db.execute("""
            UPDATE tasks SET state=?, retries=?, error=?, agent_id=NULL, updated_at=?
            WHERE task_id=?
            """, (new_state.value, retries, error, _now(), task_id))
        await self.db.commit()

    async def mark_forwarded(self, task_id: str, peer_hub_id: str) -> None:
        await self.db.execute("UPDATE tasks SET state=?, peer_hub_id=?, updated_at=? WHERE task_id=?",
                              (TaskState.FORWARDED.value, peer_hub_id, _now(), task_id))
        await self.db.commit()

    async def list_tasks(self, limit: int = 100) -> list[dict]:
        async with self.db.execute("SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)) as cur:
            return [dict(row) for row in await cur.fetchall()]

    async def record_reward(self, operator_id: str, agent_id: str, task_id: str, tokens: int, credits: float) -> None:
        await self.db.execute("""
            INSERT INTO reward_ledger (operator_id, agent_id, task_id, tokens_generated, credits_earned)
            VALUES (?,?,?,?,?)
            """, (operator_id, agent_id, task_id, tokens, credits))
        await self.db.execute("""
            UPDATE operators SET total_tasks=total_tasks+1, total_tokens=total_tokens+?, total_credits=total_credits+?
            WHERE operator_id=?
            """, (tokens, credits, operator_id))
        await self.db.commit()

    async def reward_summary(self) -> list[dict]:
        async with self.db.execute("SELECT * FROM reward_summary") as cur:
            return [dict(row) for row in await cur.fetchall()]

    async def add_peer(self, hub_id: str, hub_url: str, operator_id: str) -> None:
        await self.db.execute("""
            INSERT INTO peer_hubs (hub_id, hub_url, operator_id, status, last_seen) VALUES (?,?,?,'ACTIVE',?)
            ON CONFLICT(hub_id) DO UPDATE SET hub_url=excluded.hub_url, status='ACTIVE', last_seen=excluded.last_seen
            """, (hub_id, hub_url, operator_id, _now()))
        await self.db.commit()

    async def list_peers(self) -> list[dict]:
        async with self.db.execute("SELECT * FROM peer_hubs") as cur:
            return [dict(row) for row in await cur.fetchall()]

    async def mark_peer_seen(self, hub_id: str) -> None:
        await self.db.execute("UPDATE peer_hubs SET last_seen=?, status='ACTIVE' WHERE hub_id=?", (_now(), hub_id))
        await self.db.commit()

    async def mark_peer_unreachable(self, hub_id: str) -> None:
        await self.db.execute("UPDATE peer_hubs SET status='UNREACHABLE' WHERE hub_id=?", (hub_id,))
        await self.db.commit()

    async def recent_pulse_logs(self, limit: int = 50) -> list[dict]:
        async with self.db.execute("SELECT * FROM pulse_log ORDER BY logged_at DESC LIMIT ?", (limit,)) as cur:
            return [dict(row) for row in await cur.fetchall()]

    # ── Watchlist ────────────────────────────────────────────────

    async def add_to_watchlist(self, entity_type: str, entity_id: str,
                               reason: str, action: str = "SUSPENDED",
                               expires_hours: int | None = 24) -> None:
        expires_at = None
        if expires_hours is not None:
            expires_at = f"datetime('now', '+{expires_hours} hours')"
        if expires_at:
            await self.db.execute(f"""
                INSERT INTO watchlist (entity_type, entity_id, reason, action, created_at, expires_at)
                VALUES (?, ?, ?, ?, datetime('now'), {expires_at})
                ON CONFLICT(entity_type, entity_id) DO UPDATE SET
                    reason=excluded.reason, action=excluded.action,
                    created_at=excluded.created_at, expires_at=excluded.expires_at
            """, (entity_type, entity_id, reason, action))
        else:
            await self.db.execute("""
                INSERT INTO watchlist (entity_type, entity_id, reason, action, created_at, expires_at)
                VALUES (?, ?, ?, ?, datetime('now'), NULL)
                ON CONFLICT(entity_type, entity_id) DO UPDATE SET
                    reason=excluded.reason, action=excluded.action,
                    created_at=excluded.created_at, expires_at=NULL
            """, (entity_type, entity_id, reason, action))
        await self.db.commit()

    async def is_watchlisted(self, entity_type: str, entity_id: str) -> dict | None:
        async with self.db.execute("""
            SELECT * FROM watchlist
            WHERE entity_type=? AND entity_id=?
              AND (expires_at IS NULL OR expires_at > datetime('now'))
        """, (entity_type, entity_id)) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def remove_from_watchlist(self, entity_type: str, entity_id: str) -> bool:
        async with self.db.execute(
            "DELETE FROM watchlist WHERE entity_type=? AND entity_id=? RETURNING id",
            (entity_type, entity_id),
        ) as cur:
            row = await cur.fetchone()
        await self.db.commit()
        return row is not None

    async def list_watchlist(self) -> list[dict]:
        async with self.db.execute(
            "SELECT * FROM watchlist WHERE expires_at IS NULL OR expires_at > datetime('now') ORDER BY created_at DESC"
        ) as cur:
            return [dict(row) for row in await cur.fetchall()]

    async def pending_task_count(self) -> int:
        async with self.db.execute("SELECT COUNT(*) FROM tasks WHERE state='PENDING'") as cur:
            row = await cur.fetchone()
        return row[0] if row else 0
