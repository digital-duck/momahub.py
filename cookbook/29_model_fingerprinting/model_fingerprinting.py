#!/usr/bin/env python3
# Recipe 29: Model Fingerprinting
#
# Tests output consistency and determinism from the same model across different
# agents. Sends identical prompts multiple times and compares responses to
# identify variance, agent identity, and cross-node reliability.
#
# Usage:
#   python model_fingerprinting.py
#   python model_fingerprinting.py --hub http://localhost:8000 --model llama3 --runs 3

import json
import os
import time
import uuid
import click
import httpx
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Test cases: deterministic-math, stable-factual, creative-haiku
TEST_CASES = [
    {
        "name": "deterministic-math",
        "prompt": "What is 2 + 2? Answer with just the number.",
        "temperature": 0.0,
        "expect_stable": True,
    },
    {
        "name": "stable-factual",
        "prompt": "What is the boiling point of water at sea level in Celsius? Answer with just the number.",
        "temperature": 0.1,
        "expect_stable": True,
    },
    {
        "name": "creative-haiku",
        "prompt": "Write a haiku about a mountain. Output ONLY the haiku, no titles.",
        "temperature": 0.8,
        "expect_stable": False,
    },
]


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


def short_id(name: str, agent_id: str) -> str:
    if name and name not in ("", "None", "<nil>"):
        return name
    return agent_id[:8] if len(agent_id) >= 8 else agent_id


def truncate(s: str, n: int) -> str:
    s = s.replace("\n", " ")
    return s if len(s) <= n else s[:n] + "..."


def submit_and_poll(hub_url: str, model: str, prompt: str, temperature: float) -> dict:
    task_id = str(uuid.uuid4())
    try:
        with httpx.Client(timeout=90.0) as client:
            client.post(f"{hub_url}/tasks", json={
                "task_id": task_id,
                "model": model,
                "prompt": prompt,
                "max_tokens": 64,
                "temperature": temperature,
            }, timeout=10.0).raise_for_status()

            for _ in range(60):
                time.sleep(2.0)
                try:
                    resp = client.get(f"{hub_url}/tasks/{task_id}", timeout=5.0)
                    data = resp.json()
                    state = data.get("state", "")
                    if state in ("COMPLETE", "FAILED"):
                        fp = {"task_id": task_id, "state": state, "model": model}
                        if state == "COMPLETE":
                            res = data.get("result", {})
                            fp["content"] = str(res.get("content", "")).strip()
                            fp["agent_id"] = str(res.get("agent_id", ""))
                            fp["agent_name"] = str(res.get("agent_name", ""))
                            fp["agent_host"] = str(res.get("agent_host", ""))
                            fp["output_tokens"] = res.get("output_tokens", 0)
                            fp["latency_ms"] = res.get("latency_ms", 0)
                        return fp
                except Exception:
                    pass
    except Exception as e:
        return {"task_id": task_id, "state": "SUBMIT_ERROR", "model": model, "error": str(e)}
    return {"task_id": task_id, "state": "TIMEOUT", "model": model}


def run_test_case(hub_url: str, model: str, tc: dict, num_runs: int) -> dict:
    print(f"  [{tc['name']}] temp={tc['temperature']:.1f} runs={num_runs}")

    fingerprints = []
    with ThreadPoolExecutor(max_workers=num_runs) as executor:
        futures = {
            executor.submit(submit_and_poll, hub_url, model, tc["prompt"], tc["temperature"]): run
            for run in range(num_runs)
        }
        for future in as_completed(futures):
            run_num = futures[future]
            fp = future.result()
            fingerprints.append(fp)
            agent_label = short_id(fp.get("agent_name", ""), fp.get("agent_id", ""))
            content_preview = truncate(fp.get("content", ""), 40)
            print(f"    run={run_num + 1} agent={agent_label} content={content_preview!r}")

    # Measure uniqueness and consistency
    unique_outputs = set()
    complete = [fp for fp in fingerprints if fp.get("state") == "COMPLETE"]
    for fp in complete:
        if fp.get("content"):
            unique_outputs.add(fp["content"])

    consistency_pct = 0.0
    if complete:
        counts: dict[str, int] = {}
        for fp in complete:
            c = fp.get("content", "")
            counts[c] = counts.get(c, 0) + 1
        max_count = max(counts.values()) if counts else 0
        consistency_pct = max_count / len(complete) * 100

    return {
        "test_name": tc["name"],
        "prompt": tc["prompt"],
        "temperature": tc["temperature"],
        "expect_stable": tc["expect_stable"],
        "fingerprints": fingerprints,
        "unique_outputs": len(unique_outputs),
        "consistency_pct": consistency_pct,
    }


def save_results(out_dir: str, report: dict):
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(out_dir, f"model_fingerprinting_{ts}.json")
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Results saved: {path}")


@click.command()
@click.option("--hub", default=None, help="Hub URL (default: from config or http://localhost:8000)")
@click.option("--model", default="llama3", help="Model to fingerprint")
@click.option("--runs", default=3, help="Number of repeated runs per test case")
@click.option("--out", "out_dir", default="out", help="Output directory")
def main(hub, model, runs, out_dir):
    """Model Fingerprinting — cross-agent consistency test."""
    hub_url = hub or default_hub_url()

    print("Model Fingerprinting — Cross-Agent Consistency Test")
    print(f"   Hub:   {hub_url}")
    print(f"   Model: {model}")
    print(f"   Runs:  {runs} x {len(TEST_CASES)} tests\n")

    start = time.monotonic()
    results = []

    for tc in TEST_CASES:
        r = run_test_case(hub_url, model, tc, runs)
        results.append(r)
        stable_str = "stable" if tc["expect_stable"] else "variable"
        print(f"    unique={r['unique_outputs']}  consistency={r['consistency_pct']:.0f}%  (expected {stable_str})\n")

    # Summary
    stable_count = sum(
        1 for r in results
        if r["expect_stable"] and r["consistency_pct"] >= 80
    )
    expected_stable = sum(1 for tc in TEST_CASES if tc["expect_stable"])
    summary = (
        f"model={model} runs={runs}x{len(TEST_CASES)} "
        f"stable={stable_count}/{expected_stable} deterministic tests passed"
    )

    report = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "hub": hub_url,
        "model": model,
        "num_runs": runs,
        "results": results,
        "summary": summary,
    }

    save_results(out_dir, report)

    elapsed = time.monotonic() - start
    print(f"Fingerprinting complete ({elapsed:.1f}s)")
    print(f"   {summary}")


if __name__ == "__main__":
    main()
