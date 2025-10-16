Change Log (append-only)
- 2025-10-16 — OpenAI Responses FIX: moved Structured Outputs envelope to text.format.schema (removed json_schema wrapper); kept name="evaluation_result" and strict=false; tools:[{"type":"web_search"}], tool_choice=auto, reasoning.effort=high; grounding always ON.

Result Log (append-only)
- 2025-10-16 — OpenAI Responses success after fix: All OpenAI gpt-5 single/pairwise runs succeeded; server accepted text.format.schema; grounding verified; parsed_json_found=True.
- 2025-10-16 — OpenAI Responses error after change: Added text.format.name="evaluation_result" (type=json_schema), switched tools to {"type":"web_search"}, enforced reasoning.effort=high; Gemini runs succeeded, but OpenAI gpt-5 runs failed with HTTP 400 invalid_request_error “Missing required parameter: 'text.format.schema'” (param=text.format.schema). Interpretation: current API path expects the schema under text.format.schema (or nested as text.format.json_schema.schema depending on docs); follow-up change will relocate the schema while keeping grounding ON and tool_choice=auto.

Change Log (append-only)
- 2025-10-16 — OpenAI Responses: added text.format.name="evaluation_result"; use tools:[{"type":"web_search"}]; enforce reasoning.effort=high; grounding always ON; policy: document any eval change here (append-only).

# Definitive Ground Truth — Reasoning + Web Search + JSON/Structured Output (by provider-model)

Scope
- What’s listed: for each provider-model, the ground-truth status of:
  - Reasoning controls (e.g., reasoning.effort)
  - Built-in web search/browsing tool
  - Structured output (JSON), including schema-backed modes
- Evidence: links to official docs plus observed behavior from this repo’s diagnostics when relevant.
- Status labels: Supported (Docs), Supported (Observed), Intermittent/Account- or Model-Gated, Incompatibility Observed, Not Supported (Reports).

OpenAI

- openai/gpt-5
  - Reasoning: Supported (Docs). Supports low/medium/high reasoning_effort via Responses API.
  - Web search: Supported (Docs) via built-in web_search tool in Responses API.
  - JSON/Structured outputs: Supported (Docs) via Structured Outputs with text.format.type=json_schema.
  - Notes:
    - Docs explicitly state GPT-5 supports web_search + Structured Outputs in Responses API. [O5][O1][O2][O3]
    - Field observations in this repo:
      - 400 invalid_json_schema errors until payload conformed to text.format.json_schema nesting. [R1]
      - 500 server_error when combining tools (web_search) + json_schema on gpt-5-mini; “web_search cannot be used with JSON mode” surfaced in logs on some runs. [R1]
    - Interpretation: Docs say supported; real-world behavior appears model/account/region/tool-version-sensitive. Implement fallbacks and validate entitlements.
- openai/gpt-5-mini
  - Reasoning: Supported (Docs, by family).
  - Web search: Supported (Docs).
  - JSON/Structured outputs: Supported (Docs).
  - Notes:
    - Reports indicate tool_choice restrictions (auto only). [O6]
    - This repo observed intermittent 500s combining web_search + json_schema, even after schema fix. [R1]
- openai/gpt-4.1
  - Reasoning: Supported (Docs, Responses API guidance).
  - Web search: Claimed supported in some docs; community experiences mixed (playground vs API discrepancies). [O3][O4]
  - JSON/Structured outputs: Supported (Docs).
  - Notes: Expect variance by account/region/tool name (web_search vs web_search_preview). Validate on your tenant. [O4]
- openai/o4-mini
  - Reasoning: Supported (o-series).
  - Web search: Not Supported (Reports) via API in some snapshots (despite playground hints). [O5]
  - JSON/Structured outputs: Supported (Docs) for the family, but pairing with web_search may fail in practice; verify.

Google Gemini (google/*)

- google/gemini-2.5-pro
  - Reasoning: N/A for OpenAI-style “reasoning.effort”; Gemini has “Thinking” capability flags separate from OpenAI semantics. Focus here is on grounding + JSON.
  - Web search (Grounding with Google Search): Supported (Docs) via google_search tool; grounded responses include groundingMetadata, webSearchQueries, searchEntryPoint, groundingSupports. [G2]
  - JSON/Structured outputs:
    - Supported (Docs) via response_mime_type=application/json and response_schema. [G1][G4]
    - Interplay with Grounding: Docs don’t explicitly guarantee joint robustness; this repo observed occasional missing grounding evidence in single-call runs despite tools enabled (strict enforcer blocked output). [R2][R3]
  - Notes: Strengthen prompts to explicitly require search and citations; consider retries for “missing grounding.” [R2][R3]
- google/gemini-2.5-flash
  - Web search: Supported (Docs); Observed consistent grounding signals in this repo. [G2][R2][R3]
  - JSON/Structured outputs: Supported (Docs). [G1][G4]
  - Notes: Reliable grounding metadata observed under single-call policy. [R2]
- google/gemini-2.5-flash-lite
  - Web search: Supported (Docs); Observed consistent grounding signals. [G2][R2]
  - JSON/Structured outputs: Supported (Docs). [G1][G4]
  - Notes: Similar to flash, grounding signals observed reliably. [R2]

OpenRouter

- openrouter/(various backend slugs, e.g., openai/gpt-4o, openai/o3-mini)
  - Reasoning: Supported (Platform) via a unified reasoning object (e.g., {"effort":"high"}) for reasoning-capable models; also convenience slugs. [R4]
  - Web search:
    - Supported (Platform) via built-in Web Search plugin or :online model-suffix; citations may be injected by the router. [R4]
    - Provider-native grounding (e.g., Gemini google_search) is best configured via provider SDK when you need full native signals. [R4]
  - JSON/Structured outputs: Routed to backend; behavior depends on underlying provider/model support. Verify per backend.
  - Notes: Parameter names and support vary by backend provider; ensure client library can pass through extra body fields.

Cross-cutting guidance (from evidence)

- Tool naming drift: web_search_preview vs web_search (and potentially versioned tool names). Prefer web_search; validate on your tenant. [O4]
- Entitlements and region: Web search tool availability is account/region-gated in some environments (esp. Azure/OpenAI). Collect request IDs and confirm with support if you see 4xx/5xx. [O7][O8]
- Concurrency: Backend instability can surface as 500s when combining tools + structured outputs. Serialize tests; add backoff; consider prompt-JSON fallback for OpenAI on 5xx. [R1]
- Gemini structured output with grounding: Docs show both features exist, but don’t specify interaction details. Repo data shows occasional missing grounding signals in single-call runs; strong prompts and optional retry policies improve success rates. [G1][G2][R2][R3]
- Schema shape (OpenAI): For Responses API, json_schema must be nested under text.format.json_schema (not directly under schema or legacy response_format). Strict mode has limitations. [O2][O9][R1]

References

OpenAI
- [O1] Model – GPT‑5 (Supports web_search and Structured Outputs): https://platform.openai.com/docs/models/gpt-5
- [O2] Responses API reference (Structured Outputs, tools): https://platform.openai.com/docs/api-reference/responses
- [O3] Using GPT‑5 (guidance noting web_search + Structured Outputs): https://platform.openai.com/docs/guides/latest-model
- [O4] Community: web_search vs web_search_preview tool naming and playground/API discrepancies:
  - https://community.openai.com/t/new-search-tool-web-search-2025-08-26-and-web-search-vs-legacy-web-search-preview/1354682
  - https://community.openai.com/t/web-search-works-in-playground-but-not-via-api/1152213
- [O5] StackOverflow: “Web Search is not supported in o4‑mini …” (API): https://stackoverflow.com/questions/79598009/getting-web-search-is-not-supported-in-o4-mini-even-though-it-is-supported-and
- [O6] openai‑python issue: Tool choices other than “auto” not supported on gpt‑5‑mini: https://github.com/openai/openai-python/issues/2537
- [O7] Azure entitlement note (web search): https://learn.microsoft.com/en-us/answers/questions/2237879/web-search-tool-is-not-enabled-for-this-organizati
- [O8] Azure OpenAI “What’s new” (gpt‑5, region/registration): https://learn.microsoft.com/en-us/azure/ai-foundry/openai/whats-new
- [O9] Text generation guide (Structured Outputs overview): https://platform.openai.com/docs/guides/text

Google Gemini
- [G1] Structured output (response_mime_type/response_schema): https://ai.google.dev/gemini-api/docs/structured-output
- [G2] Grounding with Google Search (groundingMetadata, webSearchQueries, searchEntryPoint, groundingSupports): https://ai.google.dev/gemini-api/docs/google-search
- [G3] Changelog (grounding added; model/tool updates): https://ai.google.dev/gemini-api/docs/changelog
- [G4] API reference (generateContent with response_mime_type/response_schema): https://ai.google.dev/api/generate-content

OpenRouter (summary based on in‑repo doc; verify with OpenRouter docs for parameter names)
- [R4] Repo note: OpenRouter — reasoning and grounding (reasoning object, web plugin, :online): api_cost_multiplier/docs/openrouter-reasoning-grounding.md

This repository’s observed evidence
- [R1] OpenAI grounded + JSON failures (schema nesting, 5xx with tools+json_schema, tool_choice notes, “web search cannot be used with JSON mode” log): api_cost_multiplier/docs/openai_grounded_json_failures_research_report_20251014.md and api_cost_multiplier/docs/repeating_problems_7_fpf_json.md
- [R2] Gemini 2.5 Pro grounding failure (intermittent absence of grounding signals in single-call runs): api_cost_multiplier/docs/gemini_pro_grounding_failure_20251012.md
- [R3] Consolidated Gemini grounding reports and contract for JSON handling: 
  - api_cost_multiplier/docs/repreating problems google grounding 4 oct.md
  - api_cost_multiplier/docs/REPEATING PROBLEMS GROUINGS OCT.md

Practical verification checklist (minimal)
- OpenAI:
  - Single serialized run with gpt‑5 and tools=[{type:"web_search"}] + text.format.json_schema under Responses API; verify success and structured output; if 5xx, retry with prompt‑JSON.
- Gemini:
  - Single-call grounded run (tools: google_search) + prompt-only JSON instruction; verify groundingMetadata presence and that JSON text can be extracted; if missing grounding, retry with stronger prompt.
- OpenRouter:
  - Enable reasoning: {"reasoning":{"effort":"high"}} and web search via plugins or :online suffix; confirm citations appear and backend accepts pass-through fields.

Addendum — 2025‑10‑16: OpenAI Responses API requires text.format.name for Structured Outputs
- Change detected: OpenAI now validates that text.format includes a name when type="json_schema"; omitting it triggers HTTP 400 “Missing required parameter: 'text.format.name'”.
- Code update: OpenAI adapter (providers/openai/fpf_openai_main.py) now sets:
  - payload["text"]["format"] = {"type":"json_schema","name":"evaluation_result","json_schema":{...},"strict":false}
- Rationale:
  - Keeps Structured Outputs compatible with tools=[{"type":"web_search"}] while satisfying current server-side validation.
  - Eliminates the observed 400 errors without changing our grounding policy (always-on) or the schema body.
- Evidence:
  - Failed eval logs before fix showed repeated 400s with param=text.format.name.
  - This addendum records the policy so future regressions can be spotted quickly.
