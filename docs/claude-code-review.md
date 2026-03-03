# MoMaHub (i-grid) — Code Review by Claude

**Reviewer:** Claude Sonnet 4.6
**Date:** 2026-03-02
**Codebase:** `momahub-gemini` (Gemini CLI implementation)
**Scope:** Full review against the four spec files in `specs/`, architecture quality, correctness, security, and testability.

---

## Executive Summary

Gemini produced a well-structured, readable skeleton that correctly identifies the major architectural components (Hub, Agent, CLI, Schema, SPL). The code is clean, the module boundaries are sensible, and the Pydantic schemas closely mirror the protocol specs. However, the implementation is largely a **scaffolded prototype**: critical spec requirements are either missing, hardcoded with mock data, or contain correctness bugs that would prevent the system from working reliably even at the PoC scale described in `specs/overview.md`. The gap between spec and implementation is the central theme of this review.

---

## 1. What Works Well

- **Schema design** — `igrid/schema/` is well-aligned to the specs. Pydantic models are clean, field descriptions are informative, and the `__init__.py` re-exports are tidy.
- **Module separation** — Hub, Agent, CLI, Schema, and SPL are cleanly separated with no circular imports.
- **FastAPI usage** — Endpoints use `response_model`, proper HTTP exception handling, and async handlers.
- **Test breadth** — Tests exist for all five modules (schema, hub, agent, cli, spl), and they use appropriate tools (`TestClient`, `CliRunner`, `unittest.mock`).
- **Dispatcher logic** — `TaskDispatcher.select_agent()` correctly implements the tier-ranked, VRAM-filtered selection with a clean sort key.

---

## 2. Spec Deviations

These are cases where the implementation diverges from a written requirement in `specs/`.

| # | Spec Source | Requirement | Implementation | Impact |
|---|---|---|---|---|
| S1 | `spec-handshake.md` | `POST /register` returns `201 Created` | Returns `200 OK` | Minor protocol non-conformance |
| S2 | `spec-handshake.md` | `hardware_id` must prevent **duplicate registrations** | Not checked; same node can register multiple times, leaking tokens | Medium — corrupts registry |
| S3 | `spec-handshake.md` | `compute_tier` "Calculated based on local TPS benchmark" | Agent self-reports any tier it chooses; `moma join` hardcodes `GOLD` | High — reward system is gameable |
| S4 | `spec-handshake.md` | `session_token` stored **in memory only** | Persisted to `~/.moma/config.yaml` | Medium — security requirement violated |
| S5 | `spec-pulse.md` | Auto-evict after **3 consecutive missed pulses** (90s) | Never implemented; agents stay in registry forever | High — dead nodes accept tasks |
| S6 | `spec-pulse.md` | **Task rerouting** when agent goes OFFLINE mid-task | Not implemented | High — tasks are silently dropped |
| S7 | `spec-moma-cli-v1.md` | `moma down` — graceful sign-off | Command does not exist | High — no clean shutdown path |
| S8 | `spec-moma-cli-v1.md` | `moma config` — manage local settings | Command does not exist | Medium |
| S9 | `spec-moma-cli-v1.md` | `moma logs` — stream real-time agent logs | Command does not exist | Medium |
| S10 | `spec-moma-cli-v1.md` | `secret_key` stored in config for persistent identity | Not present in `Config` or schema | Medium — identity is fragile |
| S11 | `specs/overview.md` | `moma run <file.spl>` — submit SPL to the grid | Command does not exist | High — the primary user workflow is missing |

---

## 3. Correctness Bugs

These are issues that would cause the system to malfunction in practice.

### B1 — Pulse interval ignored (`igrid/agent/worker.py:94`)
`AgentWorker._pulse_loop` hardcodes `time.sleep(10)`. The Hub returns `pulse_interval=30` in `HandshakeResponse`, but the agent never reads or stores it. The server-side configuration is entirely ignored.

### B2 — `pull_task` is a state-mutating GET (`igrid/hub/app.py:90`)
`GET /pull_task` calls `.pop()` on both `assigned_tasks` and `task_queue`. A GET request must be idempotent. If the network drops after the pop and before the agent receives the packet, the task is permanently lost with no recovery path.

### B3 — Race condition in task dispatch (`igrid/hub/app.py:74-86`)
`dispatcher.dispatch_task()` marks the agent BUSY and returns, but the `TaskPacket` is stored in `task_queue` *after* the dispatcher returns. A concurrent pulse arriving between these two operations would find the agent BUSY but no task in the queue, causing undefined behavior.

### B4 — Reward data is entirely hardcoded (`igrid/cli/main.py:73,78`)
`moma status` prints `"1,250 points"` and `moma reward` prints `"$12.50 Credit"` as string literals. There is no connection to actual token counts from `TaskResult`. The reward system is purely cosmetic.

### B5 — Hardware detection is hardcoded (`igrid/cli/main.py:17-25`)
`moma join` always sends `hardware_id="hw_hash_ubuntu_gpu_01"`, `gpu_model="NVIDIA GTX 1080 Ti"`, `gpu_vram_gb=11.0`, and `compute_tier=ComputeTier.GOLD` regardless of the actual machine. The spec requirement to "detect hardware" is not met.

### B6 — Benchmark is mocked (`igrid/agent/llm.py:54`)
`OllamaWrapper.benchmark()` returns the literal `45.2`. The `spec-handshake.md` requires the tier to be *calculated* from this benchmark, but the benchmark never runs real inference.

### B7 — Errors returned as strings (`igrid/agent/llm.py:46-48`)
`OllamaWrapper.generate()` catches all exceptions and returns `f"Error: {str(e)}"` as a string. The caller in `AgentWorker._execute_task` has no way to distinguish a real inference result from a failure string. Failed tasks are submitted to the Hub as successful results.

---

## 4. Security Issues

### SE1 — Unauthenticated task submission
`POST /submit_task` has no authentication. Any process that can reach port 8000 can inject arbitrary prompts into the grid, consuming agent compute and moma rewards.

### SE2 — Self-reported compute tier
Agents decide their own `ComputeTier`. A malicious or misconfigured agent could claim PLATINUM tier, monopolize task dispatch, and earn maximum rewards without the hardware to justify it.

### SE3 — Session token persisted to disk
`spec-handshake.md` explicitly requires the session token to be "stored in memory only." Writing it to `~/.moma/config.yaml` allows token theft via file system access.

### SE4 — No identity continuity
There is no `secret_key` or persistent identity mechanism. Every `moma join` generates a new `session_token` and creates a new registry entry. Previous reward balances (if they existed) are unreachable.

---

## 5. Architecture Concerns

### A1 — Global mutable state in `app.py`
`agent_registry`, `task_queue`, `assigned_tasks`, and `task_results` are module-level Python dicts. This is a single-process, single-thread-of-safety design. Running uvicorn with `--workers 2` would instantly corrupt state. The `TaskDispatcher` holds a reference to `agent_registry` but not to the other dicts, making the state management inconsistent.

### A2 — No `moma down` → no OFFLINE transition
An agent can only become OFFLINE via the auto-eviction timeout (which is not implemented). There is no API endpoint to deregister, no `OFFLINE` pulse status accepted by the Hub, and no CLI command. Agents accumulate in the registry permanently.

### A3 — SPL parser has no model routing
`SPLParser` extracts CTE blocks but hardcodes `"model": "llama3"` for every chunk (`core.py:22`). The entire point of SPL for the i-grid is to route different CTEs to different agents with different models. There is no mechanism to annotate a CTE with a target model or VRAM requirement.

### A4 — No CTE dependency tracking
The SPL spec describes chained CTEs where `step2` depends on the output of `step1`. The parser extracts them as a flat list with no dependency graph, so they would be dispatched in parallel even when sequential execution is required. The `SELECT` clause is parsed but discarded.

### A5 — `TaskResult` tokens never accumulate
`TaskResult.tokens_processed` is submitted to the Hub and stored in `task_results`, but no endpoint or data structure accumulates per-agent token counts. The reward system has no source of truth.

---

## 6. Test Coverage Gaps

| Gap | Description |
|---|---|
| T1 | No test for `TaskDispatcher` — the tier ranking and VRAM filter logic is untested |
| T2 | No test for `moma join` or `moma up` CLI commands |
| T3 | `tests/e2e/` directory exists but is empty |
| T4 | SPL tests don't verify `TaskRequest` model integration or model assignment |
| T5 | No test for the auto-eviction path (not yet implemented) |
| T6 | `bare except:` in `igrid/ui/streamlit/app.py:38` is untestable and swallows all errors silently |

---

## 7. Suggested Improvements for the Claude Implementation

The following are prioritized proposals for `momahub-claude`. **No code will be written until these are approved.**

---

### Priority 1 — Correctness & Spec Fidelity

**P1-A: Implement auto-eviction with a background health monitor**
Run an `asyncio` background task in the Hub (via FastAPI's `lifespan` context) that checks `last_seen` timestamps every 30s and evicts agents that have missed 3 pulses. When an agent is evicted while holding a task, re-enqueue the task for re-dispatch.

**P1-B: Make task delivery atomic with a task status machine**
Replace the raw dict `.pop()` pattern with a proper task status field: `PENDING → DISPATCHED → IN_FLIGHT → COMPLETE | FAILED`. A `POST /pull_task` (not GET) transitions the task to `IN_FLIGHT`. If the agent is evicted in this state, the Hub transitions the task back to `PENDING` for re-dispatch.

**P1-C: Add `moma down` command and a `POST /deregister` Hub endpoint**
Agents should gracefully leave the grid, triggering task re-routing for any in-progress work.

**P1-D: Agent must respect `pulse_interval` from `HandshakeResponse`**
Store the server-returned interval in config after `moma join` and use it in the pulse loop.

**P1-E: Add `moma run <file.spl>` command**
Parse the SPL file, submit each CTE as a `TaskRequest`, poll for results, and assemble the final output in `SELECT` order.

---

### Priority 2 — Real Hardware & Benchmark

**P2-A: Detect real hardware at `moma join`**
Use `platform`, `uuid`, and optionally `pynvml` / `subprocess(nvidia-smi)` to get the real GPU model, VRAM, and a stable `hardware_id`. Fall back to CPU-only mode with a clear warning.

**P2-B: Run a real benchmark to assign compute tier**
At `moma join`, run a timed inference via Ollama to measure TPS. The Hub assigns tier server-side: `PLATINUM (>60 TPS)`, `GOLD (>30)`, `SILVER (>15)`, `BRONZE (≤15)`.

**P2-C: Real telemetry in pulse**
Use `pynvml` where available for GPU temp and VRAM; fall back to mock values with a clear log warning so operators know telemetry is simulated.

---

### Priority 3 — Security & Identity

**P3-A: Persistent node identity with `secret_key`**
Generate a stable `node_id` and `secret_key` at first `moma join`, stored in `~/.moma/config.yaml`. Use the `secret_key` to sign pulse requests (HMAC-SHA256). The Hub verifies the signature, rejecting forged pulses.

**P3-B: Hub-side tier assignment**
The Hub ignores the client-reported `compute_tier` and assigns it based on the benchmark TPS reported at registration.

**P3-C: Prevent duplicate registrations via `hardware_id` index**
Index the registry by `hardware_id`. Re-registration updates the entry and preserves the reward balance, rather than creating a new entry.

**P3-D: API key for task submission**
`POST /submit_task` requires a shared API key in the request header, preventing unauthenticated prompt injection.

---

### Priority 4 — Reward System

**P4-A: Per-agent token accumulation on the Hub**
Maintain a `reward_ledger` (`hardware_id → {tokens_total, points_balance}`). On `POST /submit_result`, accumulate `tokens_processed` and convert to points (e.g., 1 point per 1000 tokens). Expose via `GET /rewards/{node_id}`.

**P4-B: `moma status` fetches real data**
Query `GET /rewards/{node_id}` and display live token count, points balance, and current uptime rather than hardcoded strings.

---

### Priority 5 — SPL Improvements

**P5-A: Per-CTE model and VRAM annotation**
Extend the SPL grammar to support `WITH step1 AS (PROMPT '...' MODEL 'llama3' VRAM 4)`. The parser extracts these fields and populates `TaskRequest.model` and `TaskRequest.min_vram_gb` per chunk.

**P5-B: CTE dependency graph**
Track `SELECT ... FROM <cte_name>` references to build a DAG. Dispatch independent CTEs in parallel; chain dependent ones sequentially, passing the prior result as context data in the next `TaskPacket`.

---

### Priority 6 — Architecture

**P6-A: Encapsulate Hub state in a `GridState` class**
Replace bare module-level dicts with a single `GridState` dataclass injected via FastAPI dependency injection. This makes testing trivially easy and prepares for a real database backend (`dd-db`).

**P6-B: `OllamaWrapper.generate()` should raise on error**
Return only the response string on success; raise a typed `OllamaError` on failure. Callers can distinguish real results from errors and mark tasks as `FAILED` rather than submitting garbage.

---

## 8. Summary Scorecard

| Dimension | Score | Notes |
|---|---|---|
| Schema / Protocol Design | 8/10 | Clean, well-annotated, spec-aligned |
| Spec Coverage | 4/10 | ~40% of specified behavior is implemented |
| Correctness | 4/10 | Several silent data-loss paths, pervasive mock data |
| Security | 3/10 | Self-reported tier, unauthenticated endpoints, token on disk |
| Architecture | 5/10 | Good module structure, fragile global state |
| Test Quality | 6/10 | Good breadth, limited depth |
| **Overall** | **5/10** | Solid scaffold; not yet a functional PoC |

---

*Pending your approval of the suggestions above, the full reimplementation will be produced at `C:\Users\p2p2l\projects\digital-duck\momahub-claude`.*
