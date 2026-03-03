"""
Paper Digest page: submit arxiv URLs overnight, wake up to an HTML digest.

Workflow:
  1. Paste one or more arxiv URLs
  2. Choose extraction engine (pypdf or docling), model, and analysis depth
  3. Click "Analyse" — tasks fan out to the grid in parallel
  4. Watch live progress; download the HTML digest when done

Extraction engines:
  pypdf  — fast, zero-weight, text-only; fine for single-column preprints
  docling — IBM layout-aware engine; preserves tables, figures, reading order;
             requires `pip install docling` and ~1-2 GB model download on first run
"""

from __future__ import annotations
import io
import os
import re
import tempfile
import time
import uuid
from datetime import datetime
from textwrap import dedent

import httpx
import streamlit as st

# ---------------------------------------------------------------------------
# Optional engine imports
# ---------------------------------------------------------------------------

try:
    import pypdf  # type: ignore
    _PYPDF_OK = True
except ImportError:
    _PYPDF_OK = False

try:
    from docling.document_converter import DocumentConverter  # type: ignore
    _DOCLING_OK = True
except ImportError:
    _DOCLING_OK = False

HUB_URL = os.environ.get("IGRID_HUB_URL", "http://localhost:8000")
ARXIV_PDF_BASE = "https://arxiv.org/pdf"
ARXIV_ABS_BASE = "https://arxiv.org/abs"

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Paper Digest", layout="wide")
st.title("📚 Arxiv Paper Digest")
st.caption(
    "Drop arxiv URLs before you sleep — the grid reads and digests them overnight. "
    "Wake up to a ready-to-share HTML report."
)

# ---------------------------------------------------------------------------
# Sidebar — hub + engine selector
# ---------------------------------------------------------------------------

hub_url = st.sidebar.text_input("Hub URL", value=HUB_URL)

st.sidebar.markdown("---")
st.sidebar.markdown("### PDF Extraction Engine")

_ENGINE_LABELS = ["pypdf", "docling"]
engine = st.sidebar.radio(
    "Engine",
    _ENGINE_LABELS,
    captions=[
        "Fast · lightweight · text only",
        "Slow · layout-aware · tables + figures",
    ],
    label_visibility="collapsed",
)

if engine == "pypdf":
    if _PYPDF_OK:
        st.sidebar.success(
            "**pypdf** is ready.  \n"
            "Best for: single-column LaTeX preprints.  \n"
            "⚠️ Two-column layouts, tables, and math may be garbled."
        )
    else:
        st.sidebar.error("pypdf not installed — run: `pip install pypdf`")

else:  # docling
    st.sidebar.info(
        "**docling** (IBM Research) understands document layout:  \n"
        "✅ Multi-column reading order  \n"
        "✅ Tables → clean Markdown  \n"
        "✅ Figure captions extracted  \n"
        "✅ OCR for scanned PDFs  \n\n"
        "**First run** downloads ~1-2 GB of models.  \n"
        "⏱️ ~10-30 s per paper (GPU recommended)."
    )
    if not _DOCLING_OK:
        st.sidebar.error(
            "docling not installed.  \n"
            "Run: `pip install docling`  \n"
            "Then restart the Streamlit app."
        )

# ---------------------------------------------------------------------------
# Arxiv helpers
# ---------------------------------------------------------------------------

_ARXIV_ID_RE = re.compile(
    r"(?:arxiv\.org/(?:abs|pdf)/|^)(\d{4}\.\d{4,5}(?:v\d+)?)"
)


def _extract_arxiv_id(url: str) -> str | None:
    url = url.strip()
    m = _ARXIV_ID_RE.search(url)
    return m.group(1) if m else None


def _pdf_url(arxiv_id: str) -> str:
    return f"{ARXIV_PDF_BASE}/{arxiv_id}"


def _abs_url(arxiv_id: str) -> str:
    return f"{ARXIV_ABS_BASE}/{arxiv_id}"


def _fetch_pdf_bytes(arxiv_id: str, timeout: float = 30.0) -> bytes | None:
    url = _pdf_url(arxiv_id)
    try:
        resp = httpx.get(url, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        return resp.content
    except Exception as exc:
        st.warning(f"Could not fetch {url}: {exc}")
        return None


# ---------------------------------------------------------------------------
# Extraction — pypdf
# ---------------------------------------------------------------------------

def _extract_text_pypdf(pdf_bytes: bytes, max_chars: int) -> str:
    """Fast text extraction with pypdf. No layout awareness."""
    if not _PYPDF_OK:
        return "[pypdf not installed]"
    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        parts, total = [], 0
        for page in reader.pages:
            text = page.extract_text() or ""
            parts.append(text)
            total += len(text)
            if total >= max_chars:
                break
        return "\n".join(parts)[:max_chars]
    except Exception as exc:
        return f"[pypdf extraction error: {exc}]"


# ---------------------------------------------------------------------------
# Extraction — docling
# ---------------------------------------------------------------------------

def _extract_text_docling(pdf_bytes: bytes, max_chars: int) -> str:
    """
    Layout-aware extraction via docling.

    Returns clean Markdown that preserves:
    - Correct reading order for multi-column papers
    - Tables as Markdown tables
    - Figure captions labelled [Figure N]
    - Section headings as # / ## / ###
    """
    if not _DOCLING_OK:
        return "[docling not installed]"
    tmp_path = None
    try:
        # docling requires a file path; write bytes to a temp file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fh:
            fh.write(pdf_bytes)
            tmp_path = fh.name

        converter = DocumentConverter()
        result = converter.convert(tmp_path)
        md = result.document.export_to_markdown()
        return md[:max_chars]
    except Exception as exc:
        return f"[docling extraction error: {exc}]"
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _extract_text(pdf_bytes: bytes, max_chars: int, use_docling: bool) -> str:
    if use_docling:
        return _extract_text_docling(pdf_bytes, max_chars)
    return _extract_text_pypdf(pdf_bytes, max_chars)


# ---------------------------------------------------------------------------
# Metadata scrape
# ---------------------------------------------------------------------------

def _fetch_abstract(arxiv_id: str) -> dict:
    """Light HTML scrape of arxiv abs page for title / authors."""
    meta: dict = {"title": arxiv_id, "authors": ""}
    try:
        resp = httpx.get(_abs_url(arxiv_id), timeout=10.0, follow_redirects=True)
        html = resp.text
        m = re.search(
            r'<h1 class="title[^"]*">\s*(?:<span[^>]*>[^<]*</span>\s*)?([^<]+)', html
        )
        if m:
            meta["title"] = m.group(1).strip()
        m = re.search(r'<div class="authors">(.*?)</div>', html, re.DOTALL)
        if m:
            authors_raw = re.sub(r"<[^>]+>", "", m.group(1))
            meta["authors"] = re.sub(r"\s+", " ", authors_raw).strip()
    except Exception:
        pass
    return meta


# ---------------------------------------------------------------------------
# Grid task submission + polling
# ---------------------------------------------------------------------------

_ANALYSIS_SYSTEM = (
    "You are a rigorous academic reviewer who produces clear, structured paper digests. "
    "Write in precise English. Be specific — avoid vague phrases like 'this paper presents'. "
    "Always ground your analysis in the actual text provided."
)

_ANALYSIS_PROMPT_TEMPLATE = """\
## Paper text

{text}

---

Produce a structured digest with the following sections:

### 1. Title & Core Claim (1–2 sentences)
### 2. Problem Statement
### 3. Methodology
### 4. Key Results  (include numbers / tables if present in the text)
### 5. Limitations & Open Questions
### 6. Relevance  (who should read this and why)
### 7. One-Line Summary  (a single sentence for a literature review)
"""


def _submit_analysis_task(
    hub: str, arxiv_id: str, paper_text: str, model: str, max_tokens: int
) -> str:
    task_id = f"digest-{arxiv_id.replace('.', '-')}-{uuid.uuid4().hex[:6]}"
    payload = {
        "task_id": task_id,
        "model": model,
        "prompt": _ANALYSIS_PROMPT_TEMPLATE.format(text=paper_text),
        "system": _ANALYSIS_SYSTEM,
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }
    with httpx.Client(timeout=10.0) as client:
        client.post(f"{hub}/tasks", json=payload).raise_for_status()
    return task_id


def _poll_task(hub: str, task_id: str, timeout_s: int = 600) -> dict:
    deadline = time.monotonic() + timeout_s
    interval = 3.0
    with httpx.Client(timeout=5.0) as client:
        while time.monotonic() < deadline:
            try:
                r = client.get(f"{hub}/tasks/{task_id}")
                data = r.json()
                if data.get("state", "") in ("COMPLETE", "FAILED"):
                    return data
            except Exception:
                pass
            time.sleep(interval)
            interval = min(interval * 1.2, 15.0)
    return {"state": "TIMEOUT", "result": None}


# ---------------------------------------------------------------------------
# HTML digest builder
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Arxiv Paper Digest — {date}</title>
<style>
  :root {{
    --bg: #0f1117; --card: #1a1d27; --accent: #4f8ef7;
    --text: #e0e0e0; --sub: #9ca3af; --border: #2d3148;
    --ok: #22c55e; --warn: #f59e0b;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text);
          font-family: 'Segoe UI', system-ui, sans-serif;
          padding: 2rem; max-width: 960px; margin: 0 auto; }}
  h1 {{ font-size: 1.8rem; color: var(--accent); margin-bottom: 0.25rem; }}
  .meta {{ color: var(--sub); font-size: 0.85rem; margin-bottom: 2.5rem; }}
  .card {{ background: var(--card); border: 1px solid var(--border);
           border-radius: 12px; padding: 1.5rem; margin-bottom: 1.8rem; }}
  .card-header {{ display: flex; justify-content: space-between;
                  align-items: flex-start; margin-bottom: 1rem; }}
  .paper-title {{ font-size: 1.1rem; font-weight: 600; color: var(--accent); }}
  .paper-authors {{ font-size: 0.8rem; color: var(--sub); margin-top: 0.2rem; }}
  .arxiv-link {{ font-size: 0.78rem; color: var(--sub); text-decoration: none;
                 border: 1px solid var(--border); border-radius: 6px;
                 padding: 0.2rem 0.5rem; white-space: nowrap; }}
  .arxiv-link:hover {{ color: var(--accent); border-color: var(--accent); }}
  .digest {{ font-size: 0.92rem; line-height: 1.65; white-space: pre-wrap; }}
  .digest h3 {{ color: var(--accent); font-size: 0.9rem; margin: 1rem 0 0.3rem; }}
  .digest table {{ border-collapse: collapse; width: 100%; margin: 0.8rem 0; font-size: 0.82rem; }}
  .digest td, .digest th {{ border: 1px solid var(--border); padding: 0.35rem 0.6rem; }}
  .digest th {{ background: #252840; color: var(--accent); }}
  .badge {{ display: inline-block; font-size: 0.72rem; border-radius: 20px;
            padding: 0.15rem 0.5rem; margin-left: 0.5rem; }}
  .badge-ok   {{ background: rgba(34,197,94,0.15); color: var(--ok); }}
  .badge-fail {{ background: rgba(245,158,11,0.15); color: var(--warn); }}
  .stats {{ font-size: 0.78rem; color: var(--sub); margin-top: 1rem;
            border-top: 1px solid var(--border); padding-top: 0.75rem;
            display: flex; gap: 1.5rem; flex-wrap: wrap; }}
  footer {{ margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--border);
            font-size: 0.75rem; color: var(--sub); text-align: center; }}
</style>
</head>
<body>
<h1>📚 Arxiv Paper Digest</h1>
<p class="meta">
  Generated {datetime} &nbsp;·&nbsp; {n_papers} paper(s) &nbsp;·&nbsp;
  Model: {model} &nbsp;·&nbsp; Engine: {engine} &nbsp;·&nbsp; Hub: {hub_url}
</p>

{cards}

<footer>
  Generated by <strong>MoMaHub i-grid</strong> &nbsp;·&nbsp;
  Digital Duck &amp; Dog Team &nbsp;·&nbsp;
  <a href="https://github.com/digital-duck/momahub-claude" style="color:#4f8ef7;">momahub-claude</a>
</footer>
</body>
</html>"""


def _format_digest_as_html(content: str) -> str:
    """Convert markdown digest to simple HTML (headings + paragraphs)."""
    lines = content.split("\n")
    out = []
    for line in lines:
        if line.startswith("### "):
            out.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("## "):
            out.append(f"<h3>{line[3:]}</h3>")
        else:
            out.append(line)
    return "\n".join(out)


def _build_html_digest(papers: list[dict], model: str, hub: str, eng: str) -> str:
    cards = []
    for p in papers:
        arxiv_id = p["arxiv_id"]
        status = p.get("state", "UNKNOWN")
        badge_cls = "badge-ok" if status == "COMPLETE" else "badge-fail"
        content = p.get("content", p.get("error", "No result"))
        digest_html = _format_digest_as_html(content)
        result = p.get("result_data", {})
        tokens = (result.get("input_tokens", 0) or 0) + (result.get("output_tokens", 0) or 0)
        latency = result.get("latency_ms", 0) or 0

        card = f"""
<div class="card">
  <div class="card-header">
    <div>
      <div class="paper-title">
        {p.get('title', arxiv_id)}
        <span class="badge {badge_cls}">{status}</span>
      </div>
      <div class="paper-authors">{p.get('authors', '')}</div>
    </div>
    <a class="arxiv-link" href="https://arxiv.org/abs/{arxiv_id}" target="_blank">
      arxiv:{arxiv_id} ↗
    </a>
  </div>
  <div class="digest">{digest_html}</div>
  <div class="stats">
    <span>Tokens: {tokens:,}</span>
    <span>Latency: {latency/1000:.1f}s</span>
    <span>Agent: {result.get('agent_id', model)}</span>
    <span>Engine: {eng}</span>
  </div>
</div>"""
        cards.append(card)

    return _HTML_TEMPLATE.format(
        date=datetime.now().strftime("%Y-%m-%d"),
        datetime=datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
        n_papers=len(papers),
        model=model,
        engine=eng,
        hub_url=hub,
        cards="\n".join(cards),
    )


# ---------------------------------------------------------------------------
# Main UI — form
# ---------------------------------------------------------------------------

with st.form("digest_form"):
    urls_input = st.text_area(
        "Arxiv URLs (one per line)",
        height=160,
        placeholder=dedent("""\
            https://arxiv.org/abs/2312.12345
            https://arxiv.org/pdf/2401.99999
            2409.12345
        """),
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        model = st.text_input("Analysis model", value="llama3")
    with col2:
        depth = st.selectbox(
            "Analysis depth",
            ["Standard (4k tokens)", "Deep (8k tokens)", "Quick (2k tokens)"],
        )
    with col3:
        max_pdf_chars = st.selectbox(
            "PDF text limit",
            ["12,000 chars", "24,000 chars (thorough)", "6,000 chars (abstract only)"],
        )

    submitted = st.form_submit_button("🌙 Analyse on the grid", type="primary")

# ---------------------------------------------------------------------------
# Submit handler
# ---------------------------------------------------------------------------

if submitted:
    use_docling = engine == "docling"

    # Guard: check selected engine is available
    if use_docling and not _DOCLING_OK:
        st.error("docling is not installed. Run `pip install docling` and restart.")
        st.stop()
    if not use_docling and not _PYPDF_OK:
        st.error("pypdf is not installed. Run `pip install pypdf` and restart.")
        st.stop()

    # Parse URLs
    raw_urls = [u.strip() for u in urls_input.strip().splitlines() if u.strip()]
    arxiv_ids, bad = [], []
    for u in raw_urls:
        aid = _extract_arxiv_id(u)
        if aid:
            arxiv_ids.append(aid)
        else:
            bad.append(u)

    if bad:
        st.warning(f"Could not parse these as arxiv IDs: {bad}")
    if not arxiv_ids:
        st.error("No valid arxiv IDs found.")
        st.stop()

    max_tokens_map = {
        "Standard (4k tokens)": 4096,
        "Deep (8k tokens)": 8192,
        "Quick (2k tokens)": 2048,
    }
    pdf_chars_map = {
        "12,000 chars": 12_000,
        "24,000 chars (thorough)": 24_000,
        "6,000 chars (abstract only)": 6_000,
    }
    max_tokens = max_tokens_map[depth]
    max_chars = pdf_chars_map[max_pdf_chars]

    engine_label = f"docling (layout-aware)" if use_docling else "pypdf (text-only)"
    st.info(
        f"Processing **{len(arxiv_ids)} paper(s)** · model `{model}` · engine `{engine_label}`"
    )

    # --- Phase 1: Fetch + extract + submit ---
    papers: list[dict] = []
    progress = st.progress(0, text="Fetching PDFs...")
    total = len(arxiv_ids)

    if use_docling:
        st.caption(
            "⏱️ docling: first paper may be slow while models load (~30-60s). "
            "Subsequent papers are faster."
        )

    for i, arxiv_id in enumerate(arxiv_ids):
        progress.progress(i / (total * 2), text=f"Fetching {arxiv_id}...")
        meta = _fetch_abstract(arxiv_id)

        pdf_bytes = _fetch_pdf_bytes(arxiv_id)
        if pdf_bytes:
            with st.spinner(f"Extracting text from {arxiv_id} with {engine}..."):
                paper_text = _extract_text(pdf_bytes, max_chars, use_docling)
        else:
            paper_text = f"[Could not fetch PDF for {arxiv_id}]"

        try:
            task_id = _submit_analysis_task(hub_url, arxiv_id, paper_text, model, max_tokens)
            papers.append({
                "arxiv_id": arxiv_id,
                "title": meta["title"],
                "authors": meta["authors"],
                "task_id": task_id,
                "state": "PENDING",
            })
            st.write(f"  ✅ Submitted: `{meta['title'][:80]}`")
        except Exception as exc:
            st.error(f"  ❌ Failed to submit {arxiv_id}: {exc}")
            papers.append({
                "arxiv_id": arxiv_id,
                "title": meta["title"],
                "authors": meta["authors"],
                "task_id": None,
                "state": "FAILED",
                "error": str(exc),
            })

    # --- Phase 2: Poll ---
    progress.progress(0.6, text="Waiting for grid results...")
    completed = 0
    status_ph = st.empty()

    for p in papers:
        if p["task_id"] is None:
            continue
        status_ph.info(f"Waiting for: *{p['title'][:60]}*...")
        result_data = _poll_task(hub_url, p["task_id"], timeout_s=600)
        state = result_data.get("state", "TIMEOUT")
        p["state"] = state
        r = result_data.get("result", {}) or {}
        if state == "COMPLETE":
            p["content"] = r.get("content", "")
            p["result_data"] = r
            completed += 1
        else:
            p["content"] = ""
            p["error"] = r.get("error", f"State: {state}")
            p["result_data"] = {}

    status_ph.empty()
    progress.progress(1.0, text="All done!")

    # --- Phase 3: Build HTML digest ---
    html = _build_html_digest(papers, model, hub_url, engine_label)
    st.success(f"Analysis complete! {completed}/{len(papers)} paper(s) digested.")

    for p in papers:
        with st.expander(f"📄 {p.get('title', p['arxiv_id'])[:80]}", expanded=False):
            if p.get("content"):
                st.markdown(p["content"])
            else:
                st.error(p.get("error", "No result"))

    st.divider()
    st.subheader("HTML Digest")
    fname = f"digest_{datetime.now().strftime('%Y%m%d_%H%M')}.html"
    st.download_button(
        "⬇️ Download HTML Digest",
        data=html,
        file_name=fname,
        mime="text/html",
        type="primary",
    )
    with st.expander("Preview digest HTML", expanded=False):
        st.components.v1.html(html, height=800, scrolling=True)
