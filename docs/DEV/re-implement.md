# Hub Re-implementation: Python → Go

**Date:** March 2026
**Decision:** Rewrite the hub server in Go

---

## Why Rewrite

The Python hub (FastAPI + aiosqlite) works, but has friction for deployment:

- `pip install` pulls ~30 transitive dependencies (FastAPI, uvicorn, pydantic, httpx, aiosqlite, ...)
- Python version compatibility issues (3.9+ required, venv management)
- ~30 MB memory footprint just for the interpreter
- No single binary — requires Python runtime on target machine

The hub is a lightweight network dispatcher (~500 lines). It doesn't do computation — the agents do (via Ollama, which is also written in Go). A Go rewrite gives us:

1. **Single binary** — `scp momahub user@server:~ && ./momahub` — done
2. **Zero dependencies** — no pip, no venv, no Python runtime
3. **Cross-compilation** — `GOOS=linux GOARCH=arm64 go build` for Oracle Cloud ARM
4. **Lower memory** — ~10 MB vs ~30 MB for Python
5. **Better concurrency** — goroutines are cheaper than Python async tasks
6. **Matches Ollama's stack** — agents talk to Ollama (Go); hub talks to agents; same ecosystem

## Why Go over Rust

| Factor | Go | Rust |
|--------|----|----|
| Hub workload | I/O bound (HTTP, SQLite, dispatch) | Same |
| Performance ceiling | More than enough | Higher, but irrelevant here |
| Development speed | Fast — port in a weekend | Slow — 3-5x longer |
| Deployment | Single binary | Single binary |
| SQLite | `modernc.org/sqlite` (pure Go, no CGO) | rusqlite (needs spawn_blocking for async) |
| Async model | Goroutines (natural, lightweight) | tokio (powerful but complex) |
| Learning curve | Gentle | Steep |
| Ecosystem fit | Ollama is Go; Kubernetes is Go | Different ecosystem |

The hub routes tasks between clients and GPU agents. An agent takes 1-30 seconds per inference. The hub spends microseconds routing. Rust's zero-cost abstractions don't matter when the bottleneck is GPU inference, not the dispatcher.

## What Changes

| Component | Python | Go |
|-----------|--------|----|
| Hub server | FastAPI + uvicorn | net/http + chi (or stdlib) |
| Database | aiosqlite | modernc.org/sqlite |
| JSON schemas | Pydantic models | Go structs + encoding/json |
| Task dispatch | asyncio.create_task | goroutines |
| SSE streaming | StreamingResponse | http.Flusher |
| CLI | Typer (Click) | cobra or stdlib flag |
| Config | PyYAML | gopkg.in/yaml.v3 |

## What Stays in Python

- **Agents** — they wrap Ollama's HTTP API. Python is fine here since the agent is a thin shim.
- **Streamlit dashboard** — Streamlit is Python-only. The dashboard talks to the hub via HTTP, so it doesn't care what language the hub is.
- **SPL integration** — SPL is a Python project. The SPL runner submits tasks via HTTP.
- **Test runner** — `tests/e2e/runner.py` submits tasks via HTTP. Language-agnostic.

The Go hub is a **drop-in replacement**: same HTTP API, same SQLite schema, same protocol. Everything that talks to the hub via HTTP (agents, CLI, dashboard, SPL) continues to work unchanged.

## Deployment Comparison

### Before (Python)

```bash
# On target server
sudo apt install python3-pip
pip install momahub
moma hub up --host 0.0.0.0 --port 8000
```

### After (Go)

```bash
# On build machine
GOOS=linux GOARCH=arm64 go build -o momahub ./cmd/hub

# On target server
scp momahub user@server:~
ssh user@server './momahub --host 0.0.0.0 --port 8000'
```

Or with GitHub releases: download a binary, run it. No install step.

---

## References

- Ollama source (Go): https://github.com/ollama/ollama
- chi router: https://github.com/go-chi/chi
- modernc.org/sqlite: https://pkg.go.dev/modernc.org/sqlite
