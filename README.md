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
pip install -e "."

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

## Proven Performance

MoMaHub has been validated in real-world LAN environments:

- **2-GPU Milestone (2026-03-08):** Successfully deployed across two nodes using **NVIDIA GTX 1080 Ti (11GB VRAM)**. Achieved 100% completion rate on burst stress tests with automated agent-side queueing and hub-level load balancing.
- **Tiers:** Measured ~55 TPS (GOLD) and ~105 TPS (PLATINUM) on benchmarked models.

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
- GPU recommended (CPU-only works but will be slow)

## Documentation

- **[USER-GUIDE](USER-GUIDE.md)** for detailed usage instructions, 
- **[Cookbook](./cookbook/README.md)** with 20+ examples.

## Research

MoMaHub is the reference implementation for the paper:

> **MoMaHub: A Prompt Compiler and Accessible Inference Grid**
> Wen Gong (2026). *arXiv preprint in preparation.*

The paper introduces two core ideas:

1. **The Prompt Compiler** — reframing Text2SPL as a full compiler pipeline (front-end NL→SPL, mid-end CTE DAG optimisation, back-end model/VRAM mapping), with SPL as the intermediate representation between human intent and GPU execution. The compiler is self-hosting: it runs on the i-grid it compiles for.

2. **The Distributed Inference Runtime** — MoMaHub as the runtime layer that abstracts distributed consumer GPUs into a programmable compute surface, analogous to the JVM or the Linux kernel for traditional computing.

Related work:
- SPL (Structured Prompt Language): [arXiv:2602.21257](https://arxiv.org/abs/2602.21257)
- Geodesic Reranking: [arXiv:2602.15860](https://arxiv.org/abs/2602.15860)

## License

Apache 2.0
