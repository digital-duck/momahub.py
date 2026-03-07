"""Request / Response Log page.

Browse, filter and inspect every task submitted to the hub.
Uses AgGrid for sortable/filterable/paginated table — click any row to inspect
the full prompt and response.

Requires: pip install streamlit-aggrid
"""
import os

import httpx
import pandas as pd
import streamlit as st

HUB_URL = os.environ.get("IGRID_HUB_URL", "http://localhost:8000")
st.set_page_config(page_title="Request Log", layout="wide")
st.title("📋 Request / Response Log")
st.caption("Full history of every task submitted to the hub. Click a row to inspect the prompt and response.")

hub_url = st.sidebar.text_input("Hub URL", value=HUB_URL)
limit    = st.sidebar.selectbox("Fetch last N tasks", [50, 100, 250, 500, 1000], index=1)
auto_ref = st.sidebar.checkbox("Auto-refresh (15s)", value=False)

if st.sidebar.button("🔄 Refresh now"):
    st.cache_data.clear()

# ── Fetch ─────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=15)
def fetch_tasks(hub: str, n: int) -> list[dict]:
    try:
        return httpx.get(f"{hub}/tasks", params={"limit": n}, timeout=5.0).json().get("tasks", [])
    except Exception:
        return []

raw = fetch_tasks(hub_url, limit)

if not raw:
    st.info("No tasks found. Submit some tasks with `moma submit` or via the Run page.")
    st.stop()

df = pd.DataFrame(raw)

# Ensure expected columns exist
for col in ["system", "content", "agent_id", "error", "peer_hub_id",
            "input_tokens", "output_tokens", "latency_ms", "retries"]:
    if col not in df.columns:
        df[col] = ""

df["input_tokens"]  = pd.to_numeric(df["input_tokens"],  errors="coerce").fillna(0).astype(int)
df["output_tokens"] = pd.to_numeric(df["output_tokens"], errors="coerce").fillna(0).astype(int)
df["latency_s"]     = (pd.to_numeric(df["latency_ms"], errors="coerce").fillna(0) / 1000).round(2)
df["retries"]       = pd.to_numeric(df["retries"], errors="coerce").fillna(0).astype(int)
df["prompt_preview"]   = df["prompt"].str[:150].str.replace("\n", " ", regex=False)
df["response_preview"] = df["content"].astype(str).str[:150].str.replace("\n", " ", regex=False)

# ── Summary metrics ───────────────────────────────────────────────────────────
complete = int((df["state"] == "COMPLETE").sum())
failed   = int((df["state"] == "FAILED").sum())
pending  = int(df["state"].isin(["PENDING", "DISPATCHED", "IN_FLIGHT"]).sum())
total_tok = int(df["output_tokens"].sum())

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Tasks fetched",  len(df))
m2.metric("Complete",       complete)
m3.metric("Failed",         failed)
m4.metric("Pending/Active", pending)
m5.metric("Output tokens",  f"{total_tok:,}")

st.divider()

# ── AgGrid table ──────────────────────────────────────────────────────────────
try:
    from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode, JsCode

    grid_df = df[[
        "task_id", "state", "model", "prompt_preview", "response_preview",
        "input_tokens", "output_tokens", "latency_s", "retries", "agent_id", "created_at",
    ]].copy()

    gb = GridOptionsBuilder.from_dataframe(grid_df)
    gb.configure_default_column(
        filterable=True, sortable=True, resizable=True,
        wrapText=False, autoHeight=False,
    )
    gb.configure_column("task_id",          header_name="Task ID",          width=180, pinned="left")
    gb.configure_column("state",            header_name="State",            width=110,
                        cellStyle=JsCode("""function(params) {
                            const c = {
                                COMPLETE: '#1a7a1a', FAILED: '#a00', PENDING: '#888',
                                IN_FLIGHT: '#0055cc', DISPATCHED: '#0055cc'
                            };
                            return {color: c[params.value] || '#333', fontWeight: 'bold'};
                        }"""))
    gb.configure_column("model",            header_name="Model",            width=130)
    gb.configure_column("prompt_preview",   header_name="Prompt",           flex=2, minWidth=200)
    gb.configure_column("response_preview", header_name="Response",         flex=2, minWidth=200)
    gb.configure_column("input_tokens",     header_name="In tok",           width=90,  type=["numericColumn"])
    gb.configure_column("output_tokens",    header_name="Out tok",          width=90,  type=["numericColumn"])
    gb.configure_column("latency_s",        header_name="Latency (s)",      width=100, type=["numericColumn"])
    gb.configure_column("retries",          header_name="Retries",          width=80,  type=["numericColumn"])
    gb.configure_column("agent_id",         header_name="Agent",            width=160)
    gb.configure_column("created_at",       header_name="Created",          width=160)

    gb.configure_selection(selection_mode="single", use_checkbox=False)
    gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=20)
    gb.configure_grid_options(rowHeight=28, headerHeight=36)

    grid_resp = AgGrid(
        grid_df,
        gridOptions=gb.build(),
        update_mode=GridUpdateMode.SELECTION_CHANGED,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        fit_columns_on_grid_load=False,
        allow_unsafe_jscode=True,
        height=520,
        use_container_width=True,
        theme="streamlit",
    )

    selected_rows = grid_resp.get("selected_rows")

except ImportError:
    st.warning(
        "streamlit-aggrid not installed. Falling back to standard table.\n\n"
        "Install with: `pip install streamlit-aggrid`"
    )
    st.dataframe(df[[
        "task_id", "state", "model", "prompt_preview", "response_preview",
        "input_tokens", "output_tokens", "latency_s", "agent_id", "created_at",
    ]], use_container_width=True, height=400)
    selected_rows = None

# ── Detail inspector ──────────────────────────────────────────────────────────
st.divider()
st.subheader("Inspect Task")

# Resolve selected row: from AgGrid selection OR manual dropdown
selected_id = None

if selected_rows is not None and len(selected_rows) > 0:
    if isinstance(selected_rows, pd.DataFrame):
        selected_id = selected_rows.iloc[0]["task_id"]
    elif isinstance(selected_rows, list) and selected_rows:
        selected_id = selected_rows[0].get("task_id")

task_ids = df["task_id"].tolist()
default_idx = task_ids.index(selected_id) if selected_id in task_ids else 0
selected_id = st.selectbox(
    "Task ID (or click a row above)",
    task_ids,
    index=default_idx,
    format_func=lambda x: x,
)

if selected_id:
    row = df[df["task_id"] == selected_id].iloc[0]

    meta1, meta2, meta3, meta4 = st.columns(4)
    meta1.metric("State",   str(row.get("state", "—")))
    meta2.metric("Model",   str(row.get("model", "—")))
    meta3.metric("Tokens",  f"{int(row.get('input_tokens') or 0)} → {int(row.get('output_tokens') or 0)}")
    meta4.metric("Latency", f"{float(row.get('latency_ms') or 0) / 1000:.2f}s")

    col_req, col_res = st.columns(2)

    with col_req:
        st.markdown("**Request (prompt)**")
        sys_text = str(row.get("system") or "")
        if sys_text:
            with st.expander("System prompt", expanded=False):
                st.text(sys_text)
        st.text_area("Prompt", value=str(row.get("prompt") or ""), height=300,
                     key="prompt_view", disabled=True)

    with col_res:
        st.markdown("**Response**")
        content = str(row.get("content") or "")
        if content:
            tab_raw, tab_rendered = st.tabs(["Raw text", "Rendered"])
            with tab_raw:
                st.text_area("Response", value=content, height=300,
                             key="response_view", disabled=True)
            with tab_rendered:
                st.markdown(content)
        elif str(row.get("state", "")) in ("PENDING", "DISPATCHED", "IN_FLIGHT"):
            st.info("Task is still running.")
        elif row.get("error"):
            st.error(f"Error: {row['error']}")
        else:
            st.info("No response recorded.")

    with st.expander("Full metadata (JSON)", expanded=False):
        meta_fields = [
            "task_id", "state", "model", "agent_id", "peer_hub_id",
            "input_tokens", "output_tokens", "latency_ms", "retries",
            "min_tier", "min_vram_gb", "max_tokens", "temperature",
            "timeout_s", "priority", "error", "created_at", "updated_at",
        ]
        st.json({k: row.get(k) for k in meta_fields if k in row.index})

# ── Auto-refresh ──────────────────────────────────────────────────────────────
if auto_ref:
    import time
    time.sleep(15)
    st.cache_data.clear()
    st.rerun()
