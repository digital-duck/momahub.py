"""SPL runner: parse and execute .spl files on the i-grid."""
from __future__ import annotations
import logging
import typer

_log = logging.getLogger("igrid.spl.runner")

async def run_spl_file(spl_path: str, hub_url: str, params: dict | None = None) -> None:
    try:
        from spl.parser import Parser
        from spl.optimizer import Optimizer
        from spl.executor import Executor
        from igrid.spl.igrid_adapter import IGridAdapter
    except ImportError as exc:
        raise RuntimeError("SPL package not found. Install it: pip install -e /path/to/SPL") from exc
    with open(spl_path) as f: source = f.read()
    stmts = Parser(source).parse()
    optimizer = Optimizer()
    executor = Executor(adapter=IGridAdapter(hub_url=hub_url))
    try:
        for stmt in stmts:
            plan = optimizer.optimize_single(stmt)
            result = await executor.execute(plan, params=params or {}, stmt=stmt)
            typer.echo(f"\n=== {plan.prompt_name} ===")
            typer.echo(result.content)
            typer.echo(f"\n[model={result.model}  tokens={result.input_tokens}+{result.output_tokens}  latency={result.latency_ms:.0f}ms]")
    finally:
        executor.close()
