"""Rewards page."""
import os, httpx, streamlit as st
HUB_URL = os.environ.get("IGRID_HUB_URL", "http://localhost:8000")
st.set_page_config(page_title="Rewards", layout="wide")
st.title("💰 Reward Ledger")
hub_url = st.sidebar.text_input("Hub URL", value=HUB_URL)

@st.cache_data(ttl=15)
def fetch_rewards(u):
    try: return httpx.get(f"{u}/rewards", timeout=3.0).json().get("summary", [])
    except: return []

rows = fetch_rewards(hub_url)
if not rows:
    st.info("No rewards recorded yet.")
else:
    import pandas as pd
    df = pd.DataFrame(rows)
    totals = df[["total_tasks","total_tokens","total_credits"]].sum()
    col1,col2,col3 = st.columns(3)
    col1.metric("Total Tasks", int(totals["total_tasks"]))
    col2.metric("Total Tokens", int(totals["total_tokens"]))
    col3.metric("Total Credits", f"{totals['total_credits']:.2f}")
    st.divider(); st.subheader("By Operator")
    st.dataframe(df, use_container_width=True)
    st.caption("PoC: 1 credit per 1,000 output tokens. Full econ model TBD.")

if st.button("🔄 Refresh"):
    st.cache_data.clear(); st.rerun()
