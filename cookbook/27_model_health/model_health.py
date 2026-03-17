#!/usr/bin/env python3
# Recipe 27 — Model Health Check
#
# Measures per-model loading time and inference TPS on each agent node by
# sending two identical probe requests back-to-back per model:
#   request 1 (warmup)  -> model loads into VRAM  -> records load_time
#   request 2 (probe)   -> model already hot       -> records infer_time + TPS
#
# Usage:
#   python model_health.py
#   python model_health.py --hub http://192.168.0.177:8000
#   python model_health.py --interval 60   # repeat every 60 min

import json
import os
import time
import uuid
import click
import httpx
from datetime import datetime

PROBE_PROMPT = "Reply with exactly: 'Model online.'"
PROBE_MAX_TOKENS = 20

client = httpx.Client(timeout=30.0)


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


def is_embedding_model(model: str) -> bool:
    lower = model.lower()
    return any(pat in lower for pat in ["embed", "bge-", "bge_"])


def collect_models(hub_url: str) -> list[str]:
    try:
        resp = client.get(f"{hub_url}/agents", timeout=10.0)
        data = resp.json()
    except Exception:
        return []
    seen = set()
    models = []
    for agent in data.get("agents", []):
        if agent.get("status") != "ONLINE":
            continue
        model_str = agent.get("supported_models", "[]")
        try:
            model_list = json.loads(model_str)
        except Exception:
            model_list = []
        for m in model_list:
            if m and m not in seen:
                seen.add(m)
                models.append(m)
    return sorted(models)


def get_agent_names(hub_url: str) -> dict[str, str]:
    names = {}
    try:
        resp = client.get(f"{hub_url}/agents", timeout=10.0)
        for a in resp.json().get("agents", []):
            agent_id = a.get("agent_id", "")
            name = a.get("name", "") or agent_id[:12]
            names[agent_id] = name
    except Exception:
        pass
    return names


def probe(hub_url: str, model: str, timeout_s: int) -> dict:
    task_id = f"health-{uuid.uuid4().hex[:8]}"
    t0 = time.monotonic()
    try:
        client.post(f"{hub_url}/tasks", json={
            "task_id": task_id,
            "model": model,
            "prompt": PROBE_PROMPT,
            "max_tokens": PROBE_MAX_TOKENS,
        }, timeout=10.0).raise_for_status()
    except Exception as e:
        return {"model": model, "error": str(e)}

    deadline = time.monotonic() + timeout_s
    interval = 2.0
    while time.monotonic() < deadline:
        try:
            resp = client.get(f"{hub_url}/tasks/{task_id}", timeout=5.0)
            data = resp.json()
            state = data.get("state", "")
            if state == "COMPLETE":
                res = data.get("result") or data
                lat_ms = res.get("latency_ms", 0) or 0
                out_tok = res.get("output_tokens", 0) or 0
                tps = out_tok / (lat_ms / 1000) if lat_ms > 0 else 0.0
                load_time_ms = (time.monotonic() - t0) * 1000
                return {
                    "model": model,
                    "agent_id": res.get("agent_id", ""),
                    "load_time_ms": load_time_ms,
                    "infer_ms": lat_ms,
                    "tps": tps,
                    "tokens": out_tok,
                }
            if state == "FAILED":
                return {"model": model, "error": "task failed"}
        except Exception:
            pass
        time.sleep(interval)
        if interval < 8.0:
            interval = min(interval * 1.2, 8.0)
    return {"model": model, "error": "timeout"}


def print_table(results: list[dict], agent_names: dict[str, str]):
    # Group by agent name
    by_agent: dict[str, list[dict]] = {}
    agent_order = []
    for r in results:
        key = agent_names.get(r.get("agent_id", ""), "") or r.get("agent_id", "") or ""
        if key not in by_agent:
            agent_order.append(key)
            by_agent[key] = []
        by_agent[key].append(r)

    sep = "\u2500" * 74
    print(f"\n{sep}")
    print(f"{'AGENT':<20}  {'MODEL':<22}  {'LOAD_TIME':>9}  {'INFER_MS':>9}  {'TPS':>7}  STATUS")
    print(sep)

    for agent in sorted(agent_order):
        for r in by_agent[agent]:
            err = r.get("error", "")
            model = r.get("model", "")
            if err == "embedding model":
                print(f"{agent:<20}  {model:<22}  {'—':>9}  {'—':>9}  {'—':>7}  EMBED")
            elif err:
                print(f"{agent:<20}  {model:<22}  {'—':>9}  {'—':>9}  {'—':>7}  ERROR: {err}")
            else:
                load_ms = r.get("load_time_ms", 0)
                infer_ms = r.get("infer_ms", 0)
                tps = r.get("tps", 0)
                print(f"{agent:<20}  {model:<22}  {load_ms:>8.0f}ms  {infer_ms:>8.0f}ms  {tps:>6.1f}  OK")
    print(f"{sep}\n")


def save_results(name: str, data: dict):
    os.makedirs("out", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join("out", f"{name}_{ts}.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Results saved: {path}")


def run_health_check(hub_url: str, timeout_s: int):
    ts = datetime.now()
    print(f"Model Health Check  —  {ts.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Hub: {hub_url}\n")

    agent_names = get_agent_names(hub_url)

    models = collect_models(hub_url)
    if not models:
        print("No agents online.")
        return

    print(f"  Models to probe: {', '.join(models)}\n")
    results = []

    for model in models:
        print(f"  [{model}]")

        if is_embedding_model(model):
            print("    skip — embedding model (no inference probe)\n")
            results.append({"model": model, "error": "embedding model"})
            continue

        # Request 1: warmup (loads model)
        print("    warmup... ", end="", flush=True)
        w = probe(hub_url, model, timeout_s)
        w_name = agent_names.get(w.get("agent_id", ""), w.get("agent_id", "")[:12])
        if w.get("error"):
            print(f"ERROR {w['error']}")
            results.append({**w, "agent_name": w_name, "error": "warmup: " + w["error"]})
            print()
            continue
        print(f"ok  {w['load_time_ms']:.0f}ms (load)  agent={w_name}")

        # Request 2: inference (model already hot)
        print("    probe...  ", end="", flush=True)
        p = probe(hub_url, model, timeout_s)
        p_name = agent_names.get(p.get("agent_id", ""), p.get("agent_id", "")[:12])
        if p.get("error"):
            print(f"ERROR {p['error']}")
            results.append({
                "model": model,
                "agent_id": w.get("agent_id", ""),
                "agent_name": w_name,
                "load_time_ms": w["load_time_ms"],
                "error": "probe: " + p["error"],
            })
            print()
            continue

        same_agent = p.get("agent_id") == w.get("agent_id")
        agent_note = "" if same_agent else f" (routed to {p_name})"
        print(f"ok  {p['tps']:.1f} TPS  {p['infer_ms']:.0f}ms{agent_note}")

        results.append({
            "model": model,
            "agent_id": w.get("agent_id", ""),
            "agent_name": w_name,
            "load_time_ms": w["load_time_ms"],
            "infer_ms": p["infer_ms"],
            "tps": p["tps"],
            "tokens": p["tokens"],
        })
        print()

    print_table(results, agent_names)
    save_results("model_health", {
        "timestamp": ts.isoformat(),
        "hub": hub_url,
        "results": results,
    })


@click.command()
@click.option("--hub", default=None, help="Hub URL (default: from config or http://localhost:8000)")
@click.option("--timeout", "timeout_s", default=180, help="Per-task timeout in seconds")
@click.option("--interval", "interval_min", default=0, help="Repeat every N minutes (0 = run once)")
def main(hub, timeout_s, interval_min):
    """Model Health Check — probe each model on each agent node."""
    hub_url = hub or default_hub_url()
    while True:
        run_health_check(hub_url, timeout_s)
        if interval_min <= 0:
            break
        print(f"Next check in {interval_min} min...\n")
        time.sleep(interval_min * 60)


if __name__ == "__main__":
    main()
