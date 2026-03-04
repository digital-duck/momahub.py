# Cookbook

Ready-to-run recipes demonstrating MoMaHub i-grid capabilities. Each recipe is self-contained.

## Prerequisites

```bash
pip install -e ".[dev]"          # install momahub
ollama pull llama3               # at least one model
moma hub up --host 0.0.0.0      # start hub
moma join http://<hub-ip>:8000   # start agent(s)
```

## Recipes

| # | Recipe | Script | Description |
|---|--------|--------|-------------|
| 01 | Single Node Hello | `hello.spl` | Minimal SPL program — verify hub + agent + Ollama work |
| 02 | Multi-CTE Parallel | `multi_cte.spl` | Two models in parallel, then synthesis — fan-out demo |
| 03 | Two-Hub Cluster | `setup.py` | Set up and test hub peering and task forwarding |
| 04 | Benchmark Models | `benchmark.py` | Same prompt to multiple models, compare TPS and latency |
| 05 | RAG on Grid | `rag_query.spl` | Retrieval-augmented generation dispatched to the grid |
| 06 | Paper Digest | `digest.py` | Arxiv papers to dark-mode HTML digest overnight |
| 07 | Stress Test | `stress.py` | Fire N tasks, watch all GPUs light up, measure throughput |
| 08 | Model Arena | `arena.py` | Side-by-side HTML comparison of multiple models |
| 09 | Doc Pipeline | `pipeline.py` | PDF -> extract -> grid summarize -> formatted output |
| 10 | Chain Relay | `chain.py` | Multi-step reasoning: Research -> Analyze -> Summarize |
| 11 | Batch Translate | `translate.py` | One text to 5 languages in parallel |

## Quick start

```bash
# Smoke test
moma run cookbook/01_single_node_hello/hello.spl

# Stress test (all GPUs)
python cookbook/07_stress_test/stress.py -n 20

# Model comparison
python cookbook/08_model_arena/arena.py

# Multi-step chain
python cookbook/10_chain_relay/chain.py "distributed AI inference"

# Translate in parallel
python cookbook/11_batch_translate/translate.py "Hello, world!"
```

## Demo

A guided demo script for presentations is available at:

```bash
python tests/demos/unc-chapel-hill/demo.py
```
