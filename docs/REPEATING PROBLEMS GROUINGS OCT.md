============================================================
FPF MUST ALWAYS USE GROUNDING AND REASONING. IT IS UNCONFIGURABLE.
IF YOU WANT TO CHANGE GROUNDING IN FPF, STOP IMMEDIATELY.

FPF MUST ALWAYS USE GROUNDING AND REASONING.
DO NOT ATTEMPT TO CHANGE FPF AWAY FROM GROUNDING AND REASONING.
============================================================

Title: Repeating Problems — Grounding (October)
Author: Cline
Date: 2025-10-12

1) Contract (YES/NO, unambiguous)
- If JSON is NOT requested: no JSON flag/parameter is passed to any provider.
- If JSON IS requested:
  - OpenAI/OpenRouter: pass provider JSON controls (e.g., response_format=json_object or a schema).
  - Google: never set generationConfig.responseMimeType or responseJsonSchema. Instead, instruct the model to return strict JSON; if JSON appears as text in the single response, extract it. No second call.

2) “Auto mode” removal (what it was, why it’s gone)
- What it was: a provider-aware convenience that attempted to decide when to use provider JSON based on model/tool compatibility.
- Why it fails requirements:
  - It creates ambiguity. The contract demands binary behavior:
    - json=False → no provider JSON controls
    - json=True → OpenAI sets JSON control; Google never sets JSON control (instruction-only)
  - It risks regressions from provider drift. The policy prioritizes explicit, deterministic behavior.
- Decision: Remove all references to “auto” in config, code, and docs. JSON handling is strictly boolean.

3) Exact implementation requirements (code-level)
A. Config (FilePromptForge/fpf_config.yaml)
- Set:
  - json: false        # boolean only
- Remove:
  - allow_json_with_tools
  - Any mention of “auto” JSON modes
- Rationale: configuration must reflect strictly boolean JSON intent.

B. Core (FilePromptForge/file_handler.py)
- Treat cfg["json"] strictly as boolean. No heuristics.
- request_json path:
  - If request_json=True, only attempt single-call text extraction via _extract_json_from_text on the provider’s textual output. Never perform a second LLM call.
- Do not inject provider JSON flags implicitly; adapters decide based on cfg["json"] and provider.
- Keep mandatory grounding/reasoning asserts intact.

C. Google adapter (FilePromptForge/providers/google/fpf_google_main.py)
- Never set generationConfig.responseMimeType or responseJsonSchema.
- When cfg["json"] is True:
  - Prepend a short instruction to return only a single valid JSON object, no prose, in the model’s textual output.
  - Grounding stays mandatory; the payload must continue to include the google_search tool.
- Parsing:
  - Continue using parse_response for human text.
  - If higher layer requested JSON, rely on the single-call extractor for JSON text, no second call.

D. OpenAI adapter (FilePromptForge/providers/openai/…)
- When cfg["json"] is True:
  - Set response_format=json_object (or schema if provided).
- When cfg["json"] is False:
  - Do not set any JSON controls.
- Grounding and reasoning remain enforced per project policy.

E. Documentation
- Purge all “auto” references from docs and comments.
- Update docs to state the boolean contract above verbatim.

4) Test plan (single-call only, no two-stage)
- Generate (ACM):
  - Case G1: json=False → Confirm no provider JSON controls are sent to Google or OpenAI.
  - Case G2: json=True →
    - OpenAI: confirm response_format/json_object present.
    - Google: confirm no responseMimeType or schema is set; confirm prompt includes JSON-only instruction; confirm JSON can be extracted from the text if present.
  - For all Google runs: confirm groundingMetadata/citations present and no responseMimeType in request payload.
- Evaluate:
  - For json=False templates: confirm no provider JSON flags set; still grounded.
  - For json=True templates: confirm OpenAI uses JSON flag; Google uses instruction-only approach; JSON can be extracted if present.
- Logs:
  - Capture FilePromptForge/logs/*.json request/response snapshots; verify no JSON parameter for Google in generationConfig.

5) Acceptance criteria
- No references to “auto” in code or docs.
- json=False → zero provider JSON flags for all providers.
- json=True:
  - OpenAI/OpenRouter → response_format/json_object (or schema).
  - Google → no JSON parameters; JSON instruction-only; extraction from text only when present.
- Grounding always enforced (mandatory) and passes verification.

6) Migration/rollback
- Migration:
  - Set json: false in fpf_config.yaml and remove any “auto” references.
  - Deploy updated adapters.
- Rollback:
  - Revert the specific commits; restore prior config if needed (not recommended).

7) Rationale summary (why boolean-only)
- Eliminates ambiguity; aligns perfectly with the stated contract.
- Reduces maintenance risk from provider drift.
- Keeps single-call constraint; preserves mandatory grounding.

8) Next steps
- Implement the code/doc edits listed above.
- Run generate and evaluate; attach new log IDs and observations to this doc.

END OF DOCUMENT
