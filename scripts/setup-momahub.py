#!/usr/bin/env python3
"""setup-momahub.py — One-command node bootstrap for Momahub (Momahub).

Idempotent: safe to re-run. Handles GPU check, Ollama install,
model pull, pip install, smoke test, and prints the join command.

Usage:
    python setup-momahub.py                         # defaults (llama3)
    python setup-momahub.py --models llama3 mistral  # pull multiple models
    python setup-momahub.py --skip-ollama            # skip Ollama install/pull
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# ── Helpers ──────────────────────────────────────────────────────

GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
NC = "\033[0m"


def info(msg: str) -> None:
    print(f"{GREEN}[INFO]{NC}  {msg}")


def warn(msg: str) -> None:
    print(f"{YELLOW}[WARN]{NC}  {msg}")


def error(msg: str) -> None:
    print(f"{RED}[ERROR]{NC} {msg}")


def run(cmd: list[str], check: bool = True, capture: bool = False,
        **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, capture_output=capture,
                          text=True, **kwargs)


def cmd_exists(name: str) -> bool:
    return shutil.which(name) is not None


def detect_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def ollama_api(endpoint: str, payload: dict | None = None,
               timeout: float = 5.0) -> dict | None:
    """Quick HTTP call to local Ollama API (no httpx dependency needed)."""
    import urllib.request
    import urllib.error
    url = f"http://localhost:11434{endpoint}"
    try:
        if payload is not None:
            data = json.dumps(payload).encode()
            req = urllib.request.Request(url, data=data,
                                         headers={"Content-Type": "application/json"})
        else:
            req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


# ── Stages ───────────────────────────────────────────────────────

def stage_gpu() -> None:
    info("Stage 1/5: Checking GPU...")
    if not cmd_exists("nvidia-smi"):
        warn("nvidia-smi not found — will run CPU-only (slower inference).")
        return
    result = run(["nvidia-smi", "--query-gpu=name,memory.total",
                  "--format=csv,noheader"], check=False, capture=True)
    if result.returncode == 0 and result.stdout.strip():
        info(f"GPU detected: {result.stdout.strip()}")
    else:
        warn("nvidia-smi found but no GPU reported — will run CPU-only.")


def stage_ollama() -> None:
    info("Stage 2/5: Checking Ollama...")
    if cmd_exists("ollama"):
        result = run(["ollama", "--version"], check=False, capture=True)
        ver = result.stdout.strip() if result.returncode == 0 else "unknown version"
        info(f"Ollama already installed: {ver}")
    else:
        info("Installing Ollama...")
        if platform.system() == "Windows":
            error("Auto-install not supported on Windows. "
                  "Download from https://ollama.com/download/windows")
            sys.exit(1)
        run(["bash", "-c", "curl -fsSL https://ollama.com/install.sh | sh"])
        info("Ollama installed.")

    # Ensure Ollama is running
    if ollama_api("/api/version") is not None:
        info("Ollama is running.")
        return

    info("Starting Ollama service...")
    if cmd_exists("systemctl"):
        result = run(["sudo", "systemctl", "start", "ollama"], check=False, capture=True)
        if result.returncode != 0:
            subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
    else:
        subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)

    time.sleep(3)
    if ollama_api("/api/version") is None:
        error("Could not start Ollama. Please start it manually: ollama serve")
        sys.exit(1)
    info("Ollama is running.")


def stage_pull(models: list[str]) -> None:
    info("Stage 3/5: Pulling models...")
    result = run(["ollama", "list"], check=False, capture=True)
    existing = result.stdout if result.returncode == 0 else ""

    for model in models:
        short = model.split(":")[0]
        if short in existing:
            info(f"  {model} — already present.")
        else:
            info(f"  Pulling {model} (this may take a while)...")
            run(["ollama", "pull", model])


def stage_install() -> None:
    info("Stage 4/5: Installing Momahub...")
    result = run([sys.executable, "-m", "pip", "show", "moma-hub"],
                 check=False, capture=True)
    if result.returncode == 0:
        info("moma-hub already installed.")
    else:
        run([sys.executable, "-m", "pip", "install", "-e", f"{SCRIPT_DIR}[dev]"])
        info("moma-hub installed.")


def stage_smoke(model: str) -> None:
    info("Stage 5/5: Smoke test...")
    resp = ollama_api("/api/generate", {
        "model": model,
        "prompt": "Say hello in 5 words.",
        "stream": False,
    }, timeout=60.0)
    if resp and resp.get("response"):
        text = resp["response"][:80]
        info(f"Smoke test passed: {text}")
    else:
        warn("Smoke test failed — Ollama may still be loading the model. Try again in a minute.")


# ── Main ─────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="One-command node bootstrap for Momahub (Momahub).")
    parser.add_argument("--models", nargs="+", default=["llama3"],
                        help="Models to pull (default: llama3)")
    parser.add_argument("--skip-ollama", action="store_true",
                        help="Skip Ollama install/start/pull stages")
    args = parser.parse_args()

    stage_gpu()

    if not args.skip_ollama:
        stage_ollama()
        stage_pull(args.models)

    stage_install()

    if not args.skip_ollama:
        stage_smoke(args.models[0])

    lan_ip = detect_lan_ip()

    print()
    info("=== Setup complete ===")
    print()
    print("  To start a hub on this machine:")
    print("    moma hub up --host 0.0.0.0 --port 8000")
    print()
    print("  To join an existing hub as an agent:")
    print(f"    moma join http://<HUB_IP>:8000 --host {lan_ip} --port 8100")
    print()
    print(f"  This machine's LAN IP: {lan_ip}")
    print()


if __name__ == "__main__":
    main()
