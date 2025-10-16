# OpenAI Responses “text.format.schema” 400 — Grounded Structured Output Incident Report (Ten‑Page Detail)

Author: Cline  
Date: 2025‑10‑16  
Scope: FPF eval path with grounding always ON (OpenAI + Gemini); Structured Outputs for OpenAI via Responses API; incident after adding text.format.name and switching tool type to web_search. This report documents the failure, root cause analysis, corrective options, verification plans, and durable guardrails.

1) TL;DR (Executive Summary)

- What failed: OpenAI GPT‑5 runs returned HTTP 400 invalid_request_error “Missing required parameter: 'text.format.schema'” after we required grounding + JSON and set “text.format” with type=json_schema, name, and json_schema payload.  
- Why: The OpenAI endpoint we hit validated the Schema at text.format.schema (top‑level key) rather than nested under text.format.json_schema — i.e., a different “dialect” of the Structured Outputs envelope.  
- Fix: Adjust the OpenAI adapter to emit the server‑expected envelope: "text": { "format": { "type":"json_schema", "name":"evaluation_result", "schema": {...}, "strict": false } }, keep tools:[{"type":"web_search"}], tool_choice:"auto", and reasoning.effort≠minimal; verify with canary and document result in Ground Truth (append‑only).

2) Grounding‑First Policy and Context

- Policy: Grounding and reasoning are mandatory and unconfigurable in FPF; runs without evidence are rejected.  
- JSON in eval: We require structured outputs for OpenAI; for Gemini we use prompt‑JSON only when grounded due to docs/threads stating responseSchema isn’t supported with google_search together (single call).  
- Recent code changes (OpenAI):
  - Enforce tools: [{"type":"web_search"}] instead of legacy “web_search_preview”.  
  - Enforce tool_choice:"auto" + reasoning:{"effort":"high"} (to avoid GPT‑5 “minimal” disabling tools).  
  - Add Structured Outputs via “text.format”: type:"json_schema"; added “name”; placed schema under “json_schema” wrapper (previously missing name).

3) Timeline of Events (UTC)

- T‑0: Add name="evaluation_result"; keep schema under format.json_schema; switch tool to web_search; maintain grounding verification and reasoning.  
- T+X: Run single and pairwise eval batches; Gemini passes with grounding+prompt‑JSON; OpenAI GPT‑5 returns 400 “Missing required parameter: 'text.format.schema'”.  
- T+X+ε: Confirms repeated 400s across single/pairwise OpenAI runs; Gemini continues to succeed; append Ground Truth with “Result Log (append‑only)”.

4) Observed Error Signals

- HTTP 400 invalid_request_error  
- "message": "Missing required parameter: 'text.format.schema'."  
- "param": "text.format.schema"  
- "code": "missing_required_parameter"  
- Implication: The server’s validator expects a "schema" field at text.format.schema; our payload instead provided text.format.json_schema (with the schema object nested there).

5) Structured Outputs Envelope — Competing Dialects (Evidence Synthesis)

- Dialect A (Top‑level schema):
  - text.format = { type:"json_schema", name:"...", schema:{...}, strict:false }  
  - This is consistent with the server error param ("text.format.schema") and with portions of Responses API examples that treat “schema” as a sibling to “type/name/strict”.
- Dialect B (Nested “json_schema” wrapper):
  - text.format = { type:"json_schema", json_schema:{ schema:{...}, name:"...", strict:true|false } }  
  - Some documentation and derived examples suggest placing schema within a json_schema wrapper; earlier 400s (pre‑name) led us to adopt this; however, the latest server validator rejects it.
- Conclusion: Our tenant/model path currently enforces Dialect A; we must conform to A while preserving mandatory grounding and tool usage.

6) Payload Before vs After (Concrete Snippets)

- Current (failing 400):  
  "text": {  
    "format": {  
      "type": "json_schema",  
      "name": "evaluation_result",  
      "json_schema": {                 ← server complains it wants "schema" at this level  
        "type": "object",  
        "properties": { "evaluations": { "type":"array", "items": {...} }, "winner_doc_id": {...}, "reason": {...} },  
        "additionalProperties": true  
      },  
      "strict": false  
    }  
  }

- Proposed (expected passing):  
  "text": {  
    "format": {  
      "type": "json_schema",  
      "name": "evaluation_result",  
      "schema": {                      ← top‑level "schema" per error param  
        "type": "object",  
        "properties": { "evaluations": { "type":"array", "items": {...} }, "winner_doc_id": {...}, "reason": {...} },  
        "additionalProperties": true  
      },  
      "strict": false  
    }  
  }

- Tools (unchanged):  
  "tools": [{ "type": "web_search" }], "tool_choice": "auto", "reasoning": {"effort":"high"}

7) Root Cause Analysis

- Misaligned envelope: We provided the schema under format.json_schema, while the server requires format.schema; the validator pinpoints the expected field location.  
- Documentation churn: Multiple sources show differing envelopes (schema nested versus top‑level), likely due to API evolution or mixed examples (Assistants/Chat vs Responses, older vs newer).  
- Environment variance: Tenants, models, and snapshot versions can enforce distinct validation paths; our logs reflect the active validator demanding top‑level format.schema.

8) Constraints and Non‑Negotiables

- Grounding always ON: tools must include web_search; tool_choice must remain "auto"; reasoning.effort cannot be “minimal” for GPT‑5.  
- Single call: We will not degrade to multi‑step or remove tools; schema envelope changes must preserve agentic tool use.  
- Append‑only documentation: Every change and its result will be prepended to the Ground Truth change/results sections.

9) Corrective Action Plan (Code‑Level)

- OpenAI adapter (providers/openai/fpf_openai_main.py):  
  - In build_payload(), replace the “json_schema” wrapper with top‑level "schema".  
  - Keep "name":"evaluation_result" and "strict": false as siblings of "type" and "schema".  
  - Preserve "tools":[{"type":"web_search"}], "tool_choice":"auto", and reasoning:{"effort":"high"}.
- Example patch (illustrative structure):  
  payload["text"] = {  
    "format": {  
      "type": "json_schema",  
      "name": "evaluation_result",  
      "schema": SCHEMA_OBJECT,  
      "strict": False  
    }  
  }

10) Verification Strategy

- Canary (single, serialized):  
  - Model: gpt‑5; request with "schema" at top‑level; expect 200 OK, tool usage evidence (web_search tool call items), and structured output validation.  
- Batch smoke (single + pairwise):  
  - Repeat the previous eval set; ensure OpenAI runs pass grounding+JSON checks; compare failure rates vs Gemini.  
- Telemetry:  
  - Persist request IDs and redacted payload shape; log validator error deltas post‑change.

11) Risks and Mitigations

- Further envelope drift: The provider may revert or expect the nested form; mitigation is a capability flag or probe that switches envelopes based on first error param (json_schema vs schema).  
- Tool naming/version churn: Continue to prefer "web_search" (not preview); if the server returns “unknown tool type”, swap to the officially enumerated alias and document in Ground Truth.  
- Long JSON truncation: Ensure max_output_tokens are adequate; keep strict=false to reduce over‑constraining; validate JSON client‑side with repair if strictly necessary (without turning off tools).

12) Why Gemini Passed

- We do not use responseSchema/responseMimeType while grounded; instead, we instruct prompt‑JSON and parse the textual JSON; this aligns with Google docs/forums indicating lack of native schema enforcement with google_search in the same call.  
- Grounding metadata (searchEntryPoint, groundingSupports, webSearchQueries) consistently observed; parsed_json_found=True in logs.

13) Long‑Term Hardening

- Envelope autodetect: On first 400, inspect "param" to toggle adapter envelope from format.schema to format.json_schema (including name/strict placement) while keeping grounding ON; do NOT disable tools.  
- Model registry feature bit: Record which model snapshot expects which envelope; persist decisions in Ground Truth.  
- Weekly health checks: Run canaries and record outcomes; update Result Log (append‑only).

14) Compliance With Documentation

- The incident shows that public examples vary; the only authoritative source is server‑side validation + official error params; we will conform to those while enforcing grounding.  
- Our Ground Truth now tracks both changes and results in prepend‑only sections to avoid knowledge drift.

15) Action Items (Immediate)

- Implement format.schema envelope in OpenAI adapter; do not alter tools/grounding.  
- Re‑run eval; expect OpenAI to pass grounding+JSON; prepend Ground Truth with the result entry.  
- If still failing, enable envelope autodetect and rerun canary; document outcomes.

Appendix A — Full Request Skeleton (Proposed)

{
  "model": "gpt-5",
  "tools": [ { "type": "web_search" } ],
  "tool_choice": "auto",
  "reasoning": { "effort": "high" },
  "input": [{ "role":"user", "content": "..." }],
  "text": {
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
          },
          "winner_doc_id": { "type": "string" },
          "reason": { "type": "string" }
        },
        "additionalProperties": true
      },
      "strict": false
    }
  }
}

Appendix B — Error Excerpt (Pre‑Fix)

HTTP 400 (invalid_request_error)
- "message": "Missing required parameter: 'text.format.schema'."
- "param": "text.format.schema"
- "code": "missing_required_parameter"

Appendix C — Ground Truth Updates (Bookkeeping)

- Prepend “Result Log” entry with the 400 schema error (done).  
- All future eval code changes and their outcomes must be appended/prepended per policy; NEVER delete existing content.

Appendix D — Definitions

- Grounding evidence (OpenAI): tool usage items for web_search; (Gemini): groundingMetadata.* presence; both are required by verifier.  
- Structured Outputs: Provider‑side schema enforcement for JSON responses; envelope format is provider‑specific and evolving.

Closing

- The failure was a schema envelope mismatch; we will conform to the server‑expected text.format.schema while preserving grounding+reasoning invariants and tool use.  
- Gemini remains stable under grounding with prompt‑JSON.  
- Ground Truth now records both the code change and the resulting error, preventing repeated loops and ensuring auditable progress.
