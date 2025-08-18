# OpenRouter — reasoning and grounding (corrected & expanded)

This note documents how OpenRouter exposes "reasoning" controls and web-search grounding, and how to use those features from GPT-Researcher (gpt-r). It corrects and expands the earlier summary.

Summary / quick verdict
- Reasoning: OpenRouter supports a unified `reasoning` object (e.g., `{"effort":"high"}`) for models that support reasoning (o-series, o3/o4 mini family). It also advertises convenience slugs like `openai/o3-mini-high`. GPT-Researcher will forward reasoning settings for supported models.
- Grounding / web search: OpenRouter provides model-agnostic web search via a built-in Web Search plugin and also supports an `:online` model-suffix for convenience (e.g., `openai/gpt-4o:online`). That means you can opt a model into browsing at request time without separate orchestration. OpenRouter’s web search (powered by Exa) can inject standardized URL citations into responses.
- Practical: Use OpenRouter’s `reasoning` object and the web plugin / `:online` option to enable reasoning and browsing. If you need provider-native grounding (e.g., Google Gemini’s Google Search tool), prefer the provider SDK for full grounding features; OpenRouter may or may not forward provider-specific tooling automatically—test for your setup.

Contents
1) Reasoning (how to specify)
2) Grounding / Web Search (how to enable)
3) How this repo interoperates with OpenRouter
4) Practical examples & caveats
5) Test snippet suggestion

---

## 1) Reasoning (how to specify)

OpenRouter supports a structured `reasoning` field. Typical shape:

```json
{
  "model": "openai/o3-mini",
  "messages": [{"role":"user","content":"Solve this problem..."}],
  "reasoning": {"effort": "high"}
}
```

- `effort` values: `"low" | "medium" | "high"`.
- OpenRouter pages and model pages may also show legacy flags (`include_reasoning`) and convenience model slugs (e.g., `openai/o3-mini-high`) that default the setting.
- Not all models return internal reasoning tokens in responses; reasoning controls inference behavior (how much budget is spent on reasoning) even if you do not see internal steps.

In this repository:
- GPT-Researcher exposes `REASONING_EFFORT` in DEFAULT_CONFIG and reads it via `Config`.
- The provider layer lists supported models (e.g., o3/o4 minis) in `SUPPORT_REASONING_EFFORT_MODELS`. The code forwards the reasoning parameter to the LangChain client for those models.
- If you route to OpenRouter (provider `openrouter`), GPT-Researcher will pass the reasoning kwarg and OpenRouter will include it in the request body to the routed backend.

---

## 2) Grounding / Web Search (how to enable)

OpenRouter provides several ways to add web-search grounding to a request:

A) Web Search plugin (model-agnostic)
- OpenRouter has a built-in Web Search plugin (powered by Exa). You can enable it per-request and OpenRouter will perform searches and inject standardized citations into the assistant message.
- Example (conceptual):
```json
{
  "model": "openai/gpt-4o",
  "messages": [{ "role": "user", "content": "What are the latest articles about X?" }],
  "plugins": [{"id": "web"}],
  "web_search_options": {
    "max_results": 5,
    "context_tier": "medium"
  }
}
```
- This works for models that don't natively browse — OpenRouter performs the search and attaches results.

B) `:online` model-suffix
- Convenience syntax: append `:online` to model slug to enable browsing, e.g. `openai/gpt-4o:online`.
- This is syntactic sugar that turns on the built-in web search for that request.

C) Provider-native grounding (e.g., Google Gemini)
- Some providers expose their own grounding tools (Google GenAI has a `GoogleSearch` tool). In the repo we use `google.genai` with tool configs when `enable_grounding` is enabled for Gemini.
- When using provider-native grounding, prefer the provider SDK to configure the grounding tool rather than relying on a routing proxy.

Important: OpenRouter supports both plugin-based browsing and some provider-level built-in browsing controls (e.g., `web_search_options`). Behavior, pricing and exact fields may vary by provider/model. Always test.

---

## 3) How this repo (GPT-Researcher + MA) interoperates with OpenRouter

- Provider wrapper (file): `gpt_researcher/llm_provider/generic/base.py` contains an `openrouter` path that builds a `ChatOpenAI` with `openai_api_base='https://openrouter.ai/api/v1'` and uses OPENROUTER_API_KEY.
- Reasoning: GPT-Researcher sets `reasoning` (or equivalent) via `reasoning_effort` config for supported models; the wrapper will forward the kwarg to OpenRouter when provider=`openrouter` or when using `openai` client pointed at OpenRouter base URL.
- Grounding:
  - For Gemini grounding, this repo uses `google.genai` client directly (see llm-doc-eval evaluator) with a `Tool(google_search=GoogleSearch())`.
  - For OpenRouter web plugin, configure provider=`openrouter` and include `plugins` or `web_search_options` in the kwargs — the repo will pass supported kwargs into the LangChain/Chat client; make sure your LangChain client allows extra body fields or that OpenRouter-compatible client is installed.

---

## 4) Practical examples & caveats

- Reasoning example (OpenRouter):
```json
{
  "model": "openai/o3-mini",
  "messages": [{"role":"user","content":"Explain this math proof."}],
  "reasoning": {"effort":"high"}
}
```

- Web plugin example (OpenRouter):
```json
{
  "model": "openai/gpt-4o",
  "messages": [{"role":"user","content":"Latest research on AI safety"}],
  "plugins": [{"id":"web"}],
  "web_search_options": {"max_results":5, "context_tier":"medium"}
}
```

- Using GPT-Researcher with OpenRouter:
  - Set env: `SMART_LLM=openrouter:openai/o3-mini`
  - Set `REASONING_EFFORT=high` in env (Config reads env) or pass equivalent kwargs if calling programmatically.
  - For plugin browsing, ensure the repo forwards `plugins`/`web_search_options` through the LangChain client (test).

Caveats:
- Parameter support depends on both OpenRouter and the backend provider/model. OpenRouter normalizes requests but backend behavior may differ.
- Some LangChain clients validate args; you may need updated client versions or to use `extra_body`/`extra` mechanisms.
- Web search via OpenRouter is billable and has its own pricing & limits; check OpenRouter pricing docs.

---

## 5) Test snippet (Python curl-style) — requires OPENROUTER_API_KEY
```python
import requests, os, json

url = "https://api.openrouter.ai/v1/chat/completions"
headers = {"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}", "Content-Type":"application/json"}
payload = {
    "model": "openai/o3-mini",
    "messages": [{"role":"user","content":"Explain quantum computing in simple terms"}],
    "reasoning": {"effort":"high"},
    "plugins": [{"id":"web"}],
    "web_search_options": {"max_results": 3}
}
resp = requests.post(url, headers=headers, json=payload)
print(resp.status_code, resp.text)
```

---

## References
- OpenRouter model pages & docs (reasoning / web search examples).
- OpenRouter API reference (endpoint examples).
- GPT-Researcher code (llm_provider/generic/base.py, skills/deep_research.py, multi_agents ResearchAgent).

---

If you want, I will:
- Overwrite the repo doc (I already updated it), and
- Add a small in-repo test script (safe placeholder that the user can run after setting OPENROUTER_API_KEY).
- Or implement MA-per-run temp-copy helper that injects `REASONING_EFFORT` and plugin settings when calling MA.

Which follow-up should I do?
