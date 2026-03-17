#!/usr/bin/env python3
# Recipe 28: Federated Search Grid — Distribute search and synthesize results.
#
# This recipe demonstrates how to use the grid to parallelize information gathering:
# 1. Partitioning: Split a complex query into 3 specific sub-queries.
# 2. Parallel Search: Dispatch sub-queries to different agents (mocking search).
# 3. Synthesis: Aggregate the findings into a final report.
#
# Usage:
#   python search.py "Recent breakthroughs in room-temperature superconductivity"
#   python search.py --hub http://192.168.0.177:8000 "Quantum computing advances"

import json
import os
import time
import uuid
import sys
import click
import httpx
from concurrent.futures import ThreadPoolExecutor, as_completed


def default_hub_url():
    config_path = os.path.expanduser("~/.igrid/config.yaml")
    try:
        import yaml
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        hub_urls = cfg.get("hub", {}).get("urls", [])
        if hub_urls:
            return hub_urls[0].rstrip("/")
        port = cfg.get("hub", {}).get("port")
        if port:
            return f"http://localhost:{port}"
    except Exception:
        pass
    return "http://localhost:8000"


def clean_json(s: str) -> str:
    s = s.strip()
    s = s.removeprefix("```json").removeprefix("```")
    s = s.removesuffix("```")
    return s.strip()


def submit_task(hub: str, system: str, prompt: str, model: str, client: httpx.Client) -> str:
    task_id = f"search-{uuid.uuid4().hex[:8]}"
    client.post(f"{hub}/tasks", json={
        "task_id": task_id,
        "model": model,
        "prompt": prompt,
        "system": system,
        "max_tokens": 1024,
    }, timeout=10.0).raise_for_status()
    return task_id


def poll_task(hub: str, task_id: str, client: httpx.Client, timeout_s: int = 120) -> str:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            data = client.get(f"{hub}/tasks/{task_id}", timeout=5.0).json()
            state = data.get("state", "")
            if state == "COMPLETE":
                res = data.get("result", {})
                return res.get("content", "")
            if state == "FAILED":
                return ""
        except Exception:
            pass
        time.sleep(1.0)
    return ""


def search_subquery(hub: str, system: str, sub_query: str, model: str, idx: int) -> tuple[int, str]:
    with httpx.Client(timeout=30.0) as c:
        print(f"         -> Sub-query {idx + 1}: {sub_query}")
        task_id = submit_task(hub, system, f"Research: {sub_query}", model, c)
        content = poll_task(hub, task_id, c, timeout_s=120)
        return idx, content


@click.command()
@click.argument("query")
@click.option("--hub", default=None, help="Hub URL (default: from config or http://localhost:8000)")
@click.option("--model", default="llama3", help="Model to use")
def main(query, hub, model):
    """Federated Search Grid — partition query, parallel search, synthesize report."""
    hub_url = hub or default_hub_url()

    print(f"\nFederated Search Grid: \"{query}\"")
    print(f"   Hub: {hub_url}\n")

    client = httpx.Client(timeout=30.0)

    # Step 1: Partitioning
    print("   [1/3] Partitioning query... ", end="", flush=True)
    partition_system = (
        "Split the query into 3 distinct, specific sub-queries for research. "
        "Return ONLY JSON: [\"q1\", \"q2\", \"q3\"]"
    )
    try:
        task_id = submit_task(hub_url, partition_system, f"Query: {query}", model, client)
        partition_json = poll_task(hub_url, task_id, client, timeout_s=120)
        sub_queries = json.loads(clean_json(partition_json))
    except Exception as e:
        print(f"FAILED: {e}")
        client.close()
        sys.exit(1)
    print(f"done ({len(sub_queries)} sub-queries)")

    # Step 2: Parallel Search
    print("   [2/3] Dispatching federated search tasks...")
    search_system = "You are a search agent. Provide a detailed summary of facts for the given sub-query."
    results = [""] * len(sub_queries)

    with ThreadPoolExecutor(max_workers=len(sub_queries)) as executor:
        futures = {
            executor.submit(search_subquery, hub_url, search_system, q, model, i): i
            for i, q in enumerate(sub_queries)
        }
        for future in as_completed(futures):
            idx, content = future.result()
            results[idx] = content

    # Step 3: Synthesis
    print("\n   [3/3] Synthesizing final report...")
    synthesis_system = "Synthesize the provided research findings into a single, cohesive technical report."
    findings = ""
    for i, r in enumerate(results):
        findings += f"Findings from Sub-query {i + 1}:\n{r}\n\n"

    try:
        task_id = submit_task(hub_url, synthesis_system, findings, model, client)
        report = poll_task(hub_url, task_id, client, timeout_s=180)
    except Exception as e:
        print(f"Synthesis FAILED: {e}")
        client.close()
        sys.exit(1)

    client.close()

    print(f"\n{'=' * 60}")
    print("FINAL FEDERATED SEARCH REPORT")
    print(f"{'=' * 60}\n")
    print(report)


if __name__ == "__main__":
    main()
