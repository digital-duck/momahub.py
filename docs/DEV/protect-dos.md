# DoS Protection — Rate Limiting, Prompt Size Caps & Flood Detection

## Problem

MoMaHub had **no protection** against denial-of-service attacks:

- **Agent -> Hub**: Unlimited tasks with unbounded prompt sizes could flood the task queue and SQLite database.
- **Hub -> Agent**: No enforcement on the agent side for concurrent task limits.
- **No flood detection**: No mechanism to detect, suspend, or block malicious actors.

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Default 50K chars, hard ceiling 200K | arxiv papers run ~12K-40K chars; 50K covers all legitimate use; Pydantic 200K hard ceiling catches bugs |
| 60 req/min sustained, 200/10s burst | 1 req/s easily handles overnight digest batches; 200 in 10s is clearly malicious |
| 24h auto-expire on suspension | Prevents permanent lockout from transient issues; admin can make permanent via CLI |
| In-memory rate limiter (no Redis) | Zero deps; hub is single-process; state resets on restart which is acceptable |
| Agent semaphore default 3 | Matches hub's `max_concurrent_tasks=3` default; prevents GPU OOM |

## Implementation

### Part 1: Schema Validators (Pydantic Field Limits)

**`igrid/schema/task.py`** — `Field()` bounds on all `TaskRequest` fields:

- `prompt`: max 200K chars (hard ceiling)
- `system`: max 100K chars
- `max_tokens`: 1–32,768
- `temperature`: 0.0–2.0
- `timeout_s`: 10–3,600
- `priority`: 0–100
- `task_id`, `model`: max 256 chars

**`igrid/schema/handshake.py`** — `Field()` bounds on all `JoinRequest` fields:

- `port`: 1–65,535
- `gpus`: max 32 entries
- `supported_models`, `cached_models`: max 200 entries
- `cpu_cores`: 0–4,096; `ram_gb`: 0–65,536
- String fields: max 256–512 chars

### Part 2: Hub-Side Rate Limiter

**`igrid/hub/rate_limit.py`** — New file (~60 lines). Sliding-window rate limiter using `collections.deque` of timestamps per key.

```python
class RateLimiter:
    def __init__(self, max_requests=60, window_s=60,
                 burst_threshold=200, burst_window_s=10): ...

    def check(self, key: str) -> tuple[bool, bool]:
        """Returns (allowed, is_flood)."""

    def reset(self, key: str) -> None:
        """Clear state for a key (e.g. after manual unblock)."""

    def cleanup(self) -> int:
        """Remove stale keys."""
```

- **Sustained rate**: prune entries older than `window_s`, check `len(dq) <= max_requests`
- **Burst/flood**: count entries in last `burst_window_s`, flag if `>= burst_threshold`

### Part 3: Watchlist & Flood Detection

**`igrid/hub/hub_ddl.sql`** — New `watchlist` table:

```sql
CREATE TABLE IF NOT EXISTS watchlist (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,  -- 'operator' or 'agent' or 'ip'
    entity_id   TEXT NOT NULL,
    reason      TEXT NOT NULL DEFAULT '',
    action      TEXT NOT NULL DEFAULT 'SUSPENDED',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at  TEXT,  -- NULL = permanent
    UNIQUE(entity_type, entity_id)
);
```

**`igrid/hub/state.py`** — CRUD methods:

- `add_to_watchlist(entity_type, entity_id, reason, action, expires_hours)`
- `is_watchlisted(entity_type, entity_id)` — checks expiry
- `remove_from_watchlist(entity_type, entity_id)`
- `list_watchlist()` — active entries only
- `pending_task_count()` — for queue depth checks

### Part 4: Hub App Wiring

**`igrid/hub/app.py`** — `create_app()` gains new parameters (all with defaults):

```python
def create_app(...,
    max_prompt_chars: int = 50_000,
    max_queue_depth: int = 1000,
    rate_limit: int = 60,
    burst_threshold: int = 200,
) -> FastAPI:
```

Protection applied in endpoints:

| Endpoint | Checks |
|----------|--------|
| `POST /tasks` | Watchlist -> Rate limit -> Flood auto-suspend -> Prompt size (413) -> Queue depth (503) |
| `POST /join` | Watchlist -> Rate limit -> Flood auto-suspend |
| `POST /pulse` | No rate limit (telemetry is expected to be frequent) |

New endpoints:

- `GET /watchlist` — list active watchlist entries
- `DELETE /watchlist/{entity_id}` — unblock (tries all entity types)

Flood auto-suspension flow:

```
rate_limiter.check(ip) returns is_flood=True
  -> add_to_watchlist("ip", ip, reason, expires_hours=24)
  -> rate_limiter.reset(ip)
  -> HTTP 429 "Suspended for flood. Contact admin."
```

**Bonus fix**: Replaced `Annotated[GridState, Depends(get_state)]` type aliases with `= Depends()` default values, fixing a pre-existing bug where all hub API tests (9 tests) failed on Python 3.9 due to `from __future__ import annotations` making the local `GridDep` type alias an unresolvable string.

### Part 5: Agent-Side Protection

**`igrid/agent/worker.py`**:

- `asyncio.Semaphore(max_concurrent=3)` guards `/run` endpoint
- Returns `TaskResult(state=FAILED, error="Agent at capacity")` when semaphore is locked
- Prompt size check before calling `backend.generate()`

**`igrid/agent/sse_consumer.py`**:

- Semaphore passed into `_handle_task()` to bound concurrent SSE-dispatched inference

### Part 6: CLI Knobs

**`igrid/cli/main.py`** — `moma hub up` gains:

```
--max-prompt-chars  50000   Max prompt size in chars (hard ceiling: 200K)
--max-queue-depth   1000    Max pending tasks in queue
--rate-limit        60      Max requests per minute per IP
--burst-threshold   200     Flood detection: requests in 10s
```

New commands:

- `moma watchlist` — show watchlist entries
- `moma unblock <entity_id>` — remove from watchlist

## Files Changed

| File | Change |
|------|--------|
| `igrid/schema/task.py` | `Field()` bounds on all TaskRequest fields |
| `igrid/schema/handshake.py` | `Field()` bounds on all JoinRequest fields |
| `igrid/hub/rate_limit.py` | **New** — sliding-window rate limiter + flood detector |
| `igrid/hub/hub_ddl.sql` | Added `watchlist` table |
| `igrid/hub/state.py` | Watchlist CRUD + `pending_task_count()` |
| `igrid/hub/app.py` | Rate limiter, prompt/queue checks, watchlist endpoints, flood auto-suspend, `Annotated` -> `Depends()` fix |
| `igrid/agent/worker.py` | Concurrency semaphore + prompt size check |
| `igrid/agent/sse_consumer.py` | Semaphore for concurrent SSE tasks |
| `igrid/cli/main.py` | DoS CLI knobs + `watchlist`/`unblock` commands |
| `tests/unit/test_hub_api.py` | Fixed lifespan in test fixture |

## Verification

```bash
# Schema validation (hard ceiling)
python -c "from igrid.schema.task import TaskRequest; TaskRequest(model='m', prompt='x'*200_001)"
# -> ValidationError

# Run all unit tests (30 pass)
pytest tests/unit/ -v -p no:spark

# Start hub with custom limits
moma hub up --rate-limit 30 --burst-threshold 100 --max-prompt-chars 100000 --max-queue-depth 500

# Watchlist management
moma watchlist
moma unblock 192.168.1.50
```
