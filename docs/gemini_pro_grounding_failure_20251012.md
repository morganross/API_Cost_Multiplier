# Gemini 2.5 Pro Grounding Failure Incident Report (2025-10-12)

Summary
- One run (first batch) using Google Gemini 2.5 Pro failed mandatory grounding enforcement and was blocked from output write.
- Subsequent batch run for the same model succeeded with full grounding signals.
- Root cause is most likely intermittent provider omission of grounding signals or insufficiently deterministic prompt-level grounding instruction under single-call policy. Enforcement logic behaved correctly.

Scope and policy context
- JSON policy: boolean-only; generate path uses json=false; single-call only (no two-stage).
- Google policy: never set responseMimeType/responseJsonSchema; prompt-only instruction; rely on single response; extract signals from response when present.
- Grounding and reasoning: mandatory; runs without evidence are rejected.
- Dynamic Google endpoint: model-derived override to https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent.
- Concurrency: global max_concurrency=32; qps=0.1 (10s min interval); deep-research bypasses global limit.

Timeline (from logs)
- 12:12:20.109 FPF scheduler starts, concurrency configured.
- 12:12:30.261 gemini-2.5-flash success; log written: FilePromptForge/logs/20251012T121230-f318f04c.json.
- 12:12:33.845 gemini-2.5-flash-lite success; log written: FilePromptForge/logs/20251012T121233-7505d9bd.json.
- 12:12:44.529 gemini-2.5-pro failed (first batch):
  - fpf_run.log: “Provider response failed mandatory checks: missing grounding (web_search/citations). Enforcement is strict; no report may be written.”
  - No consolidated JSON log was written for this failed attempt (by design).
- 13:59:52.906 Second batch launched with json override confirmed (json=False).
- 14:00:24.587 gemini-2.5-pro success (second batch); log written: FilePromptForge/logs/20251012T140024-2f4ee652.json.

Evidence

1) Failure message (first batch)
From api_cost_multiplier/logs/fpf_run.log:
- 2025-10-12 12:12:44,529 WARNING fpf_scheduler: Run failed (attempt 1/5) id=fpf-3-1 provider=google model=gemini-2.5-pro err=Provider response failed mandatory checks: missing grounding (web_search/citations). Enforcement is strict; no report may be written. See logs for details.

Notes:
- Enforcer correctly blocked output write since grounding signals were absent.
- No per-run consolidated JSON was produced for failed runs.

2) Successful gemini-2.5-pro (second batch) consolidated log
File: api_cost_multiplier/FilePromptForge/logs/20251012T140024-2f4ee652.json
Key fields observed:
- request.tools: [{"google_search": {}}]
- response.groundingMetadata.searchEntryPoint: present (HTML snippet)
- response.groundingChunks: present (URIs via vertexaisearch redirect with titles: cbsnews.com, washingtonpost.com, aa.com.tr, paychex.com, pbs.org, house.gov, etc.)
- response.groundingSupports: present with segments mapped to chunk indices
- response.webSearchQueries: present
- usageMetadata: prompt/candidate/tool/thoughts token counts recorded
- human_text: generated narrative aligned to prompt

3) Successful gemini-2.5-flash (first batch) consolidated log
File: api_cost_multiplier/FilePromptForge/logs/20251012T121230-f318f04c.json
Key fields observed (analogous to Pro success case):
- groundingMetadata.searchEntryPoint: present
- groundingChunks: present
- groundingSupports: present
- webSearchQueries: present

Analysis

What failed
- The first batch gemini-2.5-pro response did not include sufficient grounding evidence signals required by the enforcer (specifically “web_search/citations” class of evidence). Under strict policy, this correctly prevented output write.

Why it failed (most likely)
- Intermittent provider behavior on single-call Google runs: despite tools=[google_search], Gemini responses can occasionally omit explicit grounding/citation signals (e.g., missing groundingMetadata fields or linkable citations) depending on search pathway activation or internal heuristics.
- Prompt-level determinism: Under single-call policy, we rely exclusively on prompt text to require citations and evidence. If the instruction strength is below threshold or phrased in a way that Gemini occasionally does not surface grounding cues, enforcement will fail even if content looks plausible.
- Not an endpoint issue: Dynamic endpoint overrides are logged for flash/flash-lite and were correct. For Pro, config target already matched the model endpoint in the successful run; the failure was not an HTTP or endpoint error.
- Not a JSON/payload issue: Generate path json=false by policy; success cases demonstrate that grounding signals are independent of JSON settings.

What worked
- Enforcement: Strict validation caught the missing grounding case and blocked output as intended.
- Subsequent run (second batch) succeeded for Pro with clear grounding metadata, confirming no persistent configuration defect.

Mitigations and recommendations

A. Prompt-level hardening for Google single-call
- Prepend a strong, compact instruction requiring:
  - Use of Google web search.
  - Inclusion of inline citations with explicit source anchors (e.g., [1], [2]) and a final “Sources” section.
  - Do not produce an answer unless at least N independent sources are included (e.g., 3).
- Example instruction (to be inserted only when provider==google and json==false):
  - “You must perform a fresh web search and include direct citations for every major claim. Provide at least 3 independent sources. Use inline numeric citations like [1], [2] mapped to a ‘Sources’ section containing full URLs. If you cannot ground a claim, omit it.”

B. Retry strategy refinement (optional)
- Distinguish transient “missing grounding” from hard failures:
  - Immediately retry up to R times with an incremental backoff jitter bounded by provider QPS rules when grounding signals are missing.
  - Record “retry_reason=missing_grounding” to metrics for tracking.
- Current scheduler reports “attempt 1/5” but the first batch still ended with 1 failed; ensure retry conditions include validation-failure triggers (not just transport/status errors), if deemed acceptable for throughput.

C. Search context knobs for Google
- Consider elevating search_context_size from “low” to “medium” for sensitive topics with fast-moving facts. The second batch Pro success (config showed “low”) did succeed, so this is optional, but testing may show increased determinism of grounding signals.

D. Logging and triage
- Continue writing per-run consolidated logs on success; for failures, add an option to write a minimal failure artifact capturing:
  - request.tools
  - top-level response keys (if present)
  - detection flags (which signals were missing)
  - timing and model
  This accelerates incident analysis without relaxing enforcement.

E. Enforcement rule hygiene
- Current success cases confirm Google-specific signals (groundingMetadata, searchEntryPoint, groundingChunks, groundingSupports) are recognized. Do not relax. Optional enhancement: accept Google’s grounded URIs list as sufficient if inline citations are missing but groundingSupports is present for the majority of claim segments.

Appendix: Key artifacts and references
- Failure (first batch): api_cost_multiplier/logs/fpf_run.log at 2025-10-12 12:12:44,529
- Success (Pro, second batch): api_cost_multiplier/FilePromptForge/logs/20251012T140024-2f4ee652.json
- Success (Flash, first batch): api_cost_multiplier/FilePromptForge/logs/20251012T121230-f318f04c.json

Conclusion
- The incident was an isolated provider-side omission of grounding signals under single-call constraints. The system behaved correctly by blocking output.
- Adopting stronger Google-specific grounding instructions and optionally widening retry logic for “missing grounding” should reduce intermittent failures while preserving strict evidence requirements.
