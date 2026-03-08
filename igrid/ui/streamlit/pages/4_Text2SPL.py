"""
Text2SPL page: natural language → SPL query, then run on the Momahub.

Adapted from SPL-flow's Text2SPLNode — uses the hub's Ollama backend
(or any registered adapter) to do the NL→SPL translation.
"""

import asyncio
import os
import re
import uuid

import httpx
import streamlit as st

HUB_URL = os.environ.get("IGRID_HUB_URL", "http://localhost:8000")

st.set_page_config(page_title="Text2SPL", layout="wide")
st.title("✏️ Text2SPL — Natural Language to SPL")
st.caption(
    "Describe what you want in plain English (or any language). "
    "The grid translates it to SPL and can run it immediately."
)

hub_url = st.sidebar.text_input("Hub URL", value=HUB_URL)

# ---------------------------------------------------------------------------
# SPL system prompt (adapted from SPL-flow spl_templates.py)
# ---------------------------------------------------------------------------

_TEXT2SPL_SYSTEM = """\
You are an expert SPL (Structured Prompt Language) code generator.
SPL is a SQL-inspired declarative language for orchestrating LLM prompts on a distributed AI inference grid.

## SPL Syntax Reference

```sql
PROMPT <name>
[WITH BUDGET <n> tokens]
[USING MODEL "<ollama-model-name>"]

[WITH <cte_name> AS (
    PROMPT <inner_name>
    [WITH BUDGET <n> tokens]
    [USING MODEL "<model>"]

    SELECT
        SYSTEM_ROLE('system prompt text'),
        context.<param> AS <alias>

    GENERATE
        <identifier>('<instruction with {alias} placeholders>'
                     [FORMAT markdown|json|text]
                     [TEMPERATURE <0.0-1.0>])
    [WITH OUTPUT BUDGET <n>]
),
<cte2> AS ( ... )]

SELECT
    SYSTEM_ROLE('system prompt'),
    context.<param> AS <alias>,
    RAG_QUERY('<query string>') AS <alias>

GENERATE
    <identifier>('<instruction>'
                 [FORMAT markdown|json|text]
                 [TEMPERATURE <0.0-1.0>])
[WITH OUTPUT BUDGET <n>];
```

## When to Use CTEs

Use multi-model CTEs when the task has **distinct sub-tasks**:
- Analysis in multiple steps (extract data → synthesise)
- Parallel independent sub-questions (answers gathered, then composed)
- Different language or domain specialists needed per sub-task

Use a **single PROMPT** when one model handles the task well.

## Critical Syntax Rules

1. Statement starts with `PROMPT <name>`
2. `WITH BUDGET <n> tokens` and `USING MODEL "<model>"` come BEFORE any `WITH` or `SELECT` clauses.
3. Model names MUST be in double quotes: `USING MODEL "llama3"`
4. `GENERATE` MUST be followed by an identifier: `GENERATE my_result('...')`
5. `{alias}` placeholders inside GENERATE refer to SELECT aliases
6. `WITH OUTPUT BUDGET <n>` comes AFTER the GENERATE block.
7. Statement ends with semicolon.
8. Output ONLY valid SPL — no explanation, no markdown code fences.

## Output Budget Guide

| Output type                    | BUDGET  |
|-------------------------------|---------|
| Short answer / sentence       | 200–400 |
| Paragraph / brief summary     | 400–800 |
| List of 5–10 items            | 800–1500|
| Full table / structured report| 2000–4000|
| Long-form analysis            | 2000–4000|"""

_TEXT2SPL_EXAMPLES = """
---
## EXAMPLE 1 — Simple single-model grid query

User: "Summarize this article in 3 bullet points"

```sql
PROMPT summarize_article
WITH BUDGET 1000 tokens
USING MODEL "llama3"

SELECT
    SYSTEM_ROLE('You are a concise technical writer.'),
    context.article AS doc

GENERATE
    summary('Summarize {doc} in exactly 3 bullet points. Each bullet captures a key insight.'
            FORMAT markdown
            TEMPERATURE 0.3)
WITH OUTPUT BUDGET 500 tokens;
```

---
## EXAMPLE 2 — Parallel CTE analysis

User: "Compare pros and cons of distributed AI inference, then synthesise"

```sql
PROMPT synthesise
WITH BUDGET 4000 tokens
USING MODEL "llama3"

WITH
    pros AS (
        PROMPT list_pros
        WITH BUDGET 1000 tokens
        USING MODEL "llama3"

        SELECT
            SYSTEM_ROLE('You are a technology analyst.')
        GENERATE
            advantages('List 5 key advantages of distributed LLM inference.'
                       FORMAT markdown)
        WITH OUTPUT BUDGET 800 tokens
    ),
    cons AS (
        PROMPT list_cons
        WITH BUDGET 1000 tokens
        USING MODEL "mistral"

        SELECT
            SYSTEM_ROLE('You are a critical technology reviewer.')
        GENERATE
            challenges('List 5 key challenges of distributed LLM inference.'
                       FORMAT markdown)
        WITH OUTPUT BUDGET 800 tokens
    )

SELECT
    SYSTEM_ROLE('You are a balanced technology writer.'),
    context.pros AS advantages,
    context.cons AS challenges

GENERATE
    assessment('Given advantages: {advantages}\\nAnd challenges: {challenges}\\nWrite a balanced 4-sentence assessment.'
               FORMAT markdown
               TEMPERATURE 0.5)
WITH OUTPUT BUDGET 1500 tokens;
```"""



def _build_text2spl_prompt(user_query: str, error: str = "") -> str:
    parts = [_TEXT2SPL_SYSTEM, _TEXT2SPL_EXAMPLES, "---"]
    if error:
        parts.append(
            f"## Previous attempt failed to parse\n\nError: {error}\n\n"
            "Please fix the SPL syntax and try again."
        )
    parts.append(
        f"## User Request\n\n{user_query}\n\n"
        "Output ONLY valid SPL code. No explanation. No markdown fences."
    )
    return "\n\n".join(parts)


def _strip_llm_artifacts(spl: str) -> str:
    """Remove <think> blocks and markdown fences that LLMs sometimes emit."""
    spl = re.sub(r"<think>.*?</think>", "", spl, flags=re.DOTALL | re.IGNORECASE)
    spl = re.sub(r"<think>.*", "", spl, flags=re.DOTALL | re.IGNORECASE)
    spl = spl.strip()
    if spl.startswith("```"):
        lines = spl.split("\n")
        end = -1 if lines[-1].strip() == "```" else len(lines)
        spl = "\n".join(lines[1:end])
    return spl.strip()


# ---------------------------------------------------------------------------
# Submit a task to the hub and poll for result
# ---------------------------------------------------------------------------

def _submit_and_poll(
    hub: str, model: str, prompt: str, system: str, max_tokens: int
) -> tuple[str, str]:
    """Returns (content, error)."""
    task_id = str(uuid.uuid4())
    payload = {
        "task_id": task_id,
        "model": model,
        "prompt": prompt,
        "system": system,
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }
    import time
    try:
        with httpx.Client(timeout=10.0) as client:
            client.post(f"{hub}/tasks", json=payload).raise_for_status()

        deadline = time.monotonic() + 120
        interval = 2.0
        with httpx.Client(timeout=5.0) as client:
            while time.monotonic() < deadline:
                r = client.get(f"{hub}/tasks/{task_id}")
                data = r.json()
                state = data.get("state", "")
                if state == "COMPLETE":
                    return data.get("result", {}).get("content", ""), ""
                if state == "FAILED":
                    return "", data.get("result", {}).get("error", "unknown")
                time.sleep(interval)
                interval = min(interval * 1.3, 8.0)
        return "", "Timed out waiting for Text2SPL translation"
    except Exception as exc:
        return "", str(exc)


def _run_spl_on_grid(hub: str, spl_source: str) -> tuple[str, str]:
    """Parse and run SPL via IGridAdapter. Returns (content, error)."""
    try:
        from spl.lexer import Lexer
        from spl.parser import Parser
        from spl.optimizer import Optimizer
        from spl.executor import Executor
        from igrid.spl.igrid_adapter import IGridAdapter

        tokens = Lexer(spl_source).tokenize()
        program = Parser(tokens).parse()
        stmts = program.statements
        optimizer = Optimizer()
        adapter = IGridAdapter(hub_url=hub)
        executor = Executor(adapter=adapter)

        async def _run():
            results = []
            for stmt in stmts:
                plan = optimizer.optimize_single(stmt)
                r = await executor.execute(plan, stmt=stmt)
                results.append(r)
            executor.close()
            return results

        results = asyncio.run(_run())
        combined = "\n\n---\n\n".join(r.content for r in results)
        return combined, ""
    except ImportError:
        return "", "SPL package not installed. Run: pip install -e /path/to/SPL"
    except Exception as exc:
        return "", str(exc)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader("1 · Describe your task")
    user_query = st.text_area(
        "What do you want to do?",
        height=160,
        placeholder=(
            "e.g. Analyse this research paper and summarise the methodology, "
            "results and limitations. Run it on the grid overnight."
        ),
    )

    translate_model = st.text_input(
        "Translation model (on grid)",
        value="llama3",
        help="Ollama model used to translate your query into SPL",
    )

    translate_btn = st.button("🔄 Translate to SPL", type="primary")

with col_right:
    st.subheader("2 · Generated SPL")

    # Session state to hold generated SPL across reruns
    if "generated_spl" not in st.session_state:
        st.session_state.generated_spl = ""
    if "translate_error" not in st.session_state:
        st.session_state.translate_error = ""

    if translate_btn:
        if not user_query.strip():
            st.warning("Please describe your task first.")
        else:
            with st.spinner(f"Translating via {translate_model} on grid..."):
                prompt = _build_text2spl_prompt(
                    user_query, st.session_state.translate_error
                )
                content, err = _submit_and_poll(
                    hub_url, translate_model, prompt, _TEXT2SPL_SYSTEM, max_tokens=2000
                )
                if err:
                    st.error(f"Translation error: {err}")
                    st.session_state.translate_error = err
                else:
                    spl = _strip_llm_artifacts(content)
                    st.session_state.generated_spl = spl
                    st.session_state.translate_error = ""

    spl_editor = st.text_area(
        "Edit SPL if needed",
        value=st.session_state.generated_spl,
        height=300,
        key="spl_editor_box",
    )
    # Sync edits back to session state
    st.session_state.generated_spl = spl_editor

    if spl_editor.strip():
        st.download_button(
            "⬇️ Download .spl",
            data=spl_editor,
            file_name="query.spl",
            mime="text/plain",
        )

st.divider()
st.subheader("3 · Run on Grid")

run_col, hint_col = st.columns([1, 2])
with run_col:
    run_btn = st.button("⚡ Run SPL on Grid", type="primary",
                        disabled=not st.session_state.generated_spl.strip())
with hint_col:
    st.caption(
        "Requires the SPL package installed (`pip install -e /path/to/SPL`). "
        "Make sure at least one agent is online."
    )

if run_btn and st.session_state.generated_spl.strip():
    with st.spinner("Running SPL on the Momahub..."):
        content, err = _run_spl_on_grid(hub_url, st.session_state.generated_spl)
    if err:
        st.error(f"Run error: {err}")
    else:
        st.success("Done!")
        st.markdown("### Result")
        st.markdown(content)
        st.download_button(
            "⬇️ Download result",
            data=content,
            file_name="result.md",
            mime="text/markdown",
        )
