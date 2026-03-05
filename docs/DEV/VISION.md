# Vision: Accessible AI Through a distributed Inference Network

## The Thesis

Human language is the programming language of the AI era. The missing piece is the infrastructure to compile, optimise, and execute that language across distributed hardware — owned by anyone, anywhere.

We are building that infrastructure.

```
Human language (any language)
    → MoMa Compiler (understand, translate, optimise)
    → MoMaHub i-grid (distributed inference runtime)
    → Results back to human
```

Just as the internet made information accessible to anyone with a connection, MoMaHub makes AI inference accessible to anyone with a GPU. A home office, a university lab, a startup rack — all contribute to and benefit from the same grid.

---

## The Stack

```
┌─────────────────────────────────────────────────────────┐
│                    Human Intent                         │
│           (any language — English, Chinese,             │
│            Spanish, code, mixed)                        │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│               MoMa Compiler                             │
│                                                          │
│  ┌─────────────┐   ┌──────────────┐   ┌───────────────┐  │
│  │  Front-end  │   │   Mid-end    │   │   Back-end    │  │
│  │             │   │              │   │               │  │
│  │ - Detect    │   │ - CTE DAG    │   │ - Model/VRAM  │  │
│  │   language  │──►│   analysis   │──►│   mapping     │  │
│  │ - Translate │   │ - Dedup      │   │ - Chunk split │  │
│  │   to English│   │ - Prune      │   │ - Grid-aware  │  │
│  │ - NL → SPL  │   │ - Collapse   │   │   scheduling  │  │
│  │   (Text2SPL)│   │ - Batch      │   │ - Privacy     │  │
│  │             │   │ - Rewrite    │   │   envelope    │  │
│  └─────────────┘   └──────────────┘   └───────────────┘  │
│                                                          │
│  Powered by fine-tuned lightweight LLM (on the same grid) │
└──────────────────────┬───────────────────────────────────┘
                       │  Optimised, encrypted prompt chunks
                       ▼
┌─────────────────────────────────────────────────────────┐
│              MoMaHub i-grid Runtime                     │
│                                                         │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐             │
│  │  Hub A   │◄─►│  Hub B   │◄─►│  Hub C   │  ...        │
│  └────┬─────┘   └────┬─────┘   └────┬─────┘             │
│       │              │              │                   │
│  ┌────┴────┐    ┌────┴────┐    ┌────┴────┐              │
│  │ GPU GPU │    │ GPU GPU │    │ GPU GPU │   (anyone's) │
│  └─────────┘    └─────────┘    └─────────┘              │
│                                                         │
│  - Hub-and-spoke dispatch    - Proof of work            │
│  - Tier-based routing        - Reward economy           │
│  - Cluster forwarding        - Encrypted chunks         │
│  - Rate limiting / DoS       - Canary verification      │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│                  Human gets results                     │
│          (assembled, decrypted, in their language)      │
└─────────────────────────────────────────────────────────┘
```

---

## MoMa Compiler

The MoMa Compiler unifies Text2SPL and the SPL optimiser into a single LLM-powered component. It is itself a user of the i-grid — the compiler runs inference to compile inference.

### Pipeline

```
Input: "Analysiere diesen Vertrag auf Haftungsklauseln" (German)
                          │
                          ▼
            ┌─────────────────────────┐
            │  1. Language Detection  │  Detect: German
            └────────────┬────────────┘
                          ▼
            ┌─────────────────────────┐
            │  2. Translate to English │  "Analyse this contract
            │     (LLM call on grid)  │   for liability clauses"
            └────────────┬────────────┘
                          ▼
            ┌─────────────────────────┐
            │  3. NL → SPL            │  PROMPT analyse_contract
            │     (Text2SPL,          │  WITH reasoning AS (...)
            │      LLM call on grid)  │  WITH formatting AS (...)
            └────────────┬────────────┘
                          ▼
            ┌─────────────────────────┐
            │  4. Optimisation Passes  │  - Dedup shared system prompts
            │     (deterministic +     │  - Prune unreachable CTEs
            │      LLM-assisted)       │  - Collapse single-dep chains
            │                          │  - Batch independent CTEs
            │                          │  - Rewrite verbose prompts
            └────────────┬────────────┘
                          ▼
            ┌─────────────────────────┐
            │  5. Grid-Aware Backend   │  - Map CTEs to model/VRAM
            │                          │  - Split for privacy chunks
            │                          │  - Schedule across hubs
            └────────────┬────────────┘
                          ▼
              Optimised prompt chunks → i-grid dispatch
```

### Self-Hosting Property

The MoMa Compiler is powered by a fine-tuned lightweight model specialised for language detection, translation, and NL→SPL transformation. We are exploring Liquid AI's LFM (Liquid Foundation Models) for this purpose — their compact architecture is designed for efficient inference on edge hardware, making the compiler runnable even on modest consumer devices. The compiler's own inference calls run on the i-grid, making it a client of the runtime it compiles for. This is analogous to a self-hosting compiler in traditional CS — a C compiler written in C.

This means the system bootstraps: a minimal grid with one GPU can compile and run simple tasks. As more GPUs join, the compiler can handle more complex multi-CTE programs, which utilise the larger grid, which attracts more GPUs.

### Compiler Passes (Detail)

| Pass | Type | What It Does |
|------|------|--------------|
| Language detection | LLM or heuristic | Identify input language, confidence score |
| Translation | LLM | Non-English → English (preserves domain terms) |
| NL → SPL | LLM (Text2SPL) | English intent → SPL syntax with CTEs |
| CTE deduplication | Deterministic | Merge CTEs with identical system + prompt |
| Dead CTE elimination | Deterministic | Remove CTEs whose output is never referenced |
| Chain collapsing | Deterministic | A→B single-dep chain → one merged CTE |
| Prompt batching | Deterministic | Group independent CTEs for parallel dispatch |
| Prompt rewriting | LLM | Shorten verbose system prompts to save tokens |
| Privacy chunking | Deterministic | Split sensitive content across agents |
| Model/VRAM mapping | Grid-aware | Assign CTEs to optimal model + node tier |

Deterministic passes are fast and free. LLM-assisted passes cost tokens but produce better output. The compiler can be configured to skip LLM passes for cost-sensitive workloads.

---

## MoMaHub as Inference Runtime

### The OpenRouter Comparison

| | OpenRouter | MoMaHub i-grid |
|---|---|---|
| What it is | API routing proxy | Distributed inference runtime |
| Hardware | Cloud provider GPUs | Anyone's GPUs |
| Models | Whatever providers offer | Whatever the grid has |
| Execution | Delegates to provider API | Owns the execution |
| Scheduling | Round-robin / cost-based | Tier/VRAM/model-aware dispatch |
| Privacy | Provider sees everything | Chunk obfuscation, no single agent sees full prompt |
| Proof of work | Trust the provider | Canary tokens + encrypted chunks |
| Economy | Pay per token to providers | Reward economy — GPU owners earn credits |
| Lock-in | Depends on cloud providers | Self-hosted, federated, open participation |
| Compiler | None — raw API calls | MoMa Compiler: NL → optimised prompt chunks |

OpenRouter solves "which API do I call?" MoMaHub solves "how do I run AI across distributed hardware?"

### Runtime Analogy

```
Traditional computing:
  Source code → Compiler (gcc) → Machine code → OS runtime → CPU

AI computing:
  Human intent → MoMa Compiler → Optimised prompts → MoMaHub runtime → GPUs
```

MoMaHub is to LLM inference what the JVM is to Java bytecode, what the Linux kernel is to system calls — the runtime layer that abstracts physical hardware into a programmable compute surface.

---

## Encrypted Prompt Chunking

### The Privacy Problem

In a distributed grid, agents see the full prompt text. Sensitive work — legal documents, medical records, proprietary code — cannot be sent to untrusted nodes in plaintext.

### The Solution

Use SPL's CTE structure as natural chunk boundaries. Distribute chunks across multiple agents so no single agent sees the full context. Encrypt the transport layer between hub and agent.

```
Original: "Review this contract for liability clauses: [full document]"

Chunk 1 → Agent A: "Identify legal terms in: [paragraph 1-3]"
Chunk 2 → Agent B: "Identify legal terms in: [paragraph 4-6]"
Chunk 3 → Agent C: "Identify legal terms in: [paragraph 7-9]"

Hub reassembles → final analysis (only hub sees the full picture)
```

### Simplified Proof of Work

| Current Approach | Encrypted Chunk Approach |
|------------------|--------------------------|
| Hub sends benchmark tasks to verify agents | Every real task *is* proof of work |
| Hub heuristically checks if results are "reasonable" | Hub validates against known chunk semantics |
| Agents can game benchmarks (cache answers) | Agents can't game what they can't read |
| Complex sampling + verification pipeline | Embed canary tokens — wrong answer = provably cheating |

### Key Management

```
Hub startup → Generate RSA-4096 key pair
Per-task    → AES-256 session key (envelope-encrypted with RSA)
Agent sees  → Opaque ciphertext, decrypted only in sandboxed execution
```

### Roadmap

1. **Now**: Chunk obfuscation via CTE splits (no crypto infra needed)
2. **Next**: Canary token injection for lightweight proof of work
3. **Future**: TEE/SGX enclaves for full hardware-enforced privacy

---

## Open Participation Model

### Who Participates

| Role | Who | What They Do |
|------|-----|--------------|
| **User** | Anyone who can type | Writes intent in any language |
| **GPU Provider** | Gamer, researcher, startup, university | Runs `moma join` — their GPU earns rewards |
| **Hub Operator** | Organisation, company, university | Runs `moma hub up` — coordinates a local grid |
| **Compiler Developer** | Open-source contributor | Improves MoMa Compiler passes |

Like the internet, participation is open. A university in Nairobi can run a hub. A researcher in Berlin can write SPL scripts. A gamer in Seoul can contribute their RTX 4090. The barrier to entry is a GPU and an internet connection.

### Network Effect

```
More GPU providers join
    → More compute available
    → MoMa Compiler can handle bigger tasks
    → More users find value
    → More demand for compute
    → More GPU providers incentivised to join
    → ...
```

The same network effect that grew the internet: each new participant makes the network more valuable for everyone.

### Privacy Enables Enterprise

The encrypted chunk model unlocks enterprise adoption:

- A hospital can run medical NLP on the public grid — no agent sees full patient records
- A law firm can analyse contracts — no agent reconstructs the full document
- A government agency can process sensitive queries — chunks are meaningless in isolation

Privacy enables enterprise adoption. Enterprise adoption brings more compute to the grid. More compute attracts more users. The cycle continues.

---

## Why a Physicist

Distributed systems are physics problems:

- **Partition tolerance** is a conservation law — you cannot have consistency and availability simultaneously, just as you cannot measure position and momentum simultaneously (Heisenberg)
- **Consensus** is statistical mechanics — enough nodes must agree for the system state to be "real," just as macroscopic thermodynamic properties emerge from microscopic particle agreement
- **Task dispatch** is optimisation under constraints — minimise latency subject to VRAM, tier, and locality, the same class of problem as Lagrangian mechanics
- **The reward economy** is an equilibrium system — supply (GPU providers) and demand (users) reach a steady state through price signals (credits per token)
- **The MoMa Compiler** is a Hamiltonian optimiser — finding the lowest-energy (most efficient) prompt execution path through the CTE DAG

The rigor transfers. The intuition transfers. And the audacity to think you can model a complex system with a few clean equations — that transfers too.

---

## Milestones

| Phase | Milestone | Status |
|-------|-----------|--------|
| 1 | Hub + Agent + CLI (single hub, LAN) | Done |
| 2 | Cluster (multi-hub, task forwarding) | Done |
| 3 | SSE pull mode (WAN-safe agents) | Done |
| 4 | Admin mode (agent verification) | Done |
| 5 | DoS protection (rate limit, watchlist) | Done |
| 6 | SPL integration (`moma run`, IGridAdapter) | Done |
| 7 | MoMa Compiler (unified Text2SPL + optimiser) | Planned |
| 8 | Encrypted prompt chunking (privacy layer) | Planned |
| 9 | Reward economy (credits, redemption) | Planned |
| 10 | Public grid (multi-org, federated hubs) | Planned |

---

*"The best way to predict the future is to invent it." — Alan Kay*

*We are building the infrastructure that makes AI accessible to everyone.*
