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

| # | Recipe | Script | Description | Status |
|---|--------|--------|-------------|--------|
| 01 | Single Node Hello | `hello.spl` | Minimal SPL program — verify hub + agent + Ollama work | x |
| 02 | Multi-CTE Parallel | `multi_cte.spl` | Two models in parallel, then synthesis — fan-out demo | x |
| 03 | Batch Translate | `translate.py` | One text to 5 languages in parallel | x |
| 04 | Benchmark Models | `benchmark.py` | Same prompt to multiple models, compare TPS and latency | - |
| 05 | RAG on Grid | `rag_query.spl` | Retrieval-augmented generation dispatched to the grid | x |
| 06 | Paper Digest | `digest.py` | Arxiv papers to dark-mode HTML digest overnight | - |
| 07 | Stress Test | `stress.py` | Fire N tasks, watch all GPUs light up, measure throughput | - |
| 08 | Model Arena | `arena.py` | Side-by-side HTML comparison of multiple models | x |
| 09 | Doc Pipeline | `pipeline.py` | PDF -> extract -> grid summarize -> formatted output | - |
| 10 | Chain Relay | `chain.py` | Multi-step reasoning: Research -> Analyze -> Summarize | x | - |
| 12 | Tier-Aware Dispatch | `tier_dispatch.py` | Submit tasks with VRAM hints, verify routing to correct agent tier | - |
| 13 | Multi-Agent Throughput | `throughput.py` | Measure tokens/s scaling: 1 agent vs 2 vs 3 — key paper metric | - |
| 15 | Agent Failover | `failover.py` | Kill an agent mid-run, verify tasks re-queue and complete | - |
| 16 | Math Olympiad | `math_olympiad.py` | Benchmark mathstral + qwen2-math on 15 problems, score accuracy | - |
| 17 | Code Review Pipeline | `code_review.py` | review → summarise → refactor across deepseek-coder + llama3 | - |
| 18 | Smart Router | `smart_router.py` | Auto-route math/code/general prompts to the optimal model | - |
| 19 | Privacy Chunk Demo | `privacy_demo.py` | Split document across agents — no single agent sees the full text | - |
| 20 | Overnight Batch | `overnight.py` | Submit 100–500 tasks overnight, full report by morning | - |
| 21 | Language Accessibility | `language_grid.py` | Same question in 10 languages in parallel — accessibility demo | - |
| 22 | Rewards Report | `rewards_report.py` | Pretty-print reward ledger: tasks, tokens, credits per operator | x | - |
| 23 | Wake/Sleep Resilience | `resilience.py` | Tasks flow continuously as agents join/leave dynamically | - |
| 24 | SPL Compiler Pipeline | `compiler_demo.py` | 5-step: translate → concepts → optimise → generate → format | - |
| 25 | Model Diversity | `model_diversity.py` | All 14 models benchmarked on 6 domains — latency, TPS, quality | - |
| 90 | Two-Hub Cluster | `setup.py` | Set up and test hub peering and task forwarding | - |

## Quick start

```bash
# Smoke test
moma run cookbook/01_single_node_hello/hello.spl

=== hello_grid ===
The i-grid is a novel distributed inference network that enables efficient and scalable machine learning tasks by partitioning a large neural network into smaller, interconnected sub-networks, each running on different devices or nodes within a grid-like structure. By leveraging this decentralized approach, the i-grid allows for massive parallelization of computations, reduced communication overhead, and improved overall performance in complex inference scenarios.

[model=llama3  tokens=41+76  latency=4893ms]


moma run cookbook/02_multi_cte_parallel/multi_cte.spl

=== synthesis ===
Distributed LLM (Large Language Model) inference has both empowering and challenging aspects. On the one hand, it enables faster and more scalable processing of complex language tasks by leveraging multiple devices or machines, which can be particularly beneficial for large-scale applications and those requiring real-time responses. On the other hand, distributed LLM inference also introduces added complexity in terms of infrastructure setup, data synchronization, and potential latency issues that need to be carefully managed to ensure seamless performance.

[model=llama3  tokens=65+94  latency=18460ms]


# Translate in parallel
python cookbook/03_batch_translate/translate.py "Hello, world!"


  Batch Translate
    Hub:       http://localhost:8000
    Model:     llama3
    Languages: ['French', 'German', 'Chinese', 'Spanish']
    Text:      Hello, world!

    German          5 tok    2.1s  agent=..4f02c8a9e6cc
    Spanish         5 tok    2.1s  agent=..4f02c8a9e6cc
    Chinese        12 tok    2.1s  agent=..4f02c8a9e6cc
    French          5 tok    4.5s  agent=..4f02c8a9e6cc

  ==================================================
  4/4 translations complete  wall=4.6s

  [Chinese]
  nǐ hǎo, shìjiè!

  [French]
  Bonjour, monde !

  [German]
  Hallo, Welt!

  [Spanish]
  Hola, mundo!

  Report: translations_20260307_1316.html


# RAG on Grid
moma run cookbook/05_rag_on_grid/rag_query.spl

=== rag_answer ===
Based on general knowledge and understanding, I can tell you that the key benefits of hub-and-spoke inference are:

1. **Scalability**: Hub-and-spoke architecture allows for easy scaling by adding more nodes to the network, making it suitable for large-scale AI applications.
2. **Flexibility**: This approach enables the use of different machine learning models and algorithms for each spoke, allowing for flexibility in model selection and experimentation.
3. **Efficient computation**: By offloading computations to smaller, specialized machines (spokes), hub-and-spoke inference reduces the computational burden on the central node (hub), improving overall performance and efficiency.
4. **Improved latency**: With computations distributed across multiple nodes, hub-and-spoke inference can reduce processing times and improve response latency for real-time AI applications.

These benefits make hub-and-spoke inference a popular choice for many AI use cases, such as natural language processing, computer vision, and recommendation systems.

[model=llama3  tokens=59+192  latency=8279ms]



# Stress test (all GPUs)
python cookbook/07_stress_test/stress.py -n 20

# Model comparison
python cookbook/08_model_arena/arena.py

  Model Arena
    Hub:    http://localhost:8000
    Models: ['llama3', 'mistral', 'phi3']

    [llama3] submitting... 245 tok  45.36s  5.4 tps
    [mistral] submitting... 389 tok  12.51s  31.1 tps
    [phi3] submitting... 351 tok  25.72s  13.6 tps

  MODEL           STATE        TOKENS    LATENCY      TPS
  -------------------------------------------------------
  llama3          COMPLETE        245      45.4s     5.4
  mistral         COMPLETE        389      12.5s    31.1
  phi3            COMPLETE        351      25.7s    13.6

  Report: /home/papagame/projects/digital-duck/momahub.py/cookbook/08_model_arena/arena_20260307_2233.html
  Open in browser for dark-mode side-by-side comparison.


# Multi-step chain
python cookbook/10_chain_relay/chain.py "distributed AI inference"


  Chain Relay
    Topic:  distributed AI inference
    Hub:    http://localhost:8000
    Model:  llama3
    Steps:  Research -> Analyze -> Summarize

  [1/3] Research... 674 tok  18.2s  agent=..4f02c8a9e6cc
  [2/3] Analyze... 560 tok  18.2s  agent=..4f02c8a9e6cc
  [3/3] Summarize... 234 tok  8.1s  agent=..4f02c8a9e6cc

  ============================================================
  Chain complete!
    Total tokens: 1,468
    Total latency: 32908ms
    Agents used: 1 (4f02c8a9e6cc)

  --- Final Summary ---

**Executive Summary:**

Distributed AI inference has emerged as a crucial technology for modern AI development, offering scalability, speed, and flexibility. As the trend continues to grow, it's essential to understand its strengths, weaknesses, opportunities, and risks.

**Key Takeaways:**

• Distributed AI inference enables real-time processing of large datasets, making it suitable for complex AI tasks.
• Scalability challenges and communication overhead are critical considerations in deploying distributed AI inference, requiring careful optimization.
• The integration of edge computing and quantum computing with distributed AI inference has the potential to revolutionize AI applications.

**Recommended Next Steps:**

1. Conduct a thorough analysis of your organization's current infrastructure and data processing needs to determine the feasibility of implementing distributed AI inference.
2. Develop a plan for optimizing communication between devices and ensuring scalability as you scale up your distributed AI inference architecture.
3. Explore opportunities to integrate edge computing and quantum computing with your distributed AI inference implementation.

**One-Sentence Bottom Line:**

To fully unlock the potential of distributed AI inference, organizations must carefully balance scalability challenges, communication overhead, and optimization strategies while exploring innovative applications in edge computing and quantum computing.



# Tier-aware dispatch (VRAM routing)
python cookbook/12_tier_aware_dispatch/tier_dispatch.py

# Throughput scaling (run with 1, 2, 3 agents — compare results)
python cookbook/13_multi_agent_throughput/throughput.py --label "3-agents" --out scaling.json

# Failover test (kill an agent mid-run)
python cookbook/15_agent_failover/failover.py -n 30

# Math olympiad (accuracy + TPS comparison)
python cookbook/16_math_olympiad/math_olympiad.py --models mathstral,qwen2-math

# Code review pipeline (multi-step, multi-model)
python cookbook/17_code_review_pipeline/code_review.py --file igrid/hub/dispatcher.py

# Smart router (auto-route by prompt type)
python cookbook/18_smart_router/smart_router.py --demo

# Privacy chunk demo
python cookbook/19_privacy_chunk_demo/privacy_demo.py

# Overnight batch (100 tasks)
python cookbook/20_overnight_batch/overnight.py --tasks 100

# Language accessibility (10 languages in parallel)
python cookbook/21_language_accessibility/language_grid.py --topic ai

# Rewards report
python cookbook/22_rewards_report/rewards_report.py

(momahub) papagame@papa-game:~/projects/digital-duck/momahub.py$ python cookbook/22_rewards_report/rewards_report.py

  Reward Economy Report
    Hub:   http://localhost:8000
    Time:  2026-03-07 18:18:33

  ──────────────────────────────────────────────────
  GRID TOTALS
  ──────────────────────────────────────────────────
  Total tasks:            54
  Total tokens:        6,459
  Total credits:      6.4590
  Credit rate:    1 credit per 1,000 output tokens (PoC)

  ──────────────────────────────────────────────────
  BY OPERATOR
  ──────────────────────────────────────────────────
  Operator                Tasks       Tokens    Credits
  ----------------------------------------------------
  duck (GOLD)                54        6,459     6.4590

  ──────────────────────────────────────────────────
  BY MODEL (last 500 tasks)
  ──────────────────────────────────────────────────
  Model                        Tasks     Tokens    Avg Lat
  -------------------------------------------------------
  llama3                          44      4,132      3980ms
  qwen3                            4      1,782     69990ms
  mistral                          2        411      5707ms
  mathstral                        2        134     14670ms

  Note: Full reward economy (redemption, transfer, billing)
        coming in Phase 9. Credits are currently indicative.

  Report: /home/papagame/projects/digital-duck/momahub.py/cookbook/22_rewards_report/rewards_20260307_1818.html


# Wake/sleep resilience (5 minutes)
python cookbook/23_wake_sleep_resilience/resilience.py --duration 300

# MoMa Compiler pipeline demo
python cookbook/24_spl_compiler_pipeline/compiler_demo.py --demo

# Model diversity — quick probe (check which models are alive)
python cookbook/25_model_diversity/model_diversity.py --probe

# Model diversity — full 14-model benchmark
python cookbook/25_model_diversity/model_diversity.py --out results.json --report diversity.html

# Test only the 6 previously uncovered models
python cookbook/25_model_diversity/model_diversity.py \
  --models llama3.1,qwen3,deepseek-r1,gemma3,phi4,phi4-mini \
  --report new_models.html
```

## Demo

A guided demo script for presentations is available at:

```bash
python tests/demos/unc-chapel-hill/demo.py
```
