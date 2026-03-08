# MoMaHub - Hub-and-spoke distributed AI inference network

Users submit requests to a **Hub**, the Hub dispatches them to **Agent** nodes running [Ollama](https://ollama.com).

## Requirements

- Python >= 3.11
- [Ollama](https://ollama.com) on every agent node
- GPU recommended (CPU-only works but will be slow)

## Quick start

```bash
# Install Ollama on all GPU nodes
curl -fsSL https://ollama.com/install.sh | sh
bash scripts/pull_ollama.sh

# Create virtualenv
conda create -n moma python=3.11
conda activate moma

# Git clone
git clone https://github.com/digital-duck/momahub.py.git

# Install from source
pip install -e .

# (Re)Start the hub on a GPU node
moma hub up

# Get hub node IP address, to be used by an agent node to join the hub
hostname -I 
# hub-ip-address

# (Re)Start an agent on all GPU nodes including hub node
moma join http://<hub-ip-address>:8000

# Submit a task from any GPU node
moma submit "Explain distributed inference in two sentences" --model <model of your choice pulled before>

# Monitor MoMaHub status
moma status
moma agents
moma tasks
moma rewards

# Get Help
moma --help
```

## Features

- **Hub-and-spoke dispatch** — automatic agent selection by compute tier, VRAM, and model availability
- **Multi-hub clustering** — peer hubs share capabilities and forward tasks across the network
- **Compute tiers** — agents ranked PLATINUM / GOLD / SILVER / BRONZE by measured tokens-per-second
- **Reward ledger** — tracks operator contributions (tasks completed, tokens generated, credits earned)
- **SPL integration** — run structured prompt programs on the grid with `ON GRID` / `WITH VRAM` syntax
- **Streamlit dashboard** — real-time overview, grid monitor, rewards, SPL runner, Text2SPL, and Paper Digest
- **CLI (`moma`)** — full grid management from the terminal

## Proven Performance

MoMaHub has been validated in real-world LAN environments:

- **3-GPU Milestone (2026-03-08):** Successfully deployed across 3 GPU nodes using 2 **NVIDIA GTX 1080 Ti (11GB VRAM)** + 1 **NVIDIA GTX 1050 Ti (4GB VRAM)**. Achieved 100% completion rate on burst stress tests with automated agent-side queueing and hub-level load balancing.
- **Tiers:** Measured between 50 and 100 TPS on benchmarked models.

## Codebase layout

```
igrid/
  schema/      Pydantic models (enums, handshake, pulse, task, reward, cluster)
  hub/         Hub FastAPI app (db, state, dispatcher, cluster, monitor)
  agent/       Agent FastAPI app (hardware detection, LLM runner, telemetry)
  spl/         SPL adapter and runner
  cli/         moma CLI
  ui/          Streamlit app
docs/          User-Guide, SPL arXiv paper
cookbook/      Ready-to-run recipes
scripts/       Utility scripts
tests/         Unit and integration tests
```

## Documentation

- **[User Guide](./docs/USER-GUIDE.md)** for detailed usage instructions, 
- **[Cookbook](./cookbook/README.md)** with 20+ examples.

## Research

### MoMaHub - the python implementation for this upcoming arxiv paper (in preparation)

> **MoMaHub: A Prompt Compiler and Decentralized LLM Inference Network**
> Wen G. Gong (2026)

The paper introduces two key ideas:

1. **The Prompt Compiler** — reframing Text2SPL as a full compiler pipeline (front-end NL→SPL, mid-end CTE DAG optimisation, back-end model/VRAM mapping), with SPL as the intermediate representation between human intent and GPU execution. The compiler is self-hosting: it runs on the i-grid it compiles for.

2. **The Distributed Inference Runtime** — MoMaHub as the runtime layer that abstracts distributed consumer GPUs into a programmable compute surface, analogous to the JVM or the Linux kernel for traditional computing.

### Related work
- **SPL - Structured Prompt Language:** [arXiv:2602.21257](https://arxiv.org/abs/2602.21257)
  > Wen G. Gong. (2026). *Structured Prompt Language: Declarative Context Management for LLMs*. arXiv preprint arXiv:2602.21257.

  ```bibtex
  @article{gong2026spl,
    title={Structured Prompt Language: Declarative Context Management for LLMs},
    author={Gong, Wen G.},
    journal={arXiv preprint arXiv:2602.21257},
    year={2026}
  }
  ```
- **Geodesic Reranking:** [arXiv:2602.15860](https://arxiv.org/abs/2602.15860)
  > Wen G. Gong. (2026). *Reranker Optimization via Geodesic Distances on k-NN Manifolds*. arXiv preprint arXiv:2602.15860.

  ```bibtex
  @article{gong2026geodesic,
    title={Reranker Optimization via Geodesic Distances on k-NN Manifolds},
    author={Gong, Wen G.},
    journal={arXiv preprint arXiv:2602.15860},
    year={2026}
  }
  ```

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details on our development workflow and coding standards.

## License

Apache 2.0
