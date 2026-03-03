# Specification: i-grid (Inference Grid) - Project MoMa
**Version:** 0.1.0-PoC
**Objective:** Create a decentralized "Internet for Inference" using SPL (Structured Prompt Language) to distribute LLM tasks across autonomous Agents.

---
## 0. SPL - Structured Prompt Language

SPL is a SQL-like language for Declarative Context Management for LLMs, available at https://github.com/digital-duck/SPL

---

## 1. System Components

### A. The Coordinator (The "Hub")
The Coordinator is a lightweight, high-availability service that manages the "Marketplace of Inference."
- **Node Registry:** Maintains a real-time table of active Agents (ID, VRAM, Model List, Reputation).
- **SPL Parser:** Breaks incoming `.spl` files into discrete Logical Chunks (Packets) based on CTE blocks.
- **Task Dispatcher:** Matches Logical Chunks to Agents based on hardware capability and latency requirements.
- **Health Monitor:** Conducts "Heartbeat" checks and "Proof of Inference" (PoI) verification.

### B. The Agent (The "Node")
The Agent is the autonomous software running on participant hardware (e.g., GTX 1080 Ti, Mobile NPU).
- **Autonomy Engine:** Decides whether to accept a task based on local resource availability.
- **Inference Wrapper:** Interfaces with `Ollama` to execute tasks locally.
- **Secure Handshake:** Uses a `moma join` protocol to establish identity and capability with the Coordinator.
- **Wallet/Reward Tracker:** Records successfully completed tokens to calculate **moma rewards** (points).

---

## 2. The `moma` CLI Interface
The CLI must be the primary touchpoint for both developers and participants.

| Command | Description |
| :--- | :--- |
| `moma join <url>` | Perform handshake and benchmark local GPU/NPU. |
| `moma up` | Transition Agent to 'Ready' state to begin accepting tasks. |
| `moma down` | Transition Agent to 'Offline' state by signing off the grid. |
| `moma status` | View local health, active tasks, and reward points. |
| `moma reward` | View balance and redeem contribution points. |
| `moma run <file.spl>` | Submit an SPL script to the grid for coordination. |

---

## 3. Communication Protocol (Handshake & Health)

### Step 1: Handshake (`moma join`)
1. Agent sends `HandshakeRequest`: `{node_id, gpu_model, vram_total, ollama_version, available_models[]}`.
2. Coordinator responds with `HandshakeAck` and assigns a `SessionToken`.

### Step 2: Health Check (The "Pulse")
- **Frequency:** Every 30 seconds.
- **Payload:** `{status: "idle/busy", vram_free: "4GB", temp: "65C"}`.
- **Timeout:** If no pulse for 90s, Coordinator marks Agent as 'Offline' and reroutes pending tasks.

---

## 4. Logical Chunking Workflow
1. **Input:** User submits an SPL query with multiple CTEs.
2. **Decomposition:** Coordinator identifies `CTE_1` (Reasoning) and `CTE_2` (Formatting).
3. **Dispatch:** - `CTE_1` -> Sent to Agent A (High VRAM / GPU).
   - `CTE_2` -> Sent to Agent B (Mobile Phone / NPU).
4. **Assembly:** Coordinator collects results and returns the final response to the User.

---

## 5. Success Metrics for PoC
- Successful registration of two 1080 Ti Agents to one Coordinator.
- Distribution of a single SPL script into two parallel tasks across both GPUs.
- Accurate calculation of **reward points** displayed in `moma status`.
