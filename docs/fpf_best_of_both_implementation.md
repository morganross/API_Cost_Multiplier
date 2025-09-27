# FilePromptForge: Best-of-Both Implementation Plan (Exhaustive)

Audience: maintainers of API Cost Multiplier and FilePromptForge

Objective
- Merge the newer, cleaner structure in the Target codebase with the more advanced deep‑research features in the Source codebase, without regressing strict policies (provider‑side web_search usage and explicit reasoning) or logging.
- Target (structure): morganross/api_cost_multiplier/FilePromptForge/
- Source (features): C:\dev\betterday\API_Cost_Multiplier\FilePromptForge\

What was reviewed (complete inventory)
- Core orchestrators: file_handler.py (both), fpf_main.py (both), helpers.py (Target), fpf/fpf_main.py (both)
- Providers: openai, google (both), openaidp (Source only)
- Config and docs: fpf_config.yaml (both), openai_model_api_parameters.yaml (Target), readmes/audits (both)
- Pricing: pricing_loader.py, pricing_index.json, fetch_pricing.py, schema.json (both)
- Package initializers: providers/__init__.py (both)
- Structure extras: Source has ARCHIVE/ and audit reports (do not affect runtime)

High‑level differences: structure vs. features
- Structure advantage (Target)
  - helpers.py module centralizes load_config, load_env_file, compose_input
  - fpf_main.py is clean and identical across repos
  - providers/openai and providers/google are up‑to‑date and consistent
- Feature advantage (Source)
  - Deep‑research model routing to provider openaidp
  - Longer default HTTP timeout (600s)
  - Unique run_id added to default output filenames
  - Pricing canonicalization (treat openaidp as openai when looking up prices)
  - Additional docs (audit files) for web_search/reasoning validation

Preserve and port decisions
- Keep from Target:
  - Directory layout and helpers.py
  - Providers: openai, google (semantics match Source)
  - Strict validations: enforce provider web_search and explicit reasoning
  - Consolidated per‑run JSON logging under logs/
- Port from Source:
  - providers/openaidp adapter (deep‑research models)
  - file_handler: 600s timeout, deep‑research auto‑routing, run_id in outputs, pricing canonicalization
  - fpf_config.yaml: support openaidp endpoint and recommended DR preset values

Detailed implementation plan (step‑by‑step with exact patches)

1) Add deep‑research provider adapter
- Create a new file based on Source:
  - File: FilePromptForge/providers/openaidp/fpf_openaidp_main.py
  - Purpose:
    - Whitelist: {"o3-deep-research","o4-mini-deep-research"} (prefix tolerant)
    - Build payload:
      - tools: [{"type":"web_search_preview","search_context_size":"medium"}]
      - reasoning ensured: {"effort": cfg.reasoning.effort | "high"}
      - include/instructions passed through when present
    - extract_reasoning/parse_response:
      - handle top‑level reasoning, outputs[*].reasoning/content, and DR hints (research_steps, plan, queries)
  - No special headers; file_handler handles Authorization/x-goog-api-key.

2) Update provider package initializer
- File: FilePromptForge/providers/__init__.py
- Change:
  __all__ = ["openai", "google"]
- To:
  __all__ = ["openai", "google", "openaidp"]

Why: file_handler dynamically imports providers.{provider}.fpf_{provider}_main. Exposing openaidp in __all__ is not strictly required for import, but documents availability and keeps parity.

3) Extend file_handler.py (Target) with Source features
Start from Target’s FilePromptForge/file_handler.py and apply these minimal, surgical patches.

3A. Increase default HTTP timeout from 300 to 600
- Locate:
  def _http_post_json(url: str, payload: Dict, headers: Dict, timeout: int = 300) -> Dict:
- Replace with:
  def _http_post_json(url: str, payload: Dict, headers: Dict, timeout: int = 600) -> Dict:

Rationale: deep‑research/tool phases can be lengthy. Source already uses 600s.

3B. Auto‑route deep‑research models to openaidp
- In run(...), after cfg is loaded and before provider module load, set provider_name and reroute by model name:

Insert (or adapt the existing provider_name logic) to:
  provider_name = (provider or cfg.get("provider", "openai")).lower()
  try:
      _sel_model = (cfg.get("model") or "").lower()
      _norm_model = _sel_model.split(":", 1)[0]
      if _norm_model.startswith("o3-deep-research") or _norm_model.startswith("o4-mini-deep-research"):
          provider_name = "openaidp"
  except Exception:
      pass

- Then use provider_name for:
  - provider = _load_provider_module(provider_name)
  - provider_url = cfg["provider_urls"][provider_name]
  - Header decisions and env key names
  - Pricing canonicalization (below)

3C. Canonical .env key fallback behavior
- Keep Target’s policy: read only FilePromptForge/.env (repo env).
- Build api_key_name from provider_name, but also fallback to OPENAI_API_KEY when provider in ("openai","openaidp"):

  api_key_name = f"{provider_name.upper()}_API_KEY"
  api_key_value = _read_key_from_env_file(repo_env, api_key_name)
  if not api_key_value and provider_name in ("openai", "openaidp"):
      api_key_value = _read_key_from_env_file(repo_env, "OPENAI_API_KEY")
  if not api_key_value:
      raise RuntimeError(f"API key not found. Set {api_key_name} in filepromptforge/.env")
  os.environ[api_key_name] = api_key_value

3D. Unique run_id in default output path and placeholder support
- At the top of the run (or right before computing out_path), create:
  import uuid as _uuid
  run_id = _uuid.uuid4().hex[:8]

- When expanding out_path, support placeholders:
  if out_path:
      out_path = (out_path
                  .replace("<model_name>", model_name_sanitized)
                  .replace("<file_b_stem>", file_b_stem)
                  .replace("<run_id>", run_id))
  else:
      out_name = f"{file_b_stem}.{model_name_sanitized}.{run_id}.fpf.response.txt"
      out_path = str(b_path.parent / out_name)

Why: prevents overwrite of subsequent runs and improves traceability.

3E. Canonicalize provider for pricing lookup
- In cost computation section (where model_slug is computed), normalize provider:
  canonical_provider = "openai" if provider_name in ("openaidp",) else provider_name
  model_slug = model_cfg if "/" in str(model_cfg) else f"{canonical_provider}/{model_cfg}"

Why: Source recognized openaidp should use openai’s pricing table.

3F. Preserve strict validations and consolidated logging
- Do not relax:
  - If _response_used_websearch(raw_json) is False: error out
  - If extract_reasoning(...) returns empty: error out
- Keep consolidated per‑run log JSON (already in both codebases): logs/YYYYMMDDT...-<runid>.json

4) Update fpf_config.yaml (Target)
4A. Add openaidp endpoint
Ensure provider_urls contains:
  provider_urls:
    openai: https://api.openai.com/v1/responses
    openaidp: https://api.openai.com/v1/responses
    google: https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent

4B. Keep safe defaults for standard runs (OpenAI non‑DR)
  provider: openai
  model: gpt-5-mini
  reasoning:
    effort: low
  max_completion_tokens: 50000
  grounding:
    max_results: 1

4C. Document a deep‑research preset (switch when needed)
  provider: openaidp            # optional; auto‑route also works by model name
  model: o4-mini-deep-research
  reasoning:
    effort: medium
  web_search:
    search_context_size: medium
  include:
    - web_search_call.action.sources
  max_completion_tokens: 200000
  grounding:
    max_results: 9

4D. Encourage unique outputs with run_id placeholder
  test:
    out: test/output/<file_b_stem>.<model_name>.<run_id>.fpf.response.md

5) Providers comparison and notes
- openai (Target vs. Source): equivalent behavior
  - ALLOWED_MODELS: {"gpt-5","gpt-5-mini","gpt-5-nano","o4-mini","o3"}
  - tools: [{"type":"web_search_preview"}]
  - reasoning: enforced via model‑aware mapping (effort vs. max_tokens), strict whitelist
- google (Target vs. Source): equivalent behavior
  - tools: [{"google_search": {}}]
  - reasoning: extracted from groundingMetadata.webSearchQueries
- openaidp (Source only; to be added)
  - ALLOWED_MODELS: {"o3-deep-research","o4-mini-deep-research"}
  - tools: [{"type":"web_search_preview","search_context_size":"medium"}]
  - reasoning: {"effort": cfg.reasoning.effort | "high"}

6) Pricing and usage accounting
- pricing_loader.py, pricing_index.json are consistent across repos.
- Only change: canonical_provider mapping to ensure deep‑research prices are read from openai entries.

7) Security and keys (explicit)
- Single canonical source for secrets: FilePromptForge/.env (Target policy)
- Required keys:
  - OPENAI_API_KEY=... (used for openai and openaidp)
  - GOOGLE key is handled via x-goog-api-key header when provider_name == "google"
- No reliance on process env outside repo .env by design (ensures predictability)

8) Testing matrix (Windows / repository‑relative)
Note: Replace paths appropriately if running from a different working directory.

8A. Standard OpenAI run (non‑deep‑research)
- Precondition: FilePromptForge/.env contains OPENAI_API_KEY
- Recommended config (fpf_config.yaml):
  provider: openai
  model: gpt-5-mini
- Run:
  python morganross/api_cost_multiplier/FilePromptForge/fpf_main.py --file-a morganross/api_cost_multiplier/FilePromptForge/test/input/sample_utf8.txt --file-b morganross/api_cost_multiplier/FilePromptForge/test/prompts/standard_prompt.txt --config morganross/api_cost_multiplier/FilePromptForge/fpf_config.yaml -v
- Expect:
  - tools include web_search_preview; reasoning attached
  - Output file: test/output/<file_b_stem>.<model_name>.<run_id>.fpf.response.md (if configured), otherwise default with run_id suffix
  - logs/ gets a new consolidated JSON with request/response/usage/cost

8B. Deep‑research run (openaidp, auto‑routed)
- Switch only the model in fpf_config.yaml:
  model: o4-mini-deep-research
  # provider can remain openai; auto‑route logic forces provider_name = "openaidp"
- Run:
  python morganross/api_cost_multiplier/FilePromptForge/fpf_main.py --file-a morganross/api_cost_multiplier/FilePromptForge/test/input/sample_utf8.txt --file-b morganross/api_cost_multiplier/FilePromptForge/test/prompts/standard_prompt.txt --config morganross/api_cost_multiplier/FilePromptForge/fpf_config.yaml -v
- Expect:
  - provider_name resolved to openaidp
  - tools include {"type":"web_search_preview","search_context_size":"medium"}
  - reasoning present ({"effort":...})
  - pricing based on openai records due to canonicalization
  - strict validations pass; else see logs/.json

8C. Negative validations (to confirm policies)
- Artificially remove web_search evidence in a stubbed response (or force tool_choice="none") to verify:
  - Error: "Provider did not perform web_search"
- Remove reasoning from a stubbed response:
  - Error: "Provider did not return reasoning"

9) Risk and compatibility notes
- API drift: keep tools block minimal (web_search_preview/google_search). Avoid speculative fields inside tools to prevent 400 errors.
- Whitelists: openai adapter purposely restricts to a known set; openaidp handles only DR SKUs. This avoids accidental parameter sends to unsupported models.
- Cost control: DR configs are expensive; keep Target defaults conservative, with explicit switch to DR presets as needed.

10) Implementation checklist (actionable)
- [ ] Add providers/openaidp/fpf_openaidp_main.py (copy from Source)
- [ ] Update providers/__init__.py to include "openaidp"
- [ ] In file_handler.py:
  - [ ] _http_post_json: default timeout 600
  - [ ] provider_name resolution with DR auto‑routing
  - [ ] .env key fallback for ("openai","openaidp") -> OPENAI_API_KEY
  - [ ] run_id for default outputs + <run_id> placeholder support
  - [ ] canonical_provider for pricing when provider_name == "openaidp"
- [ ] In fpf_config.yaml:
  - [ ] Add provider_urls.openaidp
  - [ ] Document DR preset block (model, reasoning, tokens, grounding)
  - [ ] Optionally adopt <run_id> in test.out

Appendix A — Model and provider summary (post‑merge)
- Standard OpenAI (openai):
  - Allowed models: gpt‑5 family, o3, o4‑mini
  - tools: web_search_preview
  - reasoning: {"effort": ...} where supported
- Deep‑research OpenAI (openaidp):
  - Allowed models: o3-deep-research, o4-mini-deep-research
  - tools: web_search_preview + search_context_size=medium
  - reasoning: {"effort": cfg.reasoning.effort|high}
- Google Gemini (google):
  - Allowed models: 1.5/2.0/2.5 Pro/Flash variants
  - tools: google_search
  - reasoning: derived from groundingMetadata.webSearchQueries

Appendix B — Files verified (complete)
- Target:
  - file_handler.py, fpf_main.py, helpers.py, fpf/fpf_main.py
  - providers/openai/fpf_openai_main.py, providers/google/fpf_google_main.py, providers/__init__.py
  - fpf_config.yaml, openai_model_api_parameters.yaml
  - pricing/__init__.py, fetch_pricing.py, pricing_loader.py, pricing_index.json, schema.json
- Source:
  - file_handler.py, fpf_main.py, fpf/fpf_main.py
  - providers/openai/fpf_openai_main.py, providers/google/fpf_google_main.py
  - providers/openaidp/fpf_openaidp_main.py
  - fpf_config.yaml
  - ARCHIVE/, audit docs (websearch_reasoning_audit.md, websearch_report.md)

This plan reflects a full reading of both codebases and prescribes minimal, explicit changes to converge on a single, feature‑complete, maintainable FPF implementation, preserving strict validation and logging guarantees.
