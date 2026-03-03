# E2E Test Runner

End-to-end test runner for i-grid. Submits real prompts to a live hub and collects results (prompt, response, latency, tokens, TPS, agent assignment).

Works from both **CLI** (`moma test`) and **Streamlit UI** (Test Runner page).

---

## Quick Start

```bash
# Set hub URL (or pass --hub-url each time)
HUB=http://192.168.1.10:8000

# List available test categories
moma test --list

# Run smoke test (3 prompts, sequential)
moma test -c smoke_test --hub-url $HUB

# Run everything
moma test --hub-url $HUB
```

---

## CLI Reference

```
moma test [OPTIONS]

Options:
  --hub-url          Hub URL (default: from ~/.igrid/config.yaml)
  -p, --prompts      Path to prompts JSON (default: tests/lan/prompts.json)
  -c, --category     Run only this category (default: all)
  -j, --concurrency  Parallel task submissions (default: 1)
  -r, --repeat       Repeat entire batch N times (default: 1)
  --timeout          Per-task timeout in seconds (default: 300)
  -l, --label        Label for this test run
  -o, --output       Save results to JSON file
  --list             List available categories and exit
```

---

## Test Categories

| Category | Prompts | Purpose |
|----------|---------|---------|
| `smoke_test` | 3 | Single tasks, verify pipeline end-to-end |
| `multi_agent_dispatch` | 6 | Burst of identical-model tasks, verify spread across agents |
| `model_variety` | 4 | Different models per task, verify model routing |
| `stress_long_output` | 3 | Long generation (2048 tokens), measure sustained TPS |
| `reasoning_deepseek_r1` | 6 | Chain-of-thought reasoning with DeepSeek R1 distills |
| `edge_cases` | 3 | Empty prompt, minimal output, predictable output |

Prompts are defined in `tests/lan/prompts.json`. Add your own or pass `--prompts custom.json`.

---

## Usage Examples

### Sequential smoke test

```bash
moma test -c smoke_test --hub-url $HUB
```

Output:
```
Running 3 tasks  concurrency=1  repeat=1  hub=http://192.168.1.10:8000

  [  1/  3] OK       gemma2:2b                  342ms     28 tok     81.9 tps  agent-abc123
  [  2/  3] OK       llama3.1:8b               1205ms    156 tok    129.5 tps  agent-def456
  [  3/  3] OK       mistral:7b                 980ms    112 tok    114.3 tps  agent-abc123

────────────────────────────────────────────────────────────────────────
  Total:     3  |  Completed: 3  |  Failed: 0  |  Timeout: 0
  Avg latency: 842ms  |  Avg TPS: 108.6  |  Wall time: 3.2s
  Agent distribution:
    agent-abc123: 2 tasks
    agent-def456: 1 tasks
```

### Stress test — concurrent burst

```bash
# 6 prompts x 10 repeats x 5 parallel = 60 tasks
moma test -c multi_agent_dispatch -j 5 -r 10 --hub-url $HUB
```

### Full suite with results export

```bash
moma test -j 3 -l "hub-machine-A" -o test-machine-A.json --hub-url $HUB
```

### Hub rotation comparison

Run the same test suite with the hub on each machine, export results, then compare:

```bash
# Machine A as hub
moma test -j 3 -l "hub-A" -o test-hub-A.json --hub-url http://192.168.1.10:8000

# Machine B as hub
moma test -j 3 -l "hub-B" -o test-hub-B.json --hub-url http://192.168.1.20:8000

# Machine C as hub
moma test -j 3 -l "hub-C" -o test-hub-C.json --hub-url http://192.168.1.30:8000

# Compare
python3 -c "
import json, sys
for f in sys.argv[1:]:
    d = json.load(open(f))
    s = d['summary']
    print(f\"{d['label']:15s}  completed={s['completed']:3d}  avg_lat={s['avg_latency_ms']:.0f}ms  avg_tps={s['avg_tps']:.1f}  wall={s['wall_time_s']:.1f}s\")
" test-hub-*.json


● See you — good luck with the LAN weekend test! The key commands when you're ready:

  moma test --list                          # see categories
  moma test -c smoke_test --hub-url $HUB    # quick sanity check
  moma test -j 3 -r 5 -o results.json      # stress test

  Don't forget to ollama pull all the models on each machine before starting. Have fun!
```

---

## Streamlit UI

The Test Runner page (`moma-ui` > Test Runner) provides:

- **Single Prompt** tab — pick a model from the grid, submit, see response with metrics
- **Batch / Stress Test** tab — select categories, set concurrency and repeat count, run with live progress bar, view summary with agent distribution chart, download results JSON
- **Results** tab — upload multiple result JSON files to compare runs side-by-side (avg latency, TPS, per-model breakdown)

```bash
# Launch dashboard
IGRID_HUB_URL=http://192.168.1.10:8000 moma-ui
```

---

## Results JSON Format

Output from `moma test -o results.json`:

```json
{
  "label": "hub-machine-A",
  "hub_url": "http://192.168.1.10:8000",
  "summary": {
    "total": 25,
    "completed": 24,
    "failed": 1,
    "timed_out": 0,
    "total_tokens": 3842,
    "avg_latency_ms": 1250.3,
    "avg_tps": 38.2,
    "wall_time_s": 45.6,
    "agents_used": 3,
    "models_used": ["gemma2:2b", "llama3.1:8b", "mistral:7b"],
    "agent_distribution": {
      "agent-abc": 9,
      "agent-def": 8,
      "agent-ghi": 7
    }
  },
  "results": [
    {
      "task_id": "...",
      "category": "smoke_test",
      "prompt": "What is the capital of France?",
      "model": "gemma2:2b",
      "state": "COMPLETE",
      "content": "The capital of France is Paris.",
      "input_tokens": 12,
      "output_tokens": 8,
      "latency_ms": 342.0,
      "agent_id": "agent-abc",
      "wall_time_ms": 1520.3,
      "tps": 23.4
    }
  ]
}
```

---

## Files

| File | Purpose |
|------|---------|
| `tests/e2e/runner.py` | Core test runner (used by CLI and Streamlit) |
| `tests/lan/prompts.json` | Test prompt suite (25 prompts, 6 categories) |
| `tests/lan/README.md` | LAN weekend test plan with full setup instructions |
| `igrid/ui/streamlit/pages/6_Chat.py` | Streamlit Test Runner page |
