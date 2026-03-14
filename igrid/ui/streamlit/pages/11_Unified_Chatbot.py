"""11_Unified_Chatbot.py — Unified Chatbot

Single chat interface that routes to any of five inference backends:
  1. Momagrid / Momahub  — community-supported open-source grid (local or remote)
  2. OpenAI              — GPT-4o, o3-mini, etc.
  3. Anthropic           — Claude Sonnet 4.6, Haiku 4.5, etc.
  4. Google              — Gemini 2.0 Flash, 1.5 Pro, etc.
  5. OpenRouter          — 200+ models via a single API key

API keys are read from st.session_state (set in page 10_Register.py) or entered
inline via the sidebar.  Keys are never sent to the grid.

Fallback chain: if the selected provider fails, the chatbot can automatically
retry on the next provider in a user-configured ordered list.
"""
import json
import os
import time
import uuid

import httpx
import streamlit as st

HUB_URL = os.environ.get("IGRID_HUB_URL", "http://localhost:8000")

# ── Model lists ───────────────────────────────────────────────────────────────
OPENAI_MODELS = [
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    "o1-mini",
    "o3-mini",
]
ANTHROPIC_MODELS = [
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
]
GOOGLE_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
]
OPENROUTER_POPULAR = [
    "openai/gpt-4o-mini",
    "openai/gpt-4o",
    "anthropic/claude-sonnet-4-6",
    "google/gemini-2.0-flash-exp",
    "meta-llama/llama-3.1-8b-instruct",
    "meta-llama/llama-3.1-70b-instruct",
    "mistralai/mistral-7b-instruct",
    "qwen/qwen-2.5-72b-instruct",
    "deepseek/deepseek-r1",
]

PROVIDERS = ["Momagrid", "OpenAI", "Anthropic", "Google", "OpenRouter"]

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Unified Chatbot", page_icon="💬", layout="wide")
st.title("💬 Unified Chatbot")
st.caption(
    "One chat interface for Momagrid, OpenAI, Anthropic, Google, and OpenRouter. "
    "Switch provider at any time; conversation history is preserved."
)

# ── Session state init ────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []          # [{role, content, provider, model, meta}]
if "chat_system" not in st.session_state:
    st.session_state.chat_system = "You are a helpful, concise assistant."


# ════════════════════════════════════════════════════════════════════════════
# SIDEBAR — provider selection & settings
# ════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.header("Provider & Settings")

    provider = st.selectbox(
        "Inference provider",
        PROVIDERS,
        help="Select where to send your messages.",
    )

    st.divider()

    # ── Momagrid settings ──────────────────────────────────────────────────
    if provider == "Momagrid":
        hub_url = st.text_input("Hub URL", value=HUB_URL)

        @st.cache_data(ttl=15)
        def _grid_models(u):
            try:
                agents = httpx.get(f"{u}/agents", timeout=3.0).json().get("agents", [])
                models = set()
                for a in agents:
                    if a.get("status") in ("ONLINE", "BUSY"):
                        for m in json.loads(a.get("supported_models", "[]")):
                            models.add(m)
                return sorted(models) or ["llama3"]
            except Exception:
                return ["llama3"]

        grid_models = _grid_models(hub_url)
        model = st.selectbox("Model", grid_models)
        api_key = None

        # Hub health indicator
        try:
            h = httpx.get(f"{hub_url}/health", timeout=2.0).json()
            st.caption(
                f"✅ Hub: `{h.get('hub_id','?')}` · {h.get('agents_online',0)} agents"
            )
        except Exception:
            st.caption("❌ Hub unreachable")

    # ── OpenAI settings ────────────────────────────────────────────────────
    elif provider == "OpenAI":
        hub_url = None
        api_key = st.text_input(
            "OpenAI API Key",
            type="password",
            value=st.session_state.get("openai_api_key", ""),
            placeholder="sk-…  (or set in Register page)",
        )
        model = st.selectbox("Model", OPENAI_MODELS)

    # ── Anthropic settings ─────────────────────────────────────────────────
    elif provider == "Anthropic":
        hub_url = None
        api_key = st.text_input(
            "Anthropic API Key",
            type="password",
            value=st.session_state.get("anthropic_api_key", ""),
            placeholder="sk-ant-…  (or set in Register page)",
        )
        model = st.selectbox("Model", ANTHROPIC_MODELS)

    # ── Google settings ────────────────────────────────────────────────────
    elif provider == "Google":
        hub_url = None
        api_key = st.text_input(
            "Google AI API Key",
            type="password",
            value=st.session_state.get("google_api_key", ""),
            placeholder="AIza…  (or set in Register page)",
        )
        model = st.selectbox("Model", GOOGLE_MODELS)

    # ── OpenRouter settings ────────────────────────────────────────────────
    elif provider == "OpenRouter":
        hub_url = None
        api_key = st.text_input(
            "OpenRouter API Key",
            type="password",
            value=st.session_state.get("openrouter_api_key", ""),
            placeholder="sk-or-…  (or set in Register page)",
        )
        model_choice = st.selectbox(
            "Model (popular)",
            ["(enter custom below)"] + OPENROUTER_POPULAR,
        )
        custom_model = st.text_input(
            "Custom model ID",
            placeholder="e.g. nousresearch/hermes-3-llama-3.1-70b",
        )
        model = custom_model.strip() if custom_model.strip() else (
            model_choice if model_choice != "(enter custom below)" else OPENROUTER_POPULAR[0]
        )

    st.divider()

    # ── Shared generation settings ─────────────────────────────────────────
    st.markdown("**Generation**")
    system_prompt = st.text_area(
        "System prompt",
        value=st.session_state.chat_system,
        height=80,
        key="system_prompt_input",
    )
    st.session_state.chat_system = system_prompt

    max_tokens = st.slider("Max tokens", 64, 4096, 1024, step=64)
    temperature = st.slider("Temperature", 0.0, 2.0, 0.7, step=0.1)
    timeout_s = st.number_input("Timeout (s)", 10, 600, 120, step=10)

    st.divider()

    # ── Fallback chain ─────────────────────────────────────────────────────
    with st.expander("🔗 Fallback chain"):
        st.caption(
            "If the selected provider fails, retry on the next provider in this list. "
            "Reorder by dragging or editing the text field."
        )
        use_fallback = st.checkbox("Enable fallback chain", value=False)
        fallback_order_str = st.text_input(
            "Fallback order (comma-separated)",
            value="Momagrid, OpenRouter, OpenAI",
            help="Provider names in order. First = preferred. Current provider is tried first regardless.",
        )
        fallback_chain = [p.strip() for p in fallback_order_str.split(",") if p.strip()]

    st.divider()

    # ── Conversation controls ──────────────────────────────────────────────
    if st.button("🗑️ Clear conversation", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    if st.session_state.messages:
        convo_json = json.dumps(st.session_state.messages, indent=2)
        st.download_button(
            "⬇️ Export conversation",
            data=convo_json,
            file_name="conversation.json",
            mime="application/json",
            use_container_width=True,
        )


# ════════════════════════════════════════════════════════════════════════════
# PROVIDER CALL FUNCTIONS
# ════════════════════════════════════════════════════════════════════════════

def _call_momagrid(
    hub_url: str,
    model: str,
    messages: list,
    system: str,
    max_tokens: int,
    temperature: float,
    timeout_s: int,
) -> dict:
    """Submit task to Momagrid/Momahub hub and poll for result."""
    # Build prompt from conversation history
    history_parts = []
    for m in messages[:-1]:  # everything except the last user message
        role = "User" if m["role"] == "user" else "Assistant"
        history_parts.append(f"{role}: {m['content']}")
    prompt = messages[-1]["content"]
    if history_parts:
        prompt = "\n".join(history_parts) + f"\nUser: {prompt}"

    task_id = f"chat-{uuid.uuid4().hex[:8]}"
    payload = {
        "task_id": task_id,
        "model": model,
        "prompt": prompt,
        "system": system,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    try:
        httpx.post(f"{hub_url}/tasks", json=payload, timeout=5.0).raise_for_status()
    except Exception as exc:
        return {"error": f"Submit failed: {exc}"}

    deadline = time.monotonic() + timeout_s
    interval = 1.5
    while time.monotonic() < deadline:
        try:
            data = httpx.get(f"{hub_url}/tasks/{task_id}", timeout=5.0).json()
        except Exception:
            time.sleep(interval)
            continue
        state = data.get("state", "")
        if state == "COMPLETE":
            r = data.get("result", {})
            return {
                "content": r.get("content", ""),
                "input_tokens": r.get("input_tokens", 0),
                "output_tokens": r.get("output_tokens", 0),
                "latency_ms": r.get("latency_ms", 0),
                "agent_id": r.get("agent_id", ""),
                "provider": "Momagrid",
                "model": model,
            }
        if state == "FAILED":
            return {"error": data.get("result", {}).get("error", "Task failed")}
        time.sleep(interval)
        interval = min(interval * 1.2, 8.0)

    return {"error": f"Timeout after {timeout_s}s"}


def _call_openai(
    api_key: str,
    model: str,
    messages: list,
    system: str,
    max_tokens: int,
    temperature: float,
    timeout_s: int,
) -> dict:
    """Call OpenAI Chat Completions API."""
    oai_messages = [{"role": "system", "content": system}]
    for m in messages:
        oai_messages.append({"role": m["role"], "content": m["content"]})

    try:
        r = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": oai_messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=timeout_s,
        )
        r.raise_for_status()
        data = r.json()
        choice = data["choices"][0]["message"]
        usage = data.get("usage", {})
        return {
            "content": choice.get("content", ""),
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
            "latency_ms": 0,
            "provider": "OpenAI",
            "model": model,
        }
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:300]
        return {"error": f"OpenAI HTTP {exc.response.status_code}: {detail}"}
    except Exception as exc:
        return {"error": f"OpenAI error: {exc}"}


def _call_anthropic(
    api_key: str,
    model: str,
    messages: list,
    system: str,
    max_tokens: int,
    temperature: float,
    timeout_s: int,
) -> dict:
    """Call Anthropic Messages API."""
    ant_messages = []
    for m in messages:
        ant_messages.append({"role": m["role"], "content": m["content"]})

    try:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "system": system,
                "messages": ant_messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=timeout_s,
        )
        r.raise_for_status()
        data = r.json()
        content = data["content"][0]["text"] if data.get("content") else ""
        usage = data.get("usage", {})
        return {
            "content": content,
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "latency_ms": 0,
            "provider": "Anthropic",
            "model": model,
        }
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:300]
        return {"error": f"Anthropic HTTP {exc.response.status_code}: {detail}"}
    except Exception as exc:
        return {"error": f"Anthropic error: {exc}"}


def _call_google(
    api_key: str,
    model: str,
    messages: list,
    system: str,
    max_tokens: int,
    temperature: float,
    timeout_s: int,
) -> dict:
    """Call Google Gemini generateContent API."""
    # Convert to Gemini contents format (user/model alternating)
    contents = []
    if system:
        # Gemini doesn't have a system role — prepend as first user turn
        # (or use systemInstruction for models that support it)
        pass  # handled via systemInstruction below

    for m in messages:
        gemini_role = "model" if m["role"] == "assistant" else "user"
        contents.append({"role": gemini_role, "parts": [{"text": m["content"]}]})

    body = {
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
        },
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}

    try:
        r = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            f"?key={api_key}",
            json=body,
            timeout=timeout_s,
        )
        r.raise_for_status()
        data = r.json()
        text = ""
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts)
        usage = data.get("usageMetadata", {})
        return {
            "content": text,
            "input_tokens": usage.get("promptTokenCount", 0),
            "output_tokens": usage.get("candidatesTokenCount", 0),
            "latency_ms": 0,
            "provider": "Google",
            "model": model,
        }
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:300]
        return {"error": f"Google HTTP {exc.response.status_code}: {detail}"}
    except Exception as exc:
        return {"error": f"Google error: {exc}"}


def _call_openrouter(
    api_key: str,
    model: str,
    messages: list,
    system: str,
    max_tokens: int,
    temperature: float,
    timeout_s: int,
) -> dict:
    """Call OpenRouter (OpenAI-compatible) API."""
    or_messages = [{"role": "system", "content": system}]
    for m in messages:
        or_messages.append({"role": m["role"], "content": m["content"]})

    try:
        r = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://github.com/digital-duck/momahub",
                "X-Title": "Momahub Unified Chatbot",
            },
            json={
                "model": model,
                "messages": or_messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=timeout_s,
        )
        r.raise_for_status()
        data = r.json()
        choice = data["choices"][0]["message"]
        usage = data.get("usage", {})
        return {
            "content": choice.get("content", ""),
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
            "latency_ms": 0,
            "provider": "OpenRouter",
            "model": model,
        }
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:300]
        return {"error": f"OpenRouter HTTP {exc.response.status_code}: {detail}"}
    except Exception as exc:
        return {"error": f"OpenRouter error: {exc}"}


def _dispatch(
    provider: str,
    model: str,
    messages: list,
    system: str,
    max_tokens: int,
    temperature: float,
    timeout_s: int,
    api_key: str = None,
    hub_url: str = None,
) -> dict:
    """Route to the correct provider call function."""
    if provider == "Momagrid":
        return _call_momagrid(hub_url, model, messages, system, max_tokens, temperature, timeout_s)
    elif provider == "OpenAI":
        return _call_openai(api_key, model, messages, system, max_tokens, temperature, timeout_s)
    elif provider == "Anthropic":
        return _call_anthropic(api_key, model, messages, system, max_tokens, temperature, timeout_s)
    elif provider == "Google":
        return _call_google(api_key, model, messages, system, max_tokens, temperature, timeout_s)
    elif provider == "OpenRouter":
        return _call_openrouter(api_key, model, messages, system, max_tokens, temperature, timeout_s)
    return {"error": f"Unknown provider: {provider}"}


def _get_api_key_for(p: str) -> str:
    """Pull the api key for provider p from session state."""
    mapping = {
        "OpenAI": "openai_api_key",
        "Anthropic": "anthropic_api_key",
        "Google": "google_api_key",
        "OpenRouter": "openrouter_api_key",
    }
    return st.session_state.get(mapping.get(p, ""), "")


def _get_model_for(p: str) -> str:
    """Return a sensible default model for provider p."""
    defaults = {
        "Momagrid": "llama3",
        "OpenAI": OPENAI_MODELS[0],
        "Anthropic": ANTHROPIC_MODELS[1],
        "Google": GOOGLE_MODELS[0],
        "OpenRouter": OPENROUTER_POPULAR[0],
    }
    return defaults.get(p, "llama3")


# ════════════════════════════════════════════════════════════════════════════
# CHAT UI
# ════════════════════════════════════════════════════════════════════════════

# Render conversation history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        meta = msg.get("meta")
        if meta and msg["role"] == "assistant":
            provider_tag = meta.get("provider", "")
            model_tag = meta.get("model", "")
            in_tok = meta.get("input_tokens", 0)
            out_tok = meta.get("output_tokens", 0)
            lat = meta.get("latency_ms", 0)
            parts = [f"**{provider_tag}** · `{model_tag}`"]
            if in_tok or out_tok:
                parts.append(f"{in_tok}+{out_tok} tok")
            if lat:
                parts.append(f"{lat:.0f} ms")
            st.caption(" · ".join(parts))

# Chat input at the bottom
if user_input := st.chat_input("Message…"):
    # Append user message
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Build the full message list for the API call (user messages only for context)
    api_messages = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages
    ]

    # Attempt provider(s)
    providers_to_try = [provider]
    if use_fallback:
        for fb in fallback_chain:
            if fb != provider and fb in PROVIDERS:
                providers_to_try.append(fb)

    result = None
    used_provider = None
    used_model = None

    with st.chat_message("assistant"):
        placeholder = st.empty()

        for attempt_provider in providers_to_try:
            attempt_model = model if attempt_provider == provider else _get_model_for(attempt_provider)
            attempt_key  = api_key if attempt_provider == provider else _get_api_key_for(attempt_provider)
            attempt_hub  = hub_url if attempt_provider == provider else None

            # Key guard for cloud providers
            if attempt_provider != "Momagrid" and not attempt_key:
                if attempt_provider == provider:
                    placeholder.warning(
                        f"No API key for **{attempt_provider}**. "
                        "Set it in the sidebar or visit **Register & Config** (page 10)."
                    )
                continue

            label = f"⏳ Calling **{attempt_provider}** · `{attempt_model}`…"
            if attempt_provider != provider:
                label = f"↩️ Fallback → {label}"
            placeholder.markdown(label)

            t0 = time.monotonic()
            result = _dispatch(
                provider=attempt_provider,
                model=attempt_model,
                messages=api_messages,
                system=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout_s=timeout_s,
                api_key=attempt_key,
                hub_url=attempt_hub,
            )
            elapsed_ms = (time.monotonic() - t0) * 1000

            if "error" not in result:
                used_provider = attempt_provider
                used_model = attempt_model
                if result.get("latency_ms", 0) == 0:
                    result["latency_ms"] = elapsed_ms
                break
            else:
                err_msg = result["error"]
                if attempt_provider != providers_to_try[-1]:
                    placeholder.warning(f"**{attempt_provider}** failed: {err_msg} — trying fallback…")
                else:
                    placeholder.error(f"All providers failed. Last error: {err_msg}")

        if result and "error" not in result:
            content = result.get("content", "")
            placeholder.markdown(content)

            # Metrics below response
            in_tok  = result.get("input_tokens", 0)
            out_tok = result.get("output_tokens", 0)
            lat_ms  = result.get("latency_ms", 0)
            agent   = result.get("agent_id", "")

            caption_parts = [
                f"**{used_provider}** · `{used_model}`",
            ]
            if in_tok or out_tok:
                caption_parts.append(f"{in_tok}+{out_tok} tok")
            if lat_ms:
                caption_parts.append(f"{lat_ms:.0f} ms")
            if agent:
                caption_parts.append(f"agent …{agent[-12:]}")

            st.caption(" · ".join(caption_parts))

            # Persist to session
            st.session_state.messages.append({
                "role": "assistant",
                "content": content,
                "meta": {
                    "provider": used_provider,
                    "model": used_model,
                    "input_tokens": in_tok,
                    "output_tokens": out_tok,
                    "latency_ms": lat_ms,
                    "agent_id": agent,
                },
            })
        elif result and "error" in result:
            # Error already shown above; don't append to history
            pass


# ── Conversation stats in expander ───────────────────────────────────────────
if st.session_state.messages:
    with st.expander("📊 Conversation stats", expanded=False):
        msgs = st.session_state.messages
        user_turns  = sum(1 for m in msgs if m["role"] == "user")
        asst_turns  = sum(1 for m in msgs if m["role"] == "assistant")
        total_in    = sum(m.get("meta", {}).get("input_tokens", 0)  for m in msgs)
        total_out   = sum(m.get("meta", {}).get("output_tokens", 0) for m in msgs)
        providers_used = list({
            m["meta"]["provider"] for m in msgs
            if m["role"] == "assistant" and m.get("meta")
        })

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("User turns",      user_turns)
        c2.metric("Assistant turns", asst_turns)
        c3.metric("Input tokens",    total_in)
        c4.metric("Output tokens",   total_out)
        c5.metric("Providers used",  ", ".join(providers_used) or "—")

        # Per-provider breakdown
        if len(providers_used) > 1:
            import pandas as pd
            rows = []
            for m in msgs:
                if m["role"] == "assistant" and m.get("meta"):
                    meta = m["meta"]
                    rows.append({
                        "provider": meta.get("provider", ""),
                        "model":    meta.get("model", ""),
                        "in_tok":   meta.get("input_tokens", 0),
                        "out_tok":  meta.get("output_tokens", 0),
                        "lat_ms":   meta.get("latency_ms", 0),
                    })
            if rows:
                df = pd.DataFrame(rows)
                st.dataframe(
                    df.groupby(["provider", "model"]).agg(
                        turns=("out_tok", "count"),
                        total_in=("in_tok", "sum"),
                        total_out=("out_tok", "sum"),
                        avg_latency_ms=("lat_ms", "mean"),
                    ).round(0),
                    use_container_width=True,
                )
