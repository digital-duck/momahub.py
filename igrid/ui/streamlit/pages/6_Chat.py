"""Test Runner page — submit prompts to Momahub via UI, single or batch."""
import json, os, time, uuid, httpx, streamlit as st

HUB_URL = os.environ.get("IGRID_HUB_URL", "http://localhost:8000")
st.set_page_config(page_title="Momahub Test Runner", layout="wide")
st.title("Momahub Test Runner")

# ── Sidebar ──────────────────────────────────────────────────────────
hub_url = st.sidebar.text_input("Hub URL", value=HUB_URL)

@st.cache_data(ttl=15)
def fetch_models(u):
    try:
        agents = httpx.get(f"{u}/agents", timeout=3.0).json().get("agents", [])
        models = set()
        for a in agents:
            if a.get("status") in ("ONLINE", "BUSY"):
                for m in json.loads(a.get("supported_models", "[]")):
                    models.add(m)
        return sorted(models) if models else ["llama3.1:8b"]
    except Exception:
        return ["llama3.1:8b"]

@st.cache_data(ttl=10)
def fetch_health(u):
    try:
        return httpx.get(f"{u}/health", timeout=3.0).json()
    except Exception as exc:
        return {"error": str(exc)}

health = fetch_health(hub_url)
if "error" in health:
    st.sidebar.error(f"Hub unreachable: {health['error']}")
else:
    st.sidebar.success(f"Hub: {health.get('hub_id', '?')} | Agents: {health.get('agents_online', 0)}")

if st.sidebar.button("Refresh"):
    st.cache_data.clear()
    st.rerun()

available_models = fetch_models(hub_url)

# ── Tabs ─────────────────────────────────────────────────────────────
tab_single, tab_batch, tab_results = st.tabs(["Single Prompt", "Batch / Stress Test", "Results"])

# ── Tab 1: Single Prompt ─────────────────────────────────────────────
with tab_single:
    st.subheader("Submit a single prompt")
    model = st.selectbox("Model", available_models, key="single_model")
    prompt = st.text_area("Prompt", height=120, key="single_prompt")
    col1, col2 = st.columns(2)
    max_tokens = col1.slider("Max tokens", 64, 4096, 1024, key="single_max_tokens")
    temperature = col2.slider("Temperature", 0.0, 2.0, 0.7, step=0.1, key="single_temp")

    if st.button("Submit", key="single_submit"):
        if not prompt.strip():
            st.warning("Enter a prompt.")
        else:
            task_id = str(uuid.uuid4())
            with st.spinner("Submitting..."):
                try:
                    httpx.post(f"{hub_url}/tasks",
                               json={"task_id": task_id, "model": model, "prompt": prompt,
                                     "max_tokens": max_tokens, "temperature": temperature},
                               timeout=5.0).raise_for_status()
                except Exception as exc:
                    st.error(f"Submit failed: {exc}")
                    st.stop()

            progress = st.progress(0, text="Waiting...")
            deadline = time.monotonic() + 300
            interval = 1.5
            steps = 0
            while time.monotonic() < deadline:
                data = httpx.get(f"{hub_url}/tasks/{task_id}", timeout=5.0).json()
                state = data.get("state", "")
                steps = min(steps + 5, 90)
                progress.progress(steps, text=f"State: {state}")
                if state == "COMPLETE":
                    progress.progress(100, text="Complete!")
                    r = data.get("result", {})
                    st.markdown("### Response")
                    st.write(r.get("content", ""))
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Model", r.get("model", ""))
                    c2.metric("Tokens", f"{r.get('input_tokens', 0)} + {r.get('output_tokens', 0)}")
                    c3.metric("Latency", f"{r.get('latency_ms', 0):.0f} ms")
                    c4.metric("Agent", r.get("agent_id", "")[:12])
                    # Store in session
                    if "results" not in st.session_state:
                        st.session_state.results = []
                    st.session_state.results.append({
                        "task_id": task_id, "category": "single", "model": model,
                        "prompt": prompt, "state": "COMPLETE", "content": r.get("content", ""),
                        "input_tokens": r.get("input_tokens", 0),
                        "output_tokens": r.get("output_tokens", 0),
                        "latency_ms": r.get("latency_ms", 0),
                        "agent_id": r.get("agent_id", ""),
                    })
                    break
                if state == "FAILED":
                    st.error(f"Failed: {data.get('result', {}).get('error', 'unknown')}")
                    break
                time.sleep(interval)
                interval = min(interval * 1.2, 5.0)

# ── Tab 2: Batch / Stress Test ───────────────────────────────────────
with tab_batch:
    st.subheader("Run test suite against the grid")

    # Load prompts
    prompts_dict = {}
    uploaded = st.file_uploader("Upload prompts JSON (or uses built-in tests/lan/prompts.json)", type="json")
    if uploaded:
        prompts_dict = json.load(uploaded)
    else:
        try:
            from tests.e2e.runner import load_prompts
            prompts_dict = load_prompts()
        except Exception:
            st.warning("Could not load default prompts file.")

    if prompts_dict:
        # Category selector
        all_cats = list(prompts_dict.keys())
        selected_cats = st.multiselect("Categories", all_cats, default=all_cats,
                                       help="Select which test categories to run")

        # Count prompts
        total_prompts = sum(len(prompts_dict[c]) for c in selected_cats)
        st.caption(f"{total_prompts} prompts selected across {len(selected_cats)} categories")

        # Show preview
        with st.expander("Preview prompts"):
            for cat in selected_cats:
                st.markdown(f"**{cat}** ({len(prompts_dict[cat])} prompts)")
                for i, entry in enumerate(prompts_dict[cat]):
                    st.text(f"  [{i+1}] {entry.get('model', '?')}: {entry.get('prompt', '')[:80]}")

        col1, col2, col3 = st.columns(3)
        concurrency = col1.number_input("Concurrency", 1, 20, 1, help="Parallel submissions")
        repeat = col2.number_input("Repeat", 1, 10, 1, help="Repeat entire batch N times")
        timeout_s = col3.number_input("Timeout (s)", 30, 600, 300)
        run_label = st.text_input("Run label", value="", placeholder="e.g. hub-machine-A")

        if st.button("Run Batch", type="primary", key="batch_run"):
            if not selected_cats:
                st.warning("Select at least one category.")
            else:
                from tests.e2e.runner import run_categories
                total = total_prompts * repeat
                progress = st.progress(0, text=f"Running 0/{total}...")
                results_container = st.container()
                done = {"n": 0}
                live_results = []

                def on_result(r):
                    done["n"] += 1
                    pct = int(done["n"] / total * 100)
                    status = "OK" if r.state == "COMPLETE" else r.state
                    progress.progress(pct, text=f"[{done['n']}/{total}] {status} {r.model}")
                    live_results.append(r)

                report = run_categories(
                    hub_url, prompts_dict, categories=selected_cats,
                    concurrency=concurrency, timeout_s=timeout_s, repeat=repeat,
                    on_result=on_result, label=run_label or "batch",
                )
                progress.progress(100, text="Done!")

                # Summary
                s = report.summary()
                st.markdown("### Results Summary")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Completed", s["completed"])
                c2.metric("Failed", s["failed"])
                c3.metric("Avg Latency", f"{s.get('avg_latency_ms', 0):.0f} ms")
                c4.metric("Avg TPS", f"{s.get('avg_tps', 0):.1f}")

                c5, c6, c7, c8 = st.columns(4)
                c5.metric("Total Tokens", s.get("total_tokens", 0))
                c6.metric("Wall Time", f"{s.get('wall_time_s', 0):.1f}s")
                c7.metric("Agents Used", s.get("agents_used", 0))
                c8.metric("Timed Out", s["timed_out"])

                # Agent distribution
                dist = s.get("agent_distribution", {})
                if dist:
                    st.markdown("**Agent distribution**")
                    import pandas as pd
                    st.bar_chart(pd.Series(dist, name="tasks"))

                # Results table
                st.markdown("### Task Details")
                import pandas as pd
                rows = []
                for r in report.results:
                    rows.append({
                        "category": r.category, "model": r.model, "state": r.state,
                        "tokens": r.output_tokens, "latency_ms": round(r.latency_ms, 0),
                        "tps": round(r.tps, 1), "agent": r.agent_id,
                        "prompt": r.prompt[:60], "response": (r.content or "")[:100],
                        "error": r.error,
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True)

                # Store for Results tab
                st.session_state.last_report = report.to_json()

                # Download button
                report_json = json.dumps(report.to_json(), indent=2)
                st.download_button("Download results JSON", report_json,
                                   file_name=f"test-{run_label or 'batch'}.json",
                                   mime="application/json")

# ── Tab 3: Results viewer ────────────────────────────────────────────
with tab_results:
    st.subheader("View & compare test results")

    uploaded_results = st.file_uploader("Load results JSON", type="json", key="results_upload",
                                        accept_multiple_files=True)
    reports = []
    if uploaded_results:
        for f in uploaded_results:
            reports.append(json.load(f))
    if "last_report" in st.session_state:
        reports.append(st.session_state.last_report)

    if not reports:
        st.info("Run a batch test or upload result files to view them here.")
    else:
        # Comparison table
        import pandas as pd
        rows = []
        for r in reports:
            s = r.get("summary", {})
            rows.append({
                "label": r.get("label", "?"),
                "total": s.get("total", 0),
                "completed": s.get("completed", 0),
                "failed": s.get("failed", 0),
                "avg_latency_ms": s.get("avg_latency_ms", 0),
                "avg_tps": s.get("avg_tps", 0),
                "total_tokens": s.get("total_tokens", 0),
                "wall_time_s": s.get("wall_time_s", 0),
                "agents_used": s.get("agents_used", 0),
            })
        st.markdown("### Run Comparison")
        st.dataframe(pd.DataFrame(rows), use_container_width=True)

        # Per-report details
        for r in reports:
            with st.expander(f"Details: {r.get('label', '?')}"):
                results_list = r.get("results", [])
                if results_list:
                    df = pd.DataFrame(results_list)
                    display_cols = [c for c in ["category", "model", "state", "output_tokens",
                                                "latency_ms", "tps", "agent_id", "prompt", "error"]
                                   if c in df.columns]
                    st.dataframe(df[display_cols], use_container_width=True)

                    # Per-model breakdown
                    completed = df[df["state"] == "COMPLETE"]
                    if not completed.empty:
                        st.markdown("**Per-model stats**")
                        model_stats = completed.groupby("model").agg(
                            count=("state", "size"),
                            avg_latency=("latency_ms", "mean"),
                            avg_tps=("tps", "mean"),
                            total_tokens=("output_tokens", "sum"),
                        ).round(1)
                        st.dataframe(model_stats, use_container_width=True)
