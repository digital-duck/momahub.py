"""ClusterManager: hub-to-hub peering and task forwarding."""
from __future__ import annotations
import asyncio
import json
import logging
import httpx
from igrid.schema.cluster import PeerHandshake, PeerHandshakeAck, PeerCapability, PeerCapabilityUpdate
from igrid.schema.enums import ComputeTier, TaskState
from igrid.schema.task import TaskRequest, TaskResult
from igrid.hub.state import GridState

_log = logging.getLogger("igrid.hub.cluster")

def _capabilities_from_agents(agents: list[dict]) -> list[PeerCapability]:
    counts: dict[ComputeTier, set] = {t: set() for t in ComputeTier}
    models_by_tier: dict[ComputeTier, set] = {t: set() for t in ComputeTier}
    for a in agents:
        if a.get("status") == "OFFLINE": continue
        tier = ComputeTier(a["tier"])
        counts[tier].add(a["agent_id"])
        for m in json.loads(a.get("supported_models") or "[]"):
            models_by_tier[tier].add(m)
    return [PeerCapability(tier=t, count=len(counts[t]), models=sorted(models_by_tier[t]))
            for t in ComputeTier if counts[t]]

class ClusterManager:
    def __init__(self, state: GridState, this_hub_url: str):
        self.state = state
        self.this_hub_url = this_hub_url

    async def add_peer(self, peer_url: str) -> PeerHandshakeAck:
        agents = await self.state.list_agents()
        caps = _capabilities_from_agents(agents)
        hs = PeerHandshake(hub_id=self.state.hub_id, hub_url=self.this_hub_url,
                           operator_id=self.state.operator_id, capabilities=caps)
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{peer_url}/cluster/handshake", json=hs.model_dump())
            resp.raise_for_status()
            ack = PeerHandshakeAck(**resp.json())
        if ack.accepted:
            await self.state.add_peer(ack.hub_id, peer_url, "")
            _log.info("peer hub %s added", ack.hub_id)
        return ack

    async def push_capabilities(self) -> None:
        peers = await self.state.list_peers()
        if not peers: return
        agents = await self.state.list_agents()
        update = PeerCapabilityUpdate(hub_id=self.state.hub_id, capabilities=_capabilities_from_agents(agents))
        async with httpx.AsyncClient(timeout=5.0) as client:
            for peer in peers:
                if peer["status"] != "ACTIVE": continue
                try:
                    await client.post(f"{peer['hub_url']}/cluster/capabilities", json=update.model_dump())
                    await self.state.mark_peer_seen(peer["hub_id"])
                except Exception as exc:
                    _log.warning("cannot reach peer %s: %s", peer["hub_id"], exc)
                    await self.state.mark_peer_unreachable(peer["hub_id"])

    async def forward_task(self, req: TaskRequest) -> TaskResult | None:
        peers = [p for p in await self.state.list_peers() if p["status"] == "ACTIVE"]
        if not peers: return None
        async with httpx.AsyncClient(timeout=req.timeout_s + 15.0) as client:
            for peer in peers:
                try:
                    resp = await client.post(f"{peer['hub_url']}/tasks", json=req.model_dump())
                    resp.raise_for_status()
                    fwd_id = resp.json().get("task_id", req.task_id)
                    await self.state.mark_forwarded(req.task_id, peer["hub_id"])
                    result = await self._poll_peer(client, peer["hub_url"], fwd_id, req.timeout_s)
                    if result:
                        result.task_id = req.task_id
                        await self.state.complete_task(req.task_id, result)
                        return result
                except Exception as exc:
                    _log.warning("forward to peer %s failed: %s", peer["hub_id"], exc)
                    await self.state.mark_peer_unreachable(peer["hub_id"])
        return None

    @staticmethod
    async def _poll_peer(client, base_url, task_id, timeout_s) -> TaskResult | None:
        import time
        deadline = time.monotonic() + timeout_s
        interval = 2.0
        while time.monotonic() < deadline:
            try:
                resp = await client.get(f"{base_url}/tasks/{task_id}")
                data = resp.json()
                state = data.get("state", "")
                if state in (TaskState.COMPLETE.value, TaskState.FAILED.value):
                    return TaskResult(**(data.get("result") or data))
            except Exception: pass
            await asyncio.sleep(interval)
            interval = min(interval * 1.5, 10.0)
        return None
