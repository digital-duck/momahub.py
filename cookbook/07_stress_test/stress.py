#!/usr/bin/env python3
"""Recipe 07: Stress Test -- fire N tasks rapidly, watch them fan out.

Demonstrates dispatcher load balancing across all agents on the grid.
Great for the LAN weekend: see all 3 GPUs light up simultaneously.

Usage:
    python stress.py                          # 20 tasks, default settings
    python stress.py -n 50 --model mistral    # 50 tasks with mistral
    python stress.py -n 10 --hub http://192.168.1.10:8000

Tip: run 'moma agents' in another terminal to watch agent status live.
     run 'moma logs -f' to watch pulse logs in real time.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime

import click
import httpx

PROMPTS = [
    "Explain Newton's first law in two sentences.",
    "What is the difference between TCP and UDP?",
    "Write a haiku about distributed computing.",
    "Summarize the concept of entropy in physics.",
    "What is a hash table and why is it fast?",
    "Explain the double-slit experiment simply.",
    "What is gradient descent in machine learning?",
    "Describe the CAP theorem in distributed systems.",
    "What is the Turing test?",
    "Explain the concept of recursion with an example.",
    "What is quantum entanglement?",
    "How does public-key cryptography work?",
    "What is the Big Bang theory?",
    "Explain MapReduce in three sentences.",
    "What is natural selection?",
    "How does a neural network learn?",
    "What is the halting problem?",
    "Explain the second law of thermodynamics.",
    "What is a blockchain?",
    "Describe the observer effect in quantum mechanics.",
]


async def submit_and_wait(client: httpx.AsyncClient, hub: str, task_id: str,
                          prompt: str, model: str, max_tokens: int,
                          timeout_s: int) -> dict:
    t0 = time.monotonic()
    await client.post(f"{hub}/tasks", json={
        "task_id": task_id, "model": model, "prompt": prompt, "max_tokens": max_tokens,
    })
    deadline = time.monotonic() + timeout_s
    interval = 1.5
    while time.monotonic() < deadline:
        try:
            r = await client.get(f"{hub}/tasks/{task_id}")
            data = r.json()
            state = data.get("state", "")
            if state == "COMPLETE":
                result = data.get("result", {})
                elapsed = time.monotonic() - t0
                return {"task_id": task_id, "state": "COMPLETE",
                        "agent_id": result.get("agent_id", ""),
                        "output_tokens": result.get("output_tokens", 0),
                        "latency_s": round(elapsed, 2),
                        "tps": round(result.get("output_tokens", 0) / max(elapsed, 0.001), 1)}
            if state == "FAILED":
                return {"task_id": task_id, "state": "FAILED", "agent_id": "",
                        "output_tokens": 0, "latency_s": 0, "tps": 0}
        except Exception:
            pass
        await asyncio.sleep(interval)
        interval = min(interval * 1.2, 8.0)
    return {"task_id": task_id, "state": "TIMEOUT", "agent_id": "",
            "output_tokens": 0, "latency_s": 0, "tps": 0}


async def run_stress(hub: str, n: int, model: str, max_tokens: int,
                     concurrency: int, timeout_s: int):
    prompts = [PROMPTS[i % len(PROMPTS)] for i in range(n)]
    task_ids = [f"stress-{uuid.uuid4().hex[:8]}" for _ in range(n)]

    click.echo(f"\n  Stress Test")
    click.echo(f"    Hub:         {hub}")
    click.echo(f"    Tasks:       {n}")
    click.echo(f"    Model:       {model}")
    click.echo(f"    Concurrency: {concurrency}")
    click.echo(f"    Max tokens:  {max_tokens}")
    click.echo()

    wall_start = time.monotonic()
    results = []
    sem = asyncio.Semaphore(concurrency)

    async def bounded(client, tid, prompt):
        async with sem:
            return await submit_and_wait(client, hub, tid, prompt, model, max_tokens, timeout_s)

    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s + 30.0)) as client:
        tasks = [bounded(client, tid, p) for tid, p in zip(task_ids, prompts)]
        for coro in asyncio.as_completed(tasks):
            r = await coro
            results.append(r)
            status = r["state"]
            agent = r.get("agent_id", "")[-12:] or "?"
            click.echo(f"    [{len(results):>3}/{n}] {status:<8} {r['latency_s']:>6.1f}s  "
                        f"{r['output_tokens']:>4} tok  {r['tps']:>5.1f} tps  agent=..{agent}")

    wall_time = time.monotonic() - wall_start

    # Summary
    completed = [r for r in results if r["state"] == "COMPLETE"]
    failed = [r for r in results if r["state"] == "FAILED"]
    timed_out = [r for r in results if r["state"] == "TIMEOUT"]
    total_tokens = sum(r["output_tokens"] for r in completed)

    click.echo(f"\n  {'='*60}")
    click.echo(f"  Results:")
    click.echo(f"    Completed: {len(completed)}/{n}  |  Failed: {len(failed)}  |  Timeout: {len(timed_out)}")
    click.echo(f"    Wall time: {wall_time:.1f}s")
    click.echo(f"    Total tokens: {total_tokens:,}")
    if completed:
        avg_lat = sum(r["latency_s"] for r in completed) / len(completed)
        avg_tps = sum(r["tps"] for r in completed) / len(completed)
        throughput = total_tokens / wall_time
        click.echo(f"    Avg latency: {avg_lat:.1f}s  |  Avg TPS: {avg_tps:.1f}")
        click.echo(f"    Grid throughput: {throughput:.1f} tokens/s")

    # Agent distribution
    agent_counts: dict[str, int] = {}
    for r in completed:
        aid = r.get("agent_id", "unknown")
        agent_counts[aid] = agent_counts.get(aid, 0) + 1
    if agent_counts:
        click.echo(f"\n  Agent distribution:")
        for aid, cnt in sorted(agent_counts.items(), key=lambda x: -x[1]):
            bar = "#" * cnt
            click.echo(f"    {aid[-16:]:<18} {cnt:>3} tasks  {bar}")
    click.echo()


@click.command()
@click.option("--hub", default="http://localhost:8000", show_default=True)
@click.option("-n", "--num-tasks", default=20, show_default=True, type=int, help="Number of tasks")
@click.option("--model", default="llama3", show_default=True)
@click.option("--max-tokens", default=150, show_default=True, type=int)
@click.option("--concurrency", default=10, show_default=True, type=int,
              help="Max parallel submissions")
@click.option("--timeout", default=300, show_default=True, type=int, help="Per-task timeout (s)")
def main(hub, num_tasks, model, max_tokens, concurrency, timeout):
    """Fire N tasks at the grid and measure throughput."""
    asyncio.run(run_stress(hub, num_tasks, model, max_tokens, concurrency, timeout))


if __name__ == "__main__":
    main()
