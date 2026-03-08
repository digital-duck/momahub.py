# User Guide

Complete guide to running Momahub: installation, CLI reference, cookbook recipes, and a weekend LAN test plan for 3 GPUs.

---

## Table of contents

1. [Installation](#installation)
2. [Configuration](#configuration)
3. [CLI reference](#cli-reference)
4. [Dashboard](#dashboard)
5. [Cookbook recipes](#cookbook-recipes)
6. [Weekend LAN test — 3 GPU setup](#weekend-lan-test--3-gpu-setup)
7. [Troubleshooting](#troubleshooting)

---

## Installation

```bash
conda create -n momahub python=3.11
conda activate momahub


# (Optional) Install SPL for moma run / ON GRID syntax
pip install -e $HOME/projects/digital-duck/SPL
pip install -e $HOME/projects/digital-duck/SPL-flow

# Clone the repo

git clone https://github.com/digital-duck/momahub.py.git
cd momahub.py

# Install in dev mode
pip install -e ".[dev]"

```

Every agent node needs [Ollama](https://ollama.com) installed and running with at least one model pulled:

```bash
ollama pull llama3
ollama pull llama3.1
ollama pull mistral
ollama pull mathstral   
ollama pull qwen3
ollama pull qwen2.5
ollama pull qwen2.5-coder
ollama pull qwen2-math
ollama pull deepseek-r1
ollama pull deepseek-coder-v2
ollama pull gemma3
ollama pull phi4
ollama pull phi4-mini
ollama pull phi3
```

## Configuration

Config lives at `~/.igrid/config.yaml`. View or update it with:

```bash
moma config                          # show current config
# use `hostname -I` or `ip a` to identify IP address
hostname -I

moma config --set hub_urls=http://192.168.0.177:8000
moma config --set operator_id=duck
```

> **Tip:** Cookbook recipes (in `cookbook/`) now automatically detect your Hub URL from this configuration. You no longer need to pass `--hub` manually for every script.

### Concurrency Defaults

The system is tuned for multi-GPU performance by default:
- **Hub:** Tracks individual agent capacity and supports up to 8 concurrent global tasks.
- **Agent:** Buffers tasks locally and supports 4 concurrent inferences per node.

Key settings:

| Key | Default | Description |
|-----|---------|-------------|
| `operator_id` | `duck` | Your operator name (appears in reward ledger) |
| `hub_urls` | `["http://localhost:8000"]` | Hub(s) to connect to |
| `ollama_url` | `http://localhost:11434` | Local Ollama endpoint |
| `db_path` | `.igrid/hub.sqlite` | SQLite database path |
| `api_key` | (empty) | Optional API key for hub authentication |
| `agent_name` | (empty) | Human-friendly agent name (default: hostname) |
| `agent_id` | (empty) | Agent UUID (auto-saved on join) |

## CLI reference

The `moma` CLI is organized into commands and subcommand groups.

### Hub management

```bash
# Find the hub process
pkill -f "moma hub up" 

moma hub up                                # start hub on 0.0.0.0:8000
moma hub up --host 0.0.0.0 --port 9000     # custom bind address
moma hub up --api-key mysecret             # require API key for joins
```

### Agent management

```bash
# open a new terminal 

hostname -I
# 192.168.0.170
moma join http://192.168.0.177:8000

moma join http://localhost:8000             # start agent, join one hub
moma join http://hub1:8000 http://hub2:8000 # join multiple hubs
moma join http://hub:8000 --port 8100       # custom agent port
moma join http://hub:8000 --name alice      # human-friendly name
moma join http://hub:8000 --pull            # SSE pull mode (WAN-safe)
moma down                                   # deregister from all hubs
moma down --agent-id <uuid>                 # deregister a specific agent
```

### Task operations

```bash
moma submit 'what is 10!' --model mistral
moma submit "Summarize this" --model mistral --max-tokens 512
moma tasks                                  # list recent tasks
```

Example `moma tasks` output:
```text
TASK_ID                                STATE        MODEL                AGENT            SUBMITTED 
------------------------------------------------------------------------------------------------------
stress-c775daae                        COMPLETE     llama3               papa-game        05:52:41  
stress-67b96180                        COMPLETE     llama3               wengong          05:52:41  
```

```bash
moma tasks --limit 50                       # show more
```

### Grid status

```bash
moma status                                 # hub health check
moma agents                                 # list online agents with tier/TPS
moma logs                                   # recent pulse log
moma logs --follow                          # tail the log
```

### Cluster (multi-hub)

```bash
moma peer add http://192.168.1.20:8000      # connect to a peer hub
moma peer list                              # show peer hubs
```

### Rewards

```bash
moma rewards                                # operator contribution summary

(momahub) papagame@papa-game:~/projects/digital-duck/momahub.py$ moma rewards
OPERATOR                TASKS       TOKENS    CREDITS
duck                        7          486       0.49

```

### SPL execution

```bash
moma run cookbook/01_single_node_hello/hello.spl
```

```response
=== hello_grid ===
Here is an introduction to the Momahub:

The Momahub is a novel distributed inference network that enables efficient and scalable inference across multiple devices, allowing for real-time processing of complex data streams. By harnessing the power of interconnected devices on the grid, the Momahub facilitates collaborative learning and reasoning, breaking down traditional boundaries between devices and unlocking new possibilities in artificial intelligence, machine learning, and beyond.

[model=llama3  tokens=41+80  latency=33446ms]

```

### Submit prompt directly

```bash
moma submit "what is 1+2"
```

```response

Task submitted: 5b286594-c47c-46ca-9498-868c6ace58fd

The answer to 1+2 is... 3!
[model=llama3 tokens=16+13 latency=387ms]

```


```bash
(momahub) papagame@papa-game:~/projects/digital-duck/momahub.py$ moma submit "what is 10!"
Task submitted: 986f3841-139b-449a-a720-82d77e6be7f1

A simple but exciting question!

10! (also written as 10 factorial) is the product of all positive integers from 1 to 10, multiplied together.

So, 10! is:

10! = 10 × 9 × 8 × 7 × 6 × 5 × 4 × 3 × 2 × 1

Which equals:

10! = 3,628,800
[model=llama3 tokens=15+86 latency=1752ms]
(momahub) papagame@papa-game:~/projects/digital-duck/momahub.py$ moma submit "what is 10!"
Task submitted: 638cf6c3-e67f-4b6d-a73f-30feb19da820

A factorial!

The exclamation mark (!) in math notation indicates the factorial operation. So, 10! (read as "10 factorial") is the result of multiplying all positive integers from 1 to 10:

10! = 10 × 9 × 8 × 7 × 6 × 5 × 4 × 3 × 2 × 1

Calculating this...

10! = 3,628,800
[model=llama3 tokens=15+91 latency=1816ms]

(momahub) papagame@papa-game:~/projects/digital-duck/momahub.py$ moma submit "what is 10!" --model mathstral
Task submitted: 0009d0dd-e962-4b1a-96bf-d82a8cf13124

10!, which is the factorial of 10, means multiplying all positive integers from 1 to 10 together. So, 10! = 1 × 2 × 3 × 4 × 5 × 6 × 7 × 8 × 9 × 10 = 3,628,800.
[model=mathstral tokens=11+80 latency=28394ms]

(momahub) papagame@papa-game:~/projects/digital-duck/momahub.py$ moma submit "what is 5!" --model mathstral
Task submitted: fb3df4ab-8b7b-4ae8-9e96-561aee112a12

5! (which is read as "five factorial") means the product of all positive integers up to and including 5. So, 5! = 5 × 4 × 3 × 2 × 1 = 120.
[model=mathstral tokens=10+54 latency=945ms]


python cookbook/03_batch_translate/translate.py "Welcome to Momahub! What is 10! " --hub http://192.168.0.177:8000


(momahub) wengong@wengong:~/projects/digital-duck/momahub.py$ python cookbook/03_batch_translate/translate.py "Welcome to Momahub! What is 10! "

  Batch Translate
    Hub:       http://192.168.0.177:8000
    Model:     llama3
    Languages: ['French', 'German', 'Chinese', 'Spanish']
    Text:      Welcome to Momahub! What is 10! 

    French         17 tok    4.6s  agent=..77ea8b6ee4c8
    Spanish      FAILED: Agent at capacity
    German         14 tok    4.7s  agent=..77ea8b6ee4c8
    Chinese        14 tok    7.5s  agent=..77ea8b6ee4c8

  ==================================================
  3/4 translations complete  wall=7.6s

  [Chinese]
  欢迎来到MoMa-Grid！这是10吗？

  [French]
  Bienvenue à Momahub ! Qu'est-ce que cela signifie ?

  [German]
  Willkommen zu Momahub! Was ist 10?

  Report: /home/wengong/projects/digital-duck/momahub.py/cookbook/03_batch_translate/translations_20260307_2336.html

```


## Dashboard

Launch the Streamlit dashboard:

```bash
moma-ui
# or point it at a specific hub:
IGRID_HUB_URL=http://192.168.0.177:8000 moma-ui
```

Pages:

| Page | Description |
|------|-------------|
| **Overview** | Hub health, agent count, recent tasks |
| **Grid Monitor** | Live agent status, tiers, TPS, GPU utilization |
| **Rewards** | Operator contribution leaderboard |
| **Run SPL** | Upload and execute SPL files from the browser |
| **Text2SPL** | Natural-language to SPL program generation |
| **Paper Digest** | Arxiv paper analysis powered by the grid |

---

## Cookbook recipes

The `cookbook/` directory contains ready-to-run examples that demonstrate grid capabilities. Each recipe is self-contained.

### 01 — Single node hello

**File:** `cookbook/01_single_node_hello/hello.spl`

A minimal SPL program that sends one prompt to the grid. Good for verifying that the hub, agent, and Ollama are working end-to-end.

```bash
moma run cookbook/01_single_node_hello/hello.spl
```

The program asks the grid to introduce Momahub in two sentences using `llama3`.

### 02 — Multi-CTE parallel

**File:** `cookbook/02_multi_cte_parallel/multi_cte.spl`

Demonstrates parallel fan-out: two CTE branches (`pros` and `cons`) run on different models (`llama3` and `mistral`) simultaneously, then a final synthesis step merges the results.

```bash
moma run cookbook/02_multi_cte_parallel/multi_cte.spl
```

Requires both `llama3` and `mistral` models available on agents in the grid.

### 03 — Two-hub cluster

**Files:** `cookbook/03_two_hub_cluster/setup.py` (Click CLI), `setup.sh` (reference)

Set up and test a two-machine cluster. Hub A peers with Hub B; tasks submitted to Hub A can be forwarded to Hub B if no local agent can handle them.

```bash
# Interactive Python CLI (recommended):
python cookbook/03_two_hub_cluster/setup.py status
python cookbook/03_two_hub_cluster/setup.py peer
python cookbook/03_two_hub_cluster/setup.py test
python cookbook/03_two_hub_cluster/setup.py full             # all steps

# Custom hub URLs:
python cookbook/03_two_hub_cluster/setup.py --hub-a http://192.168.1.10:8000 --hub-b http://192.168.1.20:8000 full
```

### 04 — Benchmark models

**File:** `cookbook/04_benchmark_models/benchmark.py`

A Python script that submits the same prompt to multiple models (`llama3`, `mistral`, `phi3`) in parallel and reports latency, output tokens, and TPS for each.

```bash
python cookbook/04_benchmark_models/benchmark.py
```

Output example:

```
MODEL           STATE      TOKENS    LATENCY      TPS
-------------------------------------------------------
llama3          COMPLETE       87       2.41      36.1
mistral         COMPLETE       92       2.68      34.3
phi3            COMPLETE       78       3.12      25.0
```

### 05 — RAG on grid

**File:** `cookbook/05_rag_on_grid/rag_query.spl`

Dispatches a retrieval-augmented generation query to the grid. The `RAG_QUERY` function fetches context, then `GENERATE` answers based on that context.

```bash
moma run cookbook/05_rag_on_grid/rag_query.spl
```

### 06 — Arxiv paper digest

**Files:** `cookbook/06_arxiv_paper_digest/digest.py`, `urls_example.txt`

Fetches arxiv papers by URL or ID, extracts PDF text, sends analysis tasks to the grid in parallel, and produces a dark-mode HTML digest.

```bash
# Single paper
python cookbook/06_arxiv_paper_digest/digest.py https://arxiv.org/abs/2312.00752

# From a URL list file
python cookbook/06_arxiv_paper_digest/digest.py --file cookbook/06_arxiv_paper_digest/urls_example.txt

# Custom model / hub
python cookbook/06_arxiv_paper_digest/digest.py --model mistral --hub http://192.168.1.10:8000 2312.00752
```

Each paper receives a structured 7-part digest: title, problem, methodology, results, limitations, relevance, and a one-liner summary.

### 07 — Stress test

**File:** `cookbook/07_stress_test/stress.py`

Fire N tasks at the grid simultaneously and measure throughput, agent distribution, and grid-level tokens/second.

```bash
python cookbook/07_stress_test/stress.py                          # 20 tasks, default
python cookbook/07_stress_test/stress.py -n 50 --model mistral    # 50 tasks
python cookbook/07_stress_test/stress.py --hub http://192.168.1.10:8000
```

Great for watching all GPUs light up and measuring grid throughput.

### 08 — Model arena

**File:** `cookbook/08_model_arena/arena.py`

Submit the same prompt to multiple models and generate a dark-mode HTML report comparing quality, speed, and token efficiency.

```bash
python cookbook/08_model_arena/arena.py                                  # default 3 models
python cookbook/08_model_arena/arena.py --models llama3,mistral,phi3,qwen2.5
python cookbook/08_model_arena/arena.py --prompt "Explain quantum computing"
```

Opens as a side-by-side comparison in the browser. Fastest model gets a trophy.

### 09 — Document pipeline

**File:** `cookbook/09_doc_pipeline/pipeline.py`

End-to-end document processing: extract PDF text (via `dd-extract`), summarize on the grid, and format the output (via `dd-format`).

```bash
python cookbook/09_doc_pipeline/pipeline.py paper.pdf                          # local PDF
python cookbook/09_doc_pipeline/pipeline.py https://arxiv.org/pdf/2312.12345   # from URL
python cookbook/09_doc_pipeline/pipeline.py paper.pdf --format docx --out summary.docx
```

Requires `pip install dd-extract dd-format`.

### 10 — Chain relay

**File:** `cookbook/10_chain_relay/chain.py`

Multi-step reasoning chain where each step's output feeds into the next: Research -> Analyze -> Summarize. Tasks may land on different agents.

```bash
python cookbook/10_chain_relay/chain.py "quantum computing"
python cookbook/10_chain_relay/chain.py "distributed AI inference" --model mistral
```

Watch `moma logs -f` to see tasks hop between nodes.

### 11 — Batch translate

**File:** `cookbook/11_batch_translate/translate.py`

Translate one text into multiple languages in parallel across all grid agents.

```bash
python cookbook/11_batch_translate/translate.py "Hello, world! AI is changing everything."
python cookbook/11_batch_translate/translate.py --file input.txt --languages fr,de,ja,zh,es,ko
```

All agents work simultaneously on different languages. Generates an HTML report.

---

## Milestone: 2-GPU LAN Success (2026-03-08)

The first verified multi-node Momahub deployment was achieved with the following configuration:

### Hardware
- **Node A (Hub + Agent):** 1x NVIDIA GTX 1080 Ti (11GB VRAM)
- **Node B (Agent):** 1x NVIDIA GTX 1080 Ti (11GB VRAM)

### Verification Results
Running the `stress.py` recipe with `-n 10` and concurrency 10:
- **Success Rate:** 100% (10/10 tasks complete)
- **Zero-Drop Reliability:** Transient burst load was handled by agent-side queueing.
- **Load Balancing:** Hub correctly distributed tasks across both machines (`papa-game` and `wengong`).
- **Throughput:** ~41 tokens/s aggregate grid throughput.

### Key Learnings
1. **Per-Agent Capacity:** Setting `max_concurrent` to 4 on agents and 8 on the Hub provided the best balance of speed and stability.
2. **Local Queueing:** Allowing agents to buffer tasks locally prevents "hard failures" during sub-second dispatch bursts.

---

## Weekend LAN test — 3 GPU setup

This section walks through setting up a 3-node Momahub on a home LAN using 3 machines each with a GTX 1080 Ti (11 GB VRAM). Expected performance: ~35-45 TPS per card (GOLD tier).

### Prerequisites

On **every machine**:

1. Install Ollama and pull models:
   ```bash
   ollama pull llama3
   ollama pull mistral   # optional
   ```
2. Install Momahub:
   ```bash
   pip install -e ".[dev]"
   ```
3. Ensure machines can reach each other on the LAN (check firewalls).

### Network plan

| Machine | LAN IP | Role | Ports |
|---------|--------|------|-------|
| **A** | `192.168.1.10` | Hub + Agent | 8000 (hub), 8100 (agent) |
| **B** | `192.168.1.20` | Agent | 8100 (agent) |
| **C** | `192.168.1.30` | Agent | 8100 (agent) |

> Adjust IPs to match your LAN. Use `ip addr` (Linux) or `ipconfig` (Windows) to find them.

### Step 1 — Start the hub (Machine A)

```bash
moma hub up --host 0.0.0.0 --port 8000
```

Verify it's running:
```bash
curl http://192.168.1.10:8000/health
```

### Step 2 — Start agents (all three machines)

**Machine A** (hub machine also runs an agent):
```bash
moma join http://192.168.1.10:8000 --host 192.168.1.10 --port 8100
```

**Machine B:**
```bash
moma join http://192.168.1.10:8000 --host 192.168.1.20 --port 8100
```

**Machine C:**
```bash
moma join http://192.168.1.10:8000 --host 192.168.1.30 --port 8100
```

### Step 3 — Verify the grid

From any machine:
```bash
moma status --hub-url http://192.168.1.10:8000
moma agents --hub-url http://192.168.1.10:8000
```

You should see 3 agents online, each at GOLD tier (~35-45 TPS).

### Step 4 — Run tests

**Smoke test** — single task:
```bash
moma submit "Hello from the grid" --model llama3 --hub-url http://192.168.1.10:8000
```

**Parallel load** — benchmark across models:
```bash
python cookbook/04_benchmark_models/benchmark.py
```

**Fan-out** — parallel CTE dispatched to multiple agents:
```bash
moma run cookbook/02_multi_cte_parallel/multi_cte.spl --hub-url http://192.168.1.10:8000
```

**Paper digest** — real workload across all agents:
```bash
python cookbook/06_arxiv_paper_digest/digest.py --file cookbook/06_arxiv_paper_digest/urls_example.txt
```

### Step 5 — Monitor

**Terminal:**
```bash
moma logs --follow --hub-url http://192.168.1.10:8000
moma rewards --hub-url http://192.168.1.10:8000
```

**Dashboard:**
```bash
IGRID_HUB_URL=http://192.168.1.10:8000 moma-ui
```

Open the Grid Monitor page to watch agent TPS, GPU utilization, and task dispatch in real time.

### Step 6 — Run unit tests

```bash
pytest tests/unit/ -v
```

### What to look for

- All 3 agents appear as **GOLD** tier (TPS 30-60)
- Tasks dispatch round-robin across available agents
- `moma rewards` shows contributions from each operator
- Failed tasks retry (up to 3 times) and re-queue on agent eviction (90s timeout)
- Dashboard Grid Monitor shows live GPU utilization per agent

### Common issues

| Symptom | Fix |
|---------|-----|
| Agent shows 0 TPS / BRONZE | Ollama isn't running or model not pulled — run `ollama list` |
| Agent not appearing | Check firewall; agent must be reachable from hub on its port |
| "Connection refused" | Verify the hub IP/port; ensure `--host 0.0.0.0` is set |
| Tasks stuck PENDING | No agent has the requested model — pull it with `ollama pull <model>` |
| Agent evicted after 90s | Agent crashed or lost network — restart with `moma join` |

---

## Troubleshooting

### Hardware detection

The agent detects GPUs in order: **pynvml** -> **nvidia-smi** -> CPU-only (logged as WARNING). If your GPU isn't detected:

```bash
pip install pynvml
nvidia-smi          # verify driver is working
```

### Database

The hub uses SQLite at `.igrid/hub.sqlite` (configurable). To reset:

```bash
rm .igrid/hub.sqlite
moma hub up          # recreates the database
```

### Logs

Hub logs go to stdout. Increase verbosity by setting the `IGRID_LOG_LEVEL` environment variable or checking uvicorn output directly.
