#!/usr/bin/env python3
"""
Recipe 06: Arxiv Paper Digest — CLI version.

Submit a list of arxiv papers before bed. The i-grid analyses them in
parallel overnight. Wake up to a self-contained HTML digest file.

Usage:
    python digest.py 2312.12345 2401.99999 https://arxiv.org/abs/2409.11111
    python digest.py --urls urls.txt --model llama3 --hub http://localhost:8000
    python digest.py --urls urls.txt --out ~/Desktop/my_digest.html

Output: digest_YYYYMMDD_HHMM.html  (dark-mode, self-contained HTML)
"""

from __future__ import annotations
import argparse
import asyncio
import io
import re
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import httpx

try:
    import pypdf  # type: ignore
    _PYPDF_OK = True
except ImportError:
    print("ERROR: pypdf not installed. Run: pip install pypdf", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Config defaults
# ---------------------------------------------------------------------------

DEFAULT_HUB = "http://localhost:8000"
DEFAULT_MODEL = "llama3"
DEFAULT_MAX_TOKENS = 4096
DEFAULT_MAX_CHARS = 12_000

ARXIV_PDF_BASE = "https://arxiv.org/pdf"
ARXIV_ABS_BASE = "https://arxiv.org/abs"

_ARXIV_ID_RE = re.compile(
    r"(?:arxiv\.org/(?:abs|pdf)/)?(\d{4}\.\d{4,5}(?:v\d+)?)"
)

# ---------------------------------------------------------------------------
# Analysis prompt
# ---------------------------------------------------------------------------

SYSTEM = (
    "You are a rigorous academic reviewer who produces clear, structured paper digests. "
    "Write precisely — avoid vague phrases. Ground every claim in the provided text."
)

PROMPT_TPL = """\
## Paper text (first {chars:,} characters extracted from PDF)

{text}

---

Produce a structured digest with these sections:

### 1. Title & Core Claim
What does this paper claim to contribute? (1–2 sentences)

### 2. Problem Statement
What specific problem does it address and why does it matter?

### 3. Methodology
Key technical approach and design choices.

### 4. Key Results
Most important quantitative or qualitative findings.

### 5. Limitations & Open Questions
What does the paper leave unresolved? Honest weaknesses.

### 6. Relevance
Who benefits most from reading this? Practical or research implications.

### 7. One-Line Summary
A single crisp sentence suitable for a literature review citation.
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_arxiv_id(raw: str) -> str | None:
    m = _ARXIV_ID_RE.search(raw.strip())
    return m.group(1) if m else None


def fetch_pdf_text(arxiv_id: str, max_chars: int) -> tuple[str, str]:
    """Returns (text, error). Fetches PDF and extracts text with pypdf."""
    url = f"{ARXIV_PDF_BASE}/{arxiv_id}"
    try:
        resp = httpx.get(url, timeout=30.0, follow_redirects=True)
        resp.raise_for_status()
        reader = pypdf.PdfReader(io.BytesIO(resp.content))
        parts = []
        total = 0
        for page in reader.pages:
            t = page.extract_text() or ""
            parts.append(t)
            total += len(t)
            if total >= max_chars:
                break
        return "\n".join(parts)[:max_chars], ""
    except Exception as exc:
        return "", str(exc)


def fetch_meta(arxiv_id: str) -> dict:
    meta = {"title": arxiv_id, "authors": ""}
    try:
        resp = httpx.get(f"{ARXIV_ABS_BASE}/{arxiv_id}", timeout=10.0, follow_redirects=True)
        html = resp.text
        m = re.search(r'<h1 class="title[^"]*">\s*(?:<span[^>]*>[^<]*</span>\s*)?([^<]+)', html)
        if m:
            meta["title"] = m.group(1).strip()
        m = re.search(r'<div class="authors">(.*?)</div>', html, re.DOTALL)
        if m:
            meta["authors"] = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(1))).strip()
    except Exception:
        pass
    return meta


def submit_task(hub: str, arxiv_id: str, text: str, model: str, max_tokens: int) -> str:
    task_id = f"digest-{arxiv_id.replace('.', '-')}-{uuid.uuid4().hex[:6]}"
    payload = {
        "task_id": task_id,
        "model": model,
        "prompt": PROMPT_TPL.format(text=text, chars=len(text)),
        "system": SYSTEM,
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }
    with httpx.Client(timeout=10.0) as client:
        client.post(f"{hub}/tasks", json=payload).raise_for_status()
    return task_id


def poll_task(hub: str, task_id: str, timeout_s: int = 900) -> dict:
    deadline = time.monotonic() + timeout_s
    interval = 5.0
    with httpx.Client(timeout=5.0) as client:
        while time.monotonic() < deadline:
            try:
                r = client.get(f"{hub}/tasks/{task_id}")
                data = r.json()
                if data.get("state") in ("COMPLETE", "FAILED"):
                    return data
            except Exception:
                pass
            time.sleep(interval)
            interval = min(interval * 1.2, 20.0)
    return {"state": "TIMEOUT", "result": None}

# ---------------------------------------------------------------------------
# HTML output
# ---------------------------------------------------------------------------

_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Arxiv Digest — {date}</title>
<style>
:root{{--bg:#0f1117;--card:#1a1d27;--accent:#4f8ef7;--text:#e0e0e0;
      --sub:#9ca3af;--border:#2d3148;--ok:#22c55e;--warn:#f59e0b}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);
     font-family:'Segoe UI',system-ui,sans-serif;padding:2rem;max-width:960px;margin:0 auto}}
h1{{font-size:1.8rem;color:var(--accent);margin-bottom:.25rem}}
.meta{{color:var(--sub);font-size:.85rem;margin-bottom:2.5rem}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:12px;
       padding:1.5rem;margin-bottom:1.8rem}}
.card-header{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:1rem}}
.paper-title{{font-size:1.1rem;font-weight:600;color:var(--accent)}}
.paper-authors{{font-size:.8rem;color:var(--sub);margin-top:.2rem}}
.arxiv-link{{font-size:.78rem;color:var(--sub);text-decoration:none;
             border:1px solid var(--border);border-radius:6px;padding:.2rem .5rem;white-space:nowrap}}
.arxiv-link:hover{{color:var(--accent);border-color:var(--accent)}}
.digest{{font-size:.92rem;line-height:1.65;white-space:pre-wrap}}
.digest h3{{color:var(--accent);font-size:.9rem;margin:1rem 0 .3rem}}
.badge{{display:inline-block;font-size:.72rem;border-radius:20px;padding:.15rem .5rem;margin-left:.5rem}}
.ok{{background:rgba(34,197,94,.15);color:var(--ok)}}
.fail{{background:rgba(245,158,11,.15);color:var(--warn)}}
.stats{{font-size:.78rem;color:var(--sub);margin-top:1rem;border-top:1px solid var(--border);
        padding-top:.75rem;display:flex;gap:1.5rem;flex-wrap:wrap}}
footer{{margin-top:3rem;padding-top:1rem;border-top:1px solid var(--border);
        font-size:.75rem;color:var(--sub);text-align:center}}
</style>
</head>
<body>
<h1>📚 Arxiv Paper Digest</h1>
<p class="meta">Generated {datetime} &nbsp;·&nbsp; {n} paper(s) &nbsp;·&nbsp;
Model: {model} &nbsp;·&nbsp; Hub: {hub}</p>
{cards}
<footer>Generated by <strong>MoMaHub i-grid</strong> &nbsp;·&nbsp; Digital Duck &amp; Dog Team</footer>
</body>
</html>"""

_CARD = """\
<div class="card">
<div class="card-header">
  <div>
    <div class="paper-title">{title}<span class="badge {cls}">{state}</span></div>
    <div class="paper-authors">{authors}</div>
  </div>
  <a class="arxiv-link" href="https://arxiv.org/abs/{aid}" target="_blank">arxiv:{aid} ↗</a>
</div>
<div class="digest">{digest}</div>
<div class="stats"><span>Tokens: {tokens:,}</span><span>Latency: {lat:.1f}s</span></div>
</div>"""


def fmt_digest(text: str) -> str:
    out = []
    for line in text.split("\n"):
        if line.startswith("### "):
            out.append(f"<h3>{line[4:]}</h3>")
        else:
            out.append(line)
    return "\n".join(out)


def build_html(papers: list[dict], model: str, hub: str) -> str:
    cards = []
    for p in papers:
        state = p.get("state", "UNKNOWN")
        cls = "ok" if state == "COMPLETE" else "fail"
        content = p.get("content") or p.get("error") or "No result"
        r = p.get("result_data") or {}
        tokens = (r.get("input_tokens") or 0) + (r.get("output_tokens") or 0)
        lat_ms = r.get("latency_ms") or 0
        cards.append(_CARD.format(
            title=p.get("title", p["arxiv_id"]),
            cls=cls, state=state,
            authors=p.get("authors", ""),
            aid=p["arxiv_id"],
            digest=fmt_digest(content),
            tokens=tokens, lat=lat_ms / 1000,
        ))
    return _HTML.format(
        date=datetime.now().strftime("%Y-%m-%d"),
        datetime=datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
        n=len(papers), model=model, hub=hub,
        cards="\n".join(cards),
    )

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ids", nargs="*", help="arxiv IDs or URLs")
    ap.add_argument("--urls", help="Text file with one arxiv URL/ID per line")
    ap.add_argument("--hub", default=DEFAULT_HUB, help=f"Hub URL (default: {DEFAULT_HUB})")
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model (default: {DEFAULT_MODEL})")
    ap.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    ap.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS, help="PDF text chars per paper")
    ap.add_argument("--out", default="", help="Output HTML file (default: digest_YYYYMMDD_HHMM.html)")
    args = ap.parse_args()

    # Collect raw IDs/URLs
    raw = list(args.ids)
    if args.urls:
        raw += Path(args.urls).read_text().splitlines()
    raw = [r.strip() for r in raw if r.strip()]
    if not raw:
        ap.error("Provide at least one arxiv ID or URL.")

    arxiv_ids = [parse_arxiv_id(r) for r in raw]
    arxiv_ids = [a for a in arxiv_ids if a]
    if not arxiv_ids:
        print("ERROR: No valid arxiv IDs found.", file=sys.stderr)
        sys.exit(1)

    print(f"\n📚 Arxiv Paper Digest")
    print(f"   Hub:    {args.hub}")
    print(f"   Model:  {args.model}")
    print(f"   Papers: {len(arxiv_ids)}")
    print()

    # Phase 1: fetch + submit
    papers = []
    for arxiv_id in arxiv_ids:
        print(f"  [{arxiv_id}] fetching metadata...", end=" ", flush=True)
        meta = fetch_meta(arxiv_id)
        print(f"{meta['title'][:60]}")

        print(f"  [{arxiv_id}] fetching PDF...", end=" ", flush=True)
        text, err = fetch_pdf_text(arxiv_id, args.max_chars)
        if err:
            print(f"FAILED: {err}")
            papers.append({"arxiv_id": arxiv_id, **meta, "task_id": None,
                           "state": "FAILED", "error": err})
            continue
        print(f"{len(text):,} chars")

        print(f"  [{arxiv_id}] submitting to grid...", end=" ", flush=True)
        try:
            task_id = submit_task(args.hub, arxiv_id, text, args.model, args.max_tokens)
            print(f"task_id={task_id}")
            papers.append({"arxiv_id": arxiv_id, **meta, "task_id": task_id, "state": "PENDING"})
        except Exception as exc:
            print(f"FAILED: {exc}")
            papers.append({"arxiv_id": arxiv_id, **meta, "task_id": None,
                           "state": "FAILED", "error": str(exc)})

    # Phase 2: poll for results
    print(f"\n⏳ Waiting for {sum(1 for p in papers if p['task_id'])} analyses...\n")
    for p in papers:
        if not p.get("task_id"):
            continue
        print(f"  [{p['arxiv_id']}] polling...", end=" ", flush=True)
        result = poll_task(args.hub, p["task_id"])
        state = result.get("state", "TIMEOUT")
        p["state"] = state
        r = result.get("result") or {}
        if state == "COMPLETE":
            p["content"] = r.get("content", "")
            p["result_data"] = r
            tokens = (r.get("input_tokens") or 0) + (r.get("output_tokens") or 0)
            print(f"done ({tokens:,} tokens)")
        else:
            p["content"] = ""
            p["error"] = r.get("error", f"State: {state}")
            p["result_data"] = {}
            print(f"FAILED: {p['error']}")

    # Phase 3: write HTML
    html = build_html(papers, args.model, args.hub)
    out_path = args.out or f"digest_{datetime.now().strftime('%Y%m%d_%H%M')}.html"
    Path(out_path).write_text(html, encoding="utf-8")

    ok = sum(1 for p in papers if p.get("state") == "COMPLETE")
    print(f"\n✅ Digest written to: {out_path}  ({ok}/{len(papers)} papers analysed)")
    print("   Open in your browser — dark mode, self-contained HTML.\n")


if __name__ == "__main__":
    main()
