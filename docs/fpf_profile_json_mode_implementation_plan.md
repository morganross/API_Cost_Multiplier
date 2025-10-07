# FilePromptForge (FPF) — Profile + JSON Mode Implementation Plan

Status: Proposed  
Owner: FPF maintainers  
Consumers: llm-doc-eval evaluator (model-agnostic), other ACM components  
Goal: Centralize provider/model knowledge and JSON-enforcement in FPF profiles. Evaluator passes only an opaque profile name and an evaluation “mode” (single|pairwise). FPF selects the concrete provider/model and guarantees strict JSON outputs using provider-specific best practices.

## 1) Background and Current State

- Evaluator (llm-doc-eval) currently externalizes prompts and anonymizes doc IDs but still loops over `provider:model` pairs.
- We want to remove all provider/model awareness from the evaluator.
- FPF already knows how to call providers (OpenAI, OpenRouter compatible, Gemini, etc.).
- Evaluator will only pass:
  - `profile`: an opaque string (e.g., `judge_default`, `judge_gemini_strict`)
  - `mode`: `"single"` or `"pairwise"` (so FPF knows which output schema to enforce)
- FPF must take responsibility for:
  - Choosing provider and model (per profile)
  - Enforcing strict JSON output (provider-specific “dialect”)
  - Returning the actual model used (for transparency in DB/CSVs)

## 2) High-Level Design

- FPF profiles define everything needed to run a judging call:
  - provider, model, provider-specific knobs
  - whether strict JSON is required, and how to enforce it for that provider
  - non-streaming mode for structured outputs (to reduce schema violations)
- Evaluator calls `fpf_runner.run_filepromptforge_runs(instr_path, payload_path, num_runs=1, options={ profile, mode })`
- FPF returns:
  - `(out_path, model_name)` so the evaluator can store `model_name` in DB
  - The output file contains ONLY the model response (ideally strict JSON) which the evaluator parses, validates, and persists

## 3) FPF Config Schema Changes

Extend FPF’s config (e.g., `api_cost_multiplier/FilePromptForge/fpf_config.yaml`) to support named profiles and an output JSON toggle. The evaluator does NOT read this. FPF alone owns it.

Example:

```yaml
profiles:
  judge_default:
    provider: openai
    model: gpt-4.1
    output:
      require_json: true
      # For OpenAI-like responses:
      # prefer_tools: true            # if adapter uses function-calling
      # response_format_json: true    # alternative approach if supported
    runtime:
      streaming: false
      timeout_seconds: 120

  judge_gemini_strict:
    provider: google
    model: gemini-1.5-pro
    output:
      require_json: true
      use_response_schema: true
      # response_mime_type defaults to application/json; override if needed
      response_mime_type: application/json
    runtime:
      streaming: false
      timeout_seconds: 120

  judge_openrouter_openai:
    provider: openrouter-openai
    model: openai/gpt-4o-mini
    output:
      require_json: true
    runtime:
      streaming: false
      timeout_seconds: 120
```

Notes:
- No temperature/grounding/max_tokens at the evaluator layer. All provider tuning lives here in FPF.
- `require_json: true` is the key switch; FPF will ensure provider-specific JSON enforcement for each adapter.
- `runtime.streaming=false` recommended for structured outputs to reduce schema violations.
- If needed, add `retries` (attempts, backoff) here for JSON repair/retry.

## 4) Runner API Expectations

Update/confirm the FPF runner API surface (`api_cost_multiplier/functions/fpf_runner.py`) to accept `options.profile` and `options.mode`:

```python
# existing signature, keep backward compat
async def run_filepromptforge_runs(instr_path: str, payload_path: str, num_runs: int = 1, options: dict | None = None) -> list[tuple[str, str | None]]:
    """
    Returns a list of (output_file_path, model_name_or_profile).
    - options:
        profile: str      # REQUIRED for evaluator integration
        mode: str         # "single" | "pairwise"  (optional but recommended)
        # other provider-agnostic flags (optional)...
    """
```

Behavior:
- Resolve `profile` → profile object from FPF config.
- Use provider adapter factory to instantiate a client with profile settings.
- Enforce JSON according to the profile + provider adapter.
- Execute a single request per run (num_runs typically 1 for eval).
- Write the provider’s raw response to `out_path`. If JSON enforcement guarantees JSON, the file should be JSON-only. If some provider can still prepend text, FPF may run a repair pass or filter to JSON-only.
- Return `(out_path, actual_model_name)`:
  - `actual_model_name` is the truth of what was used (e.g., `openai:gpt-4.1`, `google:gemini-1.5-pro`).
  - If not available, return the `profile` string so the evaluator can persist something.

## 5) Provider Adapter Work

Implement JSON enforcement in each provider adapter when `profile.output.require_json = true`.

### 5.1 OpenAI / OpenRouter-OpenAI-compatible

- Preferred: function/tool calling with strict schema (if you later route schemas here).
- Alternatively: `response_format={"type":"json_object"}` or equivalent in the Responses API (depending on the SDK).
- Non-streaming for eval.
- Timeouts as configured in `profile.runtime.timeout_seconds`.
- If tool-calling is used:
  - Provide a function name and parameters schema (optional if FPF will hold schemas per mode).
- If not using tool calling:
  - Set `response_format=json` and provide very strong system prompt instructions to return ONLY JSON.

### 5.2 Google Gemini

- Set `generationConfig.response_mime_type="application/json"`.
- If `use_response_schema: true`, set `generationConfig.response_schema = <schema>`:
  - FPF owns mapping of internal JSON Schema → Gemini schema vocabulary (already available in evaluator; migrate helper to FPF).
- Non-streaming recommended.
- Strong system prompt for JSON-only fallback (in case schema fails).

### 5.3 Anthropic Claude (if applicable)

- Use tool/output settings that bias toward JSON (varies by SDK).
- Non-streaming recommended.
- Strong content/system guardrails for JSON-only returns.

### 5.4 Common JSON “repair” pass (optional)

- If the first response is not valid JSON:
  - Try a single retry with a “Return ONLY valid compact JSON. No markdown, no prose.” clarification.
  - Exponential backoff optional; cap attempts to keep costs predictable.
- This is optional given strict provider features; include behind a profile flag (e.g., `output.repair_on_invalid_json: true`).

## 6) Mode-Aware Schema in FPF (Optional Enhancement)

To maximize strictness, FPF can accept `options.mode` and enforce the correct JSON shape:

- `mode="pairwise"` → enforce:
  ```json
  {
    "type": "object",
    "properties": {
      "winner_doc_id": { "type": "string" },
      "reason": { "type": "string" }
    },
    "required": ["winner_doc_id", "reason"],
    "additionalProperties": false
  }
  ```
- `mode="single"` → enforce:
  ```json
  {
    "type": "object",
    "properties": {
      "evaluations": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "criterion": { "type": "string" },
            "score": { "type": "integer", "minimum": 1, "maximum": 5 },
            "reason": { "type": "string" }
          },
          "required": ["criterion", "score", "reason"],
          "additionalProperties": false
        }
      }
    },
    "required": ["evaluations"],
    "additionalProperties": false
  }
  ```

Provider mapping:
- OpenAI tool calling: use schema as function parameters.
- Gemini: use `response_schema` (converted vocabulary).
- Others: keep strict system prompt; return JSON only.

If schema injection is considered out-of-scope for FPF right now, FPF can still enforce JSON-only (no schema) and rely on evaluator’s parser+validator. The upgrade to schema-driven calls remains future-friendly.

## 7) Logging & Telemetry

- Log per-call metadata:
  - profile, provider, model, mode
  - require_json flag, response_schema usage (if applicable)
  - latency, approximate tokens (if available), error/repair attempts
- Do not log raw document contents. Redact/clip long fields.
- Optional: write a succinct JSON envelope per call to `api_cost_multiplier/logs/fpf_run.log` (already present).

## 8) Error Handling

- Detect non-JSON responses (when `require_json=true` and no schema enforcement is available):
  - Retry once with a stricter message (if `repair_on_invalid_json=true`).
  - On failure, propagate a clean exception that the evaluator can surface.
- Respect provider timeouts; fail fast when needed with a clear error.

## 9) Backward Compatibility

- If `options.profile` is missing, runner can fall back to a default configured profile (or current legacy behavior).
- Keep the function signature stable; only extend `options`.
- `model_name` in the returned tuple can be `None` in legacy path; evaluator already guards for `None` and can store the profile name instead.

## 10) Evaluator Integration (for context)

- Evaluator will:
  - Read `profiles` list from its own config (opaque strings).
  - For each profile, call FPF with `{ profile, mode }`.
  - Parse/validate JSON output (still required; defense in depth).
  - Persist rows with `model` column = actual model used (from FPF), else profile name.
- No provider/model/temperature/grounding in evaluator. No JSON enforcement logic in evaluator.

## 11) Testing Plan

1) Unit (FPF adapters):
   - OpenAI adapter: returns JSON-only with `response_format=json` or tools; no extra prose.
   - Gemini adapter: returns JSON-only with `response_mime_type` and `response_schema`.
   - Optional: one retry path when the model returns invalid JSON.

2) Integration (profiles):
   - Two profiles: `judge_default` (OpenAI), `judge_gemini_strict` (Gemini).
   - Use simple canned prompts (short docs) to validate JSON-only outputs.
   - Ensure `(out_path, model_name)` contains correct model name.

3) Evaluator E2E (sanity):
   - Run `run-single` and `run-pairwise` with two profiles and a tiny doc set (2–3 docs).
   - Confirm DB rows contain `model` values corresponding to actual models.
   - Confirm CSV exports exist; parseable and consistent.

4) Regression:
   - Ensure legacy code paths still function if `profile` is omitted (for other consumers).

## 12) Migration & Rollout

- Introduce profiles and JSON mode behind config; do not break existing consumers.
- Update llm-doc-eval to use `profiles` and pass `{profile, mode}`:
  - Remove `judge_defaults` in llm-doc-eval config.yaml.
  - Replace `models` with a `profiles` list.
- Update README (llm-doc-eval and FPF) to document the new workflow:
  - “Edit FPF profiles → run evaluator”
- Phase roll-out:
  - Phase 1: Add profiles/JSON to FPF, keep evaluator as-is but allow profile mode.
  - Phase 2: Switch evaluator to profile-only, remove model-specific wiring.
  - Phase 3: Optional: add schema injection for stronger guarantees.

## 13) Security & Compliance

- No secrets in logs or DB. Make sure provider keys are environment based.
- Redact sensitive contents in logs. Keep output files limited to the model response.

## 14) Performance & Cost Considerations

- Use non-streaming for JSON enforcement; reduces token-level interleaving errors.
- Optional concurrency controls at FPF or evaluator layer (evaluator likely owns global concurrency).
- Retries should be minimal (1–2) to cap costs.

## 15) Acceptance Criteria

- Given a profile with `require_json: true`, FPF returns valid JSON-only responses consistently for OpenAI and Gemini adapters.
- Evaluator passing `{ profile, mode }` produces DB rows with `model` column set to the provider:model actually used.
- No provider/model/grounding/temp knowledge remains in the evaluator code.
- Documentation updated; simple commands run end-to-end.

---

## Appendix A — Minimal Runner Pseudocode

```python
# fpf_runner.py (conceptual)
async def run_filepromptforge_runs(instr_path, payload_path, num_runs=1, options=None):
    profile_name = (options or {}).get("profile")
    mode = (options or {}).get("mode")  # "single" | "pairwise"

    profile = load_profile(profile_name)  # from fpf_config.yaml
    adapter = make_provider_adapter(profile)  # provider+model selection

    # Build request with JSON enforcement
    request = build_request(
        instructions=read_file(instr_path),
        payload=read_file(payload_path),
        json_required=profile.output.require_json,
        schema=select_schema_for_mode(mode) if profile.output.use_response_schema else None,
        response_mime_type=profile.output.response_mime_type or "application/json",
        streaming=profile.runtime.streaming is False
    )

    out_files = []
    for _ in range(num_runs):
        raw = await adapter.call(request)  # returns text/string
        text = ensure_json_only(raw, schema=maybe_schema) if profile.output.require_json else raw
        out_path = write_temp_output(text)
        out_files.append((out_path, f"{profile.provider}:{profile.model}"))

    return out_files
```

`ensure_json_only`:
- If schema available, optionally validate (or trust provider enforcement, e.g., Gemini response_schema).
- If invalid, run a single repair retry (optional and profile-controlled).

`select_schema_for_mode`:
- Returns the single or pairwise JSON schema when `mode` is provided.

---

## Appendix B — Example Profiles

```yaml
profiles:
  judge_default:
    provider: openai
    model: gpt-4.1
    output:
      require_json: true
    runtime:
      streaming: false
      timeout_seconds: 120

  judge_gemini_strict:
    provider: google
    model: gemini-1.5-pro
    output:
      require_json: true
      use_response_schema: true
      response_mime_type: application/json
    runtime:
      streaming: false
      timeout_seconds: 120
```

---

## Appendix C — Evaluator Contract (for reference)

- Evaluator calls:
  - `options = { "profile": "<name>", "mode": "single" | "pairwise" }`
  - `await run_filepromptforge_runs(instr_path, payload_path, num_runs=1, options=options)`
- FPF returns `(out_path, model_name)`; evaluator persists `model_name` in DB and validates/parses the JSON with its own schema checks (defense in depth).
- Evaluator’s config:
  - `profiles: [judge_default, judge_gemini_strict, ...]`
  - No `judge_defaults` block; no provider/model/temperature/grounding in evaluator configs.
