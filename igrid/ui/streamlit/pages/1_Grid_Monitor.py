"""Grid Monitor page."""
import json
import os

import httpx
import pandas as pd
import streamlit as st

HUB_URL = os.environ.get("IGRID_HUB_URL", "http://localhost:8000")
st.set_page_config(page_title="Grid Monitor", layout="wide")
st.title("📊 Grid Monitor")

hub_url = st.sidebar.text_input("Hub URL", value=HUB_URL)
auto_refresh = st.sidebar.toggle("Auto-refresh (10s)", value=False)
log_limit = st.sidebar.slider("Pulse log rows", 20, 200, 50, step=10)

@st.cache_data(ttl=10)
def fetch_agents(u):
    try: return httpx.get(f"{u}/agents", timeout=3.0).json().get("agents", [])
    except: return []

@st.cache_data(ttl=10)
def fetch_cluster(u):
    try: return httpx.get(f"{u}/cluster/status", timeout=3.0).json()
    except: return {}

@st.cache_data(ttl=10)
def fetch_logs(u, limit=50):
    try: return httpx.get(f"{u}/logs?limit={limit}", timeout=3.0).json().get("logs", [])
    except: return []

# ── Agents ──────────────────────────────────────────────────────────────────
agents = fetch_agents(hub_url)
st.subheader(f"Agents ({len(agents)} registered)")

if agents:
    df = pd.DataFrame(agents)
    tier_counts = df["tier"].value_counts() if "tier" in df.columns else {}
    col1, col2, col3, col4 = st.columns(4)
    for col, tier in zip([col1, col2, col3, col4], ["PLATINUM", "GOLD", "SILVER", "BRONZE"]):
        col.metric(tier, tier_counts.get(tier, 0))

    # Enrich with VRAM and GPU model
    rows = []
    for a in agents:
        gpus = json.loads(a.get("gpus") or "[]")
        gpu_label = gpus[0].get("model", "CPU") if gpus else "CPU"
        vram = gpus[0].get("vram_gb", 0) if gpus else 0
        rows.append({
            "name":       a.get("name", ""),
            "tier":       a.get("tier", ""),
            "status":     a.get("status", ""),
            "tps":        round(a.get("current_tps", 0), 1),
            "tasks":      a.get("tasks_completed", 0),
            "gpu":        gpu_label,
            "vram_gb":    vram,
            "operator":   a.get("operator_id", ""),
            "joined":     (a.get("joined_at") or "")[:19],
            "last_pulse": (a.get("last_pulse") or "")[:19],
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True)

    # TPS bar chart
    tps_data = {r["name"] or r["operator"]: r["tps"] for r in rows if r["tps"] > 0}
    if tps_data:
        st.caption("Current TPS per agent")
        st.bar_chart(tps_data)
else:
    st.info("No agents online.")

# ── Pulse log — TPS trend & GPU utilisation ──────────────────────────────────
st.divider()
st.subheader("Agent Telemetry (Pulse Log)")
logs = fetch_logs(hub_url, log_limit)

if logs:
    log_df = pd.DataFrame(logs)
    display_cols = [c for c in ["logged_at", "agent_id", "status", "current_tps",
                                "gpu_util_pct", "vram_used_gb", "tasks_completed"]
                    if c in log_df.columns]
    st.dataframe(log_df[display_cols], use_container_width=True)

    # TPS trend chart (pivot by agent)
    if "current_tps" in log_df.columns and "agent_id" in log_df.columns:
        st.caption("TPS over time (last pulse entries)")
        try:
            log_df["logged_at"] = pd.to_datetime(log_df["logged_at"])
            pivot = log_df.pivot_table(index="logged_at", columns="agent_id",
                                       values="current_tps", aggfunc="mean")
            pivot.columns = [str(c)[-16:] for c in pivot.columns]
            st.line_chart(pivot)
        except Exception:
            pass

    # GPU utilisation bars (latest reading per agent)
    if "gpu_util_pct" in log_df.columns and "agent_id" in log_df.columns:
        latest = log_df.sort_values("logged_at").groupby("agent_id").last().reset_index()
        util_data = {row["agent_id"][-14:]: row["gpu_util_pct"]
                     for _, row in latest.iterrows()
                     if row.get("gpu_util_pct") is not None}
        if util_data:
            st.caption("GPU utilisation % (latest reading per agent)")
            st.bar_chart(util_data)

    # VRAM usage
    if "vram_used_gb" in log_df.columns and "agent_id" in log_df.columns:
        latest = log_df.sort_values("logged_at").groupby("agent_id").last().reset_index()
        vram_data = {row["agent_id"][-14:]: row["vram_used_gb"]
                     for _, row in latest.iterrows()
                     if row.get("vram_used_gb") is not None}
        if vram_data:
            st.caption("VRAM used GB (latest reading per agent)")
            st.bar_chart(vram_data)
else:
    st.info("No pulse log entries yet.")

# ── Cluster peers ────────────────────────────────────────────────────────────
st.divider()
st.subheader("Cluster Peers")
peers = fetch_cluster(hub_url).get("peers", [])
if peers:
    st.dataframe(pd.DataFrame(peers), use_container_width=True)
else:
    st.info("No peer hubs. Use `moma peer add <url>` to connect another hub.")

# ── Auto-refresh ─────────────────────────────────────────────────────────────
if auto_refresh:
    import time
    time.sleep(10)
    st.cache_data.clear()
    st.rerun()
if st.button("🔄 Refresh"):
    st.cache_data.clear()
    st.rerun()
