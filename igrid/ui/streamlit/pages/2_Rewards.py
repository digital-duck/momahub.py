"""Rewards page."""
import os

import httpx
import streamlit as st

HUB_URL = os.environ.get("IGRID_HUB_URL", "http://localhost:8000")
st.set_page_config(page_title="Rewards", layout="wide")
st.title("💰 Reward Ledger")

hub_url = st.sidebar.text_input("Hub URL", value=HUB_URL)

@st.cache_data(ttl=15)
def fetch_rewards(u):
    try: return httpx.get(f"{u}/rewards", timeout=3.0).json().get("summary", [])
    except: return []

@st.cache_data(ttl=15)
def fetch_tasks(u, limit=500):
    try: return httpx.get(f"{u}/tasks?limit={limit}", timeout=3.0).json().get("tasks", [])
    except: return []

rows = fetch_rewards(hub_url)

if not rows:
    st.info("No rewards recorded yet. Submit some tasks first.")
else:
    import pandas as pd

    df = pd.DataFrame(rows)
    totals = df[["total_tasks", "total_tokens", "total_credits"]].sum()

    # ── Grid totals ──────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Tasks",   f"{int(totals['total_tasks']):,}")
    col2.metric("Total Tokens",  f"{int(totals['total_tokens']):,}")
    col3.metric("Total Credits", f"{totals['total_credits']:.4f}")

    st.divider()

    # ── Per-operator table + bar chart ───────────────────────────────────────
    left, right = st.columns([2, 1])
    with left:
        st.subheader("By Operator")
        st.dataframe(df, use_container_width=True)
        st.caption("PoC: 1 credit per 1,000 output tokens. Full economy in Phase 9.")

    with right:
        st.subheader("Credits by Operator")
        credit_data = {row["operator_id"]: row["total_credits"]
                       for _, row in df.iterrows() if row.get("operator_id")}
        if credit_data:
            st.bar_chart(credit_data)

        st.subheader("Tokens by Operator")
        token_data = {row["operator_id"]: row["total_tokens"]
                      for _, row in df.iterrows() if row.get("operator_id")}
        if token_data:
            st.bar_chart(token_data)

    # ── Per-model breakdown from task history ────────────────────────────────
    st.divider()
    st.subheader("By Model (recent tasks)")
    tasks = fetch_tasks(hub_url)
    if tasks:
        task_df = pd.DataFrame(tasks)
        completed = task_df[task_df.get("state", pd.Series()) == "COMPLETE"] if "state" in task_df.columns else pd.DataFrame()
        if not completed.empty and "model" in completed.columns:
            model_stats = completed.groupby("model").agg(
                tasks=("state", "size"),
                tokens=("output_tokens", "sum"),
                avg_latency_ms=("latency_ms", "mean"),
            ).round(1).reset_index()
            st.dataframe(model_stats, use_container_width=True)

            # Token share by model
            if len(model_stats) > 1:
                model_tokens = dict(zip(model_stats["model"], model_stats["tokens"]))
                st.caption("Token share by model")
                st.bar_chart(model_tokens)

if st.button("🔄 Refresh"):
    st.cache_data.clear()
    st.rerun()
