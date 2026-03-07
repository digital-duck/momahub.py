"""MoMa Compiler Pipeline Demo page.

Interactive 5-step pipeline: translate → concepts → optimise → generate → format.
Each step dispatched to the grid. Steps 2+3 run in parallel. Live progress timeline.

Demonstrates the MoMa Compiler front-end → mid-end → back-end architecture.
"""
from __future__ import annotations

import os
import time
import uuid

import httpx
import streamlit as st

HUB_URL = os.environ.get("IGRID_HUB_URL", "http://localhost:8000")
st.set_page_config(page_title="MoMa Compiler Demo", layout="wide")
st.title("🔧 MoMa Compiler Pipeline")
st.caption(
    "Type a query in any language. Watch the 5-step compiler pipeline execute on the grid: "
    "translate → extract concepts → optimise → generate → format."
)

hub_url = st.sidebar.text_input("Hub URL", value=HUB_URL)

@st.cache_data(ttl=15)
def fetch_models(u):
    try:
        import json
        agents = httpx.get(f"{u}/agents", timeout=3.0).json().get("agents", [])
        models = set()
        for a in agents:
            if a.get("status") == "ONLINE":
                for m in json.loads(a.get("supported_models", "[]")):
                    models.add(m)
        return sorted(models) or ["llama3"]
    except Exception:
        return ["llama3"]

available_models = fetch_models(hub_url)

STEP_SYSTEMS = {
    "translate": (
        "You are a translation assistant. If the input is already in English, "
        "output it unchanged. Otherwise translate it accurately to English."
    ),
    "concepts": (
        "You are an NLP analyst. Extract 3-5 key concepts from this query as a "
        "comma-separated list. Output ONLY the concepts, nothing else."
    ),
    "optimise": (
        "You are a prompt engineer. Rewrite this query to be clearer and more specific. "
        "Output ONLY the rewritten query, nothing else."
    ),
    "generate": (
        "You are a knowledgeable assistant. Answer the question clearly and accurately "
        "in 3-5 sentences."
    ),
    "format": (
        "You are a technical writer. Format this response as: "
        "(1) TL;DR: one sentence. (2) Full answer: the explanation."
    ),
}

STEP_LABELS = {
    "translate": "Step 1 · Translate [front-end]",
    "concepts":  "Step 2 · Extract Concepts [mid-end]",
    "optimise":  "Step 3 · Optimise Query [mid-end]",
    "generate":  "Step 4 · Generate Response [back-end]",
    "format":    "Step 5 · Format Output",
}

STEP_PARALLELS = {"concepts": "parallel with Step 3", "optimise": "parallel with Step 2"}

DEMO_QUERIES = [
    "What is distributed AI inference and why does it matter?",
    "机器学习和深度学习有什么区别？",
    "Qu'est-ce que l'intelligence artificielle?",
    "¿Cómo funciona una red neuronal?",
]

# ── Input ─────────────────────────────────────────────────────────────────────
col_input, col_settings = st.columns([2, 1])

with col_input:
    demo_choice = st.selectbox("Demo query", ["(custom)"] + DEMO_QUERIES)
    if demo_choice == "(custom)":
        query = st.text_area("Your query (any language)", height=80,
                             placeholder="Ask anything in any language...")
    else:
        query = st.text_area("Your query (any language)", value=demo_choice, height=80)

with col_settings:
    st.markdown("**Model settings**")
    translate_model = st.selectbox("Translate + Analyse", available_models,
                                   index=0, key="t_model")
    generate_model  = st.selectbox("Generate",  available_models, index=0, key="g_model")
    format_model    = st.selectbox("Format",     available_models, index=0, key="f_model")
    max_tokens      = st.slider("Max tokens (generate)", 128, 2048, 512)
    timeout_s       = st.slider("Timeout (s)", 30, 300, 120)

run_btn = st.button("▶ Run Pipeline", type="primary",
                    disabled=not query.strip())

if not run_btn:
    st.stop()

# ── Helpers ───────────────────────────────────────────────────────────────────
def submit_task(hub, prompt, system, model, max_tok):
    task_id = f"compiler-{uuid.uuid4().hex[:8]}"
    httpx.post(f"{hub}/tasks", json={
        "task_id": task_id, "model": model,
        "prompt": prompt, "system": system,
        "max_tokens": max_tok, "temperature": 0.3,
    }, timeout=5.0).raise_for_status()
    return task_id


def poll_task(hub, task_id, timeout_s):
    deadline = time.monotonic() + timeout_s
    interval = 1.5
    while time.monotonic() < deadline:
        try:
            data = httpx.get(f"{hub}/tasks/{task_id}", timeout=5.0).json()
            state = data.get("state", "")
            if state == "COMPLETE":
                return data.get("result", {})
            if state == "FAILED":
                return {"error": data.get("result", {}).get("error", "failed")}
        except Exception:
            pass
        time.sleep(interval)
        interval = min(interval * 1.2, 8.0)
    return {"error": "timeout"}

# ── Pipeline UI ───────────────────────────────────────────────────────────────
st.divider()
st.subheader("Pipeline Execution")

# Placeholders for live steps
placeholders = {s: st.empty() for s in STEP_LABELS}
summary_ph = st.empty()

def render_step(step, state, content="", latency=0.0, agent="", model=""):
    label = STEP_LABELS[step]
    parallel = STEP_PARALLELS.get(step, "")
    icon = {"running": "⏳", "done": "✅", "failed": "❌", "waiting": "⬜"}.get(state, "⬜")
    parallel_note = f" *(running in parallel)*" if parallel and state == "running" else ""
    with placeholders[step].container():
        with st.expander(f"{icon} {label}{parallel_note}", expanded=(state == "done")):
            if state == "done" and content:
                st.write(content)
                if latency:
                    st.caption(f"{latency:.1f}s | model={model} | agent=..{agent[-12:]}")
            elif state == "running":
                st.caption("Dispatched to grid, waiting...")
            elif state == "failed":
                st.error(content or "Failed")

# Init all as waiting
for step in STEP_LABELS:
    render_step(step, "waiting")

wall_start = time.monotonic()
step_results = {}

try:
    # ── Step 1: Translate ──────────────────────────────────────────────────
    render_step("translate", "running")
    t0 = time.monotonic()
    tid = submit_task(hub_url, query, STEP_SYSTEMS["translate"],
                      translate_model, 256)
    r = poll_task(hub_url, tid, timeout_s)
    if "error" in r:
        render_step("translate", "failed", r["error"])
        st.error("Pipeline aborted at Step 1.")
        st.stop()

    eng_query = r.get("content", query).strip()
    step_results["translate"] = r
    render_step("translate", "done", eng_query,
                int(r.get("latency_ms", 0)) / 1000, r.get("agent_id", ""), translate_model)

    # ── Steps 2+3: Parallel ───────────────────────────────────────────────
    render_step("concepts", "running")
    render_step("optimise", "running")

    tid2 = submit_task(hub_url, eng_query, STEP_SYSTEMS["concepts"],
                       translate_model, 128)
    tid3 = submit_task(hub_url, eng_query, STEP_SYSTEMS["optimise"],
                       translate_model, 256)
    r2 = poll_task(hub_url, tid2, timeout_s)
    r3 = poll_task(hub_url, tid3, timeout_s)

    concepts = r2.get("content", "").strip() if "error" not in r2 else ""
    optimised = r3.get("content", eng_query).strip() if "error" not in r3 else eng_query

    render_step("concepts", "done" if "error" not in r2 else "failed",
                concepts, int(r2.get("latency_ms") or 0) / 1000,
                r2.get("agent_id", ""), translate_model)
    render_step("optimise", "done" if "error" not in r3 else "failed",
                optimised, int(r3.get("latency_ms") or 0) / 1000,
                r3.get("agent_id", ""), translate_model)

    # ── Step 4: Generate ──────────────────────────────────────────────────
    render_step("generate", "running")
    tid4 = submit_task(hub_url, optimised, STEP_SYSTEMS["generate"],
                       generate_model, max_tokens)
    r4 = poll_task(hub_url, tid4, timeout_s)
    if "error" in r4:
        render_step("generate", "failed", r4["error"])
        st.error("Pipeline aborted at Step 4.")
        st.stop()

    raw_response = r4.get("content", "").strip()
    render_step("generate", "done", raw_response,
                int(r4.get("latency_ms") or 0) / 1000, r4.get("agent_id", ""), generate_model)

    # ── Step 5: Format ────────────────────────────────────────────────────
    render_step("format", "running")
    format_prompt = f"Query: {eng_query}\n\nResponse: {raw_response}"
    tid5 = submit_task(hub_url, format_prompt, STEP_SYSTEMS["format"],
                       format_model, max_tokens)
    r5 = poll_task(hub_url, tid5, timeout_s)
    final = r5.get("content", raw_response).strip() if "error" not in r5 else raw_response
    render_step("format", "done" if "error" not in r5 else "failed",
                final, int(r5.get("latency_ms") or 0) / 1000,
                r5.get("agent_id", ""), format_model)

    wall_time = time.monotonic() - wall_start

    # ── Summary ───────────────────────────────────────────────────────────
    with summary_ph.container():
        st.divider()
        st.subheader("Final Output")
        st.markdown(final)

        st.divider()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Wall time", f"{wall_time:.1f}s")
        all_results = [r, r2, r3, r4, r5]
        total_tokens = sum(int(x.get("output_tokens") or 0) for x in all_results if "error" not in x)
        c2.metric("Total tokens", total_tokens)
        agents_used = {x.get("agent_id", "")[-14:] for x in all_results
                       if x.get("agent_id") and "error" not in x}
        c3.metric("Agents used", len(agents_used))
        c4.metric("Steps parallel", "2+3")

        st.caption(
            f"Original: `{query[:80]}`  →  English: `{eng_query[:80]}`  →  "
            f"Concepts: `{concepts[:60]}`"
        )

except Exception as exc:
    st.error(f"Pipeline error: {exc}")
