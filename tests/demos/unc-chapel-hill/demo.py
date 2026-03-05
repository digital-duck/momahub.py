#!/usr/bin/env python3
"""
MoMaHub Demo for Prof. Lu Jianping — UNC Chapel Hill
=====================================================

A guided demo of the i-grid distributed AI inference network.
Designed for a LAN with 3x GTX 1080 Ti nodes.

Potential collaboration: measuring eta_AI = generated bits per joule,
bridging physics, information theory, and AI economics.

Demo flow:
    Step 0: Grid status         -- show agents online, tiers, GPUs
    Step 1: Stress test          -- all 3 GPUs fire simultaneously, throughput
    Step 2: Model arena          -- same prompt to 3 models, side-by-side
    Step 3: Chain relay          -- multi-step reasoning across nodes
    Step 4: Batch translate      -- 1 text to 5 languages in parallel
    Step 5: Energy efficiency    -- tokens/s vs watts -> eta_AI estimate

Usage:
    python demo.py                            # interactive, step by step
    python demo.py --step 1                   # run only stress test
    python demo.py --hub http://192.168.1.10:8000
    python demo.py --all                      # run all steps non-interactively

Prerequisites:
    - Hub running:  moma hub up --host 0.0.0.0 --port 8000
    - 3 agents:     moma join http://<hub-ip>:8000 --name alice
                    moma join http://<hub-ip>:8000 --name bob
                    moma join http://<hub-ip>:8000 --name charlie
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import click
import httpx

COOKBOOK = Path(__file__).resolve().parent.parent.parent / "cookbook"


def _banner(title: str):
    click.echo(f"\n{'='*60}")
    click.echo(f"  {title}")
    click.echo(f"{'='*60}\n")


def _pause():
    click.echo()
    click.pause("  Press any key to continue...")
    click.echo()


def step_0_status(hub: str):
    """Show grid status: agents, tiers, models."""
    _banner("Step 0: Grid Status")
    try:
        health = httpx.get(f"{hub}/health", timeout=5.0).json()
        click.echo(f"  Hub:     {health.get('hub_id')}")
        click.echo(f"  Status:  {health.get('status')}")
        click.echo(f"  Agents:  {health.get('agents_online')}")
        click.echo()

        agents = httpx.get(f"{hub}/agents", timeout=5.0).json().get("agents", [])
        if agents:
            click.echo(f"  {'NAME':<14} {'TIER':<10} {'STATUS':<10} {'TPS':>6}  GPU")
            click.echo(f"  {'-'*55}")
            for a in agents:
                import json
                gpus = json.loads(a.get("gpus", "[]")) if isinstance(a.get("gpus"), str) else a.get("gpus", [])
                gpu_name = gpus[0].get("model", "?") if gpus else "CPU"
                click.echo(f"  {a.get('name',''):<14} {a['tier']:<10} {a['status']:<10} "
                           f"{a['current_tps']:>6.1f}  {gpu_name}")
        else:
            click.echo("  No agents online. Start agents with: moma join <hub-url>")
    except Exception as exc:
        click.echo(f"  Could not reach hub: {exc}")


def step_1_stress(hub: str, model: str):
    """Stress test: fire 15 tasks, watch them fan out."""
    _banner("Step 1: Stress Test (15 tasks)")
    click.echo("  Firing 15 tasks at the grid...")
    click.echo("  Watch all 3 GPUs light up simultaneously.\n")
    subprocess.run([
        sys.executable, str(COOKBOOK / "07_stress_test" / "stress.py"),
        "--hub", hub, "-n", "15", "--model", model, "--concurrency", "15",
    ])


def step_2_arena(hub: str, model: str):
    """Model arena: same prompt to multiple models."""
    _banner("Step 2: Model Arena")
    click.echo("  Same question to 3 models. Which answers best?\n")
    models = f"{model},mistral,phi3"
    subprocess.run([
        sys.executable, str(COOKBOOK / "08_model_arena" / "arena.py"),
        "--hub", hub, "--models", models,
        "--prompt", "Explain the relationship between information entropy and "
                    "thermodynamic entropy. Can we define a universal efficiency "
                    "metric for AI inference in bits per joule?",
    ])


def step_3_chain(hub: str, model: str):
    """Chain relay: multi-step reasoning across nodes."""
    _banner("Step 3: Chain Relay")
    click.echo("  3-step reasoning chain: Research -> Analyze -> Summarize")
    click.echo("  Watch tasks hop between different agents.\n")
    subprocess.run([
        sys.executable, str(COOKBOOK / "10_chain_relay" / "chain.py"),
        "--hub", hub, "--model", model,
        "eta_AI: measuring AI inference efficiency in generated bits per joule, "
        "bridging Landauer's principle, Shannon entropy, and GPU energy consumption",
    ])


def step_4_translate(hub: str, model: str):
    """Batch translate: 1 text to 5 languages in parallel."""
    _banner("Step 4: Batch Translate (5 languages)")
    click.echo("  All agents working in parallel on different languages.\n")
    subprocess.run([
        sys.executable, str(COOKBOOK / "11_batch_translate" / "translate.py"),
        "--hub", hub, "--model", model,
        "Distributed AI inference allows multiple GPUs across a network to "
        "collaborate on language model tasks. By measuring the tokens generated "
        "per joule of energy consumed, we can define eta_AI, a fundamental "
        "efficiency metric that bridges information theory and thermodynamics.",
    ])


def step_5_energy(hub: str):
    """Energy efficiency discussion and measurement sketch."""
    _banner("Step 5: eta_AI -- Bits per Joule")
    click.echo("""  Proposed metric:

    eta_AI = generated_bits / energy_joules
           = (output_tokens * bits_per_token) / (watts * seconds)

  Where:
    - output_tokens:    from Ollama eval_count
    - bits_per_token:   ~10-12 bits (log2 of vocab size, adjusted for entropy)
    - watts:            GPU TDP or measured via nvidia-smi power draw
    - seconds:          eval_duration from Ollama

  For GTX 1080 Ti (250W TDP, ~35-45 TPS with llama3:8b):
    - 40 tokens/s * 11 bits/token = 440 bits/s
    - At 200W actual draw: eta_AI = 440 / 200 = 2.2 bits/joule

  Comparison points:
    - Human brain:     ~10^13 bits/s at ~20W  -> ~5 * 10^11 bits/joule
    - Landauer limit:  kT * ln(2) per bit     -> ~3 * 10^21 bits/joule at 300K
    - A100 GPU:        ~100 TPS * 11 bits     -> ~3.7 bits/joule at 300W
    - GTX 1080 Ti:     ~40 TPS * 11 bits      -> ~2.2 bits/joule at 200W

  The gap between current GPUs and Landauer's limit is ~21 orders of magnitude.
  Understanding this gap is where physics meets AI economics.

  Experiment idea:
    1. Run stress test with nvidia-smi logging power draw (1s interval)
    2. Correlate total tokens generated with total energy consumed
    3. Vary: model size, batch size, quantization level
    4. Plot eta_AI vs model_size -- does scaling law hold for efficiency?
""")
    # Show current grid stats if available
    try:
        tasks = httpx.get(f"{hub}/tasks?limit=100", timeout=5.0).json().get("tasks", [])
        completed = [t for t in tasks if t.get("state") == "COMPLETE"]
        if completed:
            total_tokens = sum(t.get("output_tokens", 0) for t in completed)
            total_ms = sum(t.get("latency_ms", 0) for t in completed)
            click.echo(f"  Grid session stats:")
            click.echo(f"    Tasks completed: {len(completed)}")
            click.echo(f"    Total tokens:    {total_tokens:,}")
            click.echo(f"    Total time:      {total_ms/1000:.1f}s")
            if total_ms > 0:
                avg_tps = total_tokens / (total_ms / 1000)
                click.echo(f"    Avg throughput:  {avg_tps:.1f} tokens/s")
                eta = avg_tps * 11 / 200  # rough estimate at 200W
                click.echo(f"    eta_AI estimate: ~{eta:.1f} bits/joule (at ~200W)")
    except Exception:
        pass


STEPS = {
    0: ("Grid Status", step_0_status),
    1: ("Stress Test", step_1_stress),
    2: ("Model Arena", step_2_arena),
    3: ("Chain Relay", step_3_chain),
    4: ("Batch Translate", step_4_translate),
    5: ("eta_AI Discussion", step_5_energy),
}


@click.command()
@click.option("--hub", default="http://localhost:8000", show_default=True)
@click.option("--model", default="llama3", show_default=True)
@click.option("--step", default=-1, type=int, help="Run only this step (0-5)")
@click.option("--all", "run_all", is_flag=True, help="Run all steps non-interactively")
def main(hub, model, step, run_all):
    """MoMaHub demo for Prof. Lu Jianping (UNC Chapel Hill).

    Interactive walkthrough of the i-grid distributed inference network.
    """
    hub = hub.rstrip("/")

    if step >= 0:
        # Single step mode
        if step not in STEPS:
            click.echo(f"Invalid step {step}. Choose 0-5.")
            return
        name, fn = STEPS[step]
        if step in (1, 2, 3, 4):
            fn(hub, model)
        else:
            fn(hub)
        return

    # Interactive / run-all mode
    click.echo("""
    ================================================================
        MoMaHub i-grid Demo
        For: Prof. Lu Jianping, UNC Chapel Hill
        Topic: Distributed AI Inference & eta_AI (bits/joule)
    ================================================================
    """)

    for i, (name, fn) in STEPS.items():
        if not run_all:
            click.echo(f"\n  Next: Step {i} - {name}")
            if not click.confirm("  Run this step?", default=True):
                continue
        if i in (1, 2, 3, 4):
            fn(hub, model)
        else:
            fn(hub)
        if not run_all and i < max(STEPS):
            _pause()

    _banner("Demo Complete")
    click.echo("  Thank you, Prof. Lu!")
    click.echo("  Collaboration topic: eta_AI = bits/joule")
    click.echo("  Repo: github.com/digital-duck/momahub.py\n")


if __name__ == "__main__":
    main()
