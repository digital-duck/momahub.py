"""CLI configuration: ~/.igrid/config.yaml"""
from __future__ import annotations
from pathlib import Path
import yaml

_CONFIG_DIR = Path.home() / ".igrid"
_CONFIG_FILE = _CONFIG_DIR / "config.yaml"
_DEFAULTS = {"operator_id": "duck", "hub_host": "0.0.0.0", "hub_port": 8000,
             "agent_host": "0.0.0.0", "agent_port": 8100,
             "hub_urls": ["http://localhost:8000"], "db_path": ".igrid/hub.db",
             "ollama_url": "http://localhost:11434", "api_key": ""}

def load_config() -> dict:
    if _CONFIG_FILE.exists():
        with open(_CONFIG_FILE) as f: user = yaml.safe_load(f) or {}
        return {**_DEFAULTS, **user}
    return dict(_DEFAULTS)

def save_config(cfg: dict) -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_FILE, "w") as f: yaml.dump(cfg, f, default_flow_style=False)

def show_config() -> dict:
    cfg = load_config()
    if cfg.get("api_key"): cfg["api_key"] = "***"
    return cfg
