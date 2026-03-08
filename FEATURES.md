# Momahub Features & Roadmap

## Current Features (v0.2.4)
- **Hub-and-spoke dispatch** — automatic agent selection by compute tier, VRAM, and model availability.
- **Multi-hub clustering** — peer hubs share capabilities and forward tasks across the network.
- **Compute tiers** — agents ranked PLATINUM / GOLD / SILVER / BRONZE by measured tokens-per-second.
- **Reward ledger** — tracks operator contributions (tasks completed, tokens generated, credits earned).
- **SPL integration** — run structured prompt programs on the grid with `ON GRID` syntax.
- **Hybrid Communication** — supports both HTTP Push and SSE Pull modes for firewall traversal.

## Roadmap & Planned Features

### 1. Re-implementation in Go (Momahub-Go)
To enhance performance, concurrency, and distribution of the hub and agent binaries, Momahub will be re-implemented in Go. This will allow for:
- Single-binary distribution (no Python dependency for nodes).
- Improved memory efficiency and faster dispatching loops.
- Native multi-platform support.

### 2. Security & Identity
To ensure reward integrity and secure communication in public/adversarial grids:
- **Private-Public Key Encryption (Ed25519)**: Agents will sign handshake requests to prove identity, preventing reward spoofing.
- **Task Payload Encryption**: End-to-end encryption between hubs and agents to protect prompt privacy.
- **Verified Rewards**: Cryptographic proof of work linked to node identities in the reward ledger.

### 3. Performance & Scalability
- **Denormalized Dispatching**: Optimize agent selection by maintaining real-time active task counters in memory/database, reducing complexity from $O(N)$ to $O(1)$ per dispatch.
- **Reactive Task Forwarding**: Replace the current polling mechanism with a webhook/SSE notification system for near-instant multi-hub task completion.
- **PostgreSQL Support**: Add an optional backend for large-scale deployments to handle high-concurrency write scenarios beyond SQLite's limits.

### 4. Resilience & Telemetry
- **Agent-side Execution Timeouts**: Implement explicit `asyncio.wait_for` logic to ensure agents remain responsive even if the local LLM backend stalls.
- **Advanced Grid Metrics**: Enhance the dashboard with queue wait times, VRAM fragmentation tracking, and per-model performance heatmaps.
- **Automated Benchmarking**: Periodically re-evaluate agent TPS tiers to account for hardware thermal throttling or background load.
