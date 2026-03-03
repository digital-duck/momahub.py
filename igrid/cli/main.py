"""moma CLI — i-grid command-line interface.
Note: Typer is used (built on Click under the hood).
"""
from __future__ import annotations
import asyncio, json, time, uuid
from typing import Optional
import httpx, typer, uvicorn
from igrid.cli.config import load_config, save_config, show_config

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
           operator_id: str = typer.Option(""), api_key: str = typer.Option("")):
    """Start the hub server."""
    cfg = load_config()
    from igrid.hub.app import create_app
    fastapi_app = create_app(operator_id=operator_id or cfg["operator_id"],
                              db_path=db or cfg["db_path"],
                              hub_url=hub_url or f"http://{host}:{port}",
                              api_key=api_key or cfg["api_key"])
    typer.echo(f"Starting hub on {host}:{port}")
    uvicorn.run(fastapi_app, host=host, port=port, log_level="info")

@hub_app.command("down")
def hub_down(): typer.echo("Use Ctrl+C or your process manager to stop the hub.")

@agent_app.command("up")
def agent_up(host: str = typer.Option("0.0.0.0"), port: int = typer.Option(8100),
             join: str = typer.Option(""), operator_id: str = typer.Option(""),
             ollama_url: str = typer.Option(""), api_key: str = typer.Option("")):
    """Start the agent node."""
    cfg = load_config()
    hub_urls = [u.strip() for u in join.split(",") if u.strip()] if join else cfg["hub_urls"]
    from igrid.agent.worker import create_agent_app
    agent_app_instance = create_agent_app(operator_id=operator_id or cfg["operator_id"],
                                          hub_urls=hub_urls, ollama_url=ollama_url or cfg["ollama_url"],
                                          api_key=api_key or cfg["api_key"])
    agent_app_instance.state.host = host if host != "0.0.0.0" else "127.0.0.1"
    agent_app_instance.state.port = port
    typer.echo(f"Starting agent on {host}:{port}  hubs={hub_urls}")
    uvicorn.run(agent_app_instance, host=host, port=port, log_level="info")

@app.command("join")
def join_grid(hub_urls: list[str] = typer.Argument(...),
              host: str = typer.Option("0.0.0.0"), port: int = typer.Option(8100),
              operator_id: str = typer.Option(""), ollama_url: str = typer.Option("")):
    """Start an agent and join hub(s)."""
    cfg = load_config()
    from igrid.agent.worker import create_agent_app
    agent_app_instance = create_agent_app(operator_id=operator_id or cfg["operator_id"],
                                          hub_urls=hub_urls, ollama_url=ollama_url or cfg["ollama_url"])
    agent_app_instance.state.host = host if host != "0.0.0.0" else "127.0.0.1"
    agent_app_instance.state.port = port
    typer.echo(f"Joining grid: hubs={hub_urls}")
    uvicorn.run(agent_app_instance, host=host, port=port, log_level="info")

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
        typer.echo(f"{'AGENT_ID':<38} {'TIER':<10} {'STATUS':<10} {'TPS':>6}")
        typer.echo("-"*70)
        for a in agents:
            typer.echo(f"{a['agent_id']:<38} {a['tier']:<10} {a['status']:<10} {a['current_tps']:>6.1f}")
    except Exception as exc: typer.echo(f"Error: {exc}", err=True); raise typer.Exit(1)

@app.command("tasks")
def list_tasks(hub_url: str = typer.Option(""), limit: int = typer.Option(20)):
    """List recent tasks."""
    cfg = load_config(); url = (hub_url or cfg["hub_urls"][0]).rstrip("/")
    try:
        tasks = httpx.get(f"{url}/tasks?limit={limit}", timeout=5.0).json().get("tasks", [])
        if not tasks: typer.echo("No tasks."); return
        typer.echo(f"{'TASK_ID':<38} {'STATE':<12} {'MODEL':<20}")
        typer.echo("-"*72)
        for t in tasks: typer.echo(f"{t['task_id']:<38} {t['state']:<12} {t['model']:<20}")
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
