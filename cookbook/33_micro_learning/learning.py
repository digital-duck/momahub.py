#!/usr/bin/env python3
# Recipe 33: Micro-Learning Grid — Generate a mini-textbook from a single subject.
#
# This recipe demonstrates a complex multi-step pipeline on the grid:
# 1. Planning: Ask a high-reasoning model for a 5-part textbook outline.
# 2. Decomposition: Split the outline into independent writing tasks.
# 3. Parallel Execution: Dispatch all parts to the grid simultaneously.
# 4. Synthesis: Combine the parts into a final Markdown textbook.
#
# Usage:
#   python learning.py "Gradient Descent"
#   python learning.py --hub http://localhost:8000 --subject "Quantum Computing"

import json
import os
import time
import uuid
import sys
import click
import httpx
from concurrent.futures import ThreadPoolExecutor, as_completed

PLANNING_SYSTEM = (
    "You are an expert curriculum designer. Given a subject, create a 5-part outline for a micro-textbook. "
    "Each part must have a 'title' and a 'description' of what to cover. "
    "Return ONLY valid JSON: [{\"title\": \"...\", \"description\": \"...\"}, ...]"
)

WRITING_SYSTEM = (
    "You are a professional technical educator. Write one chapter of a micro-textbook. "
    "Be clear, use Markdown, include examples, and keep it engaging. "
    "Do not include a preamble or postamble."
)


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


def submit_and_wait(hub: str, system: str, prompt: str, model: str, max_tokens: int = 2048) -> str:
    task_id = f"learn-{uuid.uuid4().hex[:8]}"
    with httpx.Client(timeout=120.0) as client:
        client.post(f"{hub}/tasks", json={
            "task_id": task_id,
            "model": model,
            "prompt": prompt,
            "system": system,
            "max_tokens": max_tokens,
        }, timeout=10.0).raise_for_status()

        for _ in range(100):
            try:
                resp = client.get(f"{hub}/tasks/{task_id}", timeout=5.0)
                data = resp.json()
                if data.get("state") == "COMPLETE":
                    res = data.get("result", {})
                    return str(res.get("content", ""))
                if data.get("state") == "FAILED":
                    raise RuntimeError("task failed")
            except RuntimeError:
                raise
            except Exception:
                pass
            time.sleep(2.0)
    raise RuntimeError("timeout")


def write_chapter(hub: str, model: str, subject: str, title: str, description: str, idx: int) -> tuple[int, str, str]:
    prompt = f"Subject: {subject}\nChapter: {title}\nFocus: {description}"
    try:
        content = submit_and_wait(hub, WRITING_SYSTEM, prompt, model, max_tokens=2048)
        print(f"         Chapter {idx + 1} complete: {title}")
        return idx, title, content
    except Exception as e:
        print(f"         ! Chapter {idx + 1} FAILED: {e}")
        return idx, title, f"> *Error generating this chapter: {e}*"


@click.command()
@click.argument("subject", required=False)
@click.option("--subject", "subject_opt", default=None, help="Subject to generate textbook for")
@click.option("--hub", default=None, help="Hub URL (default: from config or http://localhost:8000)")
@click.option("--model", default="llama3", help="Model to use for all steps")
def main(subject, subject_opt, hub, model):
    """Micro-Learning Grid — plan, write chapters in parallel, synthesize textbook."""
    topic = subject_opt or subject
    if not topic:
        print("Usage: python learning.py <subject>  or  python learning.py --subject <subject>")
        sys.exit(1)

    hub_url = hub or default_hub_url()

    print(f"\nMicro-Learning Grid: \"{topic}\"")
    print(f"   Hub: {hub_url}\n")

    # Step 1: Planning
    print("   [1/3] Planning curriculum... ", end="", flush=True)
    try:
        outline_json = submit_and_wait(hub_url, PLANNING_SYSTEM, f"Subject: {topic}", model, max_tokens=1024)
        outline = json.loads(clean_json(outline_json))
    except Exception as e:
        print(f"FAILED: {e}")
        sys.exit(1)
    print(f"done ({len(outline)} chapters)")

    # Step 2: Parallel Writing
    print("   [2/3] Generating chapters in parallel...")
    results: list[tuple[str, str]] = [("", "")] * len(outline)

    with ThreadPoolExecutor(max_workers=len(outline)) as executor:
        futures = {
            executor.submit(write_chapter, hub_url, model, topic, ch["title"], ch["description"], i): i
            for i, ch in enumerate(outline)
        }
        for future in as_completed(futures):
            idx, title, content = future.result()
            results[idx] = (title, content)

    # Step 3: Synthesis
    print("\n   [3/3] Synthesizing textbook...")
    lines = [
        f"# {topic}: A Micro-Textbook\n",
        "Generated by Momagrid Decentralized AI Grid\n",
        "---\n",
    ]
    for i, (title, content) in enumerate(results):
        lines.append(f"## Chapter {i + 1}: {title}\n")
        lines.append(content)
        lines.append("\n\n---\n")

    out_path = f"micro_textbook_{topic.lower().replace(' ', '_')}.md"
    with open(out_path, "w") as f:
        f.write("\n".join(lines))

    print(f"\nSuccess! Your mini-textbook is ready: {out_path}")


if __name__ == "__main__":
    main()
