# MoMaHub Claude Implementation Plan

**Author:** Claude Sonnet 4.6
**Date:** 2026-03-02
**Target:** `C:\Users\p2p2l\projects\digital-duck\momahub-claude`
**Test target:** 3× GTX 1080 Ti on a local LAN

---

## 1. Vision & Thesis

The Gemini implementation treated MoMaHub as a standalone system that happens to support Ollama.
This implementation inverts that framing:

> **MoMaHub is the distributed execution backend for the SPL/SPL-flow ecosystem.**

SPL already has the right abstractions: a rich grammar, parallel CTE execution, model-per-CTE routing, and an adapter interface. The gap is that all execution currently happens on one machine via `asyncio.gather()`. MoMaHub replaces that single-machine gather with a physical multi-node dispatch: each CTE chunk travels to the GPU node best suited for its model.

The result is a tight three-layer stack:
```
SPL grammar          ← declarative language for multi-model reasoning
SPL-flow             ← NL→SPL, validation, model routing, orchestration
MoMaHub (i-grid)     ← physical distributed execution & reward economy
```

---

## 1b. Architecture Model: Global Airport Hub-and-Spoke

MoMaHub is **not** a single centralized coordinator. It is modeled after the global airport system:

```
                  ┌─────────────────────────────────────────────┐
                  │           i-grid Cluster                  │
                  │                                             │
                  │   ┌──────────┐     cluster    ┌──────────┐│
                  │   │  Hub A   │◄─────────────────►│  Hub B   ││
                  │   │(US-West) │                   │(EU-North)││
                  │   └────┬─────┘                   └────┬─────┘│
                  │        │                              │      │
                  │   ┌────┴────┐                   ┌────┴────┐  │
                  │  Node Node Node                Node Node Node │
                  └─────────────────────────────────────────────┘
```

| Airport Concept | MoMaHub Equivalent |
|---|---|
| Airport (hub) | Hub — a coordinator running `igrid.hub.app` |
| Airline | Operator — an org/company running a fleet of nodes |
| Plane / gate | Agent node — a GPU machine running `moma up` |
| Passenger / flight | Task — an SPL CTE chunk to be executed |
| Flight itinerary | SPL script — CTEs may connect through multiple hubs |
| Air traffic control | Dispatcher — routes tasks to optimal agents |
| Code-share agreement | Hub cluster — Hub A can forward to Hub B |

**Key properties:**
- Any machine can run a Hub — a university, a company, a home server
- Agents can register with **multiple** Hubs simultaneously
- When Hub A has no suitable agent, it **forwards** the task to a peer Hub
- Hubs exchange capability summaries (models available, VRAM, agent count)
- Hub discovery: Hubs register with each other via `POST /cluster/register`
- No central authority required — a Hub can be isolated or federated

**For the PoC weekend test (3× GTX 1080 Ti):**
- Run 1 or 2 Hubs on the LAN
- If 2 Hubs: test inter-hub task forwarding
- Each GTX 1080 Ti registers as an agent node

---

## 2. SPL Grammar Enhancements

Two new optional clauses will be added to the SPL parser (lexer + parser + AST updates):

### 2.1 `ON GRID` clause (PROMPT header)
Routes a PROMPT — and all its CTEs — to the i-grid instead of local execution.

```sql
PROMPT big_analysis
WITH BUDGET 8000 tokens
USING MODEL "llama3.1:70b"
ON GRID "http://localhost:8000"    -- submit to MoMaHub Hub

WITH reasoning AS (
    PROMPT do_reasoning
    WITH BUDGET 3000 tokens
    USING MODEL "llama3.1:70b"     -- routed to 70b-capable node
    ON GRID                        -- inherits hub URL from parent
    SELECT system_role("Reason step by step"), context.question
    GENERATE reason(question) WITH OUTPUT BUDGET 2000 tokens
),
formatting AS (
    PROMPT do_formatting
    WITH BUDGET 2000 tokens
    USING MODEL "llama3.1:8b"      -- routed to any 8b-capable node
    ON GRID
    SELECT system_role("Format as JSON"), context.reasoning
    GENERATE format_result(reasoning) WITH OUTPUT BUDGET 500 tokens, FORMAT json
)

SELECT system_role("Synthesize"), reasoning, formatting
GENERATE synthesize(reasoning, formatting)
WITH OUTPUT BUDGET 2000 tokens;
```

When `ON GRID` is present, the SPL executor uses `IGridAdapter` instead of the local Ollama adapter.

### 2.2 `WITH VRAM <n>` hint (optional, per PROMPT)
Explicit VRAM override for the dispatcher. Most users won't need this — the Hub maintains a model→VRAM requirements table and derives it automatically from `USING MODEL`.

```sql
PROMPT heavy_reasoning
WITH BUDGET 4000 tokens
USING MODEL "llama3.1:70b"
WITH VRAM 44               -- override: tell dispatcher 44 GB required
ON GRID
...
```

### 2.3 Files to modify in SPL codebase
| File | Change |
|---|---|
| `spl/tokens.py` | Add `ON`, `GRID`, `VRAM` token types |
| `spl/lexer.py` | Recognize new keywords |
| `spl/ast_nodes.py` | Add `OnGridClause(url: Optional[str])`, `VramHint(gb: float)` to `PromptStatement` |
| `spl/parser.py` | Parse `ON GRID [<url>]` and `WITH VRAM <n>` in PROMPT header |
| `spl/executor.py` | If `stmt.on_grid` is set, use `IGridAdapter` |
| `spl/adapters/__init__.py` | Register `"igrid"` adapter type |

---

## 3. New Adapter: `IGridAdapter`

**Location:** `spl/adapters/igrid.py` (inside the SPL codebase)

Implements the existing `LLMAdapter` ABC — SPL-flow needs zero changes to use it.

```
IGridAdapter.generate(model, prompt, ...)
    → POST /tasks             # submit task to Hub
    → poll GET /tasks/{id}    # wait for result (short-poll with backoff)
    → return GenerationResult
```

This is the only code path that changes when you move from local to grid execution. The entire SPL/SPL-flow pipeline — NL→SPL translation, validation, optimizer, CTE dependency graph, result assembly — remains untouched.

**Model→VRAM table** (maintained in the adapter; also sent to Hub at registration):
```python
MODEL_VRAM_GB = {
    "llama3.1:8b":   8.0,
    "llama3.1:70b":  40.0,
    "llama3:8b":     8.0,
    "llama3:70b":    40.0,
    "mistral:7b":    7.0,
    "mistral:latest":7.0,
    "qwen2.5:7b":    7.0,
    "qwen2.5:72b":   41.0,
    "deepseek-r1:7b":7.0,
    # default fallback: 4.0
}
```

---

## 4. Project Structure (`momahub-claude`)

```
momahub-claude/
├── pyproject.toml
├── CLAUDE.md
├── igrid/
│   ├── schema/
│   │   ├── enums.py          # AgentStatus, ComputeTier, TaskStatus, HubStatus
│   │   ├── handshake.py      # HandshakeRequest/Response (+ benchmark_tps, operator_id)
│   │   ├── pulse.py          # PulseRequest/Response/Telemetry (real fields)
│   │   ├── task.py           # TaskRequest, TaskPacket, TaskResult, TaskRecord
│   │   ├── reward.py         # RewardEntry, RewardSummary
│   │   ├── cluster.py     # HubInfo, ClusterRequest, PeerCapabilities
│   │   └── __init__.py
│   ├── hub/
│   │   ├── app.py            # FastAPI app + lifespan + hub startup config
│   │   ├── state.py          # GridState (encapsulated, injectable)
│   │   ├── db.py             # SQLite via aiosqlite (schema + queries)
│   │   ├── dispatcher.py     # TaskDispatcher (local first, then peer hubs)
│   │   ├── cluster.py     # Hub-to-hub peering, capability exchange, forwarding
│   │   └── monitor.py        # Health monitor (agent eviction + hub liveness)
│   ├── agent/
│   │   ├── worker.py         # AgentWorker (multi-hub pulse loop)
│   │   ├── llm.py            # OllamaWrapper (real benchmark, raises OllamaError)
│   │   ├── hardware.py       # GPU detection (pynvml → nvidia-smi → CPU fallback)
│   │   └── telemetry.py      # Live GPU telemetry (pynvml → nvidia-smi → warn)
│   ├── cli/
│   │   ├── main.py           # All spec commands + hub subcommands + moma run
│   │   └── config.py         # YAML config with node_id, hubs list, operator_id
│   ├── spl/
│   │   ├── runner.py         # moma run <file.spl> (parse→dispatch→assemble)
│   │   └── igrid_adapter.py  # IGridAdapter (hub-aware, cluster-transparent)
│   └── ui/
│       ├── launch.py
│       └── streamlit/
│           ├── app.py
│           └── pages/
│               ├── 1_Grid_Monitor.py   # per-hub + cluster view
│               ├── 2_Rewards.py
│               └── 3_Run_SPL.py
└── tests/
    ├── unit/
    │   ├── test_schema.py
    │   ├── test_dispatcher.py
    │   ├── test_cluster.py
    │   ├── test_monitor.py
    │   ├── test_hardware.py
    │   ├── test_spl_runner.py
    │   ├── test_hub_endpoints.py
    │   ├── test_agent.py
    │   └── test_cli.py
    └── e2e/
        └── test_two_hub_grid.py   # Hub A + Hub B + 3 agent nodes
```

---

## 5. SQLite Schema

Six tables + one view. Each Hub has its own DB. Agent has no direct DB access.

```sql
-- This Hub's own identity (one row, set at startup)
CREATE TABLE hub_config (
    hub_id          TEXT PRIMARY KEY,
    hub_name        TEXT NOT NULL,
    region          TEXT,
    api_key_hash    TEXT,             -- SHA-256 of API key for task submission
    started_at      REAL NOT NULL
);

-- Peer Hubs in the cluster
CREATE TABLE peer_hubs (
    hub_id          TEXT PRIMARY KEY,
    hub_name        TEXT,
    hub_url         TEXT NOT NULL UNIQUE,
    region          TEXT,
    status          TEXT DEFAULT 'UNKNOWN',   -- ONLINE / OFFLINE / UNKNOWN
    capabilities    TEXT DEFAULT '{}',        -- JSON: {models:[...], total_vram_gb, agent_count}
    last_seen       REAL,
    registered_at   REAL NOT NULL
);

-- Operators (organizations running fleets of nodes)
CREATE TABLE operators (
    operator_id     TEXT PRIMARY KEY,         -- stable UUID
    operator_name   TEXT NOT NULL,
    api_key_hash    TEXT,
    registered_at   REAL NOT NULL
);

-- Registered agent nodes (keyed by stable hardware_id)
CREATE TABLE agents (
    hardware_id     TEXT PRIMARY KEY,
    node_id         TEXT UNIQUE NOT NULL,
    operator_id     TEXT,                     -- NULL = independent node
    gpu_model       TEXT NOT NULL,
    vram_gb         REAL NOT NULL,
    gpus            TEXT DEFAULT '[]',        -- JSON: [{index,model,vram_gb},...] for multi-GPU
    compute_tier    TEXT NOT NULL,            -- Hub-assigned from benchmark_tps
    ollama_version  TEXT,
    cached_models   TEXT DEFAULT '[]',        -- JSON array of model names
    status          TEXT DEFAULT 'OFFLINE',
    session_token   TEXT,
    pulse_interval  INTEGER DEFAULT 30,
    missed_pulses   INTEGER DEFAULT 0,
    last_seen       REAL,
    registered_at   REAL NOT NULL,
    benchmark_tps   REAL NOT NULL
);

-- Task lifecycle (full state machine)
CREATE TABLE tasks (
    task_id         TEXT PRIMARY KEY,
    model           TEXT NOT NULL,
    prompt          TEXT NOT NULL,
    min_vram_gb     REAL DEFAULT 4.0,
    priority        INTEGER DEFAULT 1,
    context_data    TEXT DEFAULT '{}',        -- JSON: prior CTE outputs
    status          TEXT DEFAULT 'PENDING',   -- PENDING/DISPATCHED/IN_FLIGHT/COMPLETE/FAILED
    assigned_to     TEXT,                     -- hardware_id of assigned local agent
    forwarded_to    TEXT,                     -- hub_id if forwarded to a peer hub
    retry_count     INTEGER DEFAULT 0,
    created_at      REAL NOT NULL,
    dispatched_at   REAL,
    completed_at    REAL,
    response        TEXT,
    tokens_processed INTEGER,
    duration_ms     INTEGER,
    error_msg       TEXT
);

-- Append-only reward ledger
CREATE TABLE reward_ledger (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    hardware_id     TEXT NOT NULL,
    task_id         TEXT NOT NULL UNIQUE,
    tokens_processed INTEGER NOT NULL,
    points_earned   REAL NOT NULL,            -- tokens / 1000
    recorded_at     REAL NOT NULL
);

-- Pulse log (recent N rows, used by health monitor)
CREATE TABLE pulse_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    hardware_id     TEXT NOT NULL,
    received_at     REAL NOT NULL,
    agent_status    TEXT NOT NULL,
    gpu_temp_c      REAL,
    vram_usage_pct  REAL,
    tokens_per_sec  REAL
);

-- Live reward view
CREATE VIEW reward_summary AS
SELECT
    hardware_id,
    COUNT(*)              AS tasks_completed,
    SUM(tokens_processed) AS total_tokens,
    SUM(points_earned)    AS total_points
FROM reward_ledger
GROUP BY hardware_id;
```

**Task status machine:**
```
PENDING → DISPATCHED → IN_FLIGHT → COMPLETE
        ↘                         ↓
         FORWARDED               FAILED  (agent evicted or error)
              ↓
         (peer hub handles)
FAILED → PENDING  (re-queued up to MAX_RETRIES=3, then try peer hub)
```

---

## 6. Hub Design

### 6.1 Startup

```bash
python -m igrid.hub.app --host 0.0.0.0 --port 8000 \
    --hub-name "Pioneer Hub" --region "us-west" \
    --api-key "changeme123" \
    --db-path ~/.igrid/hub.db
```

### 6.2 Endpoints

**Agent endpoints:**

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Hub summary (id, name, agents online, tasks pending) |
| `GET` | `/health` | Hub self-health check |
| `POST` | `/agents/register` → `201` | Handshake + hub-assigned tier |
| `POST` | `/agents/deregister` | Graceful sign-off |
| `POST` | `/agents/pulse` | Heartbeat + telemetry |
| `GET` | `/agents` | List all registered agents |
| `POST` | `/tasks` | Submit task (API key required) |
| `POST` | `/tasks/{id}/pull` | Agent pulls task (DISPATCHED → IN_FLIGHT) |
| `POST` | `/tasks/{id}/result` | Agent submits result (IN_FLIGHT → COMPLETE/FAILED) |
| `GET` | `/tasks/{id}` | Poll task status + result |
| `GET` | `/rewards/{node_id}` | Live reward summary |
| `GET` | `/logs` | Recent pulse log entries (polling) |

**Cluster endpoints (Hub-to-Hub):**

| Method | Path | Description |
|---|---|---|
| `POST` | `/cluster/register` | Register a peer Hub; exchange capabilities |
| `GET` | `/cluster/peers` | List known peer Hubs + their status |
| `GET` | `/cluster/capabilities` | This hub's published capabilities |
| `POST` | `/cluster/forward` | Accept a forwarded task from a peer Hub |
| `POST` | `/cluster/forward/{id}/result` | Peer Hub returns a forwarded task's result |

### 6.3 GridState (injectable)

```python
@dataclass
class GridState:
    db: AsyncDatabase            # aiosqlite wrapper
    dispatcher: TaskDispatcher
    cluster: ClusterManager
    hub_id: str
    hub_name: str
    api_key: str
```

Injected via FastAPI `Depends(get_grid_state)` — no module-level globals.

### 6.4 Background Health Monitor

Two coroutines run in FastAPI's `lifespan` context:

**Agent monitor** (every 30s):
1. Find agents where `last_seen < now - (pulse_interval * 3)`, increment `missed_pulses`
2. If `missed_pulses >= 3`: mark OFFLINE, clear session_token
3. Re-queue DISPATCHED/IN_FLIGHT tasks assigned to newly OFFLINE agents

**Cluster monitor** (every 60s):
1. Ping each peer Hub's `/health` endpoint
2. If unreachable: mark peer as OFFLINE
3. If reachable: update `capabilities` from `/cluster/capabilities`

### 6.5 Cluster Manager

**Hub peering workflow:**
```
Hub A: POST /cluster/register  →  Hub B
       {hub_id, hub_name, hub_url, region}
Hub B: responds with its own HubInfo + capabilities
Hub A: stores Hub B in peer_hubs table
```

**Task forwarding workflow:**
```
1. Dispatcher finds no suitable local agent
2. ClusterManager queries peer hubs: which has a capable idle agent?
3. Forward task via POST /cluster/forward to best peer
4. Local task status → FORWARDED (with forwarded_to = peer hub_id)
5. Poll peer hub GET /tasks/{id} or receive callback via /cluster/forward/{id}/result
6. Return result to original requester
```

**Capability summary** (published to peers):
```json
{
  "hub_id": "abc123",
  "hub_name": "Pioneer Hub",
  "region": "us-west",
  "agent_count": 3,
  "idle_agent_count": 2,
  "total_vram_gb": 33.0,
  "available_models": ["llama3.1:8b", "mistral:7b"],
  "max_compute_tier": "GOLD"
}
```

### 6.6 Tier Assignment (Hub-side)

```python
def assign_tier(tps: float) -> ComputeTier:
    if tps >= 60:  return ComputeTier.PLATINUM
    if tps >= 30:  return ComputeTier.GOLD
    if tps >= 15:  return ComputeTier.SILVER
    return ComputeTier.BRONZE
```

GTX 1080 Ti @ llama3.1:8b → ~35-45 TPS → GOLD tier.

### 6.7 Enhanced Dispatcher (local-first)

Routing priority:
1. Agent status must be IDLE
2. Agent VRAM >= task.min_vram_gb
3. Model already cached on agent (no download wait)
4. ComputeTier rank (PLATINUM > GOLD > SILVER > BRONZE)
5. VRAM headroom as tiebreaker
6. **If no local agent qualifies → forward to best peer Hub**

---

## 7. Agent Design

### 7.1 Hardware Detection (`hardware.py`)

Three-tier detection, no mocks for hardware that exists:

```
Tier 1: pynvml          → exact GPU name, VRAM, stable device serial
Tier 2: nvidia-smi CLI  → GPU name + VRAM (subprocess call)
Tier 3: CPU-only mode   → logs a clear warning, vram_gb=0.0
```

`hardware_id` = SHA-256(machine-id or MAC address)[:16] — stable across reboots.

### 7.2 Real Benchmark (`llm.py`)

At `moma join`, before registering:
1. Check if Ollama is running (`GET /api/version`)
2. Pull the smallest available model if none cached
3. Time a 50-token generation (e.g., "Count from 1 to 50")
4. Parse `eval_count / eval_duration` from Ollama's response JSON for accurate TPS
5. Report `benchmark_tps` in `HandshakeRequest`

### 7.3 Pulse Loop

- Reads `pulse_interval` from config (set at `moma join` from `HandshakeResponse`)
- Uses `pynvml` for live telemetry; logs a warning if falling back to estimated values
- Raises `OllamaError` (not returns error strings) on inference failure
- Marks task as FAILED via `/tasks/{id}/result` with `error_msg` on exception

### 7.4 moma down

Sends `POST /deregister` with session token, then stops pulse loop.
Hub moves all DISPATCHED/IN_FLIGHT tasks assigned to this agent back to PENDING.

---

## 8. CLI Commands

**Agent commands** (all spec commands + new):

| Command | Status vs Gemini | Key improvement |
|---|---|---|
| `moma join <url> [url2 ...]` | Fix | Multi-hub; real hardware + benchmark; hub-assigned tier |
| `moma up` | Fix | Respects `pulse_interval`; pulses all registered hubs |
| `moma down` | **New** | Deregisters from all hubs, graceful shutdown |
| `moma status` | Fix | Live data from primary hub |
| `moma reward` | Fix | Live data from primary hub reward ledger |
| `moma benchmark` | Fix | Real Ollama TPS measurement |
| `moma models` | Keep | Real Ollama model list |
| `moma config [key] [value]` | **New** | View/set YAML config keys |
| `moma logs [--hub <url>]` | **New** | Poll recent pulse log entries |
| `moma check` | Keep | Hub + Ollama connectivity check |
| `moma run <file.spl>` | **New** | Parse SPL, dispatch CTEs to grid, assemble results |

**Hub management commands** (`moma hub` subgroup):

| Command | Description |
|---|---|
| `moma hub start` | Start a Hub on this machine (delegates to `python -m igrid.hub.app`) |
| `moma hub peer add <url>` | Add a peer Hub to the cluster |
| `moma hub peer list` | List known peer Hubs + status |
| `moma hub peers sync` | Force-sync capabilities with all peer Hubs |

**Config file** (`~/.moma/config.yaml`):
```yaml
node_id: "pioneer-node-abc123"
secret_key: "..."          # generated at first join
operator_id: null          # optional: operator UUID
hubs:
  - url: "http://192.168.1.10:8000"
    name: "Pioneer Hub"
    session_token: "..."   # per-hub session token
    pulse_interval: 30
  - url: "http://192.168.1.11:8000"
    name: "Backup Hub"
    session_token: "..."
    pulse_interval: 30
primary_hub: "http://192.168.1.10:8000"
ollama_host: "http://localhost:11434"
```

### `moma join` with multiple hubs
```bash
moma join http://192.168.1.10:8000 http://192.168.1.11:8000
# Runs benchmark once, registers with both hubs, stores both session tokens
```

### `moma run` internals
```
1. Parse .spl file using SPL parser
2. Build CTE dependency DAG (from SELECT...FROM references)
3. For each independent CTE group (parallel batch):
   a. Create TaskRequest (model from USING MODEL, vram from MODEL_VRAM table)
   b. POST /tasks to primary hub → get task_id
   c. Poll GET /tasks/{id} with exponential backoff (max 5 min)
      (Hub handles forwarding to peer if needed; caller is unaware)
4. Assemble results in DAG order, passing prior outputs as context_data
5. Print final PROMPT result to stdout (or --output file)
```

---

## 9. Reward System

- **Earn:** 1 point per 1,000 tokens processed (adjustable constant)
- **Uptime bonus:** +10% points if agent was online for >23h in the past 24h (future)
- **Ledger:** Append-only `reward_ledger` table — no updates, only inserts
- **Redemption:** Tracked via `points_balance`; redemption stubs in CLI for future extension
- **`moma status` output:**
  ```
  Node:     pioneer-node (GOLD tier)
  Status:   IDLE
  Hub:      http://192.168.1.10:8000 (connected)
  GPU:      NVIDIA GTX 1080 Ti | 11.0 GB VRAM | 58°C | 15% used
  Tasks:    47 completed | 0 failed
  Tokens:   128,450 processed
  Rewards:  128.45 points (~$1.28 credit)
  Uptime:   4h 23m
  ```

---

## 10. Test Strategy

### Unit tests (no network, no Ollama required)
- `test_schema.py` — Pydantic validation for all models
- `test_dispatcher.py` — tier ranking, VRAM filter, model cache preference
- `test_monitor.py` — eviction logic (mock timestamps), re-queuing
- `test_hardware.py` — mock pynvml + nvidia-smi, CPU fallback path
- `test_hub_endpoints.py` — FastAPI TestClient, full task lifecycle
- `test_agent.py` — pulse loop logic, OllamaError propagation
- `test_cli.py` — all CLI commands via CliRunner
- `test_spl_runner.py` — SPL CTE parsing, DAG ordering, mock dispatch

### E2E test (for weekend test on 3× GTX 1080 Ti)
`tests/e2e/test_three_node_grid.py`:
- Starts Hub in a subprocess
- Registers 3 simulated agents with different VRAM (8, 8, 11 GB)
- Submits an SPL file with 3 CTEs of different model requirements
- Verifies: correct node selected per task, rewards accumulated, results assembled

---

## 11. Dependencies

```toml
[project]
name = "momahub"
requires-python = ">=3.11"
dependencies = [
    # Hub
    "fastapi>=0.111",
    "uvicorn[standard]",
    "aiosqlite",
    "pydantic>=2.0",
    # Agent & CLI
    "typer",
    "requests",
    "httpx",          # async HTTP for IGridAdapter
    "pyyaml",
    "pynvml",         # optional at runtime, graceful fallback
    # SPL integration (local path installs)
    # "spl @ file:../SPL",
    # "spl-flow @ file:../SPL-flow",
    # UI
    "streamlit",
]
```

`pynvml` is listed as a regular dependency but gracefully handled — if the import fails (e.g., no NVIDIA drivers), hardware detection falls back to `nvidia-smi`, then CPU-only mode, with a clear warning logged.

---

## 12. Implementation Order

Phases, each independently testable:

| Phase | Deliverable | Validates |
|---|---|---|
| 1 | SPL grammar (ON GRID, WITH VRAM) | Parser round-trip tests in SPL repo |
| 2 | Schema + DB layer | All Pydantic models + SQLite schema + migrations |
| 3 | Hub core (app + state + dispatcher + monitor) | Agent lifecycle, task lifecycle, auto-eviction |
| 4 | Hub cluster (peer_hubs, forward, capabilities) | Hub A → Hub B task forwarding |
| 5 | Agent (hardware + benchmark + worker) | Real TPS, real telemetry, multi-hub pulse |
| 6 | CLI (all commands + hub subgroup) | `join → up → status → down`, `hub peer add` |
| 7 | IGridAdapter + `moma run` | SPL → distributed dispatch → assembled result |
| 8 | Streamlit UI | Grid monitor (per-hub + cluster view) + rewards |
| 9 | Unit tests (all modules) | Full coverage for weekend confidence |
| 10 | E2E test (`test_two_hub_grid.py`) | Hub A + Hub B + 3 agent nodes, cluster forwarding |

**Weekend test topology:**
```
LAN: 192.168.1.0/24

Machine 1 (GTX 1080 Ti):   Hub A  + Agent node 1   port 8000
Machine 2 (GTX 1080 Ti):   Hub B  + Agent node 2   port 8000
Machine 3 (GTX 1080 Ti):              Agent node 3  → joins both Hub A and Hub B

Test scenarios:
 a) Node 1 busy, task needing 1080 Ti → routed to Node 2 (same hub)
 b) All Hub A agents busy → task forwarded to Hub B → handled by Node 2
 c) Node 3 (dual-registered) handles overflow from either hub
 d) moma run multi_cte.spl → 2 CTEs dispatched in parallel to different nodes
```

---

## 13. Open Questions Before Implementation

1. **SPL install mode** — Should `momahub-claude` install SPL/SPL-flow as local path dependencies (`pip install -e ../SPL`) or should SPL changes be committed to the SPL repo first? I'd recommend the local path approach during the PoC phase.

2. **Hub network binding** — For the 3-node LAN test, the Hub should bind to `0.0.0.0:8000`. Should the Hub URL be configurable at startup (env var or CLI arg)?

3. **`moma logs` implementation** — The spec says "stream real-time agent logs." Server-Sent Events (SSE) from the Hub is cleaner than file tailing. Should I implement SSE streaming from a `/logs` endpoint, or a simple polling approach for the PoC?

4. **Multi-GPU nodes** — The 1080 Ti nodes may have one GPU each, but should the schema/hardware detection support multiple GPUs per node (reporting the primary GPU's VRAM, total VRAM)?

5. **SPL grammar changes** — Should the `ON GRID` / `WITH VRAM` changes be backward-compatible additions to the SPL repo, or would you prefer them in a `momahub` branch first?

---

*Awaiting your approval to begin Phase 1 implementation.*

---

## 14. WAN Solutions: NAT Traversal for Distributed Inference

### The Problem

On a LAN, the hub can push tasks directly to agents via HTTP POST because all machines
have routable IPs. Over the internet (WAN), agents sit behind ISP firewalls/NAT and
**cannot accept inbound connections**. This section documents 4 solutions, from simplest
to most complex.

---

### Solution 1: SSE Pull Mode (Implemented)

**Complexity:** Low | **Dependencies:** None | **Latency:** ~2s

```
Agent ──GET /task-stream/{agent_id}──► Hub    (SSE, stays open)
       ◄── data: {task JSON} ──────────
Agent runs Ollama locally
Agent ──POST /results──────────────► Hub
```

**How it works:**
- Agent opens a long-lived HTTP GET to the hub's `/task-stream/{agent_id}` endpoint
- Hub holds the connection open as a Server-Sent Events stream
- When the dispatcher assigns a task to a pull-mode agent, it puts the task on an
  asyncio.Queue; the SSE handler yields it as `data: {json}\n\n`
- Agent deserializes the task, runs Ollama, POSTs the result back to `/results`
- Keepalive comments (`: keepalive\n\n`) sent every 15s prevent proxy timeouts

**Pros:**
- Outbound-only connections — works through any NAT/firewall
- No extra infrastructure — just FastAPI + asyncio.Queue
- Backward-compatible — push-mode agents work unchanged

**Cons:**
- Hub must hold one open connection per pull-mode agent (fine for <1000 agents)
- ~2s dispatch latency (dispatch loop interval)

**CLI usage:**
```bash
# Agent behind NAT joins hub on the public internet:
moma join http://hub.example.com:8000 --pull

# Hub operator needs no changes — both modes work simultaneously
moma hub up --host 0.0.0.0 --port 8000
```

---

### Solution 2: WebSocket Bidirectional Channel

**Complexity:** Medium | **Dependencies:** `websockets` | **Latency:** <100ms

```
Agent ──WS /ws/{agent_id}──► Hub    (persistent WebSocket)
       ◄── task JSON ──────────      (hub pushes instantly)
       ── result JSON ──────►        (agent sends back on same socket)
```

**How it works:**
- Agent opens a WebSocket connection to the hub
- Hub can push tasks instantly (no polling delay)
- Agent sends results back over the same WebSocket (no separate POST)
- Bidirectional — hub can also send control messages (cancel, reconfigure)

**Pros:**
- Lowest latency of all NAT-traversal solutions
- Single connection for both directions
- Built-in binary frame support for future features

**Cons:**
- More complex protocol (message framing, error recovery)
- Some corporate proxies block WebSocket upgrades
- Requires `websockets` or Starlette WebSocket support

**When to use:** When sub-second dispatch latency matters and you control the
network path (no hostile proxies).

---

### Solution 3: Reverse SSH Tunnel

**Complexity:** Medium | **Dependencies:** SSH access to hub machine | **Latency:** ~0ms (direct TCP)

```
Agent ──ssh -R 8100:localhost:8100──► Hub machine
Hub ──POST http://localhost:8100/run──► (tunneled to agent)
```

**How it works:**
- Agent opens a reverse SSH tunnel: remote port 8100 on the hub machine forwards
  to the agent's local port 8100
- Hub dispatches tasks via HTTP POST to `localhost:8100` — the SSH tunnel carries
  the traffic to the agent transparently
- The hub thinks the agent is local — zero code changes needed

**Pros:**
- Zero application code changes — hub uses normal push mode
- Strong encryption (SSH)
- Works through any firewall that allows outbound SSH

**Cons:**
- Requires SSH access to the hub machine (not always possible)
- One SSH tunnel per agent — operational overhead
- If the tunnel drops, tasks fail until reconnected
- Port management becomes complex with many agents

**Setup:**
```bash
# On the agent machine (behind NAT):
ssh -R 8100:localhost:8100 user@hub.example.com -N

# Then join normally (hub sees you as localhost):
moma join http://hub.example.com:8000 --host localhost --port 8100
```

---

### Solution 4: Tailscale / WireGuard VPN Mesh

**Complexity:** Low (setup) / High (infra) | **Dependencies:** Tailscale account or WireGuard config | **Latency:** ~0ms

```
Agent (100.x.x.x) ◄──Tailscale mesh──► Hub (100.y.y.y)
                    (encrypted WireGuard tunnel)
Hub ──POST http://100.x.x.x:8100/run──► Agent    (direct, as if LAN)
```

**How it works:**
- All machines install Tailscale (or configure WireGuard manually)
- Each machine gets a stable `100.x.x.x` IP on the Tailscale network
- Hub and agents communicate as if on a LAN — zero NAT issues
- No application code changes needed

**Pros:**
- Zero application code changes — everything works like a LAN
- Encrypted by default (WireGuard)
- Tailscale handles NAT traversal, key management, ACLs
- Works even when both sides are behind NAT (DERP relay fallback)

**Cons:**
- Requires installing Tailscale/WireGuard on every machine
- Tailscale free tier: up to 100 devices (plenty for a grid)
- Adds a dependency on external infrastructure
- WireGuard manual setup is complex for non-technical users

**Setup:**
```bash
# On every machine (hub + all agents):
curl -fsSL https://tailscale.com/install.sh | sh
tailscale up

# Hub starts normally:
moma hub up --host 0.0.0.0 --port 8000

# Agent joins using Tailscale IP of the hub:
moma join http://100.64.0.1:8000
```

---

### Comparison Matrix

| Solution | Code Changes | Latency | Firewall-Safe | Extra Infra | Best For |
|----------|-------------|---------|---------------|-------------|----------|
| SSE Pull | Hub + Agent | ~2s | Yes | None | WAN with friends, PoC |
| WebSocket | Hub + Agent | <100ms | Mostly | None | Low-latency production |
| SSH Tunnel | None | ~0ms | Yes (SSH out) | SSH access | Quick hack, 1-2 agents |
| VPN Mesh | None | ~0ms | Yes | Tailscale/WG | Permanent grid, many agents |

**Recommendation for the weekend WAN test:** Start with **SSE Pull Mode** (Solution 1).
It requires no extra infrastructure, works through any NAT, and is already implemented.
If latency becomes an issue, upgrade to WebSocket (Solution 2) later.

---

## 15. SPL as a Prompt Compiler

### Idea

Treat SPL not as a scripting language that *orchestrates* LLM calls, but as a **compiler** that operates on prompts. The analogy:

```
Source code   →  Compiler   →  Machine code  →  CPU executes
Raw intent    →  SPL        →  Optimised prompt(s)  →  LLM executes
```

A traditional compiler has phases: lexing, parsing, IR, optimisation, code generation. SPL already has the first three (tokens, AST, CTE dependency graph). The missing piece is **prompt-level optimisation passes** — transformations that rewrite, split, merge, or reorder prompt fragments before they hit the grid.

### What This Enables

| Compiler Phase | SPL Equivalent | Example |
|----------------|----------------|---------|
| Lexing / Parsing | SPL parser (exists) | `PROMPT ... WITH ... SELECT ... GENERATE` |
| IR (intermediate representation) | CTE dependency DAG (exists) | Parallel vs sequential CTE batches |
| **Constant folding** | **Prompt deduplication** | Two CTEs with identical system prompts → share one call |
| **Dead code elimination** | **Unreachable CTE pruning** | CTE whose output is never referenced → skip |
| **Inlining** | **CTE collapsing** | Single-dependency chain A→B → merge into one prompt |
| **Register allocation** | **Model/VRAM routing** | Map CTEs to GPU nodes by capacity |
| **Instruction scheduling** | **Prompt batching** | Group independent CTEs into one batched call |
| **Peephole optimisation** | **Prompt rewriting** | Shorten verbose system prompts to save tokens |

### Impact on Text2SPL

Text2SPL currently translates NL → SPL syntax. With the compiler framing, Text2SPL becomes the **front-end** of the compiler:

```
User NL intent
    → Text2SPL (front-end: NL → SPL AST)
    → Optimiser (mid-end: prompt-level passes)
    → IGridAdapter (back-end: dispatch optimised prompts to grid)
```

Text2SPL can be improved by training it to emit *compiler-friendly* SPL — e.g., preferring fine-grained CTEs that the optimiser can then merge or parallelise, rather than monolithic single-CTE prompts.

### Impact on MoMaHub

The hub dispatcher becomes the **back-end code generator** — it receives optimised prompt units from the SPL compiler and maps them to physical GPU nodes. This is exactly what a compiler back-end does: map IR instructions to physical registers/ALUs.

This framing also clarifies the boundary: SPL owns *what* to compute (prompt semantics), MoMaHub owns *where* to compute it (physical dispatch). Neither needs to know the other's internals.

### Next Steps

1. Define the optimisation pass interface (input: CTE DAG, output: transformed CTE DAG)
2. Implement one pass as a proof of concept (e.g., CTE deduplication or prompt batching)
3. Measure token savings on a real multi-CTE SPL script
4. Extend Text2SPL training to emit optimiser-friendly SPL

---

## 16. Encrypted Prompt Chunking (Public-Private Key)

### Problem

In a distributed grid, agents see the full prompt text. This has two issues:

1. **Privacy**: Sensitive prompts (legal docs, medical data, proprietary code) are exposed to every agent node that processes them.
2. **Proof of work complexity**: The current verification system must validate that an agent actually ran inference and didn't fabricate results. This requires benchmark tasks, sampling, and trust heuristics — all fragile.

### Idea

Use public-private key cryptography to **encrypt logically-chunked prompts** so that each agent only sees an opaque ciphertext blob. The agent runs inference on the encrypted chunk and returns a result — but never knows what the actual work involves.

### How It Works

```
Hub (holds private key)                    Agent (no key, sees ciphertext)
─────────────────────                      ──────────────────────────────
1. Split prompt into logical chunks
2. Encrypt each chunk with hub's public key
   (or per-task symmetric key, envelope-encrypted)
3. Dispatch encrypted chunk to agent        → Agent receives opaque blob
                                            4. Agent passes blob to Ollama
                                               (Ollama processes raw bytes
                                                as a "prompt" — see note)
                                            5. Agent returns encrypted result
6. Hub decrypts result with private key
7. Hub assembles final output
```

**Important caveat**: LLMs can't do inference on ciphertext directly — the model needs plaintext tokens. So the encryption boundary must be between the **hub and the agent process**, not between the agent and Ollama. Two practical approaches:

#### Approach A: Trusted Execution Envelope

```
Hub encrypts prompt → Agent decrypts in a sandboxed enclave (e.g., TEE/SGX)
                      → Ollama runs inside enclave → result encrypted before leaving
```

This requires hardware TEE support. Strongest guarantee but highest complexity.

#### Approach B: Chunk Obfuscation (Practical for PoC)

Rather than full encryption, **split the prompt into semantic chunks and distribute them across multiple agents** so no single agent sees the full context:

```
Original prompt: "Review this contract for liability clauses: [full contract text]"

Chunk 1 (Agent A): "Identify legal terms in: [paragraph 1-3]"
Chunk 2 (Agent B): "Identify legal terms in: [paragraph 4-6]"
Chunk 3 (Agent C): "Identify legal terms in: [paragraph 7-9]"
Hub reassembles: merges partial results → final analysis
```

Each agent sees only a fragment — no single agent can reconstruct the full document. The SPL compiler (Section 15) naturally produces these chunks via CTEs.

### Simplified Proof of Work

This approach dramatically simplifies proof of work:

| Current Approach | Encrypted Chunk Approach |
|------------------|--------------------------|
| Hub sends benchmark tasks to verify agent capability | Hub sends real (opaque) work — every task *is* a proof of work |
| Hub must check if results are "reasonable" (heuristic) | Hub decrypts and validates against known chunk semantics |
| Agents can game benchmarks (cache answers) | Agents can't game what they can't read |
| Complex sampling + verification pipeline | Simple: did the decrypted output make sense? |

The hub can also embed **canary tokens** — known-answer fragments injected into chunks. If the agent returns a wrong answer for the canary, it's provably cheating.

### Key Management

```
Hub startup:
  → Generate RSA-4096 key pair (or Ed25519 for signing)
  → Public key published at GET /hub/pubkey
  → Private key never leaves hub

Per-task encryption:
  → Generate AES-256 session key
  → Encrypt prompt with AES-256
  → Encrypt AES key with hub's RSA public key (envelope encryption)
  → Send {encrypted_prompt, encrypted_session_key} to agent
```

### Next Steps

1. Start with **Approach B** (chunk obfuscation) — it works today with no crypto infrastructure
2. SPL's CTE chunking already provides the logical split points
3. Add canary token injection to the dispatcher for lightweight proof of work
4. Evaluate TEE/SGX feasibility for Approach A as a future hardening step
