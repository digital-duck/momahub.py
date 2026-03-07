"""Run SPL page."""
import os, uuid, time, httpx, streamlit as st
HUB_URL = os.environ.get("IGRID_HUB_URL", "http://localhost:8000")
st.set_page_config(page_title="Run SPL", layout="wide")
st.title("⚡ Run on Grid")
hub_url = st.sidebar.text_input("Hub URL", value=HUB_URL)
tab_simple, tab_spl = st.tabs(["Simple Prompt", "SPL Query"])

with tab_simple:
    st.subheader("Submit a single prompt to the grid")
    model = st.text_input("Model", value="llama3")
    prompt = st.text_area("Prompt", height=150)
    max_tokens = st.slider("Max tokens", 64, 4096, 512)
    if st.button("Submit to Grid", key="submit_simple"):
        if not prompt.strip():
            st.warning("Please enter a prompt.")
        else:
            task_id = str(uuid.uuid4())
            with st.spinner("Submitting..."):
                try:
                    httpx.post(f"{hub_url}/tasks", json={"task_id": task_id, "model": model, "prompt": prompt, "max_tokens": max_tokens}, timeout=5.0).raise_for_status()
                    st.success(f"Task submitted: `{task_id}`")
                    bar = st.progress(0, text="Waiting...")
                    deadline = time.monotonic() + 120; interval = 2.0; steps = 0
                    while time.monotonic() < deadline:
                        r = httpx.get(f"{hub_url}/tasks/{task_id}", timeout=5.0); data = r.json()
                        state = data.get("state", ""); steps = min(steps+5, 90); bar.progress(steps, text=f"State: {state}")
                        if state == "COMPLETE":
                            bar.progress(100, text="Complete!")
                            result = data.get("result", {}); st.markdown("### Result"); st.write(result.get("content", ""))
                            col1,col2,col3 = st.columns(3)
                            col1.metric("Model", result.get("model","—")); col2.metric("Tokens", f"{result.get('input_tokens',0)}+{result.get('output_tokens',0)}"); col3.metric("Latency", f"{result.get('latency_ms',0):.0f}ms")
                            break
                        if state == "FAILED":
                            st.error(f"Failed: {data.get('result',{}).get('error','unknown')}"); break
                        time.sleep(interval); interval = min(interval*1.3, 8.0)
                except Exception as exc: st.error(f"Error: {exc}")

with tab_spl:
    st.subheader("Run SPL on the grid")
    spl_source = st.text_area("SPL source", height=250, value="PROMPT hello_grid\nSELECT\n    SYSTEM_ROLE('You are a helpful assistant.'),\n    GENERATE('Say hello from the i-grid in one sentence.')\nUSING MODEL 'llama3'\nON GRID;")
    params_json = st.text_input("Params (JSON)", value="{}")
    if st.button("Run SPL", key="run_spl"):
        try:
            import json, asyncio
            from spl.lexer import Lexer; from spl.parser import Parser
            from spl.optimizer import Optimizer; from spl.executor import Executor
            from igrid.spl.igrid_adapter import IGridAdapter
            params = json.loads(params_json or "{}")
            tokens = Lexer(spl_source).tokenize()
            program = Parser(tokens).parse()
            stmts = program.statements
            adapter = IGridAdapter(hub_url=hub_url); executor = Executor(adapter=adapter)
            async def _run():
                results = []
                for stmt in stmts:
                    plan = Optimizer().optimize_single(stmt)
                    r = await executor.execute(plan, params=params, stmt=stmt); results.append((plan.prompt_name, r))
                executor.close(); return results
            with st.spinner("Running..."):
                results = asyncio.run(_run())
            for name, r in results:
                st.markdown(f"### {name}"); st.write(r.content)
                st.caption(f"model={r.model}  tokens={r.input_tokens}+{r.output_tokens}  latency={r.latency_ms:.0f}ms")
        except ImportError: st.error("SPL package not installed.")
        except Exception as exc: st.error(f"Error: {exc}")
