# GEMINI.md

## Project Overview

**MoMaHub (i-grid)** is a hub-and-spoke distributed AI inference network. It allows clients to submit tasks to a **Hub**, which then dispatches them to **Agent** nodes running [Ollama](https://ollama.com).

### Main Technologies
- **Language:** Python 3.11+
- **Frameworks:** [FastAPI](https://fastapi.tiangolo.com/), [Streamlit](https://streamlit.io/) (Dashboard)
- **Data Persistence:** SQLite (via [aiosqlite](https://github.com/omnilib/aiosqlite))
- **Schema & Validation:** [Pydantic](https://docs.pydantic.dev/)
- **CLI:** [Typer](https://typer.tiangolo.com/) (Click-based)
- **Infrastructure:** Ollama (Local LLM runner)
- **Inference Languages:** Structured Prompt Language (SPL) integration

### Architecture
- **Hub (`igrid/hub/`)**: Manages agent registration, task queuing, dispatching, multi-hub clustering, and reward tracking.
- **Agent (`igrid/agent/`)**: Detects local hardware (GPUs via `pynvml`), registers with the hub, and executes LLM tasks using Ollama. Supports both HTTP push and SSE pull modes.
- **CLI (`igrid/cli/`)**: The `moma` command-line tool for managing the grid, submitting tasks, and running SPL files.
- **UI (`igrid/ui/`)**: A multi-page Streamlit dashboard for real-time monitoring, rewards, and interactive SPL execution.
- **SPL (`igrid/spl/`)**: Integration layer that adapts SPL programs to run on the i-grid.

## Building and Running

### Installation
```bash
# Install in development mode
pip install -e ".[dev]"

# (Optional) Install SPL for 'moma run' and ON GRID syntax
pip install -e /path/to/SPL
```

### Core Commands
- **Start Hub:** `moma hub up` (Defaults to `0.0.0.0:8000`)
- **Join Grid as Agent:** `moma join http://localhost:8000` (Requires Ollama running)
- **Submit Task:** `moma submit "Explain distributed inference" --model llama3`
- **Run SPL Program:** `moma run path/to/file.spl`
- **Launch Dashboard:** `moma-ui`
- **Check Status:** `moma status`, `moma agents`, `moma tasks`
- **View Rewards:** `moma rewards`

### Testing
- **Unit Tests:** `pytest tests/unit/ -v`
- **Specific Test:** `pytest tests/unit/test_state.py -v`

## Development Conventions

### Coding Style & Design
- **Asynchronous First:** Uses `asyncio` for the hub's dispatch loop, agent monitors, and API endpoints.
- **Task State Machine:** Tasks move through states: `PENDING` → `DISPATCHED` → `IN_FLIGHT` → `COMPLETE` | `FAILED` | `FORWARDED`.
- **Compute Tiers:** Agents are ranked by measured tokens-per-second (TPS):
  - **PLATINUM**: ≥ 60 TPS
  - **GOLD**: ≥ 30 TPS
  - **SILVER**: ≥ 15 TPS
  - **BRONZE**: < 15 TPS
- **Resilience:**
  - Tasks are retried up to 3 times on failure.
  - Agents are evicted after 90 seconds of inactivity, and their `IN_FLIGHT` tasks are re-queued.
- **Clustering:** Hubs can peer with each other to share capabilities and forward tasks when local resources are unavailable.

### Directory Structure
- `igrid/schema/`: Pydantic models for all network communication (handshakes, pulses, tasks).
- `igrid/hub/`: Core hub logic (database, state management, dispatcher, monitor).
- `igrid/agent/`: Agent components (hardware detection, LLM backend, telemetry).
- `cookbook/`: Examples and recipes for various grid workloads (parallelism, RAG, paper digests).

### Key Files
- `README.md`: High-level overview and quick start.
- `USER-GUIDE.md`: Detailed configuration and CLI reference.
- `CLAUDE.md`: Implementation guide for AI assistants.
- `pyproject.toml`: Dependency management and project entry points.
- `igrid/hub/app.py`: Main Hub FastAPI application.
- `igrid/agent/worker.py`: Main Agent FastAPI application.

## Weekend LAN Test (Reference Integration Scenario)
A standard integration test scenario involves 3 nodes (each with a GPU like a GTX 1080 Ti) on a local LAN.
1. Hub + Agent on Node A.
2. Agents on Node B and Node C.
3. Verification: `moma agents` shows 3 GOLD tier nodes.
4. Stress Test: `python cookbook/07_stress_test/stress.py` to verify load distribution.
