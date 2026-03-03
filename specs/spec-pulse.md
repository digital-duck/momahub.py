# Component Spec: Liveness & Telemetry (The Pulse)
**Objective:** Provide real-time status updates from the Agent to the Coordinator for task routing.

## 1. Pulse Payload
Every 30 seconds, the Agent must send a `POST /pulse` containing:
- `session_token`: (Assigned during handshake)
- `agent_status`: ["IDLE", "BUSY", "MAINTENANCE"]
- `telemetry`: 
  - `gpu_temp_c`: (Current temperature)
  - `vram_usage_percent`: (Current memory load)
- `current_task_id`: (UUID of the active SPL chunk, if any)

## 2. Coordinator Monitoring Logic
- **Liveness Tracking:** Update the `last_seen` timestamp in the Registry.
- **Auto-Eviction:** If an Agent misses **3 consecutive pulses** (90s), mark as `OFFLINE`.
- **Task Rerouting:** If an Agent goes `OFFLINE` while holding an active task, trigger the Dispatcher to resend that chunk to a different Agent.