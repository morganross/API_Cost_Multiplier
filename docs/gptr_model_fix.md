# GPTR/DR provider:model issue — analysis, fixes, and verification

Date: 2025-08-31

Overview
- Symptom: SMART_LLM / STRATEGIC_LLM in `gpt-researcher/gpt_researcher/config/variables/default.py` became corrupted with repeated provider prefixes (e.g., `google:google:gemini-2.5-flash`). This broke GPTR and DR report types (both read the same file).
- Root cause: inconsistent normalization of provider/model across three code boundaries:
  1. load_values() — sometimes set the model combobox to the combined "provider:model" string.
  2. gather_values() — read the model combobox verbatim (no sanitization).
  3. write_configs() — always composed provider + ":" + model, so if model already contained a provider prefix, the result doubled (and on repeated saves, tripled, etc.).

What I changed (deterministic fixes applied)
1. Enforce canonical representation
   - Comboboxes:
     - `comboGPTRProvider` must hold the provider string only.
     - `comboGPTRModel` must hold the model string only (no ":" allowed).
   - Config file:
     - `default.py` entries use exactly one combined string "provider:model".

2. load_values() (gptr_ma_ui.py)
   - When reading SMART_LLM or STRATEGIC_LLM:
     - If value contains ":", split and set provider → `comboGPTRProvider` and model → `comboGPTRModel` (model receives only the right-hand side).
     - If value has no ":", set `comboGPTRModel` = value and leave provider unchanged.
   - This prevents placing a combined string into the model combobox.

3. gather_values() (gptr_ma_ui.py)
   - Sanitize the model value before saving:
     - If `comboGPTRModel` contains ":", keep only the right-hand side (model = raw.split(":",1)[1]).
   - Always read provider separately from `comboGPTRProvider`.

4. write_configs() (gptr_ma_ui.py)
   - Compose final = provider + ":" + sanitized_model and write SMART_LLM/STRATEGIC_LLM once.
   - Added debug logging showing provider and sanitized model used for the write.
   - Added a guard: if default.py already contains the same combined value, skip rewriting (avoids unnecessary edits).

5. Clean up corrupted defaults
   - Fixed existing corrupted entries in `default.py` (normalized SMART_LLM and STRATEGIC_LLM to a single "provider:model" instance).

Verification performed
- Launched the GUI and observed initialization logs showing:
  - FPF provider/model loaded correctly.
  - GPTR SMART_LLM parsed into provider and model separately (model contained no colon).
  - MA model loaded from task.json (unchanged).
- Clicked "Write to Configs" and observed:
  - Debug log showing sanitized model and provider.
  - `default.py` updated with exactly one `provider:model` for SMART_LLM / STRATEGIC_LLM.
  - No double-prefixing on subsequent loads/saves.

Why the doubling happened (concise)
- The doubling is a feedback loop caused by inconsistent state: saving assumed model had no prefix, but model sometimes did; on save the provider was prefixed again. Repeating this produces N-fold prefixes.

Other run-time issues observed (from a generate run you ran)
- Embedding token-limit error: an embeddings request attempted too many tokens (OpenAI returned 400 max_tokens_per_request). Fix: chunk documents & cap tokens per embeddings request.
- FPF provider error: FPF used `max_tokens` param with a model that expects `max_completion_tokens`. Fix: map parameter names per provider/model in the FPF client.
- Tavily search errors: some search calls produced 400. Fix: add validation/retries and reduce query size or escape problematic characters.

Recommended next steps (priority)
1. Keep the GPTR normalization fix as-is (already applied).
2. Fix FPF param mapping (replace `max_tokens` with `max_completion_tokens` for models that require it).
3. Add robust chunking for embeddings (configure conservative chunk sizes and token counting).
4. Add graceful retry/backoff and validation for Tavily/search failures.
5. Add a small unit/integration test that:
   - Loads default.py with a combined SMART_LLM,
   - Starts GUI, confirms comboboxes are split,
   - Writes configs, confirms default.py has a single provider:model,
   - Repeats save to ensure idempotency.

Files changed (summary)
- API_Cost_Multiplier/GUI/gptr_ma_ui.py
  - load_values(): split combined strings and set comboboxes.
  - gather_values(): sanitize model values before persisting into vals.
  - write_configs(): compose provider:model from sanitized values, log, and guard writes.
- API_Cost_Multiplier/gpt-researcher/gpt_researcher/config/variables/default.py
  - Normalized SMART_LLM / STRATEGIC_LLM entries (cleaned corrupted values).

How to reproduce locally
- Launch GUI:
  python -m api_cost_multiplier.GUI.gui
- Observe console logs:
  - "GPTR SMART_LLM from file: 'provider:model', GPTR provider combobox: provider, GPTR model combobox: model"
  - On save: "[OK] Wrote GPTR provider/model = 'provider:model' -> .../default.py"
- Verify default.py SMART_LLM exactly equals the composed string (no repeated prefixes).

If you want, next I will:
- Implement the embedding chunking and FPF param fixes and re-run a full generate to confirm no run-time errors (recommended). This requires me to modify code and run it (Act mode). Say "go ahead" to proceed.
