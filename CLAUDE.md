# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install in dev mode
pip install -e ".[dev]"
pip install -e /path/to/SPL  # required for moma run / igrid.spl

# Unit tests
pytest tests/unit/ -v
pytest tests/unit/test_state.py -v  # single file

# Start the hub
moma hub up --host 0.0.0.0 --port 8000

# Start an agent (requires Ollama)
moma join http://localhost:8000

# Grid operations
moma status
moma agents
moma tasks
moma submit "Hello grid" --model llama3
moma run cookbook/01_single_node_hello/hello.spl

# Peer management
moma peer add http://192.168.1.20:8000
moma peer list

# Rewards / logs
moma rewards
moma logs --follow

# Dashboard
moma-ui
# or: IGRID_HUB_URL=http://localhost:8000 moma-ui
```

## Architecture

i-grid is a hub-and-spoke distributed AI inference network. Clients submit tasks to a Hub; Hub dispatches to Agent nodes running Ollama.

### Package layout (igrid/)

| Package | Role |
|---------|------|
| igrid/schema/ | Pydantic schemas: enums, handshake, pulse, task, reward, cluster |
| igrid/hub/ | Hub FastAPI app: db.py, state.py, dispatcher.py, cluster.py, monitor.py, app.py |
| igrid/agent/ | Agent FastAPI app: hardware.py, llm.py, telemetry.py, worker.py |
| igrid/cli/ | moma CLI (Typer, built on Click): config.py, main.py |
| igrid/spl/ | SPL integration: igrid_adapter.py, runner.py |
| igrid/ui/ | Streamlit dashboard: 5 pages (Overview, Grid Monitor, Rewards, Run SPL, Text2SPL, Paper Digest) |

### Key design

- **Task dispatch**: `_dispatch_loop` (2s interval) → `pick_agent()` (tier/VRAM/model filter) → `claim_task()` (atomic SQL RETURNING) → HTTP POST to agent `/run`
- **Hub-and-spoke**: `ClusterManager.add_peer()` → POST `/cluster/handshake`. Cluster monitor (60s) pushes capabilities and forwards PENDING tasks with no local eligible agent.
- **Task state machine**: PENDING → DISPATCHED → IN_FLIGHT → COMPLETE | FAILED | FORWARDED. Failed tasks retry up to MAX_RETRIES=3, then permanently FAILED. Agent eviction (90s) re-queues IN_FLIGHT tasks.
- **Hardware detection**: pynvml → nvidia-smi → CPU-only (logged WARNING)
- **TPS measurement**: Ollama `eval_count / eval_duration`. Hub assigns tier server-side.
- **Compute tiers**: PLATINUM>=60, GOLD>=30 (GTX 1080 Ti ~35-45), SILVER>=15, BRONZE<15
- **CLI**: Typer (Click-based). Config at ~/.igrid/config.yaml

### SPL grammar extensions (in SPL repo)

tokens.py, ast_nodes.py, parser.py, executor.py, adapters/__init__.py all extended for ON GRID and WITH VRAM syntax.

### Database

SQLite via aiosqlite. 7 tables: hub_config, peer_hubs, operators, agents, tasks, pulse_log, reward_ledger + reward_summary view.

### Weekend LAN test target

3x GTX 1080 Ti (11 GB VRAM, ~35-45 TPS -> GOLD tier) on a LAN. One machine runs the hub, all three run agents.
