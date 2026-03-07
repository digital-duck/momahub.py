# Code Review: MoMaHub (i-grid)

**Date:** March 7, 2026  
**Reviewer:** Gemini CLI  
**Scope:** `igrid/` core logic, `cookbook/` testing suite, and overall architecture.

---

## Executive Summary

MoMaHub (i-grid) is a well-structured distributed inference network. The implementation effectively balances complexity and functionality, providing a clear path from local GPU inference (via Ollama) to a grid-wide programmable surface. The `cookbook` serves as both documentation and an integration testing suite, which is a major strength.

---

## Strengths

### 1. Robust Dispatch Logic (`igrid/hub/dispatcher.py`)
- **Tier-Aware Scheduling:** The use of `ComputeTier` (Platinum, Gold, Silver, Bronze) allows for intelligent task placement based on actual hardware performance.
- **Model & VRAM Filtering:** Precise matching of agent capabilities to task requirements prevents unnecessary failures and maximizes grid efficiency.
- **Atomic Task Claiming:** The `claim_task` method uses atomic SQL updates (`UPDATE ... RETURNING`) to prevent race conditions during dispatch in multi-worker environments.

### 2. Comprehensive Cookbook as Integration Suite
- **Diverse Scenarios:** Recipes cover everything from simple "Hello World" to complex parallel fan-outs (`multi_cte.spl`), stress tests, and failover validation.
- **End-to-End Visibility:** Scripts like `stress.py` and `arena.py` provide rich feedback (latency, TPS, agent distribution) which is invaluable for debugging and performance tuning.
- **Real-world Utilities:** `cookbook/06_arxiv_paper_digest` demonstrates a concrete application of the grid, moving beyond synthetic benchmarks.

### 3. Resilience & State Management (`igrid/hub/state.py`)
- **Self-Healing:** The agent eviction mechanism (90s timeout) and automatic task re-queuing ensure that hardware failures or network drops don't permanently stall the grid.
- **Retry Mechanism:** Built-in `MAX_RETRIES` (3) handles transient errors gracefully.
- **SSE Pull Mode:** Support for both HTTP push and SSE pull enables agents to join from behind restrictive NATs or firewalls, increasing the reachable compute surface.

---

## Weaknesses

### 1. Synchronous Delivery Bottleneck
- **Dispatcher Blocking:** While `dispatch_pending` runs in a loop, it processes tasks in batches of 50. If delivery (especially HTTP push) is slow, it could throttle the overall dispatch throughput for the next batch.
- **In-process Task Execution:** `_deliver_and_update` is spawned as a background task, which is good, but managing thousands of concurrent delivery coroutines in a single Python process may hit the GIL or event loop latency limits.

### 2. Database Scaling (SQLite)
- **WAL Mode:** Correctly uses `journal_mode=WAL`, but as the grid grows to hundreds of agents and thousands of tasks, the single-file SQLite database might become a write-latency bottleneck, especially with frequent `pulse` updates and `task` state transitions.
- **Missing Indices:** While `idx_tasks_state` exists, indices on `agent_id` in the `tasks` table and `logged_at` in `pulse_log` would significantly improve performance for common queries (like `moma status` or `moma rewards`).

### 3. Security Considerations
- **API Key Simplicity:** The current `X-API-Key` check is a basic shared secret. This lacks granularity (e.g., distinguishing between different operators) and doesn't provide per-task authentication.
- **Prompts in Plaintext:** The database stores all prompts and results in plaintext. For some sensitive use cases, this might be a privacy concern.

---

## Enhancements & Recommendations

### 1. Performance & Scalability
- **Priority Queuing:** Enhance the `ORDER BY priority DESC, created_at` to use a more sophisticated priority scheduler (e.g., aging tasks so low-priority items aren't starved).
- **Batch Pulses:** Aggregate agent pulse reports or use a more lightweight mechanism (like Redis) for transient state if the agent count scales significantly.
- **Task Streaming:** Implement task result streaming in the hub, allowing clients to see partial generation results (tokens as they arrive from Ollama).

### 2. Observability & Debugging
- **OpenTelemetry Integration:** Add tracing to track a task from submission through dispatch to agent execution and back. This would pinpoint exactly where latency is introduced.
- **Prometheus Metrics:** Export grid-wide metrics (queue depth, active agents by tier, error rates) for standard monitoring tools.

### 3. Developer Experience (DX)
- **SPL Type Safety:** Extend the SPL integration to support schema validation for task inputs and outputs within the `.spl` files themselves.
- **Mock Agent for Testing:** Create a "dummy" agent that simulates LLM latency and TPS without requiring a local GPU, facilitating faster development and CI/CD testing of hub logic.

---

## Roadmap & Future Directions

Based on architectural discussions, the following strategic transitions are planned for the production phase:

### 1. Re-implementation in Go-lang
- **Objective:** Move from the Python prototype to a high-concurrency Go implementation.
- **Benefit:** Leveraging Go's goroutine model for managing thousands of concurrent agent connections and task deliveries without the GIL limitations of Python.

### 2. High-Performance Persistence
- **Objective:** Transition from SQLite to a more robust, distributed-ready database (e.g., PostgreSQL or a specialized time-series/message-queue hybrid).
- **Benefit:** Improved write throughput for telemetry/pulse data and better support for concurrent administrative operations.

### 3. Asymmetric Authentication (Public-Private Keys)
- **Objective:** Replace simple API keys with a public-private key infrastructure for hub-agent handshaking.
- **Benefit:** enhanced security, verifiable operator identity, and a foundation for end-to-end encryption of prompt payloads.

---

## Final Assessment

The **MoMaHub** codebase is in excellent health. The architecture is modular and the focus on "programmable compute surface" is well-executed. The `cookbook` is a standout feature that provides immediate utility and validates the system's design goals. Addressing the synchronous delivery and database indexing will prepare the system for larger-scale deployments.
