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

health = fetch_health(hub_url)
if "error" in health:
    st.error(f"Cannot reach hub: {health['error']}")
else:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Hub ID", health.get("hub_id", "—"))
    col2.metric("Status", health.get("status", "—"))
    col3.metric("Agents Online", health.get("agents_online", 0))
    col4.metric("Hub Time", health.get("time", "—")[:19])

st.divider()
st.subheader("Online Agents")
agents = fetch_agents(hub_url)
if not agents:
    st.info("No agents connected.")
else:
    import pandas as pd
    df = pd.DataFrame(agents)[["agent_id","operator_id","tier","status","current_tps","tasks_completed","last_pulse"]]
    st.dataframe(df, use_container_width=True)

st.divider()
st.subheader("Recent Tasks")
tasks = fetch_tasks(hub_url)
if not tasks:
    st.info("No tasks yet.")
else:
    import pandas as pd
    df = pd.DataFrame(tasks)[["task_id","state","model","input_tokens","output_tokens","latency_ms","created_at"]]
    st.dataframe(df, use_container_width=True)

if st.button("🔄 Refresh"):
    st.cache_data.clear(); st.rerun()
