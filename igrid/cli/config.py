"""CLI configuration: ~/.igrid/config.yaml

Schema matches the Go implementation (momahub.go/.igrid/config.yaml) so both
binaries share a single config file.

Go structure → Python keys:
  operator_id          → cfg["operator_id"]
  hub.host             → cfg["hub"]["host"]
  hub.port             → cfg["hub"]["port"]
  hub.db_path          → cfg["hub"]["db_path"]
  hub.api_key          → cfg["hub"]["api_key"]
  hub.urls             → cfg["hub"]["urls"]
  agent.host           → cfg["agent"]["host"]
  agent.port           → cfg["agent"]["port"]
  agent.id             → cfg["agent"]["id"]
  agent.name           → cfg["agent"]["name"]
  agent.ollama_url     → cfg["agent"]["ollama_url"]
  moma_ui.host         → cfg["moma_ui"]["host"]      (Python equiv of mgui)
  moma_ui.port         → cfg["moma_ui"]["port"]
  moma_ui.*_api_key    → cfg["moma_ui"]["*_api_key"]
"""
from __future__ import annotations
import copy
from pathlib import Path
import yaml

_CONFIG_DIR = Path.home() / ".igrid"
_CONFIG_FILE = _CONFIG_DIR / "config.yaml"

_DEFAULTS: dict = {
    "operator_id": "duck",
    "hub": {
        "host":     "0.0.0.0",
        "port":     8000,
        "db_path":  ".igrid/hub.sqlite",
        "api_key":  "",
        "urls":     ["http://localhost:8000"],
    },
    "agent": {
        "host":        "0.0.0.0",
        "port":        8100,
        "id":          "",
        "name":        "",
        "ollama_url":  "http://localhost:11434",
    },
    "moma_ui": {
        "host":               "127.0.0.1",
        "port":               8501,
        "fallback_chain":     ["momagrid"],
        "openai_api_key":     "",
        "anthropic_api_key":  "",
        "google_api_key":     "",
        "openrouter_api_key": "",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base (override wins on conflicts)."""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_config() -> dict:
    if _CONFIG_FILE.exists():
        with open(_CONFIG_FILE) as f:
            user = yaml.safe_load(f) or {}
        return _deep_merge(_DEFAULTS, user)
    return _deep_merge(_DEFAULTS, {})


def save_config(cfg: dict) -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_FILE, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False)


def hub_url(cfg: dict) -> str:
    """Return the first configured hub URL."""
    urls = cfg.get("hub", {}).get("urls", _DEFAULTS["hub"]["urls"])
    return (urls[0] if urls else "http://localhost:8000").rstrip("/")


def show_config() -> dict:
    display = copy.deepcopy(load_config())
    if display.get("hub", {}).get("api_key"):
        display["hub"]["api_key"] = "***"
    for key in ("openai_api_key", "anthropic_api_key", "google_api_key", "openrouter_api_key"):
        if display.get("moma_ui", {}).get(key):
            display["moma_ui"][key] = "***"
    return display
