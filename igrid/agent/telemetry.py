"""Telemetry: periodic heartbeat sender."""
from __future__ import annotations
import asyncio
import logging
import httpx
from igrid.agent.hardware import gpu_utilization
from igrid.schema.enums import AgentStatus
from igrid.schema.pulse import PulseReport

_log = logging.getLogger("igrid.agent.telemetry")
PULSE_INTERVAL_S = 30

class TelemetrySender:
    def __init__(self, agent_id: str, operator_id: str, hub_urls: list[str], get_stats):
        self.agent_id = agent_id; self.operator_id = operator_id
        self.hub_urls = hub_urls; self.get_stats = get_stats; self._running = False

    async def run(self) -> None:
        self._running = True
        while self._running:
            await asyncio.sleep(PULSE_INTERVAL_S)
            await self._send_pulse()

    async def _send_pulse(self) -> None:
        gpu_util, vram_used = gpu_utilization()
        tasks_completed, current_tps = self.get_stats()
        report = PulseReport(operator_id=self.operator_id, agent_id=self.agent_id,
                             status=AgentStatus.ONLINE, gpu_utilization_pct=gpu_util,
                             vram_used_gb=vram_used, tasks_completed=tasks_completed, current_tps=current_tps)
        async with httpx.AsyncClient(timeout=5.0) as client:
            for hub_url in self.hub_urls:
                try: await client.post(f"{hub_url}/pulse", json=report.model_dump())
                except Exception as exc: _log.warning("pulse to %s failed: %s", hub_url, exc)

    def stop(self): self._running = False
