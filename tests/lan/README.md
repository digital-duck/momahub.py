# LAN Weekend Test Plan

**Hardware:** 3x GTX 1080 Ti (11 GB VRAM, ~35-45 TPS expected → GOLD tier)
**OS:** Ubuntu (all machines)
**Topology:** 1 hub + 2 agents (hub machine also runs an agent)

---

## Network Layout

```
Machine A (hub + agent)          Machine B (agent)          Machine C (agent)
┌─────────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  moma hub up        │     │                  │     │                  │
│    :8000            │◄────│  moma join A:8000 │     │  moma join A:8000│
│  moma agent up      │     │    :8100          │     │    :8100         │
│    :8100            │     │                   │     │                  │
│  GTX 1080 Ti 11GB   │     │  GTX 1080 Ti 11GB │     │  GTX 1080 Ti 11GB│
└─────────────────────┘     └──────────────────┘     └──────────────────┘
```

---

## Pre-flight Checklist

### All machines

```bash
# Install momahub
pip install -e /path/to/momahub.py

# Install and verify Ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &          # if not running as systemd service
ollama list             # confirm it responds

# Pull models (do this BEFORE the test — pulls are slow)
ollama pull llama3.1:8b
ollama pull mistral:7b
ollama pull qwen2.5:7b
ollama pull phi3:3.8b
ollama pull gemma2:2b
ollama pull deepseek-r1:8b       # reasoning (Llama-based distill, ~5 GB)
ollama pull deepseek-r1:7b       # reasoning (Qwen-based distill, ~4.7 GB)

# Verify GPU is visible
nvidia-smi
```

### Machine A (hub)

```bash
# Find LAN IP
ip addr show | grep 'inet 192'   # e.g. 192.168.1.10

# Start hub (open mode for LAN — no --admin)
moma hub up --host 0.0.0.0 --port 8000 --hub-url http://192.168.1.10:8000

# In another terminal, start agent on same machine
moma join http://192.168.1.10:8000
```

### Machines B and C (agents)

```bash
# Replace with Machine A's actual LAN IP
moma join http://192.168.1.10:8000
```

### Verify grid is up

```bash
# From any machine
moma status --hub-url http://192.168.1.10:8000
moma agents --hub-url http://192.168.1.10:8000
# Should show 3 agents, all ONLINE, tier BRONZE (until first pulse updates TPS)
```

---

## Ollama Models to Test

All models below fit comfortably in 11 GB VRAM at Q4_K_M quantization (Ollama default).

| Model | VRAM (approx) | Params | Why test it |
|-------|---------------|--------|-------------|
| `gemma2:2b` | ~2.5 GB | 2B | Smoke test — fastest, verify pipeline works |
| `phi3:3.8b` | ~3 GB | 3.8B | Small but capable, good for quick iteration |
| `qwen2.5:7b` | ~5 GB | 7B | Strong multilingual, good code |
| `mistral:7b` | ~5 GB | 7B | Reliable general-purpose baseline |
| `llama3.1:8b` | ~5.5 GB | 8B | Primary test model — best quality at this size |
| `deepseek-r1:8b` | ~5.2 GB | 8B | Reasoning model (Llama-based distill) — chain-of-thought |
| `deepseek-r1:7b` | ~4.7 GB | 7B | Reasoning model (Qwen-based distill) — compare with 8b |

### Models to avoid (won't fit in 11 GB)

- `llama3.1:70b` — needs ~40 GB
- `mixtral:8x7b` — needs ~26 GB
- `qwen2.5:14b` — ~10-12 GB, may partially offload to CPU (kills TPS)
- `codellama:34b` — needs ~20 GB

---

## Test Prompts

Prompts are in `prompts.json` in this directory. Categories:

### Phase 1: Smoke Test (single task, verify pipeline)

Submit one task at a time, confirm it completes end-to-end.

```bash
HUB=http://192.168.1.10:8000

# Simple Q&A
moma submit "What is the capital of France?" --model llama3.1:8b --hub-url $HUB

# Code generation
moma submit "Write a Python function to check if a number is prime." --model mistral:7b --hub-url $HUB

# Tiny model
moma submit "Say hello in five languages." --model gemma2:2b --hub-url $HUB
```

### Phase 2: Multi-Agent Dispatch (concurrent tasks)

Submit several tasks rapidly to verify dispatch across agents.

```bash
# Burst of 6 tasks — should spread across 3 agents (2 each with max_concurrent=3)
for i in $(seq 1 6); do
  moma submit "Write a short poem about the number $i." --model llama3.1:8b --hub-url $HUB --no-wait &
done
wait

# Check distribution
moma tasks --hub-url $HUB
```

### Phase 3: Model Variety

Test that dispatch respects model availability.

```bash
moma submit "Explain recursion simply." --model mistral:7b --hub-url $HUB
moma submit "What is photosynthesis?" --model qwen2.5:7b --hub-url $HUB
moma submit "Write fizzbuzz in Rust." --model phi3:3.8b --hub-url $HUB
```

### Phase 4: DeepSeek R1 Reasoning

Test chain-of-thought reasoning. R1 outputs `<think>...</think>` blocks before answering — expect longer latency and higher token counts than standard models.

```bash
# Classic trick questions
moma submit "A farmer has 17 sheep. All but 9 die. How many sheep are left? Think step by step." \
  --model deepseek-r1:8b --max-tokens 1024 --hub-url $HUB

moma submit "A bat and a ball cost \$1.10 in total. The bat costs \$1.00 more than the ball. How much does the ball cost? Show your work." \
  --model deepseek-r1:8b --max-tokens 512 --hub-url $HUB

# Math proof (long reasoning chain)
moma submit "Prove that the square root of 2 is irrational." \
  --model deepseek-r1:8b --max-tokens 2048 --hub-url $HUB

# Compare 7b vs 8b distill on same problem
moma submit "There are three boxes. One contains only apples, one contains only oranges, and one contains both. All boxes are labeled incorrectly. You can pick one fruit from one box. How do you determine what's in each box? Solve step by step." \
  --model deepseek-r1:7b --max-tokens 2048 --hub-url $HUB
```

**What to watch for:**
- R1 thinking tokens inflate `output_tokens` — TPS may look lower because the model is "thinking" longer
- Correct answers to trick questions (9 sheep, $0.05 ball, 5 minutes)
- `<think>` blocks in output content

### Phase 5: Stress & TPS Measurement

Longer outputs to measure sustained TPS.

```bash
moma submit "Write a detailed 500-word essay about the history of the Internet." \
  --model llama3.1:8b --max-tokens 2048 --hub-url $HUB

moma submit "Write a complete Python implementation of a linked list with insert, delete, search, and reverse methods. Include docstrings." \
  --model mistral:7b --max-tokens 2048 --hub-url $HUB
```

### Phase 6: Admin Mode (optional)

Test the new verification pipeline.

```bash
# Restart hub with --admin
moma hub up --host 0.0.0.0 --port 8000 --admin --hub-url http://192.168.1.10:8000

# Join from another machine — should see "Pending verification" in response
moma join http://192.168.1.10:8000

# Check pending list
moma hub pending --hub-url http://192.168.1.10:8000

# Manual approve if auto-approval didn't fire
moma hub approve <agent_id> --hub-url http://192.168.1.10:8000
```

---

## Hub Rotation & Results Export

Rotate which machine runs the hub, repeat the same test phases, then compare.

### Workflow per rotation

```bash
# ── Run 1: Hub on Machine A ──
# (run test phases 1-5 above)

# Review results
moma tasks --detail --hub-url $HUB --limit 50

# Export before shutting down
moma export --label "hub-machine-A" --hub-url $HUB
# → writes results-hub-machine-A.json

# ── Run 2: Hub on Machine B ──
# Stop hub on A, start hub on B, re-join agents
moma export --label "hub-machine-B" --hub-url http://192.168.1.20:8000
# → writes results-hub-machine-B.json

# ── Run 3: Hub on Machine C ──
moma export --label "hub-machine-C" --hub-url http://192.168.1.30:8000
# → writes results-hub-machine-C.json
```

### What the export contains

Each JSON file captures a full snapshot:
- `agents` — all agents with tier, TPS, GPU info
- `tasks` — every task with prompt, response, model, latency_ms, tokens, agent_id
- `rewards` — operator credit summary

### Comparing runs

```bash
# Quick comparison: average latency per hub rotation
python3 -c "
import json, sys
for f in sys.argv[1:]:
    data = json.load(open(f))
    completed = [t for t in data['tasks'] if t['state'] == 'COMPLETE']
    avg_lat = sum(t['latency_ms'] for t in completed) / len(completed) if completed else 0
    avg_tps = sum(t['output_tokens'] for t in completed) / (sum(t['latency_ms'] for t in completed) / 1000) if completed else 0
    print(f\"{data['label']:20s}  tasks={len(completed):3d}  avg_latency={avg_lat:.0f}ms  avg_tps={avg_tps:.1f}\")
" results-hub-machine-*.json
```

---

## What to Observe

| Metric | Where to check | Expected |
|--------|---------------|----------|
| Agents online | `moma agents` | 3 agents, all ONLINE |
| Tier assignment | `moma agents` | GOLD (30-60 TPS) after first pulse |
| Task dispatch spread | `moma tasks` | Tasks distributed across all 3 agents |
| TPS per agent | `moma agents` (current_tps column) | 35-45 TPS for 1080 Ti |
| Task completion | `moma submit ... --wait` | COMPLETE, non-empty content |
| Rate limiting | Submit 10+ tasks at once | Max 3 in-flight per agent |
| Reward ledger | `moma rewards` | Credits accumulate per operator |

---

## Known Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Ubuntu firewall blocks ports | Medium | `sudo ufw allow 8000/tcp && sudo ufw allow 8100/tcp` |
| Ollama not running / model not pulled | High | Pre-pull all models before test |
| Agent sends `host=127.0.0.1` to hub | Medium | Agent auto-detects LAN IP, but verify with `moma agents` |
| Admin mode: verification race | Low | Agent `/run` may not be ready when hub sends benchmark. Retry or use open mode. |
| Default config points to hub.momahub.org | Low | Always pass `--hub-url` explicitly for LAN |

---

## Quick Troubleshooting

```bash
# Agent not showing up?
curl http://192.168.1.10:8000/health       # hub alive?
curl http://192.168.1.20:8100/health       # agent alive? (if applicable)
ollama list                                 # models pulled?

# Task stuck in PENDING?
moma agents --hub-url $HUB                 # any agents ONLINE?
moma tasks --hub-url $HUB                  # check task state

# Check logs
moma logs --follow --hub-url $HUB
```
