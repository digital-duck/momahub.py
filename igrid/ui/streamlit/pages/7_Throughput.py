"""Throughput page — scaling chart from recipe 13 results.

Load one or more throughput-*.json files produced by:
    python cookbook/13_multi_agent_throughput/throughput.py --label "N-agents" --out scaling.json

Plots tokens/s vs agent count as a line chart — the key scaling figure for the MoMa paper.
"""
import json
import os
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Throughput Scaling", layout="wide")
st.title("📈 Throughput Scaling")
st.caption(
    "Run recipe 13 with `--label '1-agent'`, `'2-agents'`, `'3-agents'` and `--out scaling.json`. "
    "Upload the file here to see the scaling chart."
)

# ── File upload or auto-detect ────────────────────────────────────────────────
uploaded = st.file_uploader(
    "Upload scaling.json (from recipe 13)", type="json", accept_multiple_files=True
)

# Also look for local throughput files
cookbook_dir = Path(__file__).parents[3] / "cookbook" / "13_multi_agent_throughput"
local_files = sorted(cookbook_dir.glob("throughput-*.json")) if cookbook_dir.exists() else []
local_files += sorted(cookbook_dir.glob("scaling*.json")) if cookbook_dir.exists() else []

runs = []
if uploaded:
    for f in uploaded:
        data = json.load(f)
        if isinstance(data, list):
            runs.extend(data)
        else:
            runs.append(data)
elif local_files:
    st.info(f"Auto-loaded {len(local_files)} local result file(s) from recipe 13.")
    for p in local_files:
        try:
            data = json.loads(p.read_text())
            if isinstance(data, list):
                runs.extend(data)
            else:
                runs.append(data)
        except Exception:
            pass

if not runs:
    st.info(
        "No data yet. Run recipe 13 to generate throughput data:\n\n"
        "```bash\n"
        "# With 1 agent:\n"
        "python cookbook/13_multi_agent_throughput/throughput.py "
        "--label '1-agent' -n 30 --out scaling.json\n\n"
        "# Add 2nd agent, then:\n"
        "python cookbook/13_multi_agent_throughput/throughput.py "
        "--label '2-agents' -n 30 --out scaling.json\n\n"
        "# Add 3rd agent, then:\n"
        "python cookbook/13_multi_agent_throughput/throughput.py "
        "--label '3-agents' -n 30 --out scaling.json\n"
        "```"
    )
    st.stop()

# ── Summary table ─────────────────────────────────────────────────────────────
import pandas as pd

rows = []
for r in runs:
    dist = r.get("agent_distribution", {})
    n_agents = len(dist)
    rows.append({
        "label":           r.get("label", "?"),
        "agents":          n_agents,
        "throughput_tps":  r.get("throughput_tps", 0),
        "wall_time_s":     r.get("wall_time_s", 0),
        "completed":       r.get("completed", 0),
        "total_tokens":    r.get("total_tokens", 0),
        "avg_latency_s":   r.get("avg_latency_s", 0),
        "model":           r.get("model", ""),
        "timestamp":       (r.get("timestamp") or "")[:19],
    })

df = pd.DataFrame(rows).sort_values("agents")

# Metrics row
if len(rows) >= 2:
    baseline = df.iloc[0]["throughput_tps"]
    best = df["throughput_tps"].max()
    speedup = best / baseline if baseline > 0 else 0
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Runs loaded", len(rows))
    col2.metric("Best throughput", f"{best:.1f} tok/s")
    col3.metric("Scaling factor", f"{speedup:.2f}×",
                help="Best throughput ÷ single-agent baseline")
    col4.metric("Models tested", ", ".join(df["model"].unique()))

# ── Throughput scaling line chart ─────────────────────────────────────────────
st.subheader("Tokens/s vs Agent Count")
chart_df = df.set_index("label")[["throughput_tps"]].rename(
    columns={"throughput_tps": "tokens/s"}
)
st.line_chart(chart_df)

# Ideal linear scaling reference
if len(rows) >= 2:
    baseline_tps = df.iloc[0]["throughput_tps"]
    ideal = {row["label"]: baseline_tps * max(row["agents"], 1)
             for _, row in df.iterrows()}
    actual = {row["label"]: row["throughput_tps"] for _, row in df.iterrows()}
    comparison = pd.DataFrame({"actual tok/s": actual, "ideal (linear)": ideal})
    st.caption("Actual vs ideal linear scaling")
    st.line_chart(comparison)

# ── Latency chart ─────────────────────────────────────────────────────────────
st.subheader("Average Latency vs Agent Count")
lat_df = df.set_index("label")[["avg_latency_s"]].rename(
    columns={"avg_latency_s": "avg latency (s)"}
)
st.line_chart(lat_df)

# ── Full table ─────────────────────────────────────────────────────────────────
st.subheader("Run Details")
st.dataframe(df, use_container_width=True)

# ── Paper figure caption ───────────────────────────────────────────────────────
st.divider()
st.caption(
    "**Figure caption (MoMa paper):** Throughput scaling on a 3-node GTX 1080 Ti grid. "
    "Grid throughput (tokens/s) as a function of active agent count. "
    "Measured using recipe 13 with identical 30-task batches at each configuration."
)
