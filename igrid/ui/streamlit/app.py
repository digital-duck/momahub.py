"""i-grid Hub Dashboard — Streamlit main page."""
import os
import httpx
import streamlit as st

HUB_URL = os.environ.get("IGRID_HUB_URL", "http://localhost:8000")
st.set_page_config(page_title="i-grid Hub Dashboard", page_icon="🌐", layout="wide")
st.title("🌐 i-grid Hub Dashboard")

@st.cache_data(ttl=5)
def fetch_health(hub_url):
    try:
        resp = httpx.get(f"{hub_url}/health", timeout=3.0); resp.raise_for_status(); return resp.json()
    except Exception as exc: return {"error": str(exc)}

@st.cache_data(ttl=5)
def fetch_agents(hub_url):
    try: return httpx.get(f"{hub_url}/agents", timeout=3.0).json().get("agents", [])
    except Exception: return []

@st.cache_data(ttl=5)
def fetch_tasks(hub_url, limit=10):
    try: return httpx.get(f"{hub_url}/tasks?limit={limit}", timeout=3.0).json().get("tasks", [])
    except Exception: return []

hub_url = st.sidebar.text_input("Hub URL", value=HUB_URL)
st.sidebar.markdown("---")
st.sidebar.markdown("**Pages**")
st.sidebar.page_link("app.py", label="Overview", icon="🏠")
st.sidebar.page_link("pages/1_Grid_Monitor.py", label="Grid Monitor", icon="📊")
st.sidebar.page_link("pages/2_Rewards.py", label="Rewards", icon="💰")
st.sidebar.page_link("pages/3_Run_SPL.py", label="Run SPL", icon="⚡")
st.sidebar.page_link("pages/4_Text2SPL.py", label="Text2SPL", icon="✏️")
st.sidebar.page_link("pages/5_Paper_Digest.py", label="Paper Digest", icon="📚")
st.sidebar.page_link("pages/6_Chat.py", label="Test Runner", icon="🧪")

@st.cache_data(ttl=5)
def fetch_pending_count(hub_url):
    try:
        tasks = httpx.get(f"{hub_url}/tasks?limit=200", timeout=3.0).json().get("tasks", [])
        return sum(1 for t in tasks if t.get("state") == "PENDING")
    except Exception: return 0

@st.cache_data(ttl=10)
def fetch_watchlist(hub_url):
    try: return httpx.get(f"{hub_url}/watchlist", timeout=3.0).json().get("entries", [])
    except Exception: return []

health = fetch_health(hub_url)
if "error" in health:
    st.error(f"Cannot reach hub: {health['error']}")
else:
    pending = fetch_pending_count(hub_url)
    watchlist = fetch_watchlist(hub_url)

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Hub ID", health.get("hub_id", "—"))
    col2.metric("Status", health.get("status", "—"))
    col3.metric("Agents Online", health.get("agents_online", 0))
    col4.metric("Pending Tasks", pending, delta=None if pending == 0 else f"{pending} queued",
                delta_color="inverse")
    col5.metric("Watchlist", len(watchlist),
                delta="⚠ blocked" if watchlist else None,
                delta_color="inverse" if watchlist else "off")

    if watchlist:
        st.warning(f"**{len(watchlist)} watchlist entry/entries** — IPs or operators suspended. "
                   f"Use `moma watchlist` to review.")

st.divider()
st.subheader("Online Agents")
agents = fetch_agents(hub_url)
if not agents:
    st.info("No agents connected.")
else:
    import pandas as pd, json as _json
    rows = []
    for a in agents:
        gpus = _json.loads(a.get("gpus") or "[]")
        vram = gpus[0]["vram_gb"] if gpus else 0
        rows.append({
            "name": a.get("name", ""),
            "tier": a["tier"],
            "status": a["status"],
            "tps": a.get("current_tps", 0),
            "tasks": a.get("tasks_completed", 0),
            "vram_gb": vram,
            "operator": a.get("operator_id", ""),
            "last_pulse": a.get("last_pulse", "")[:19],
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True)

    # TPS bar chart
    if len(rows) > 1:
        tps_data = {r["name"] or r["operator"]: r["tps"] for r in rows if r["tps"] > 0}
        if tps_data:
            st.caption("Current TPS per agent")
            st.bar_chart(tps_data)

st.divider()
st.subheader("Recent Tasks")
tasks = fetch_tasks(hub_url)
if not tasks:
    st.info("No tasks yet.")
else:
    import pandas as pd
    df = pd.DataFrame(tasks)
    cols = [c for c in ["task_id","state","model","output_tokens","latency_ms","created_at"] if c in df.columns]
    # Colour-code state
    state_counts = df["state"].value_counts().to_dict() if "state" in df.columns else {}
    if state_counts:
        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("Complete", state_counts.get("COMPLETE", 0))
        sc2.metric("Pending",  state_counts.get("PENDING", 0))
        sc3.metric("Failed",   state_counts.get("FAILED", 0))
        sc4.metric("In-Flight",state_counts.get("IN_FLIGHT", 0) + state_counts.get("DISPATCHED", 0))
    st.dataframe(df[cols], use_container_width=True)

if st.button("🔄 Refresh"):
    st.cache_data.clear(); st.rerun()
