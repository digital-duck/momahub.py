# Component Spec: Hub-Agent Handshake
**Objective:** Securely register a new hardware node (Agent) into the i-grid Coordinator's registry.

## 1. Handshake Workflow
1. **Initiation:** Agent sends a `POST /register` to the Coordinator.
2. **Identity Verification:** Agent provides a `hardware_id` (a hash of system UUID/GPU Serial) to prevent duplicate registrations.
3. **Capability Reporting:** Agent reports its hardware profile:
   - `gpu_vram_gb`: (e.g., 11.0)
   - `compute_tier`: (Calculated based on local TPS benchmark)
   - `cached_models`: (List from `ollama list`)
4. **Acknowledgment:** Coordinator returns a `201 Created` with a `session_token` and the `pulse_interval` (default 30s).

## 2. Security Requirements
- The `session_token` must be stored in memory only and used for all subsequent `/pulse` requests.
- Failed handshakes should return clear error codes for the CLI to display.