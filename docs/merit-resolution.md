# Merit Resolution: POC Repo Consolidation Analysis

**Date:** 2026-03-03
**Analyst:** Claude Opus 4.6
**Reference implementation:** `momahub.py` (v0.2.0)

---

## Context

MoMaHub has three prior implementations beyond the reference `momahub.py`:

| Repo | Model used | Nature |
|------|-----------|--------|
| `momahub-sonnet` | Claude Sonnet 4.6 | Quick POC from SPECKIT-opus.md spec |
| `momahub-opus` | Claude Opus 4.6 | Quick POC from same spec |
| `momahub-gemini` | Gemini CLI | Iterative improvement on top of momahub.py |

An interesting observation: even the same model (Opus 4.6) produced different results
when run at different times or with different prompts. Like human cognition, AI output
is time-dependent — the same architect doesn't design the same building twice. This
makes cross-pollination between implementations genuinely valuable, much like a human
refactoring exercise that brings fresh perspective to a codebase.

---

## Repo Summaries

### momahub-sonnet

- **Structure:** Flat `src/` directory, 7 Python files (~1,900 lines total)
- **Stack:** FastAPI + Click CLI + Streamlit, all in-memory state, no persistence
- **Generated in a single coding session** from the SPECKIT-opus.md spec
- **Strengths:** Clean Registry class decoupled from FastAPI, three named scheduling
  strategies (model_affinity, least_busy, round_robin), sync/async bridge for
  Streamlit, reduce-phase local Ollama fallback, comprehensive WAN migration guide
  in spec
- **Weaknesses:** No persistence, no tests, no cluster/multi-hub, no real hardware
  detection

### momahub-opus

- **Structure:** Flat root directory, 10 Python files (~2,900 lines total)
- **Stack:** FastAPI + Click CLI + Streamlit, all in-memory state, no persistence
- **Nearly identical architecture** to momahub-sonnet (same spec, same model family)
- **Strengths:** Async VRAM detection (multi-GPU summing), differentiated HTTP error
  codes (502 vs 503), clean lifespan management, idempotent setup.sh
- **Weaknesses:** Same as sonnet — no persistence, no tests, no cluster

### momahub-gemini

- **Structure:** Proper `igrid/` package layout (mirrors momahub.py)
- **Stack:** FastAPI + Typer CLI + Streamlit, in-memory state with dd-* placeholder labels
- **Built on top of momahub.py's structure** with Gemini CLI
- **Strengths:** Spec-driven development (specs/ directory), forward-looking schema
  fields (priority, cached_models, context_data, dynamic pulse interval), dd-*
  ecosystem manifest, 5-file test suite, i-grid white paper and pitch decks
- **Weaknesses:** Most features are mocked (rewards, benchmarks, telemetry, dashboard
  data), no SQLite, no real hardware detection, no cluster support

---

## Hidden Jewels Catalog

### From sonnet/opus POCs

#### Jewel #1 — `setup.sh` one-command node bootstrap
- **Source:** `momahub-sonnet/src/setup.sh`, `momahub-opus/setup.sh`
- **What:** Idempotent bash script handling the full new-node lifecycle: GPU detection,
  Ollama install (if missing), Ollama service start, model pulls, Python venv creation,
  smoke test (actual inference call to verify the stack), and prints the exact
  `moma join` command with auto-detected LAN IP.
- **Why it matters:** Reduces multi-node setup from a manual checklist to a single
  command. Critical for the weekend LAN test with 3 GPUs.
- **Status:** **ADOPTED** — implemented as `setup.sh` in momahub.py root

#### Jewel #2 — Model-affinity scheduling strategy
- **Source:** `supervisor.py` `pick_worker()` in both POCs
- **What:** Two-stage filter: (1) prefer nodes with the model already loaded in VRAM,
  (2) fall back to least-busy globally. Avoids triggering expensive Ollama cold-load
  swaps.
- **Why it matters:** momahub.py's `pick_agent()` filters by model availability but
  doesn't distinguish "model pulled" from "model loaded in VRAM."
- **Status:** Deferred — requires Ollama loaded-model tracking (not exposed in current
  heartbeat data)

#### Jewel #3 — Reduce-phase local Ollama fallback
- **Source:** `supervisor.py` `run_map_reduce()` in both POCs
- **What:** If no agent is available for the synthesis/reduce step of a map-reduce job,
  the hub calls its own local Ollama directly.
- **Why it matters:** Resilience — a single-machine setup works for map-reduce without
  requiring a separate agent process.
- **Status:** Deferred — needs design thought about hub's role boundaries

#### Jewel #4 — Auto-register on heartbeat
- **Source:** `supervisor.py` `Registry.heartbeat()` in both POCs
- **What:** If a heartbeat arrives from an unknown agent, auto-register it. Handles
  hub-restart race conditions — agents don't need reconnect logic.
- **Why it matters:** Graceful recovery from hub restarts without agent-side changes.
- **Status:** Deferred — momahub.py uses SQLite, needs careful implementation with
  proper schema validation

#### Jewel #5 — `/cluster/models` reverse-mapping endpoint
- **Source:** `client_api.py` in both POCs
- **What:** Returns a model-to-nodes mapping: which models are available and which
  agents have them. Inverts the node-centric `/agents` view into a model-centric view.
- **Why it matters:** Useful for users deciding which model to request, and for
  dashboards showing model coverage across the grid.
- **Status:** Deferred — medium priority, add when relevant

#### Jewel #6 — Differentiated HTTP error codes
- **Source:** `worker.py` in momahub-opus
- **What:** `502 Bad Gateway` for Ollama protocol errors vs `503 Service Unavailable`
  for Ollama connection failures. Distinct error semantics.
- **Why it matters:** Better debugging — operators can distinguish "Ollama is down" from
  "Ollama returned garbage."
- **Status:** Deferred — adopt when hardening agent error handling

#### Jewel #7 — Sync/async bridge for Streamlit
- **Source:** `client_lib.py` `_run()` in momahub-sonnet
- **What:** Detects if an event loop is already running (Streamlit's case) and uses
  `ThreadPoolExecutor` to run `asyncio.run()` in a worker thread, avoiding
  `RuntimeError: This event loop is already running`.
- **Why it matters:** A real fix for a real Streamlit + async incompatibility.
- **Status:** Deferred — apply when Streamlit UI hits this issue

#### Jewel #8 — CLI stress test with ASCII bar chart
- **Source:** `cli.py` stress command in both POCs
- **What:** Unicode block characters (`"█" * count`) to show per-node task distribution
  in the terminal.
- **Why it matters:** Nice DX touch for benchmarking. No external library needed.
- **Status:** Deferred — nice-to-have for a future `moma benchmark` command

#### Jewel #9 — Startup banner with join command
- **Source:** `node.py` in both POCs
- **What:** Hub prints the exact `moma join http://<LAN_IP>:<PORT>` command on startup,
  using UDP socket trick for LAN IP auto-detection.
- **Why it matters:** Zero-friction multi-node setup. The person starting the hub
  immediately knows what to tell the other machines.
- **Status:** **ADOPTED** — implemented in `igrid/cli/main.py` hub_up

### From momahub-gemini

#### Jewel #10 — Dynamic pulse interval
- **Source:** `igrid/schema/pulse.py` `PulseResponse.updated_pulse_interval`
- **What:** Hub can signal agents to change their heartbeat frequency dynamically via
  the pulse response.
- **Why it matters:** Load-adaptive monitoring — speed up heartbeats during high
  activity, slow down during idle periods.
- **Status:** Deferred — medium priority

#### Jewel #11 — TaskPacket.context_data
- **Source:** `igrid/schema/task.py` `TaskPacket.context_data: Optional[Dict[str, Any]]`
- **What:** A structured slot for passing upstream CTE results or other context alongside
  the prompt.
- **Why it matters:** Currently momahub.py passes CTE context via string interpolation
  in the SPL runner. A structured field is cleaner and enables richer pipelines.
- **Status:** Deferred — adopt when extending SPL pipeline features

#### Jewel #12 — TaskRequest.priority
- **Source:** `igrid/schema/task.py` `TaskRequest.priority: int = 1`
- **What:** Integer priority field on submitted tasks. Higher priority = dispatched first.
- **Why it matters:** Allows urgent tasks (interactive queries) to jump ahead of batch
  workloads in the dispatch queue.
- **Status:** **ADOPTED** — added to schema and dispatcher in momahub.py

#### Jewel #13 — HandshakeRequest.cached_models
- **Source:** `igrid/schema/handshake.py` `HandshakeRequest.cached_models: List[str]`
- **What:** Agents report which Ollama models are already pulled at join time.
- **Why it matters:** Hub knows agent model capabilities immediately at registration,
  before the first heartbeat cycle. Enables cache-aware routing.
- **Status:** **ADOPTED** — added to handshake schema and agent worker in momahub.py

#### Jewel #14 — System prompt support in Ollama calls
- **Source:** `igrid/agent/llm.py` `OllamaWrapper.generate(model, prompt, system=None)`
- **What:** Passes an optional `system` field to Ollama's generate API.
- **Why it matters:** SPL's `SYSTEM_ROLE()` function needs this at the agent level.
- **Status:** Deferred — verify current agent LLM code handles system prompts

#### Jewel #15 — dd-* ecosystem manifest
- **Source:** `GEMINI.md`
- **What:** Forward-looking decomposition into named packages: dd-llm, dd-db, dd-cache,
  dd-dog, dd-dispatcher, dd-session, dd-vis, dd-config, dd-verifier.
- **Why it matters:** Architectural roadmap for when momahub.py modules mature into
  standalone packages.
- **Status:** Noted — useful as a future decomposition guide

#### Jewel #16 — Spec-driven test harness structure
- **Source:** `tests/unit/` (5 files: test_schema, test_hub, test_agent, test_cli, test_spl)
- **What:** One test file per subsystem, clean separation.
- **Why it matters:** momahub.py's tests could adopt this per-subsystem organization.
- **Status:** Deferred — consider during next test refactor

---

## Adoption Summary

| Jewel | Description | Status |
|-------|-------------|--------|
| #1 | setup.sh node bootstrap | **Adopted** |
| #2 | Model-affinity scheduling | Deferred |
| #3 | Reduce-phase local fallback | Deferred |
| #4 | Auto-register on heartbeat | Deferred |
| #5 | /cluster/models endpoint | Deferred |
| #6 | Differentiated HTTP errors | Deferred |
| #7 | Sync/async bridge for Streamlit | Deferred |
| #8 | CLI ASCII bar chart | Deferred |
| #9 | Startup banner with join cmd | **Adopted** |
| #10 | Dynamic pulse interval | Deferred |
| #11 | TaskPacket.context_data | Deferred |
| #12 | TaskRequest.priority | **Adopted** |
| #13 | cached_models in handshake | **Adopted** |
| #14 | System prompt in Ollama calls | Deferred |
| #15 | dd-* ecosystem manifest | Noted |
| #16 | Per-subsystem test structure | Deferred |

---

## Cross-Pollination Observations

The three POC repos demonstrate that:

1. **Same spec, different implementations.** Sonnet and Opus built from the same
   SPECKIT-opus.md but produced subtly different code — Opus used async subprocess
   for VRAM detection while Sonnet used synchronous subprocess; Opus had more
   differentiated error codes. Like human pair programming, each "mind" brought
   different emphasis.

2. **Spec-first vs code-first.** momahub-gemini invested heavily in specs/ and
   documentation before implementation, resulting in more schema fields and fewer
   implemented features. momahub-sonnet/opus went code-first, resulting in more
   working features but less documentation.

3. **The value of revisiting.** Features that seemed unnecessary in the first pass
   (like priority, cached_models, setup.sh) prove their worth when viewed from the
   perspective of a real deployment (the weekend LAN test). Refactoring isn't just
   about code quality — it's about incorporating what you've learned since the
   first implementation.
