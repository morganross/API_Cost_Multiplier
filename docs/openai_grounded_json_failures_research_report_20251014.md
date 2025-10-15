# OpenAI Grounded + Structured Evaluation Failures: Deep-Dive Research Report (2025‑10‑14)

Author: Cline  
Date: 2025‑10‑14  
Scope: File Prompt Forge (FPF) + llm‑doc‑eval runs using OpenAI Responses API with mandatory web search (grounding) and structured outputs

1) Executive Summary

- What happened
  - In our evaluation pipeline, OpenAI runs that enforce both provider‑side web search (grounding) and structured outputs (JSON) failed.
  - We saw two clear phases:
    1) Phase A (client bug): HTTP 400 invalid_json_schema referencing text.format.schema → fixed by adding items for the evaluations array in our JSON schema.
    2) Phase B (platform instability or incompatibility): HTTP 500 server_error returned by OpenAI on multiple runs (single and pairwise) with gpt‑5‑mini despite valid schema and mandatory grounding logic. Each 500 included a request ID (e.g., req_4fdd391a3a9241eab6fbb3d098ef1d3e).
  - Under the same enforcement, Google Gemini 2.5 (Flash/Pro path using prompt‑JSON with google_search) succeeded consistently.

- Why this matters
  - Our product policy now mandates always‑on grounding and verification. The OpenAI path must be stable or fall back gracefully.
  - The behavior suggests a confluence of factors: model‑tool support churn (tool versioning), account/region gating, playground vs API discrepancies, tool_choice restrictions, and possible incompatibilities when combining web search + reasoning + structured outputs.

- High‑confidence findings (from docs/issues/forums)
  - Web search tool availability is model‑ and account‑dependent and has changed over time (web_search_preview vs web_search vs versioned tools).
  - Some models (e.g., o4‑mini) have documented incompatibilities where web_search is “not supported via API” even if temporarily exposed in playground or enabled briefly by accident.
  - GPT‑5 family imposes tool_choice constraints (“auto” only) per reported issues; using other modes can error.
  - Azure/OpenAI variants often require explicit enablement/registration for web search; missing entitlement can lead to errors (“not enabled for this organization”).
  - Documentation indicates GPT‑5 supports web_search and structured outputs; however, community reports show inconsistent real‑world support matrices and recent tool version changes.

- Probable causes for our 500s (post‑schema fix)
  - Backend path instability or gating when mixing: hosted web search tool + reasoning.effort + Structured Outputs (json_schema) on gpt‑5‑mini.
  - Tool name/version drift (legacy web_search_preview vs newer web_search vs versioned web_search_YYYY_MM_DD) producing brittle behavior not downgraded to 4xx.
  - Account/region/tool entitlement mismatches producing server side faults instead of clean 4xx.
  - Concurrency amplifying backend errors (500 instead of 429/4xx).

- Immediate path forward
  - Introduce a provider‑specific fallback for OpenAI: on 5xx with tools+json_schema, retry once with prompt‑JSON (keep web search on) and tool_choice=auto.
  - A/B tool name (web_search vs web_search_preview) with serialized runs.
  - Lower concurrency when calling OpenAI tool‑enabled paths.
  - Validate entitlement/region for web search tools; test different GPT‑5 (not mini) or gpt‑4.1 models known to work from community posts.
  - Capture and escalate request IDs to OpenAI support if failures persist.

2) Incident Context and Logs (What We Ran and Saw)

- Enforcement baseline in FPF
  - Mandatory grounding: The provider adapter must attach its search tool; FPF then asserts grounding and reasoning in the response. If either is missing, no output file is written.
  - Structured output policy:
    - OpenAI: Structured Outputs (text.format: json_schema) compatible with tools.
    - Gemini: Prompt‑JSON when grounded (no responseSchema + google_search).
    - Deep Research (OpenAI DP): Prompt‑JSON; background execution; strict verify optional.

- Observed errors
  - Phase A (fixed): HTTP 400 invalid_json_schema “array schema missing items” → our schema omission corrected by adding items to evaluations[] object and required fields.
  - Phase B (current): HTTP 500 server_error with multiple request IDs across single/pairwise on gpt‑5‑mini after schema was fixed.
  - In contrast, Gemini runs (single + pairwise) all succeeded with “Run validated: web_search used and reasoning present” + parsed_json_found=True.

3) What Official Docs and Reputable Sources Say (Citations)

- GPT‑5 support (OpenAI official)
  - “GPT‑5 … supports structured outputs and the web_search tool.” (Using GPT‑5 – OpenAI API docs)
    - Source: https://platform.openai.com/docs/guides/latest-model

- Responses API (OpenAI)
  - General API reference for tool calling, structured outputs, and parameters.
    - Source: https://platform.openai.com/docs/api-reference/responses

- Tool version churn (community)
  - “New search tool? web_search_2025_08_26 and web_search (vs legacy web_search_preview)” (Suggests tool naming/version changed mid‑2025)
    - Source: https://community.openai.com/t/new-search-tool-web-search-2025-08-26-and-web-search-vs-legacy-web-search-preview/1354682

- Playground vs API discrepancies (community reports)
  - “Web search works in playground, but not via API. Hosted tool ‘web_search_preview’ is not supported with gpt‑4o‑mini.” (March 2025)
    - Source: https://community.openai.com/t/web-search-works-in-playground-but-not-via-api/1152213

- Model/tool support regression (StackOverflow)
  - “Hosted tool ‘web_search_preview’ is not supported with o4‑mini‑2025‑04‑16.” (May 2025)
    - Source: https://stackoverflow.com/questions/79598009/getting-web-search-is-not-supported-in-o4-mini-even-though-it-is-supported-and

- Tool choice restrictions on GPT‑5 (openai‑python issue)
  - “Tool choices other than ‘auto’ are not supported with gpt‑5‑mini‑2025‑08‑07 …”
    - Source: https://github.com/openai/openai-python/issues/2537

- Entitlement/enablement (Azure/Microsoft Learn)
  - “Web Search tool is not enabled for this organization … request access / choose supported region/API version” (Apr 2025)
    - Source: https://learn.microsoft.com/en-us/answers/questions/2237879/web-search-tool-is-not-enabled-for-this-organizati
  - Azure “What’s new”: registration required for gpt‑5; region/feature variations
    - Source: https://learn.microsoft.com/en-us/azure/ai-foundry/openai/whats-new

- Third‑party references
  - LlamaIndex example shows built‑in web search tool usage with Responses API and structured outputs/strict semantics.
    - Source: https://developers.llamaindex.ai/python/examples/llm/openai_responses/

4) Reconstructed Support Matrix (2025, best‑effort from docs and community)

- Tool naming and versions
  - Legacy: web_search_preview (seen widely early/mid‑2025)
  - Canonical/latest: web_search (official docs and cookbook)
  - Versioned: web_search_2025_08_26 (community screenshot, suggests tool version rollouts)

- Model compatibility (as reported)
  - GPT‑5 family: docs claim supports web_search and structured outputs; community shows tool_choice restrictions (auto only) and sporadic 500s in the wild.
  - o4‑mini: reports show “not supported” via API (400) even when playground briefly allowed it.
  - gpt‑4.1: community reports mixed; some confirm web_search_preview works; others see errors; suggests account/region/tool version fragmentation.

- Account/region gating
  - Azure variants and some orgs require explicit enablement/registration for web search; otherwise tooling is not available or behaves inconsistently. Even within OpenAI’s own platform, feature flags can vary by region and tenant.

5) Why We Likely Saw HTTP 500 (Post‑Schema Fix)

- Hypothesis #1: Tool version mismatch (legacy vs current)
  - If the account/model expects web_search (or a specific versioned tool) and we send web_search_preview, backend may route to an unstable path. Some accounts report 4xx on mismatch, others show inconsistent server behavior.

- Hypothesis #2: Model/tool entitlement gaps
  - Even if docs say GPT‑5 supports web_search, the specific deployment or org/region may not have consistent entitlement. Azure shows explicit “request access” flows; similar gating likely exists in OpenAI for previews or staged rollouts.

- Hypothesis #3: Structured Outputs + tools + reasoning combined path
  - Structured Outputs (json_schema) are intended to be tool‑compatible. However, combining json_schema + hosted search + reasoning.effort on gpt‑5‑mini may hit a less‑tested path, surfacing 500s rather than clean 4xx notices.

- Hypothesis #4: Concurrency‑triggered backend instability
  - Our batch submitted runs with concurrency configured. Hosted search calls fan out behind the scenes; under load or quota edges, the system may 500 (some reports show this symptom class on both OpenAI and Azure OpenAI).

- Hypothesis #5: Tool choice rules
  - GPT‑5 mini reportedly restricts tool_choice to “auto” only. Our adapter uses tool_choice=auto, but any deviation or future tightening could provoke server errors. The issue queue confirms “other than auto not supported” (Aug 2025).

6) Targeted Experiments to Validate Each Hypothesis

- A. Tool version/name A/B
  - A1: Replace {type: "web_search_preview"} with {type: "web_search"} for a single serialized run against gpt‑5‑mini.
  - A2: If available in docs or API enumeration, try versioned tool type name (e.g., "web_search_2025_08_26") in a sandbox call; if unknown parameter → 4xx expected; if accepted and succeeds → tool version drift confirmed.

- B. Model substitution
  - B1: Try gpt‑5 (non‑mini) or gpt‑4.1 with the same payload shape; keep tool_choice=auto and reasoning.effort=low to reduce complexity. If one succeeds → model‑specific path issue.

- C. Entitlement/region
  - C1: Confirm with OpenAI support whether web_search tools are enabled for our account/region for the targeted model. Provide failing request IDs.
  - C2: If using Azure OpenAI in any path, verify region, API version, and entitlement status per Microsoft Learn (“not enabled for this organization”).

- D. Structured Outputs vs prompt‑JSON fallback
  - D1: For OpenAI only, on first 5xx retry the same request with prompt‑JSON (remove text.format; keep tools+reasoning). If prompt‑JSON succeeds → instability isolated to json_schema+tools path.

- E. Concurrency dampening
  - E1: Set max_concurrency=1 and space calls by 15–20 seconds; collect success/failure. If 500s drop → concurrency contributes.

- F. Tool_choice invariants
  - F1: Ensure tool_choice strictly equals "auto". Verify no code path uses allowed_tools/required modes for GPT‑5 mini.

- G. Playground parity
  - G1: Attempt the same request in Playground (copy exact payload) and inspect code export. If works in Playground but not API → likely account flag/environment mismatch; capture exact tool type and tool version from exported code.

7) Remediation Plan for Production Robustness

- 1. Provider‑specific fallback for OpenAI
  - On 5xx server_error only:
    - Retry once with prompt‑JSON (prepend “Return only a single valid JSON object …”), keep tools and reasoning; tool_choice=auto; log both attempts distinctly with request IDs (if returned).
  - Rationale: Gemini uses prompt‑JSON when grounded by design; this preserves our enforcement while bypassing suspected json_schema+tools fragility.

- 2. Tool name migration
  - Probe whether web_search (not web_search_preview) is the canonical name for our account. If successful, standardize on it.
  - Keep an adapter switch keyed by provider capability registry.

- 3. Adaptive concurrency and backoff
  - Track per‑provider error rates; reduce concurrency to 1–2 and increase inter‑request delays on 5xx spikes. Avoid retry storms which can exacerbate backend issues.

- 4. Model fallback
  - If gpt‑5‑mini remains unstable with tools, consider trying gpt‑5 or gpt‑4.1 for grounded runs until model support stabilizes.

- 5. Observability
  - Persist failing responses (status code, body, request IDs) and a redacted payload shape. Build a small dashboard of tool errors over time.

- 6. Escalation SOP
  - With captured request IDs (e.g., req_4fdd391a3a9241eab6fbb3d098ef1d3e …), contact OpenAI support; ask:
    - Whether web_search is enabled for our account/model/region.
    - Whether web_search_preview is deprecated and requires switching to web_search.
    - Whether Structured Outputs + tools + reasoning is supported for gpt‑5‑mini in our tenant (if not, ask for timeline or workaround).

8) Detailed Diagnostics We Already Applied

- Fixed schema issue
  - Our JSON schema now includes evaluations[].items with {criterion, score, reason} and required[]; strict=False to avoid over‑constraining with hosted tools.

- Enforced grounding everywhere
  - Providers attach their respective tools; FPF asserts grounding & reasoning twice (provider‑level path and core‑level check) before any output write.

- Verified Gemini path
  - Gemini succeeded consistently using prompt‑JSON + google_search, reaffirming that our enforcement pipeline is correct and robust outside of OpenAI’s tool path.

9) Minimal Reproduction Payloads (for A/B and support)

- OpenAI Responses (Structured Outputs path; redacted content)
  - model: gpt‑5‑mini
  - tools: [{ "type": "web_search_preview" }]  ← try swapping to "web_search"
  - tool_choice: "auto"
  - reasoning: { "effort": "low" }  ← use “low” for tests to reduce backend complexity
  - text: {
      "format": {
        "type": "json_schema",
        "name": "evaluation_result",
        "schema": {
          "type": "object",
          "properties": {
            "evaluations": {
              "type": "array",
              "items": {
                "type": "object",
                "properties": {
                  "criterion": { "type": "string" },
                  "score": { "type": "integer" },
                  "reason": { "type": "string" }
                },
                "required": ["criterion", "score", "reason"],
                "additionalProperties": true
              }
            }
          },
          "additionalProperties": true
        },
        "strict": false
      }
    }

- OpenAI Responses (Prompt‑JSON fallback)
  - Remove text.format block entirely; prepend to prompt:
    “Return only a single valid JSON object. Do not include any prose or Markdown fences. The object must be strictly valid JSON.”
  - Keep tools + tool_choice=auto + reasoning.effort.

10) Step‑By‑Step Runbook (Validate and Stabilize)

- Step 1: Serialize a single OpenAI request (no batch; no concurrency; one attempt)
  - Use gpt‑5‑mini; tool=web_search_preview; reasoning.effort=low; text.format=json_schema.
  - Record response or 5xx + request ID.

- Step 2: Change only the tool name
  - Switch to tool=web_search and retry; record outcome.

- Step 3: Change model
  - Retry with gpt‑5 (non‑mini) and gpt‑4.1; record outcomes. If one works → model‑specific path issue.

- Step 4: Change output mode
  - Remove text.format and switch to prompt‑JSON; keep tools; record outcomes.

- Step 5: Concurrency profile
  - Re‑enable batch with max_concurrency=1; space runs by 15–20s; record errors/success rate.

- Step 6: Escalation packet for OpenAI support
  - Include request IDs, redacted payload shapes (tool type, model, output mode), timestamps, regions, org identifiers, and a clear description of behaviors across A/B tests.

11) FAQ and Expectations

- “Docs say GPT‑5 supports web_search + structured outputs. Why doesn’t it work?”
  - It likely does for specific model/tool versions and account/region entitlements. In practice, these roll out progressively; community reports confirm periods of mismatch between playground and API and between models/tenants.

- “Why do we see 500 instead of 4xx?”
  - 500 suggests an internal exception on the provider side. It often indicates rollout/gating/version routing defects or transient service faults.

- “Is prompt‑JSON a step back?”
  - Not functionally for our use case. We still enforce grounding; we only change how we request the JSON (schema‑enforced vs instruction‑constrained). We already use prompt‑JSON for Gemini when grounded because responseSchema isn’t supported with google_search.

12) Final Recommendations

- Implement OpenAI fallback logic immediately:
  - Attempt 1: json_schema + tools + reasoning (tool_choice=auto).
  - On 5xx: Attempt 2 (single retry): prompt‑JSON + tools + reasoning (tool_choice=auto).
  - If both fail: capture request IDs; mark run as provider‑failed; do not write output; move on.

- Perform tool A/B and model A/B tests (single, serialized calls).
- Confirm entitlement for web search on our org/model; verify supported tool name/version.
- Reduce concurrency; introduce adaptive throttling on 5xx spikes.
- Keep a weekly health check of OpenAI grounded+JSON path; re‑enable json_schema first if success rate stabilizes.

13) Citations and Sources

- Using GPT‑5 – OpenAI API (supports structured outputs and the web_search tool)
  - https://platform.openai.com/docs/guides/latest-model
- Responses API reference – OpenAI
  - https://platform.openai.com/docs/api-reference/responses
- “New search tool? web_search_2025_08_26 and web_search (vs legacy web_search_preview)” – OpenAI Community
  - https://community.openai.com/t/new-search-tool-web-search-2025-08-26-and-web-search-vs-legacy-web-search-preview/1354682
- “Web search works in playground, but not via api” – OpenAI Community (gpt‑4o‑mini case)
  - https://community.openai.com/t/web-search-works-in-playground-but-not-via-api/1152213
- “Web Search is not supported in o4‑mini ...” – StackOverflow (400 invalid_request)
  - https://stackoverflow.com/questions/79598009/getting-web-search-is-not-supported-in-o4-mini-even-though-it-is-supported-and
- “GPT5 Models | Tool choices other than ‘auto’ are not supported …” – openai‑python issue #2537
  - https://github.com/openai/openai-python/issues/2537
- “Web Search tool is not enabled for this organization” – Microsoft Learn (Azure entitlement and region/API versioning)
  - https://learn.microsoft.com/en-us/answers/questions/2237879/web-search-tool-is-not-enabled-for-this-organizati
- “What’s new in Azure OpenAI” – Registration and region notes (gpt‑5)
  - https://learn.microsoft.com/en-us/azure/ai-foundry/openai/whats-new
- LlamaIndex – OpenAI Responses API example (built‑in tool calling and structured outputs)
  - https://developers.llamaindex.ai/python/examples/llm/openai_responses/

Appendix A: Representative Error Messages (From Our Logs)

- HTTP 400 (pre‑fix)
  - “Invalid schema for response_format 'evaluation_result': In context=('properties', 'evaluations'), array schema missing items.”
  - param: "text.format.schema", code: "invalid_json_schema".

- HTTP 500 (post‑fix)
  - “An error occurred while processing your request. You can retry your request, or contact us … Please include the request ID req_…”
  - Example request IDs collected:
    - req_4fdd391a3a9241eab6fbb3d098ef1d3e
    - req_8d1ae607044445aabb1c9cb16ad3b3f6
    - req_7f42f2d1e6d840918b955a01b94f3040
    - req_b0bd1e91ce124f538280aed1ae96ac69
    - req_4fa1f924bc8c4abca29e120eb3d78ffa
    - req_7d3b5b448cc148429946701f6418b50f
    - req_94b7fe4f5a1a4f2abd79ad50b5a2e16d

Appendix B: Payload Skeletons (Sanitized)

- OpenAI (Structured Outputs path)
  - tools: web_search_preview (A/B with web_search)
  - tool_choice: "auto"
  - reasoning: { effort: "low"|"high" }
  - text.format: json_schema (evaluations[] items defined)

- OpenAI (Prompt‑JSON fallback)
  - Remove text.format; prepend JSON‑only instruction to prompt; keep tools+reasoning; tool_choice=auto.

- Gemini
  - tools: [{ google_search: {} }]
  - JSON via prompt only when grounded.

Appendix C: Test Checklist

- Verify package versions (openai SDK) to latest; some forum posts note version‑sensitive tool exposure.
- Confirm endpoint is Responses API (not legacy Chat Completions) when copying code from Playground.
- Ensure tool_choice=auto (per GPT‑5 mini limitation).
- Confirm region/tenant with OpenAI support; validate entitlement for web search on the model(s) we use.
- Establish staged rollouts and capture telemetry (5xx rate, request IDs, success rate after A/B changes).

Closing

The combination of hosted web search, reasoning, and structured outputs is a powerful path but also a moving target across models, accounts, and time. Our enforcement logic is correct (validated by Gemini), and after fixing our schema, the remaining OpenAI failures appear to be platform‑side. The outlined experiments and fallbacks will isolate the exact incompatibility and stabilize production while we work with OpenAI to resolve the 500s or confirm the required tool/model configuration for our tenant.
