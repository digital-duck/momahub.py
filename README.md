# MoMaHub (i-grid)

Hub-and-spoke distributed AI inference network. Clients submit tasks to a **Hub**; the Hub dispatches them to **Agent** nodes running [Ollama](https://ollama.com).

## Features

- **Hub-and-spoke dispatch** — automatic agent selection by compute tier, VRAM, and model availability
- **Multi-hub clustering** — peer hubs share capabilities and forward tasks across the network
- **Compute tiers** — agents ranked PLATINUM / GOLD / SILVER / BRONZE by measured tokens-per-second
- **Reward ledger** — tracks operator contributions (tasks completed, tokens generated, credits earned)
- **SPL integration** — run structured prompt programs on the grid with `ON GRID` / `WITH VRAM` syntax
- **Streamlit dashboard** — real-time overview, grid monitor, rewards, SPL runner, Text2SPL, and Paper Digest
- **CLI (`moma`)** — full grid management from the terminal

## Quick start

```bash
# 1. Install
pip install -e ".[dev]"

# 2. Start the hub
moma hub up

# 3. Start an agent (requires Ollama running locally)
moma join http://localhost:8000

# 4. Submit a task
moma submit "Explain distributed inference in two sentences" --model llama3

# 5. Check status
moma status
moma agents
moma tasks
```

## Project layout

```
igrid/
  schema/      Pydantic models (enums, handshake, pulse, task, reward, cluster)
  hub/         Hub FastAPI app (db, state, dispatcher, cluster, monitor)
  agent/       Agent FastAPI app (hardware detection, LLM runner, telemetry)
  cli/         moma CLI (Typer / Click)
  spl/         SPL adapter and runner
  ui/          Streamlit dashboard (6 pages)
cookbook/       Ready-to-run recipes (see USER-GUIDE.md)
tests/         Unit and integration tests
```

## Requirements

- Python >= 3.11
- [Ollama](https://ollama.com) on every agent node
- GPU recommended (CPU-only works but is slow)

## Documentation

See **[USER-GUIDE.md](USER-GUIDE.md)** for detailed usage instructions, cookbook walkthroughs, and a step-by-step guide for running a weekend LAN test on 3 GPUs.

## License

Apache 2.0
