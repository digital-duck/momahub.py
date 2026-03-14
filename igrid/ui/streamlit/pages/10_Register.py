"""10_Register.py — Agent Registration & Provider API Keys

Two tabs:
  1. Join Grid — Register this machine as a Momagrid/Momahub agent
  2. API Keys  — Configure cloud provider keys for the Unified Chatbot
"""
import json
import os
import platform
import uuid

import httpx
import streamlit as st
from pathlib import Path

HUB_URL = os.environ.get("IGRID_HUB_URL", "http://localhost:8000")
PROVIDERS_FILE = Path.home() / ".igrid" / "providers.yaml"

st.set_page_config(page_title="Register & Config", page_icon="🔧", layout="wide")
st.title("🔧 Register & Configure")
st.caption(
    "Register this machine as a grid agent, or set API keys for cloud providers "
    "used by the Unified Chatbot."
)

# ── Sidebar ──────────────────────────────────────────────────────────────────
hub_url = st.sidebar.text_input("Hub URL", value=HUB_URL)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _probe_hub(url: str) -> dict:
    try:
        r = httpx.get(f"{url}/health", timeout=4.0)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        return {"error": str(exc)}


def _probe_ollama(ollama_url: str) -> list:
    """Return list of model names from local Ollama instance."""
    try:
        r = httpx.get(f"{ollama_url}/api/tags", timeout=4.0)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []


def _join_hub(url: str, payload: dict) -> dict:
    try:
        r = httpx.post(f"{url}/join", json=payload, timeout=10.0)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as exc:
        return {"error": f"HTTP {exc.response.status_code}: {exc.response.text[:300]}"}
    except Exception as exc:
        return {"error": str(exc)}


def _save_providers(keys: dict):
    """Save keys to ~/.igrid/providers.yaml (or .json fallback)."""
    PROVIDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        import yaml  # PyYAML
        with open(PROVIDERS_FILE, "w") as f:
            yaml.safe_dump(keys, f)
    except ImportError:
        # Fallback to JSON if PyYAML not installed
        fallback = PROVIDERS_FILE.with_suffix(".json")
        fallback.write_text(json.dumps(keys, indent=2))


def _load_providers() -> dict:
    """Load keys from disk (yaml or json fallback)."""
    try:
        import yaml
        if PROVIDERS_FILE.exists():
            return yaml.safe_load(PROVIDERS_FILE.read_text()) or {}
    except ImportError:
        fallback = PROVIDERS_FILE.with_suffix(".json")
        if fallback.exists():
            return json.loads(fallback.read_text())
    except Exception:
        pass
    return {}


# ── Load saved keys once per session ──────────────────────────────────────────
if "providers_loaded" not in st.session_state:
    saved = _load_providers()
    for k in ("openai_api_key", "anthropic_api_key", "google_api_key", "openrouter_api_key"):
        st.session_state.setdefault(k, saved.get(k, ""))
    st.session_state["providers_loaded"] = True

# ── Tabs ─────────────────────────────────────────────────────────────────────
tab_join, tab_keys = st.tabs(["🖥️ Join Grid", "🔑 API Keys"])


# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — JOIN GRID
# ════════════════════════════════════════════════════════════════════════════
with tab_join:
    st.subheader("Register this machine as a grid agent")
    st.markdown(
        "Complete this form to register as a **Momagrid / Momahub** node. "
        "Ollama must be running locally with at least one model downloaded."
    )

    # Hub connectivity check
    health = _probe_hub(hub_url)
    if "error" in health:
        st.warning(f"Hub unreachable at **{hub_url}** — {health['error']}")
    else:
        cols = st.columns(4)
        cols[0].metric("Hub ID", health.get("hub_id", "—"))
        cols[1].metric("Status", health.get("status", "—"))
        cols[2].metric("Agents Online", health.get("agents_online", 0))
        cols[3].metric("Version", health.get("version", "—"))

    st.divider()
    st.markdown("#### Step 1 — Detect local Ollama")

    ollama_url = st.text_input(
        "Ollama URL",
        value="http://localhost:11434",
        help="Local Ollama instance used for inference on this node.",
    )

    col_probe, _ = st.columns([2, 5])
    if col_probe.button("🔍 Probe Ollama", use_container_width=True):
        with st.spinner("Querying Ollama…"):
            found = _probe_ollama(ollama_url)
        if found:
            st.session_state["ollama_models"] = found
            st.success(f"Found {len(found)} model(s): `{'`, `'.join(found)}`")
        else:
            st.session_state["ollama_models"] = []
            st.error(
                "Could not reach Ollama or no models installed. "
                "Run: `ollama pull llama3` then try again."
            )

    detected_models = st.session_state.get("ollama_models", [])

    st.markdown("#### Step 2 — Fill node details")

    with st.form("join_form"):
        c1, c2 = st.columns(2)
        node_name = c1.text_input(
            "Node name",
            value=platform.node(),
            help="Human-readable name shown on the grid dashboard.",
        )
        operator_id = c2.text_input(
            "Operator ID *",
            placeholder="your-handle or email",
            help="Your identifier for reward / credit tracking.",
        )

        c3, c4 = st.columns(2)
        gpu_model = c3.text_input(
            "GPU model",
            placeholder="e.g. NVIDIA GTX 1080 Ti",
            help="GPU name (used for display and tier assignment).",
        )
        vram_gb = c4.number_input(
            "VRAM (GB)",
            min_value=0.0, max_value=256.0, value=8.0, step=0.5,
            help="Total VRAM — determines Platinum / Gold / Silver / Bronze tier.",
        )

        model_input = st.text_input(
            "Available models (comma-separated)",
            value=", ".join(detected_models) if detected_models else "",
            placeholder="llama3, mistral, phi3",
            help="Models available via Ollama on this node.",
        )

        submitted = st.form_submit_button("🚀 Join Grid", type="primary", use_container_width=True)

    if submitted:
        if not operator_id.strip():
            st.error("Operator ID is required.")
        else:
            models_list = [m.strip() for m in model_input.split(",") if m.strip()]
            if not models_list:
                st.error("Specify at least one available model.")
            elif "error" in health:
                st.error("Hub is unreachable — fix the Hub URL before registering.")
            else:
                payload = {
                    "node_id": str(uuid.uuid4()),
                    "name": node_name.strip() or platform.node(),
                    "operator_id": operator_id.strip(),
                    "gpu_model": gpu_model.strip() or "unknown",
                    "vram_total": vram_gb,
                    "ollama_url": ollama_url.strip(),
                    "available_models": models_list,
                    "ollama_version": "0.0.0",
                }
                with st.spinner("Sending handshake to hub…"):
                    result = _join_hub(hub_url, payload)

                if "error" in result:
                    st.error(f"Registration failed: {result['error']}")
                    with st.expander("Sent payload (for debugging)"):
                        st.json(payload)
                else:
                    st.success("**Registration successful!**")
                    r1, r2, r3 = st.columns(3)
                    token = result.get("session_token") or "—"
                    r1.metric("Session Token", token[:16] + "…" if len(token) > 16 else token)
                    r2.metric("Assigned Tier", result.get("tier", "—"))
                    r3.metric("Node ID", str(result.get("node_id", payload["node_id"]))[:14] + "…")

                    st.info(
                        "**Next steps:**  \n"
                        "- Python hub: run `moma up` on this machine to start accepting tasks.  \n"
                        "- Go hub (Momagrid): run `mg join <hub-url>` then `mg up`."
                    )

    st.divider()
    st.subheader("Current Grid Agents")

    @st.cache_data(ttl=10)
    def _agents(u):
        try:
            return httpx.get(f"{u}/agents", timeout=3.0).json().get("agents", [])
        except Exception:
            return []

    if st.button("🔄 Refresh agents"):
        st.cache_data.clear()

    agents = _agents(hub_url)
    if agents:
        import pandas as pd
        rows = []
        for a in agents:
            rows.append({
                "name":     a.get("name", ""),
                "operator": a.get("operator_id", ""),
                "tier":     a.get("tier", ""),
                "status":   a.get("status", ""),
                "vram_gb":  a.get("vram_total", 0),
                "models":   ", ".join(json.loads(a.get("supported_models", "[]")))[:60],
                "tasks_done": a.get("tasks_completed", 0),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
    else:
        st.info("No agents registered yet (or hub unreachable).")


# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — API KEYS
# ════════════════════════════════════════════════════════════════════════════
with tab_keys:
    st.subheader("Cloud Provider API Keys")
    st.markdown(
        "Keys are held in your **browser session** and optionally saved to  \n"
        f"`{PROVIDERS_FILE}` on this machine.  \n"
        "They are **never** transmitted to the Momagrid grid — only sent directly to "
        "the respective provider's API endpoint."
    )
    st.divider()

    # ── OpenAI ──
    st.markdown("#### 🤖 OpenAI")
    col_a, col_b = st.columns([3, 1])
    openai_key = col_a.text_input(
        "OpenAI API Key",
        type="password",
        value=st.session_state.get("openai_api_key", ""),
        placeholder="sk-…",
        help="Get yours at platform.openai.com/api-keys",
    )
    col_b.markdown("<br>", unsafe_allow_html=True)
    col_b.caption("Models: gpt-4o, gpt-4o-mini, o3-mini, …")

    # ── Anthropic ──
    st.markdown("#### 🧠 Anthropic")
    col_a, col_b = st.columns([3, 1])
    anthropic_key = col_a.text_input(
        "Anthropic API Key",
        type="password",
        value=st.session_state.get("anthropic_api_key", ""),
        placeholder="sk-ant-…",
        help="Get yours at console.anthropic.com",
    )
    col_b.markdown("<br>", unsafe_allow_html=True)
    col_b.caption("Models: claude-sonnet-4-6, claude-haiku-4-5, …")

    # ── Google ──
    st.markdown("#### 🔍 Google (Gemini)")
    col_a, col_b = st.columns([3, 1])
    google_key = col_a.text_input(
        "Google AI API Key",
        type="password",
        value=st.session_state.get("google_api_key", ""),
        placeholder="AIza…",
        help="Get yours at aistudio.google.com",
    )
    col_b.markdown("<br>", unsafe_allow_html=True)
    col_b.caption("Models: gemini-2.0-flash, gemini-1.5-pro, …")

    # ── OpenRouter ──
    st.markdown("#### 🔀 OpenRouter")
    col_a, col_b = st.columns([3, 1])
    openrouter_key = col_a.text_input(
        "OpenRouter API Key",
        type="password",
        value=st.session_state.get("openrouter_api_key", ""),
        placeholder="sk-or-…",
        help="Get yours at openrouter.ai/keys — routes to 200+ models",
    )
    col_b.markdown("<br>", unsafe_allow_html=True)
    col_b.caption("Any model: llama3, claude, gemini, …")

    st.divider()

    cs, cd, _ = st.columns([1, 2, 3])
    if cs.button("💾 Save to session", type="primary"):
        st.session_state["openai_api_key"] = openai_key
        st.session_state["anthropic_api_key"] = anthropic_key
        st.session_state["google_api_key"] = google_key
        st.session_state["openrouter_api_key"] = openrouter_key
        st.success("Keys saved to session. Visit **Unified Chatbot** to use them.")

    if cd.button("💿 Save to disk (~/.igrid/providers.yaml)"):
        _save_providers({
            "openai_api_key": openai_key,
            "anthropic_api_key": anthropic_key,
            "google_api_key": google_key,
            "openrouter_api_key": openrouter_key,
        })
        # Also update session
        st.session_state["openai_api_key"] = openai_key
        st.session_state["anthropic_api_key"] = anthropic_key
        st.session_state["google_api_key"] = google_key
        st.session_state["openrouter_api_key"] = openrouter_key
        st.success(f"Saved to `{PROVIDERS_FILE}` — will auto-load next session.")

    # Key status summary
    st.divider()
    st.markdown("**Current key status:**")
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Momagrid", "✅ built-in", help="No key needed — uses Hub URL above")
    k2.metric("OpenAI",     "✅ set" if openai_key     else "❌ not set")
    k3.metric("Anthropic",  "✅ set" if anthropic_key  else "❌ not set")
    k4.metric("Google",     "✅ set" if google_key     else "❌ not set")
    k5.metric("OpenRouter", "✅ set" if openrouter_key else "❌ not set")
