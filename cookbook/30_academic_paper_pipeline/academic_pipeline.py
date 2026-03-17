#!/usr/bin/env python3
# Recipe 30: Academic Paper Pipeline
#
# Demonstrates a complete academic writing workflow distributed across agents:
#   Stage 1  —  Abstract analysis (parse topic + key claims)
#   Stage 2  —  Literature framing (related work, motivation)
#   Stage 3  —  Methodology outline (approach + design)
#   Stage 4  —  Results interpretation (findings + implications)
#   Stage 5  —  Conclusion + abstract rewrite (consolidate)
#
# Stages 1-4 run in parallel on separate agents; Stage 5 aggregates.
# Showcases MomaGrid's map-reduce inference pipeline.
#
# Usage:
#   python academic_pipeline.py
#   python academic_pipeline.py --hub http://localhost:8000

import json
import os
import time
import uuid
import click
import httpx
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Sample research topic for the pipeline
PAPER_TOPIC = """
Title: Momagrid: A Decentralized Inference Runtime with Semantic Chunking

Abstract excerpt:
The quadratic complexity O(N^2) of the self-attention mechanism remains the
fundamental barrier to long-context inference and hardware decentralization.
We present Momagrid, a distributed inference runtime for Structured Prompt Language
(SPL) that bypasses this bottleneck through Semantic Chunking. By treating the
transformer context window as a partitioned data structure, Momagrid enables a
Map-Reduce inference pipeline that reduces peak attention complexity from O(N^2)
to O(N*k), where k is a hardware-bound constant.
"""

STAGES = [
    {
        "id": "analysis",
        "name": "Abstract Analysis",
        "system": "You are a research analyst. Extract structured information from academic text. Be precise and concise.",
        "prompt_template": """Analyze this research abstract and extract:
1. Core problem being solved (1 sentence)
2. Key technical contribution (1 sentence)
3. Main claim or result (1 sentence)
4. Research category (e.g., Systems, ML, Distributed Computing)

Abstract:
{topic}""",
    },
    {
        "id": "literature",
        "name": "Literature Framing",
        "system": "You are an academic researcher writing a literature review. Be scholarly but concise.",
        "prompt_template": """Based on this research topic, write a 3-sentence related work framing that:
1. Identifies the existing approaches this work improves on
2. Explains the gap in the literature
3. States how this work fills the gap

Research topic:
{topic}""",
    },
    {
        "id": "methodology",
        "name": "Methodology Outline",
        "system": "You are a systems researcher. Describe technical methodologies clearly and precisely.",
        "prompt_template": """Based on this research description, outline the methodology in 4 bullet points:
- Key design principle
- Core algorithmic approach
- Implementation strategy
- Evaluation approach

Research:
{topic}""",
    },
    {
        "id": "implications",
        "name": "Results & Implications",
        "system": "You are a technical writer specializing in research impact. Focus on practical significance.",
        "prompt_template": """Based on this research, describe in 3 sentences:
1. What the system achieves practically
2. Who benefits from this work
3. What future work it enables

Research:
{topic}""",
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


def submit_task(hub_url: str, model: str, system: str, prompt: str) -> dict:
    task_id = str(uuid.uuid4())
    with httpx.Client(timeout=120.0) as client:
        client.post(f"{hub_url}/tasks", json={
            "task_id": task_id,
            "model": model,
            "system": system,
            "prompt": prompt,
            "max_tokens": 512,
            "temperature": 0.3,
        }, timeout=10.0).raise_for_status()

        for _ in range(90):
            time.sleep(2.0)
            try:
                resp = client.get(f"{hub_url}/tasks/{task_id}", timeout=5.0)
                data = resp.json()
                state = data.get("state", "")
                if state in ("COMPLETE", "FAILED"):
                    sr = {"state": state}
                    if state == "COMPLETE":
                        res = data.get("result", {})
                        sr["content"] = str(res.get("content", ""))
                        sr["agent_id"] = str(res.get("agent_id", ""))
                        sr["agent_name"] = str(res.get("agent_name", ""))
                        sr["agent_host"] = str(res.get("agent_host", ""))
                        sr["output_tokens"] = res.get("output_tokens", 0)
                        sr["latency_ms"] = res.get("latency_ms", 0)
                    return sr
            except Exception:
                pass
    return {"state": "TIMEOUT"}


def run_stage(hub_url: str, model: str, stage: dict) -> dict:
    prompt = stage["prompt_template"].format(topic=PAPER_TOPIC)
    sr = submit_task(hub_url, model, stage["system"], prompt)
    sr["id"] = stage["id"]
    sr["name"] = stage["name"]
    return sr


def agent_label(sr: dict) -> str:
    name = sr.get("agent_name", "")
    if name and name not in ("", "None", "<nil>"):
        return name
    aid = sr.get("agent_id", "")
    return aid[:8] if aid else "unknown"


def truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n] + "..."


def save_results(out_dir: str, report: dict):
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(out_dir, f"academic_pipeline_{ts}.json")
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Results saved: {path}")


@click.command()
@click.option("--hub", default=None, help="Hub URL (default: from config or http://localhost:8000)")
@click.option("--model", default="llama3", help="Model to use")
@click.option("--out", "out_dir", default="out", help="Output directory")
def main(hub, model, out_dir):
    """Academic Paper Pipeline — distributed research workflow."""
    hub_url = hub or default_hub_url()

    print("Academic Paper Pipeline — Distributed Research Workflow")
    print(f"   Hub:    {hub_url}")
    print(f"   Model:  {model}")
    print(f"   Stages: {len(STAGES)} parallel + 1 synthesis\n")

    start = time.monotonic()

    # Phase 1: Run stages in parallel
    print(f"Phase 1: Parallel Analysis ({len(STAGES)} agents)")
    stage_results: list[dict] = [{} for _ in STAGES]

    with ThreadPoolExecutor(max_workers=len(STAGES)) as executor:
        futures = {
            executor.submit(run_stage, hub_url, model, stage): i
            for i, stage in enumerate(STAGES)
        }
        for future in as_completed(futures):
            i = futures[future]
            sr = future.result()
            stage_results[i] = sr
            label = agent_label(sr)
            tok = int(sr.get("output_tokens", 0))
            lat = sr.get("latency_ms", 0)
            print(f"   [{sr['name']}] -> agent={label}  {tok} tok  {lat:.0f}ms")

    # Phase 2: Synthesis — sequential, depends on all parallel stages
    print("\nPhase 2: Synthesis (conclusion + refined abstract)")

    synthesis_parts = [f"Original research topic:\n{PAPER_TOPIC}\n"]
    total_tokens = 0
    for sr in stage_results:
        synthesis_parts.append(f"=== {sr['name']} ===\n{sr.get('content', '')}\n")
        total_tokens += int(sr.get("output_tokens", 0))
    synthesis_input = "\n".join(synthesis_parts)

    conclusion_system = (
        "You are a senior researcher writing the conclusion of an academic paper. "
        "Synthesize diverse analyses into a coherent, compelling conclusion."
    )
    conclusion_prompt = (
        "Based on the following analyses of a research paper, write:\n"
        "1. A 3-sentence conclusion that captures the core contribution and its significance\n"
        "2. A polished 4-sentence abstract rewrite\n\n"
        + synthesis_input
    )

    conclusion = submit_task(hub_url, model, conclusion_system, conclusion_prompt)
    conclusion["id"] = "conclusion"
    conclusion["name"] = "Conclusion & Abstract"
    total_tokens += int(conclusion.get("output_tokens", 0))

    label = agent_label(conclusion)
    tok = int(conclusion.get("output_tokens", 0))
    lat = conclusion.get("latency_ms", 0)
    print(f"   Synthesis -> agent={label}  {tok} tok  {lat:.0f}ms")

    total_latency = time.monotonic() - start
    completed = sum(1 for sr in stage_results if sr and sr.get("state") == "COMPLETE")
    if conclusion.get("state") == "COMPLETE":
        completed += 1

    summary = (
        f"{completed}/{len(STAGES) + 1} stages complete "
        f"· {total_tokens} total tokens "
        f"· {total_latency:.1f}s"
    )

    report = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "topic": PAPER_TOPIC.strip(),
        "model": model,
        "stages": stage_results,
        "conclusion": conclusion,
        "total_tokens": total_tokens,
        "total_latency_s": total_latency,
        "summary": summary,
    }

    save_results(out_dir, report)

    print(f"\nPipeline complete: {summary}")
    print("\n-- Conclusion excerpt --")
    print(truncate(conclusion.get("content", ""), 300))


if __name__ == "__main__":
    main()
