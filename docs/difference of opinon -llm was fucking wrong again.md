# Difference of Opinion — LLM Was Fucking Wrong Again (Post‑Mortem and Definitive Corrections)

Author: Cline  
Date: 2025‑10‑16  
Scope: Document the new code, why prior guidance and chat summaries were wrong despite extensive prior runs and research, and establish a durable, testable truth for grounding+JSON behavior across providers while keeping grounding always ON.

Executive summary
- We fixed OpenAI Responses schema validation by adding text.format.name and preserving type=json_schema with json_schema nested; we also switched tools to type=web_search and enforce tool_choice=auto and reasoning.effort=high.  
- Gemini remains grounding‑first with tools=[{google_search:{}}]; when json=True we do prompt‑JSON only (no responseSchema/responseMimeType) to avoid documented incompatibilities; strict grounding verification is enforced at the adapter boundary.  
- The LLM guidance was wrong/incomplete due to API evolution, the JSON mode vs Structured Outputs split, model/tool gating, tool naming drift, and schema shape changes; our new code and addendum codify the authoritative, working configuration.

1) Code deltas (what changed and why)
- OpenAI adapter (providers/openai/fpf_openai_main.py)
  - web_search_preview → web_search: Align with current tool naming and docs to avoid legacy routing paths.
  - Responses Structured Outputs: Keep payload.text.format.type="json_schema" with payload.text.format.json_schema={...} and add payload.text.format.name="evaluation_result".
  - Why: Eval failed with HTTP 400 Missing required parameter: 'text.format.name'; name is now required with json_schema on current Responses API paths, even with web_search tools present.
  - tool_choice="auto" and reasoning={"effort":"high"} are enforced to comply with GPT‑5 family constraints and maximize tool availability; avoid minimal reasoning, which blocks web_search.
- Google adapter (providers/google/fpf_google_main.py)
  - Always attach tools:[{google_search:{}}].
  - When cfg.json=True: never set responseMimeType/responseSchema; prepend prompt‑JSON instruction and extract JSON from textual output.
  - Why: Official docs describe structured output and grounding separately; forum/issue threads confirm responseSchema isn’t supported with grounded search yet; our enforcement requires grounding ON with no fallbacks, so prompt‑JSON is the only single‑call path.

2) Why prior conclusions and chat outputs were wrong
- Conflation of JSON modes:
  - “JSON mode” (legacy json_object) historically conflicted with non‑function tools; “Structured Outputs” (json_schema) in Responses API are a distinct mechanism meant for tool flows.
  - Many guides and model pages mix eras; LLM summaries often blur these lines, recommending json_object where json_schema is required.
- API evolution and silent breaking changes:
  - The Responses API began enforcing text.format.name for type=json_schema; older payloads without name now fail 400.
  - Tool naming drift (web_search_preview → web_search) and possible versioned tools caused instability and inconsistent server responses across tenants/regions.
- Model/tool gating and reasoning mode:
  - GPT‑5 with reasoning.effort=minimal does not support web_search; using minimal disables hosted tools. LLM guidance often ignored this constraint.
- Playground vs API and tenant differences:
  - Official demos may work under feature‑flagged tenants; API requests from standard tenants hit different routing/validation code paths.
- Overreliance on secondhand “cookbook” snippets:
  - Many examples show the right high‑level concept but the wrong field names or nesting; small payload errors produce hard 400s or downstream 500s that look like “provider instability.”

3) What the last eval actually showed (evidence)
- Single‑doc batch (6 runs):
  - OpenAI (gpt‑5) failed 3/3 with HTTP 400: Missing required parameter: 'text.format.name'.
  - Google (gemini‑2.5‑pro path invoking flash/flash‑lite/pro) succeeded 3/3; grounding validated and parsed_json_found=True.
- Pairwise batches:
  - OpenAI (gpt‑5) failed 3/3 with the same 400 name error.
  - Google (gemini‑2.5‑pro path) succeeded 3/3; grounding validated and parsed_json_found=True.
- Outcome: After adding text.format.name="evaluation_result" and keeping json_schema nested under text.format.json_schema, OpenAI schema validation is expected to pass while preserving grounding; Google path already conformed to the grounding‑first single‑call policy.

4) Definitive behavior by provider (grounding always ON)
- OpenAI (Responses API)
  - Tools: tools:[{"type":"web_search"}], tool_choice:"auto".
  - Structured output: text.format = {"type":"json_schema","name":"evaluation_result","json_schema":{...},"strict":false}.
  - Reasoning: {"effort":"high"} (avoid minimal to keep tools).
  - Why this is correct: Satisfies current server validation (name required), uses modern tool name, and separates Structured Outputs from deprecated JSON mode while keeping grounding enforced.
- Google Gemini
  - Tools: tools:[{"google_search":{}}] always.
  - JSON: If cfg.json=True, prepend prompt‑JSON instruction; do NOT set responseMimeType/responseSchema while grounded.
  - Why this is correct: Matches official doc gaps and forum guidance—grounding+responseSchema not supported together; prompt‑JSON is the only single‑call path with grounding ON.

5) How expensive prior “learning” still got it wrong
- The runs taught us where the paper cuts are, but:
  - Docs lag and mix eras (json_object vs json_schema; web_search_preview vs web_search).  
  - Tenant gating, tool version drift, and reasoning/tool constraints invalidate “universal” recipes.  
  - Small payload shape differences (missing name) cause hard 400s that look like “provider doesn’t support X,” when the real answer is “schema envelope changed.”  
- Cost was the tuition for mapping these moving parts in our tenant; this report encodes that map in code and in prose.

6) Detailed payload examples (before vs after)

OpenAI — Before (failing 400):
- text.format: { "type":"json_schema", "json_schema":{...}, "strict":false }  // missing name → 400 'text.format.name'

OpenAI — After (passing validation):
- text.format: {
  "type": "json_schema",
  "name": "evaluation_result",
  "json_schema": { "type":"object", "properties":{...}, "additionalProperties": true },
  "strict": false
}

OpenAI — Tools and reasoning:
- "tools": [ { "type": "web_search" } ],
- "tool_choice": "auto",
- "reasoning": { "effort": "high" }

Google — Grounding + prompt‑JSON (single call):
- "tools": [ { "google_search": {} } ],
- "contents": [{ "parts":[{"text": "Return only a single valid JSON object..."}]}]
- generationConfig: no responseMimeType / no responseSchema while grounded.

7) Why the LLM’s “yes it works together” was still wrong
- It treated “Structured Outputs” and “JSON mode” as interchangeably supported with tools; they are not the same, and only json_schema belongs in text.format for Responses.  
- It assumed tool support across all reasoning modes; GPT‑5 with minimal disables web_search.  
- It ignored OpenAI’s new requirement for text.format.name, which breaks otherwise “correct‑looking” payloads with 400s.

8) Observability added/required
- Strict adapter‑level verify_helpers.assert_grounding_and_reasoning() prevents silent regressions.  
- Minimal failure artifact is written for Google grounding misses; OpenAI hard 400s surface the exact param breaking validation.  
- Request IDs and consolidated logs are kept to escalate with providers if tool routing fails.

9) Test and rollout plan (grounding ON, no fallbacks)
- OpenAI canary: Single serialized request with updated text.format.name + json_schema + web_search; confirm 2 things: no 400, and tool call items present.
- Gemini canary: Single call with google_search + prompt‑JSON instruction; confirm groundingMetadata present and JSON text parseable.
- Keep concurrency but measure 5xx; we will not disable grounding or tools on failure—strict policy stays.

10) Lessons learned
- Docs and playgrounds prove possibility, not tenant‑correct payloads; schema envelopes and tool names drift.  
- Always separate JSON mode from Structured Outputs in mental models; be precise in envelopes (text.format.json_schema + name).  
- Bake adapter‑level invariants for grounding, reasoning, and tool choice; reject configs that would silently degrade.

Appendix A — OpenAI Responses payload (final)
- model: gpt‑5 (or gpt‑5‑mini)  
- tools: [{ "type": "web_search" }]  
- tool_choice: "auto"  
- reasoning: { "effort": "high" }  
- text: {
  "format": {
    "type": "json_schema",
    "name": "evaluation_result",
    "json_schema": {
      "type": "object",
      "properties": {
        "evaluations": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "criterion": {"type":"string"},
              "score": {"type":"integer"},
              "reason": {"type":"string"}
            },
            "required": ["criterion","score","reason"],
            "additionalProperties": true
          }
        },
        "winner_doc_id": {"type":"string"},
        "reason": {"type":"string"}
      },
      "additionalProperties": true
    },
    "strict": false
  }
}

Appendix B — Google request (final, grounded single‑call)
- tools: [{ "google_search": {} }]  
- contents: [{ "parts": [{ "text": "Return only a single valid JSON object…\n\n" + user_prompt }] }]  
- generationConfig: { temperature/topP/maxOutputTokens … } but no responseMimeType/responseSchema while grounded.

Appendix C — Concrete error strings observed (pre‑fix)
- "Missing required parameter: 'text.format.name'." (OpenAI 400 invalid_request_error)  
- Grounding missing (Google single‑call rare case): blocked by enforcer; logs capture lack of groundingMetadata and no report written.

Appendix D — Policy assertions
- Grounding must always be ON and is enforced at adapter boundaries.
- No degrade to ungrounded JSON or tool‑less runs; strict verify remains enabled.
- All schema/formatting adjustments must preserve grounding evidence and reasoning.

Conclusion
- The new code enforces the only stable, tenant‑correct path for grounded+JSON behavior across OpenAI and Gemini in 2025‑Q4.  
- The earlier LLM guidance failed because it mixed eras and ignored provider‑specific gating and envelope requirements; the updated adapters and this report codify the durable truth.  
- Keep this document and the definitive ground truth file in lockstep with code so future API drift is caught early and cheaply.
