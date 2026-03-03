"""Grid Monitor page."""
import os, httpx, streamlit as st
HUB_URL = os.environ.get("IGRID_HUB_URL", "http://localhost:8000")
st.set_page_config(page_title="Grid Monitor", layout="wide")
st.title("📊 Grid Monitor")
hub_url = st.sidebar.text_input("Hub URL", value=HUB_URL)
auto_refresh = st.sidebar.toggle("Auto-refresh (10s)", value=False)

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

agents = fetch_agents(hub_url)
st.subheader(f"Agents ({len(agents)} online)")
if agents:
    import pandas as pd
    df = pd.DataFrame(agents)
    tier_counts = df["tier"].value_counts()
    col1,col2,col3,col4 = st.columns(4)
    for col, tier in zip([col1,col2,col3,col4], ["PLATINUM","GOLD","SILVER","BRONZE"]):
        col.metric(tier, tier_counts.get(tier, 0))
    st.dataframe(df[["agent_id","operator_id","tier","status","current_tps","tasks_completed","last_pulse"]], use_container_width=True)
else:
    st.info("No agents online.")

st.divider(); st.subheader("Cluster Peers")
peers = fetch_cluster(hub_url).get("peers", [])
if peers:
    import pandas as pd; st.dataframe(pd.DataFrame(peers), use_container_width=True)
else:
    st.info("No peer hubs. Use `moma peer add <url>` to add one.")

st.divider(); st.subheader("Recent Pulse Log")
logs = fetch_logs(hub_url)
if logs:
    import pandas as pd
    st.dataframe(pd.DataFrame(logs)[["logged_at","agent_id","status","current_tps","gpu_util_pct","vram_used_gb","tasks_completed"]], use_container_width=True)

if auto_refresh:
    import time; time.sleep(10); st.cache_data.clear(); st.rerun()
if st.button("🔄 Refresh"):
    st.cache_data.clear(); st.rerun()
