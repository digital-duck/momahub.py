"""moma CLI — i-grid command-line interface.
Note: Typer is used (built on Click under the hood).
"""
from __future__ import annotations
import asyncio, json, socket, time, uuid
from typing import Optional
import httpx, typer, uvicorn
from igrid.cli.config import load_config, save_config, show_config


def _detect_lan_ip() -> str:
    """Auto-detect LAN IP via UDP socket trick (no packets sent)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

app = typer.Typer(name="moma", help="MoMaHub i-grid: distributed AI inference network.", no_args_is_help=True)
hub_app = typer.Typer(help="Hub management commands.")
agent_app = typer.Typer(help="Agent management commands.")
peer_app = typer.Typer(help="Cluster peer management.")
app.add_typer(hub_app, name="hub")
app.add_typer(agent_app, name="agent")
app.add_typer(peer_app, name="peer")

@hub_app.command("up")
def hub_up(host: str = typer.Option("0.0.0.0"), port: int = typer.Option(8000),
           hub_url: str = typer.Option(""), db: str = typer.Option(""),
           operator_id: str = typer.Option(""), api_key: str = typer.Option(""),
           admin: bool = typer.Option(False, "--admin", help="Enable admin mode: agents require verification before receiving tasks"),
           max_concurrent: int = typer.Option(3, "--max-concurrent", help="Max concurrent tasks per agent"),
           max_prompt_chars: int = typer.Option(50_000, "--max-prompt-chars", help="Max prompt size in chars (hard ceiling: 200K)"),
           max_queue_depth: int = typer.Option(1000, "--max-queue-depth", help="Max pending tasks in queue"),
           rate_limit: int = typer.Option(60, "--rate-limit", help="Max requests per minute per IP"),
           burst_threshold: int = typer.Option(200, "--burst-threshold", help="Flood detection: requests in 10s")):
    """Start the hub server."""
    cfg = load_config()
    from igrid.hub.app import create_app
    fastapi_app = create_app(operator_id=operator_id or cfg["operator_id"],
                              db_path=db or cfg["db_path"],
                              hub_url=hub_url or f"http://{host}:{port}",
                              api_key=api_key or cfg["api_key"],
                              admin_mode=admin,
                              max_concurrent_tasks=max_concurrent,
                              max_prompt_chars=max_prompt_chars,
                              max_queue_depth=max_queue_depth,
                              rate_limit=rate_limit,
                              burst_threshold=burst_threshold)
    lan_ip = _detect_lan_ip()
    actual_url = hub_url or f"http://{lan_ip}:{port}"
    mode_label = "ADMIN (agents require verification)" if admin else "OPEN (any agent can join)"
    typer.echo(f"Starting hub on {host}:{port}")
    typer.echo(f"  Mode: {mode_label}")
    typer.echo(f"  Max concurrent tasks per agent: {max_concurrent}")
    typer.echo(f"  Rate limit: {rate_limit} req/min  |  Burst threshold: {burst_threshold}/10s")
    typer.echo(f"  Max prompt: {max_prompt_chars} chars  |  Max queue: {max_queue_depth}")
    typer.echo(f"")
    typer.echo(f"  Other machines can join with:")
    typer.echo(f"    moma join {actual_url}")
    typer.echo(f"")
    uvicorn.run(fastapi_app, host=host, port=port, log_level="info")

@hub_app.command("down")
def hub_down(): typer.echo("Use Ctrl+C or your process manager to stop the hub.")

@hub_app.command("pending")
def hub_pending(hub_url: str = typer.Option("")):
    """List agents awaiting approval."""
    cfg = load_config(); url = (hub_url or cfg["hub_urls"][0]).rstrip("/")
    try:
        agents = httpx.get(f"{url}/agents/pending", timeout=5.0).json().get("agents", [])
        if not agents: typer.echo("No agents pending approval."); return
        typer.echo(f"{'NAME':<16} {'AGENT_ID':<38} {'OPERATOR':<15} {'JOINED_AT':<25}")
        typer.echo("-"*94)
        for a in agents:
            typer.echo(f"{a.get('name',''):<16} {a['agent_id']:<38} {a.get('operator_id',''):<15} {a.get('joined_at',''):<25}")
    except Exception as exc: typer.echo(f"Error: {exc}", err=True); raise typer.Exit(1)

@hub_app.command("approve")
def hub_approve(agent_id: str = typer.Argument(..., help="Agent ID to approve"),
                hub_url: str = typer.Option("")):
    """Approve a pending agent."""
    cfg = load_config(); url = (hub_url or cfg["hub_urls"][0]).rstrip("/")
    try:
        resp = httpx.post(f"{url}/agents/{agent_id}/approve", timeout=5.0)
        resp.raise_for_status()
        typer.echo(f"Agent {agent_id} approved.")
    except httpx.HTTPStatusError as exc:
        typer.echo(f"Error: {exc.response.json().get('detail', exc)}", err=True); raise typer.Exit(1)
    except Exception as exc: typer.echo(f"Error: {exc}", err=True); raise typer.Exit(1)

@hub_app.command("reject")
def hub_reject(agent_id: str = typer.Argument(..., help="Agent ID to reject"),
               hub_url: str = typer.Option("")):
    """Reject/ban a pending agent."""
    cfg = load_config(); url = (hub_url or cfg["hub_urls"][0]).rstrip("/")
    try:
        resp = httpx.post(f"{url}/agents/{agent_id}/reject", timeout=5.0)
        resp.raise_for_status()
        typer.echo(f"Agent {agent_id} rejected.")
    except httpx.HTTPStatusError as exc:
        typer.echo(f"Error: {exc.response.json().get('detail', exc)}", err=True); raise typer.Exit(1)
    except Exception as exc: typer.echo(f"Error: {exc}", err=True); raise typer.Exit(1)

@agent_app.command("up")
def agent_up(host: str = typer.Option("0.0.0.0"), port: int = typer.Option(8100),
             join: str = typer.Option(""), operator_id: str = typer.Option(""),
             ollama_url: str = typer.Option(""), api_key: str = typer.Option(""),
             name: str = typer.Option("", "--name", help="Human-friendly agent name (default: hostname)"),
             pull: bool = typer.Option(False, "--pull", help="Use SSE pull mode (WAN-safe, no inbound ports needed)")):
    """Start the agent node."""
    cfg = load_config()
    hub_urls = [u.strip() for u in join.split(",") if u.strip()] if join else cfg["hub_urls"]
    agent_id = cfg.get("agent_id") or str(uuid.uuid4())
    from igrid.agent.worker import create_agent_app
    agent_app_instance = create_agent_app(agent_id=agent_id, operator_id=operator_id or cfg["operator_id"],
                                          hub_urls=hub_urls, ollama_url=ollama_url or cfg["ollama_url"],
                                          api_key=api_key or cfg["api_key"], pull_mode=pull,
                                          agent_name=name or cfg.get("agent_name", ""))
    agent_app_instance.state.host = host if host != "0.0.0.0" else "127.0.0.1"
    agent_app_instance.state.port = port
    cfg["agent_id"] = agent_id; cfg["hub_urls"] = hub_urls; save_config(cfg)
    mode = "PULL (SSE)" if pull else "PUSH (HTTP)"
    typer.echo(f"Starting agent on {host}:{port}  mode={mode}  hubs={hub_urls}")
    uvicorn.run(agent_app_instance, host=host, port=port, log_level="info")

@app.command("join")
def join_grid(hub_urls: list[str] = typer.Argument(...),
              host: str = typer.Option("0.0.0.0"), port: int = typer.Option(8100),
              operator_id: str = typer.Option(""), ollama_url: str = typer.Option(""),
              name: str = typer.Option("", "--name", help="Human-friendly agent name (default: hostname)"),
              pull: bool = typer.Option(False, "--pull", help="Use SSE pull mode (WAN-safe, no inbound ports needed)")):
    """Start an agent and join hub(s)."""
    cfg = load_config()
    agent_id = cfg.get("agent_id") or str(uuid.uuid4())
    from igrid.agent.worker import create_agent_app
    agent_app_instance = create_agent_app(agent_id=agent_id, operator_id=operator_id or cfg["operator_id"],
                                          hub_urls=hub_urls, ollama_url=ollama_url or cfg["ollama_url"],
                                          pull_mode=pull,
                                          agent_name=name or cfg.get("agent_name", ""))
    agent_app_instance.state.host = host if host != "0.0.0.0" else "127.0.0.1"
    agent_app_instance.state.port = port
    cfg["agent_id"] = agent_id; cfg["hub_urls"] = hub_urls; save_config(cfg)
    mode = "PULL (SSE)" if pull else "PUSH (HTTP)"
    typer.echo(f"Joining grid: mode={mode}  hubs={hub_urls}")
    uvicorn.run(agent_app_instance, host=host, port=port, log_level="info")

@app.command("down")
def down(hub_url: str = typer.Option(""), agent_id: str = typer.Option("", help="Agent ID (default: from config)")):
    """Deregister this agent from all hubs and shut down gracefully."""
    cfg = load_config()
    aid = agent_id or cfg.get("agent_id", "")
    if not aid:
        typer.echo("No agent_id found. Use --agent-id or run 'moma join' first.", err=True)
        raise typer.Exit(1)
    oid = cfg["operator_id"]
    hub_urls = [hub_url.rstrip("/")] if hub_url else [u.rstrip("/") for u in cfg["hub_urls"]]
    ok_count = 0
    for url in hub_urls:
        try:
            resp = httpx.post(f"{url}/leave", json={"operator_id": oid, "agent_id": aid}, timeout=5.0)
            resp.raise_for_status()
            typer.echo(f"  Deregistered from {url}")
            ok_count += 1
        except Exception as exc:
            typer.echo(f"  Failed to deregister from {url}: {exc}", err=True)
    if ok_count:
        cfg["agent_id"] = ""; save_config(cfg)
        typer.echo(f"Agent {aid} is down. ({ok_count}/{len(hub_urls)} hubs)")
    else:
        typer.echo("Could not reach any hub.", err=True); raise typer.Exit(1)

@app.command("status")
def status(hub_url: str = typer.Option("")):
    """Show hub health."""
    cfg = load_config(); url = (hub_url or cfg["hub_urls"][0]).rstrip("/")
    try:
        data = httpx.get(f"{url}/health", timeout=5.0).json()
        typer.echo(f"Hub: {data.get('hub_id')}  Status: {data.get('status')}  Agents: {data.get('agents_online')}")
    except Exception as exc: typer.echo(f"Error: {exc}", err=True); raise typer.Exit(1)

@app.command("agents")
def list_agents(hub_url: str = typer.Option("")):
    """List online agents."""
    cfg = load_config(); url = (hub_url or cfg["hub_urls"][0]).rstrip("/")
    try:
        agents = httpx.get(f"{url}/agents", timeout=5.0).json().get("agents", [])
        if not agents: typer.echo("No agents online."); return
        typer.echo(f"{'NAME':<16} {'AGENT_ID':<38} {'TIER':<10} {'STATUS':<10} {'TPS':>6}")
        typer.echo("-"*86)
        for a in agents:
            typer.echo(f"{a.get('name',''):<16} {a['agent_id']:<38} {a['tier']:<10} {a['status']:<10} {a['current_tps']:>6.1f}")
    except Exception as exc: typer.echo(f"Error: {exc}", err=True); raise typer.Exit(1)

@app.command("tasks")
def list_tasks(hub_url: str = typer.Option(""), limit: int = typer.Option(20),
               detail: bool = typer.Option(False, "--detail", "-d", help="Show latency, tokens, agent, and response")):
    """List recent tasks."""
    cfg = load_config(); url = (hub_url or cfg["hub_urls"][0]).rstrip("/")
    try:
        tasks = httpx.get(f"{url}/tasks?limit={limit}", timeout=5.0).json().get("tasks", [])
        if not tasks: typer.echo("No tasks."); return
        if detail:
            for t in tasks:
                typer.echo(f"{'─'*72}")
                typer.echo(f"  task_id:  {t['task_id']}")
                typer.echo(f"  state:    {t['state']}")
                typer.echo(f"  model:    {t['model']}")
                typer.echo(f"  agent:    {t.get('agent_id', '')}")
                typer.echo(f"  tokens:   {t.get('input_tokens', 0)} in / {t.get('output_tokens', 0)} out")
                typer.echo(f"  latency:  {t.get('latency_ms', 0):.0f} ms")
                typer.echo(f"  prompt:   {(t.get('prompt', '') or '')[:120]}")
                content = (t.get('content', '') or '')
                preview = content[:200].replace('\n', ' ')
                if content: typer.echo(f"  response: {preview}{'...' if len(content) > 200 else ''}")
                if t.get('error'): typer.echo(f"  error:    {t['error']}")
            typer.echo(f"{'─'*72}")
        else:
            typer.echo(f"{'TASK_ID':<38} {'STATE':<12} {'MODEL':<20} {'AGENT':<16} {'SUBMITTED':<10}")
            typer.echo("-" * 98)
            for t in tasks:
                # Format created_at (ISO 8601) to HH:MM:SS
                created = t.get("created_at", "")
                ts_str = created.split("T")[-1][:8] if "T" in created else created[:8]
                
                agent_display = t.get("agent_name") or (f"..{t['agent_id'][-12:]}" if t.get("agent_id") else "-")
                
                typer.echo(f"{t['task_id']:<38} {t['state']:<12} {t['model']:<20} {agent_display:<16} {ts_str:<10}")
    except Exception as exc: typer.echo(f"Error: {exc}", err=True); raise typer.Exit(1)

@app.command("logs")
def logs(hub_url: str = typer.Option(""), follow: bool = typer.Option(False, "--follow", "-f"),
         interval: float = typer.Option(5.0), limit: int = typer.Option(20)):
    """Show recent pulse log entries."""
    cfg = load_config(); url = (hub_url or cfg["hub_urls"][0]).rstrip("/")
    seen_ids: set = set()
    try:
        while True:
            entries = httpx.get(f"{url}/logs?limit={limit}", timeout=5.0).json().get("logs", [])
            for e in reversed(entries):
                eid = e.get("id")
                if eid not in seen_ids:
                    seen_ids.add(eid)
                    typer.echo(f"[{e.get('logged_at','')}] {e.get('agent_id','')} status={e.get('status','')} tps={e.get('current_tps',0):.1f}")
            if not follow: break
            time.sleep(interval)
    except KeyboardInterrupt: pass
    except Exception as exc: typer.echo(f"Error: {exc}", err=True); raise typer.Exit(1)

@app.command("submit")
def submit_task(prompt: str = typer.Argument(...), model: str = typer.Option("llama3"),
                hub_url: str = typer.Option(""), max_tokens: int = typer.Option(1024),
                wait: bool = typer.Option(True)):
    """Submit a single inference task."""
    cfg = load_config(); url = (hub_url or cfg["hub_urls"][0]).rstrip("/")
    task_id = str(uuid.uuid4())
    try:
        httpx.post(f"{url}/tasks", json={"task_id":task_id,"model":model,"prompt":prompt,"max_tokens":max_tokens}, timeout=10.0).raise_for_status()
        typer.echo(f"Task submitted: {task_id}")
        if wait:
            deadline = time.monotonic() + 300; interval = 2.0
            with httpx.Client(timeout=5.0) as client:
                while time.monotonic() < deadline:
                    data = client.get(f"{url}/tasks/{task_id}").json(); state = data.get("state","")
                    if state == "COMPLETE":
                        result = data.get("result",{}); typer.echo(f"\n{result.get('content','')}")
                        typer.echo(f"[model={result.get('model')} tokens={result.get('input_tokens',0)}+{result.get('output_tokens',0)} latency={result.get('latency_ms',0):.0f}ms]")
                        break
                    if state == "FAILED": typer.echo(f"FAILED: {data.get('result',{}).get('error','unknown')}", err=True); break
                    time.sleep(interval); interval = min(interval*1.3, 10.0)
    except Exception as exc: typer.echo(f"Error: {exc}", err=True); raise typer.Exit(1)

@app.command("run")
def run_spl(spl_file: str = typer.Argument(...), hub_url: str = typer.Option(""),
            params: Optional[str] = typer.Option(None)):
    """Execute an SPL file on the grid."""
    cfg = load_config()
    try:
        from igrid.spl.runner import run_spl_file
        asyncio.run(run_spl_file(spl_file, hub_url or cfg["hub_urls"][0], json.loads(params) if params else {}))
    except ImportError: typer.echo("SPL package required.", err=True); raise typer.Exit(1)
    except Exception as exc: typer.echo(f"Error: {exc}", err=True); raise typer.Exit(1)

@peer_app.command("add")
def peer_add(peer_url: str = typer.Argument(...), hub_url: str = typer.Option("")):
    """Add a peer hub to the cluster."""
    cfg = load_config(); url = (hub_url or cfg["hub_urls"][0]).rstrip("/")
    try:
        data = httpx.post(f"{url}/cluster/peers", json={"url": peer_url}, timeout=10.0).json()
        typer.echo(f"Peer {data.get('hub_id')} {'added' if data.get('accepted') else 'rejected: ' + data.get('message','')}")
    except Exception as exc: typer.echo(f"Error: {exc}", err=True); raise typer.Exit(1)

@peer_app.command("list")
def peer_list(hub_url: str = typer.Option("")):
    """List peer hubs."""
    cfg = load_config(); url = (hub_url or cfg["hub_urls"][0]).rstrip("/")
    try:
        data = httpx.get(f"{url}/cluster/status", timeout=5.0).json()
        typer.echo(f"This hub: {data.get('this_hub_id')}")
        peers = data.get("peers", [])
        if not peers: typer.echo("No peer hubs."); return
        for p in peers: typer.echo(f"  {p.get('hub_id')} {p.get('hub_url')} [{p.get('status')}]")
    except Exception as exc: typer.echo(f"Error: {exc}", err=True); raise typer.Exit(1)

@app.command("rewards")
def rewards(hub_url: str = typer.Option("")):
    """Show reward summary."""
    cfg = load_config(); url = (hub_url or cfg["hub_urls"][0]).rstrip("/")
    try:
        rows = httpx.get(f"{url}/rewards", timeout=5.0).json().get("summary", [])
        if not rows: typer.echo("No rewards yet."); return
        typer.echo(f"{'OPERATOR':<20} {'TASKS':>8} {'TOKENS':>12} {'CREDITS':>10}")
        for r in rows: typer.echo(f"{r.get('operator_id',''):<20} {r.get('total_tasks',0):>8} {r.get('total_tokens',0):>12} {r.get('total_credits',0.0):>10.2f}")
    except Exception as exc: typer.echo(f"Error: {exc}", err=True); raise typer.Exit(1)

@app.command("watchlist")
def watchlist(hub_url: str = typer.Option("")):
    """Show watchlist entries (suspended/blocked IPs, operators, agents)."""
    cfg = load_config(); url = (hub_url or cfg["hub_urls"][0]).rstrip("/")
    try:
        entries = httpx.get(f"{url}/watchlist", timeout=5.0).json().get("entries", [])
        if not entries: typer.echo("Watchlist is empty."); return
        typer.echo(f"{'TYPE':<10} {'ENTITY_ID':<40} {'ACTION':<12} {'REASON':<30} {'EXPIRES_AT':<25}")
        typer.echo("-" * 117)
        for e in entries:
            typer.echo(f"{e.get('entity_type',''):<10} {e.get('entity_id',''):<40} {e.get('action',''):<12} {e.get('reason',''):<30} {e.get('expires_at','permanent'):<25}")
    except Exception as exc: typer.echo(f"Error: {exc}", err=True); raise typer.Exit(1)

@app.command("unblock")
def unblock(entity_id: str = typer.Argument(..., help="IP, operator_id, or agent_id to unblock"),
            hub_url: str = typer.Option("")):
    """Remove an entity from the watchlist."""
    cfg = load_config(); url = (hub_url or cfg["hub_urls"][0]).rstrip("/")
    try:
        resp = httpx.delete(f"{url}/watchlist/{entity_id}", timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
        if data.get("ok"):
            typer.echo(f"Unblocked: {entity_id}")
        else:
            typer.echo(f"Not found on watchlist: {entity_id}")
    except Exception as exc: typer.echo(f"Error: {exc}", err=True); raise typer.Exit(1)

@app.command("export")
def export_results(hub_url: str = typer.Option(""),
                   output: str = typer.Option("", "--output", "-o", help="Output file path (default: results-<hub_id>.json)"),
                   label: str = typer.Option("", "--label", "-l", help="Label for this test run (e.g. 'hub-on-machine-A')"),
                   limit: int = typer.Option(500)):
    """Export completed task results to a JSON file for offline analysis."""
    from datetime import datetime
    cfg = load_config(); url = (hub_url or cfg["hub_urls"][0]).rstrip("/")
    try:
        health = httpx.get(f"{url}/health", timeout=5.0).json()
        hub_id = health.get("hub_id", "unknown")
        tasks = httpx.get(f"{url}/tasks?limit={limit}", timeout=10.0).json().get("tasks", [])
        agents = httpx.get(f"{url}/agents", timeout=5.0).json().get("agents", [])
        rewards = httpx.get(f"{url}/rewards", timeout=5.0).json().get("summary", [])
        export_data = {
            "label": label or hub_id,
            "hub_id": hub_id,
            "hub_url": url,
            "exported_at": datetime.utcnow().isoformat() + "Z",
            "agents": agents,
            "rewards": rewards,
            "tasks": tasks,
        }
        out_path = output or f"results-{label or hub_id}.json"
        with open(out_path, "w") as f:
            json.dump(export_data, f, indent=2)
        completed = sum(1 for t in tasks if t.get("state") == "COMPLETE")
        typer.echo(f"Exported {len(tasks)} tasks ({completed} completed) to {out_path}")
    except Exception as exc: typer.echo(f"Error: {exc}", err=True); raise typer.Exit(1)

@app.command("test")
def test_run(hub_url: str = typer.Option(""),
             prompts_file: str = typer.Option("", "--prompts", "-p", help="Path to prompts JSON file (default: tests/lan/prompts.json)"),
             category: Optional[str] = typer.Option(None, "--category", "-c", help="Run only this category (default: all)"),
             concurrency: int = typer.Option(1, "--concurrency", "-j", help="Parallel task submissions"),
             repeat: int = typer.Option(1, "--repeat", "-r", help="Repeat the batch N times"),
             timeout: int = typer.Option(300, "--timeout", help="Per-task timeout in seconds"),
             label: str = typer.Option("", "--label", "-l", help="Label for this test run"),
             output: str = typer.Option("", "--output", "-o", help="Save results to JSON file"),
             list_categories: bool = typer.Option(False, "--list", help="List available categories and exit")):
    """Run test prompts against the grid and report results."""
    from tests.e2e.runner import load_prompts, run_categories
    cfg = load_config(); url = (hub_url or cfg["hub_urls"][0]).rstrip("/")
    try:
        prompts_dict = load_prompts(prompts_file or None)
    except FileNotFoundError:
        typer.echo("Prompts file not found. Use --prompts to specify path.", err=True)
        raise typer.Exit(1)
    if list_categories:
        for cat, entries in prompts_dict.items():
            typer.echo(f"  {cat:<30s} ({len(entries)} prompts)")
        raise typer.Exit(0)
    cats = [category] if category else None
    total = sum(len(v) for k, v in prompts_dict.items() if cats is None or k in cats) * repeat
    typer.echo(f"Running {total} tasks  concurrency={concurrency}  repeat={repeat}  hub={url}")
    typer.echo("")
    done = {"n": 0}
    def on_result(r):
        done["n"] += 1
        status = "OK" if r.state == "COMPLETE" else r.state
        tps_str = f"{r.tps:.1f} tps" if r.tps > 0 else ""
        typer.echo(f"  [{done['n']:>3}/{total}] {status:<8} {r.model:<20} {r.latency_ms:>8.0f}ms  {r.output_tokens:>5} tok  {tps_str:>10}  {r.agent_id}")
    report = run_categories(url, prompts_dict, categories=cats, concurrency=concurrency,
                            timeout_s=timeout, repeat=repeat, on_result=on_result,
                            label=label or "test")
    s = report.summary()
    typer.echo("")
    typer.echo(f"{'─'*72}")
    typer.echo(f"  Total:     {s['total']}  |  Completed: {s['completed']}  |  Failed: {s['failed']}  |  Timeout: {s['timed_out']}")
    if s.get("avg_latency_ms"):
        typer.echo(f"  Avg latency: {s['avg_latency_ms']:.0f}ms  |  Avg TPS: {s['avg_tps']:.1f}  |  Wall time: {s['wall_time_s']:.1f}s")
    if s.get("agent_distribution"):
        typer.echo(f"  Agent distribution:")
        for agent, count in sorted(s["agent_distribution"].items()):
            typer.echo(f"    {agent}: {count} tasks")
    if output:
        with open(output, "w") as f:
            json.dump(report.to_json(), f, indent=2)
        typer.echo(f"  Results saved to {output}")

@app.command("config")
def config_cmd(set_key: Optional[str] = typer.Option(None, "--set"), show: bool = typer.Option(True)):
    """View or update ~/.igrid/config.yaml."""
    if set_key:
        if "=" not in set_key: typer.echo("Use --set key=value", err=True); raise typer.Exit(1)
        k, v = set_key.split("=", 1); cfg = load_config(); cfg[k.strip()] = v.strip(); save_config(cfg)
        typer.echo(f"Set {k.strip()} = {v.strip()}")
    if show:
        for k, v in show_config().items(): typer.echo(f"  {k}: {v}")

if __name__ == "__main__":
    app()
